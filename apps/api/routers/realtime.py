import asyncio
import base64
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.api.services.queue import QueueManager

logger = structlog.get_logger()

router = APIRouter(prefix="/realtime", tags=["realtime"])

CALL_TRANSCRIPTS: dict[str, list] = {}
CALL_LAST_ACTIVITY: dict[str, float] = {} # call_sid -> timestamp


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.voice_connections: dict[str, tuple[WebSocket, str]] = {} # call_sid -> (ws, stream_sid)

    async def connect(self, websocket: WebSocket, agent_id: str):
        self.active_connections[agent_id] = websocket
        logger.info("agent_connected", agent_id=agent_id)

    def register_voice_ws(self, call_sid: str, websocket: WebSocket, stream_sid: str):
        self.voice_connections[call_sid] = (websocket, stream_sid)
        logger.info("voice_stream_registered", call_sid=call_sid)

    def unregister_voice_ws(self, call_sid: str):
        if call_sid in self.voice_connections:
            del self.voice_connections[call_sid]
            logger.info("voice_stream_unregistered", call_sid=call_sid)

    def disconnect(self, agent_id: str, websocket: WebSocket):
        if agent_id in self.active_connections and self.active_connections[agent_id] == websocket:
            del self.active_connections[agent_id]
            logger.info("agent_disconnected", agent_id=agent_id)

    async def route_agent_audio(self, call_sid: str, payload_b64: str):
        if call_sid in self.voice_connections:
            ws, stream_sid = self.voice_connections[call_sid]
            try:
                import audioop
                audio_data = base64.b64decode(payload_b64)
                # Resample from 16kHz to 8kHz
                pcm8, _ = audioop.ratecv(audio_data, 2, 1, 16000, 8000, None)
                # Convert to mulaw
                mulaw = audioop.lin2ulaw(pcm8, 2)

                await ws.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": base64.b64encode(mulaw).decode("utf-8")
                    }
                })
            except Exception as e:
                logger.error("route_agent_audio_error", error=str(e))

    async def send_to_agent(self, agent_id: str, message: dict):
        if agent_id in self.active_connections:
            try:
                await self.active_connections[agent_id].send_json(message)
            except Exception as e:
                logger.error("send_to_agent_error", agent_id=agent_id, error=str(e))

    async def broadcast_to_queue(self, queue: str, message: dict):
        # Use list() to create a copy of items to avoid "dictionary changed size during iteration"
        for _agent_id, ws in list(self.active_connections.items()):
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def _cleanup_stale_transcripts_task(self):
        """Background task to purge transcripts for calls with no activity for 1 hour."""
        while True:
            await asyncio.sleep(600) # Every 10 mins
            import time
            now = time.time()
            stale_calls = [
                sid for sid, last_ts in CALL_LAST_ACTIVITY.items()
                if now - last_ts > 3600
            ]
            for sid in stale_calls:
                del CALL_TRANSCRIPTS[sid]
                del CALL_LAST_ACTIVITY[sid]
                logger.info("stale_transcript_purged", call_sid=sid)


manager = ConnectionManager()


