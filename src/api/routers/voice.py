from __future__ import annotations

import base64
import json
import os
import uuid

import structlog
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse

from api.services.actions import Actions
from api.services.asr import asr_service
from api.services.auth import verify_api_key
from api.services.validators import validators
from api.services.call_session import (
    VoiceSession,
    get_or_create_session,
    remove_session,
    store_session,
)
from api.services.database import (
    create_call_session,
)
from api.services.intent_classifier import classifier
from api.services.orchestrator import Orchestrator
from api.services.tts import tts_service

logger = structlog.get_logger()

router = APIRouter(prefix="/voice", tags=["voice"])

# =============================================================================
# Fonster Incoming Call Handler
# =============================================================================
# Fonster sends call events to this endpoint instead of Twilio webhooks.
# The event format differs from Twilio: use Fonster's session-based model.


@router.api_route("/incoming", methods=["GET", "POST"], dependencies=[Depends(verify_api_key)])
async def handle_incoming_call(request: Request):
    """
    Handle incoming calls from Fonster Voice Server.
    Fonster POSTs JSON with session details instead of form-encoded Twilio data.
    """
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            data = await request.json()
        else:
            data = await request.form()
            data = dict(data)
    except Exception:
        data = {}

    session_ref = data.get("sessionRef") or data.get("session_ref") or str(uuid.uuid4())
    ingress_number = data.get("ingressNumber") or data.get("from", "")
    # tenant_id comes from the webhook payload or JWT auth
    tenant_id = data.get("tenantId") or data.get("tenant_id")
    profile_id = data.get("profileId") or data.get("profile_id", "PROF-001")

    if tenant_id and not validators.validate_uuid(tenant_id):
        raise HTTPException(status_code=400, detail=f"Invalid tenant_id format: expected UUID, got '{tenant_id}'")
    if profile_id and not (validators.validate_uuid(profile_id) or (len(profile_id) <= 64 and profile_id.startswith("PROF-"))):
        raise HTTPException(status_code=400, detail=f"Invalid profile_id format: expected UUID or PROF- prefix, got '{profile_id}'")

    # Create call session in database
    call_sid = session_ref
    try:
        await create_call_session(
            tenant_id=tenant_id,
            agent_id=None,  # Will be assigned by routing logic
            caller_number=ingress_number,
            called_number=data.get("to", ingress_number),
            call_direction="inbound",
            sip_call_id=call_sid,
        )
    except Exception as e:
        logger.error(f"Failed to create call session: {e}")

    response = {
        "verb": "connect",
        "endpoint": "tcp://aetherdesk-voice:50061",
        "metadata": {
            "profile_id": profile_id,
            "session_ref": session_ref,
            "call_sid": call_sid,
            "tenant_id": tenant_id,
        },
    }

    return JSONResponse(content=response)


@router.post("/intent", dependencies=[Depends(verify_api_key)])
async def classify_transcript(request: dict):
    """Classify caller intent from transcript text."""
    text = request.get("text", "")
    if not text:
        return {"error": "No text provided"}

    result = await classifier.classify_with_fallback(text)
    return {
        "intent": result.intent,
        "entities": result.entities,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
    }


async def _handle_media_start(
    websocket: WebSocket, data: dict
) -> tuple[str | None, str | None, str | None, str | None, VoiceSession | None, Orchestrator | None]:
    start = data.get("start", {})
    stream_sid = start.get("streamSid")
    call_sid = start.get("callSid") or str(uuid.uuid4())
    tenant_id: str = data.get("tenantId") or "unknown"

    profile_id = websocket.query_params.get("profile_id", "PROF-001")

    logger.info(
        "media_stream_start",
        call_sid=call_sid,
        stream_sid=stream_sid,
        profile_id=profile_id,
        tenant_id=tenant_id,
    )

    from api.routers.realtime import manager
    manager.register_voice_ws(call_sid, websocket, stream_sid)

    session_id = f"call_{call_sid}"
    session = get_or_create_session(
        websocket.app, session_id, call_sid,
        profile_id=profile_id,
        tenant_id=tenant_id,
    )
    store_session(websocket.app, session_id, session)

    actions = Actions(websocket.app.state.redis)
    orchestrator = Orchestrator(actions)

    greeting = "Hello. How can I help you today?"
    async for chunk in session.speak_stream(greeting):
        await websocket.send_json({
            "event": "media",
            "media": {
                "payload": base64.b64encode(chunk).decode("utf-8"),
            },
        })

    return stream_sid, call_sid, tenant_id, session_id, session, orchestrator


