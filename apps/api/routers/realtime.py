import asyncio
import base64
import json
import time

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.api.services.queue import QueueManager
from apps.api.services.transcript_store import TranscriptStore

logger = structlog.get_logger()

router = APIRouter(prefix="/realtime", tags=["realtime"])

_default_store = TranscriptStore()


class ConnectionManager:
    def __init__(self, store: TranscriptStore | None = None):
        self.active_connections: dict[str, WebSocket] = {}
        self.voice_connections: dict[str, tuple[WebSocket, str]] = {} # call_sid -> (ws, stream_sid)
        self._store = store or _default_store

    async def connect(self, websocket: WebSocket, agent_id: str):
        await websocket.accept()
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

manager = ConnectionManager()


@router.websocket("/agent/{agent_id}")
async def agent_websocket(websocket: WebSocket, agent_id: str):
    await manager.connect(websocket, agent_id)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            msg_type = message.get("type")

            if msg_type == "subscribe_call":
                call_sid = message.get("call_sid")
                _default_store.get_or_create(call_sid)
                await websocket.send_json({
                    "type": "subscribed",
                    "call_sid": call_sid
                })

                for transcript in _default_store.get_transcripts(call_sid):
                    await websocket.send_json(transcript)

            elif msg_type == "send_message":
                call_sid = message.get("call_sid")
                text = message.get("text")

                if hasattr(websocket.app, 'state') and hasattr(websocket.app.state, 'redis'):
                    qm = QueueManager(websocket.app.state.redis)
                    qm.session_set(f"call_{call_sid}", {
                        "agent_message": text,
                        "timestamp": time.time()
                    })

                _default_store.touch(call_sid)

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

def cleanup_call_transcripts(call_sid: str, store: TranscriptStore | None = None):
    store = store or _default_store
    store.cleanup(call_sid)

def broadcast_transcript(call_sid: str, transcript_entry: dict, store: TranscriptStore | None = None):
    store = store or _default_store
    store.add_transcript(call_sid, transcript_entry)

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

    _default_store.get_or_create(call_sid)

    try:
        for transcript in _default_store.get_transcripts(call_sid):
            await websocket.send_json(transcript)

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "transcript":
                _default_store.add_transcript(call_sid, message)
                await manager.broadcast_to_queue("default", message)

    except WebSocketDisconnect:
        logger.info("call_websocket_disconnected", call_sid=call_sid)
    except Exception as e:
        logger.error("call_websocket_error", call_sid=call_sid, error=str(e))
    finally:
        cleanup_call_transcripts(call_sid)