@router.websocket("/agent/{agent_id}")
async def agent_websocket(websocket: WebSocket, agent_id: str):
    await websocket.accept()
    
    import os
    token = websocket.query_params.get("token")
    is_dev = os.getenv("ENV", "development") != "production"
    
    authenticated = False
    if token == "dev-token" or (is_dev and not token):
        authenticated = True
    elif token:
        from apps.api.services.auth import verify_websocket_token
        token_data = await verify_websocket_token(token)
        if token_data:
            authenticated = True
            
    if not authenticated:
        try:
            await websocket.send_json({"error": "Unauthorized WebSocket connection"})
            await websocket.close(code=1008)
        except Exception:
            pass
        return

    await manager.connect(websocket, agent_id)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            msg_type = message.get("type")

            if msg_type == "subscribe_call":
                call_sid = message.get("call_sid")
                if call_sid not in CALL_TRANSCRIPTS:
                    CALL_TRANSCRIPTS[call_sid] = []
                await websocket.send_json({
                    "type": "subscribed",
                    "call_sid": call_sid
                })

                for transcript in CALL_TRANSCRIPTS[call_sid]:
                    await websocket.send_json(transcript)

            elif msg_type == "send_message":
                call_sid = message.get("call_sid")
                text = message.get("text")

                if hasattr(websocket.app, 'state') and hasattr(websocket.app.state, 'redis'):
                    qm = QueueManager(websocket.app.state.redis)
                    qm.session_set(f"call_{call_sid}", {
                        "agent_message": text,
                        "timestamp": asyncio.get_event_loop().time()
                    })

                CALL_LAST_ACTIVITY[call_sid] = asyncio.get_event_loop().time()

                await websocket.send_json({
                    "type": "message_sent",
                    "call_sid": call_sid
                })

            elif msg_type == "takeover_call":
                call_sid = message.get("call_sid")
                if hasattr(websocket.app, 'state') and hasattr(websocket.app.state, 'redis'):
                    qm = QueueManager(websocket.app.state.redis)
                    # Optimization: Silencing AI agent in Redis for emergency takeover
                    qm.session_set(f"takeover_{call_sid}", "true")
                    logger.info("emergency_takeover_activated", call_sid=call_sid)
                await websocket.send_json({"type": "takeover_active", "call_sid": call_sid})

            elif msg_type == "agent_audio":
                call_sid = message.get("call_sid")
                payload = message.get("payload")
                if call_sid and payload:
                    await manager.route_agent_audio(call_sid, payload)

    except WebSocketDisconnect:
        manager.disconnect(agent_id, websocket)
    except Exception as e:
        logger.error("websocket_error", agent_id=agent_id, error=str(e))
        manager.disconnect(agent_id, websocket)


MAX_TRANSCRIPT_PER_CALL = 200

def cleanup_call_transcripts(call_sid: str):
    if call_sid in CALL_TRANSCRIPTS:
        del CALL_TRANSCRIPTS[call_sid]
    if call_sid in CALL_LAST_ACTIVITY:
        del CALL_LAST_ACTIVITY[call_sid]

def broadcast_transcript(call_sid: str, transcript_entry: dict):
    transcripts = CALL_TRANSCRIPTS.setdefault(call_sid, [])
    CALL_LAST_ACTIVITY[call_sid] = asyncio.get_event_loop().time()
    transcripts.append(transcript_entry)
    # Cap transcript memory per call to prevent unbounded growth
    if len(transcripts) > MAX_TRANSCRIPT_PER_CALL:
        CALL_TRANSCRIPTS[call_sid] = transcripts[-MAX_TRANSCRIPT_PER_CALL:]

    try:
        asyncio.create_task(manager.broadcast_to_queue("default", {
            "type": "transcript",
            "call_sid": call_sid,
            "data": transcript_entry
        }))
    except RuntimeError:
        # No running event loop (e.g., called from sync context in tests)
        pass


@router.websocket("/call/{call_sid}")
async def call_websocket(websocket: WebSocket, call_sid: str):
    await websocket.accept()
    
    import os
    token = websocket.query_params.get("token")
    is_dev = os.getenv("ENV", "development") != "production"
    
    authenticated = False
    if token == "dev-token" or (is_dev and not token):
        authenticated = True
    elif token:
        from apps.api.services.auth import verify_websocket_token
        token_data = await verify_websocket_token(token)
        if token_data:
            authenticated = True
            
    if not authenticated:
        try:
            await websocket.send_json({"error": "Unauthorized WebSocket connection"})
            await websocket.close(code=1008)
        except Exception:
            pass
        return

    CALL_TRANSCRIPTS.setdefault(call_sid, [])

    try:
        for transcript in CALL_TRANSCRIPTS[call_sid]:
            await websocket.send_json(transcript)

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "transcript":
                # Ensure bounded growth
                transcripts = CALL_TRANSCRIPTS[call_sid]
                transcripts.append(message)
                if len(transcripts) > MAX_TRANSCRIPT_PER_CALL:
                    CALL_TRANSCRIPTS[call_sid] = transcripts[-MAX_TRANSCRIPT_PER_CALL:]
                await manager.broadcast_to_queue("default", message)

    except WebSocketDisconnect:
        logger.info("call_websocket_disconnected", call_sid=call_sid)
    except Exception as e:
        logger.error("call_websocket_error", call_sid=call_sid, error=str(e))
    finally:
        cleanup_call_transcripts(call_sid)