async def _handle_media_chunk(
    websocket: WebSocket,
    data: dict,
    session: VoiceSession | None,
    session_id: str | None,
    call_sid: str | None,
    orchestrator: Orchestrator | None,
    tenant_id: str,
) -> None:
    if session_id is None:
        return

    media = data.get("media", {})
    payload = media.get("payload")

    if payload:
        session = get_or_create_session(
            websocket.app, session_id,
            call_sid or "unknown",
            profile_id=session.profile_id if session else "PROF-001",
            tenant_id=session.tenant_id if session else tenant_id,
        )

        audio_chunk = base64.b64decode(payload)
        text = await session.process_audio(audio_chunk)

        if text:
            history = session.transcript[:-1]
            response = await orchestrator.step(
                session.agent_state, history, text,
                tenant_id=session.tenant_id,
                profile_id=session.profile_id,
            )

            if response.text:
                async for chunk in session.speak_stream(
                    response.text,
                    sentiment=response.sentiment,
                    latency_ms=response.latency_ms,
                ):
                    await websocket.send_json({
                        "event": "media",
                        "media": {
                            "payload": base64.b64encode(chunk).decode("utf-8"),
                        },
                    })

            if response.needs_agent:
                await websocket.send_json({
                    "event": "mark",
                    "mark": {"name": "handoff"},
                })


async def _handle_media_stop(
    websocket: WebSocket,
    data: dict,
    session_id: str | None,
    call_sid: str | None,
) -> None:
    if session_id:
        remove_session(websocket.app, session_id)
    if call_sid:
        from api.routers.realtime import cleanup_call_transcripts, manager
        manager.unregister_voice_ws(call_sid)
        cleanup_call_transcripts(call_sid)


@router.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time media stream processing.
    Handles audio chunks from Fonster/FreeSWITCH for AI processing.
    """
    from api.services.auth import verify_websocket_token
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    token_data = await verify_websocket_token(token)
    if not token_data:
        await websocket.close(code=4003, reason="Invalid or expired token")
        return
    await websocket.accept()

    session_id: str | None = None
    call_sid: str | None = None
    tenant_id: str = "unknown"
    session: VoiceSession | None = None
    orchestrator: Orchestrator | None = None

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "connected":
                logger.info("media_stream_connected", data=data)

            elif event == "start":
                _, call_sid, tenant_id, session_id, session, orchestrator = (
                    await _handle_media_start(websocket, data)
                )

            elif event == "media":
                await _handle_media_chunk(
                    websocket, data, session, session_id,
                    call_sid, orchestrator, tenant_id,
                )

            elif event == "stop":
                logger.info("media_stream_stopped", data=data)
                await _handle_media_stop(websocket, data, session_id, call_sid)

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", session_id=session_id)
        await _handle_media_stop(websocket, {}, session_id, call_sid)

    except Exception as e:
        logger.error("media_stream_error", session_id=session_id, error=str(e))
        await _handle_media_stop(websocket, {}, session_id, call_sid)


# =============================================================================
# Transcription & Synthesis Endpoints
# =============================================================================

@router.post("/transcribe", dependencies=[Depends(verify_api_key)])
async def transcribe_audio(request: Request):
    """Transcribe audio using configured STT engine (Deepgram default)."""
    audio = await request.body()
    if not audio:
        return {"error": "No audio provided"}
    if len(audio) > 25 * 1024 * 1024:
        return {"error": "Audio payload too large (max 25MB)"}

    text = await asr_service.transcribe(audio)
    return {"text": text}


@router.post("/synthesize", dependencies=[Depends(verify_api_key)])
async def synthesize_text(request: dict):
    """Convert text to speech using configured TTS engine (Chatterbox default)."""
    text = request.get("text", "")
    if not text:
        return {"error": "No text provided"}

    audio = await tts_service.synthesize(text)
    return {
        "audio": base64.b64encode(audio).decode("utf-8"),
    }


@router.post("/outbound", dependencies=[Depends(verify_api_key)])
async def trigger_outbound_call(request: dict):
    """
    Trigger an outbound call via Fonoster or Twilio.
    Uses the shared voice client from main.py.
    """
    to_phone = request.get("to_phone")
    agent_profile_id = request.get("profile_id", "PROF-META-SALES")

    if not to_phone:
        raise HTTPException(status_code=400, detail="Missing to_phone")

    from api.main import fonster_client as voice_client
    if not voice_client:
        raise HTTPException(status_code=503, detail="Voice client not available")

    try:
        caller_id = os.getenv("TWILIO_FROM_NUMBER") or os.getenv("SIP_TRUNK_FROM", "")
        payload = {
            "name": f"Outbound-{to_phone}",
            "type": "EXTERNAL",
            "endpoint": "tcp://aetherdesk-voice:50061",
            "variables": {
                "outbound_caller_id": caller_id,
                "outbound_number": to_phone,
                "profile_id": agent_profile_id,
            },
        }

        result = await voice_client.create_application(payload)

        logger.info(
            "outbound_call_triggered",
            call_ref=result.get("ref"),
            to=to_phone[:6] + "****",
            profile=agent_profile_id,
        )
        return {"ok": True, "call_ref": result.get("ref"), "status": "queued"}

    except Exception as e:
        logger.error("outbound_call_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
