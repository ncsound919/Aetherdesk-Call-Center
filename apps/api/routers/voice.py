from __future__ import annotations

import base64
import json
import os
import uuid

import structlog
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse

from apps.api.services.actions import Actions
from apps.api.services.asr import asr_service
from apps.api.services.auth import verify_api_key
from apps.api.services.call_session import (
    VoiceSession,
    get_or_create_session,
    remove_session,
    store_session,
)
from apps.api.services.database import (
    create_call_session,
    get_call_session,
    update_call_status,
)
from apps.api.services.intent_classifier import classifier
from apps.api.services.orchestrator import Orchestrator
from apps.api.services.tts import tts_service

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
    app_ref = data.get("appRef") or data.get("app_ref", "")
    # tenant_id comes from the webhook payload or JWT auth
    tenant_id = data.get("tenantId") or data.get("tenant_id")
    profile_id = data.get("profileId") or data.get("profile_id", "PROF-001")

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


@router.api_route("/signalwire-webhook", methods=["GET", "POST"])
async def handle_signalwire_webhook(request: Request):
    """
    Handle incoming webhooks from SignalWire and return LaML to connect
    the call to our WebSocket media stream.
    """
    data = dict(await request.form())
    call_sid = data.get("CallSid", str(uuid.uuid4()))
    from_num = data.get("From", "unknown")
    to_num = data.get("To", "unknown")
    
    # We pass the profile ID from the URL params if we appended it when triggering
    profile_id = request.query_params.get("profile_id", "PROF-META-SALES")
    
    # Store session to db
    try:
        await create_call_session(
            tenant_id="TENANT-001",
            agent_id=None,
            caller_number=from_num,
            called_number=to_num,
            call_direction="outbound",
            sip_call_id=call_sid,
        )
    except Exception as e:
        logger.error(f"Failed to create call session: {e}")

    # Use the localtunnel host for WebSocket (replace https with wss)
    host = request.headers.get("host", "localhost:8000")
    # If the user is hitting this via localtunnel, host will be the loca.lt domain
    wss_url = f"wss://{host}/api/v1/voice/media-stream?profile_id={profile_id}"
    
    laml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{wss_url}" />
    </Connect>
</Response>"""
    from fastapi.responses import Response
    return Response(content=laml, media_type="application/xml")


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


@router.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time media stream processing.
    Handles audio chunks from Fonster/FreeSWITCH (linear PCM) or SignalWire (PCMU).
    """
    await websocket.accept()

    session_id = None
    call_sid = None
    stream_sid = None
    tenant_id = "unknown"
    session: VoiceSession | None = None
    is_pcmu = False  # Track if stream uses PCMU (SignalWire) vs linear PCM
    import audioop

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "connected":
                logger.info("media_stream_connected", data=data)

            elif event == "start":
                start = data.get("start", {})
                stream_sid = start.get("streamSid")
                call_sid = start.get("callSid") or str(uuid.uuid4())
                tenant_id = data.get("tenantId") or "unknown"
                
                # SignalWire always passes streamSid in start event
                if stream_sid:
                    is_pcmu = True
                    logger.info("media_stream_format_detected", format="PCMU (SignalWire)")

                # Get profile_id from query string
                profile_id = websocket.query_params.get("profile_id", "PROF-001")

                logger.info(
                    "media_stream_start",
                    call_sid=call_sid,
                    stream_sid=stream_sid,
                    profile_id=profile_id,
                    tenant_id=tenant_id,
                    is_pcmu=is_pcmu,
                )

                # Register voice stream for takeover
                from apps.api.routers.realtime import manager
                manager.register_voice_ws(call_sid, websocket, stream_sid)

                session_id = f"call_{call_sid}"
                session = get_or_create_session(
                    websocket.app, session_id, call_sid,
                    profile_id=profile_id,
                    tenant_id=tenant_id,
                )
                store_session(websocket.app, session_id, session)

                # Cache the orchestrator for this session
                actions = Actions(websocket.app.state.redis)
                orchestrator = Orchestrator(actions)

                greeting = "Hello. How can I help you today?"
                async for chunk in session.speak_stream(greeting):
                    # Outbound Transcoding: Convert raw PCM (from TTS) to PCMU for SignalWire
                    out_payload = chunk
                    if is_pcmu:
                        try:
                            # Downsample from 24kHz/16kHz to 8kHz, then encode to PCMU
                            # Assume TTS output is 24kHz 16-bit mono (realtime-tts default)
                            pcm_8khz, _ = audioop.ratecv(chunk, 2, 1, 24000, 8000, None)
                            out_payload = audioop.lin2ulaw(pcm_8khz, 2)
                        except Exception as e:
                            logger.error("tts_to_pcmu_failed", error=str(e))
                    
                    await websocket.send_json({
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": base64.b64encode(out_payload).decode("utf-8"),
                        },
                    })

            elif event == "media":
                if session_id is None:
                    continue

                media = data.get("media", {})
                payload = media.get("payload")

                if payload:
                    # Re-fetch session to prevent profile loss on Redis expiry
                    session = get_or_create_session(
                        websocket.app, session_id,
                        call_sid or "unknown",
                        profile_id=session.profile_id if session else "PROF-001",
                        tenant_id=session.tenant_id if session else tenant_id,
                    )

                    from apps.api.services.queue import QueueManager
                    qm = QueueManager(websocket.app.state.redis)
                    if qm.session_get(f"takeover_{call_sid}") == "true":
                        # Human supervisor is in control, bypass LLM orchestrator and TTS synthesis
                        continue

                    audio_chunk = base64.b64decode(payload)
                    
                    # Inbound Transcoding: Convert 8kHz PCMU to 16kHz linear PCM for ASR
                    if is_pcmu:
                        try:
                            pcm_8khz = audioop.ulaw2lin(audio_chunk, 2)
                            audio_chunk, _ = audioop.ratecv(pcm_8khz, 2, 1, 8000, 16000, None)
                        except Exception as e:
                            logger.error("pcmu_to_pcm_failed", error=str(e))

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
                                out_payload = chunk
                                if is_pcmu:
                                    try:
                                        pcm_8khz, _ = audioop.ratecv(chunk, 2, 1, 24000, 8000, None)
                                        out_payload = audioop.lin2ulaw(pcm_8khz, 2)
                                    except Exception as e:
                                        logger.error("tts_to_pcmu_failed", error=str(e))
                                        
                                await websocket.send_json({
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": base64.b64encode(out_payload).decode("utf-8"),
                                    },
                                })

                        if response.needs_agent:
                            await websocket.send_json({
                                "event": "mark",
                                "mark": {"name": "handoff"},
                            })

            elif event == "stop":
                logger.info("media_stream_stopped", data=data)
                if session_id:
                    remove_session(websocket.app, session_id)
                if call_sid:
                    from apps.api.routers.realtime import (
                        cleanup_call_transcripts,
                        manager,
                    )
                    manager.unregister_voice_ws(call_sid)
                    cleanup_call_transcripts(call_sid)

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", session_id=session_id)
        if session_id:
            remove_session(websocket.app, session_id)
        if call_sid:
            from apps.api.routers.realtime import cleanup_call_transcripts, manager
            manager.unregister_voice_ws(call_sid)
            cleanup_call_transcripts(call_sid)

    except Exception as e:
        logger.error("media_stream_error", session_id=session_id, error=str(e))
        if session_id:
            remove_session(websocket.app, session_id)
        if call_sid:
            from apps.api.routers.realtime import cleanup_call_transcripts, manager
            manager.unregister_voice_ws(call_sid)
            cleanup_call_transcripts(call_sid)


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
    Trigger an outbound call using SignalWire.
    """
    to_phone = request.get("to_phone")
    agent_profile_id = request.get("profile_id", "PROF-META-SALES")

    if not to_phone:
        raise HTTPException(status_code=400, detail="Missing to_phone")

    from apps.api.services.signalwire_client import signalwire_client
    
    # We construct the webhook URL so SignalWire calls us back for LaML instructions
    # We assume NGROK_URL or LOCALTUNNEL_URL is set in the environment or passed in request headers.
    # In dev, we can grab it from os.getenv
    public_url = os.getenv("PUBLIC_URL", "https://wise-shirts-give.loca.lt")
    webhook_url = f"{public_url}/api/v1/voice/signalwire-webhook?profile_id={agent_profile_id}"

    try:
        result = signalwire_client.make_call(to_phone=to_phone, webhook_url=webhook_url)

        logger.info(
            "outbound_call_triggered",
            call_ref=result.get("ref"),
            to=to_phone[:6] + "****",
            profile=agent_profile_id,
        )
        return {"ok": True, "call_ref": result.get("ref"), "status": result.get("status")}

    except Exception as e:
        logger.error("outbound_call_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e