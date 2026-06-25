
import asyncio
import json
import threading
import time
from typing import Any

import structlog
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from api.services.queue import QueueManager

logger = structlog.get_logger()

router = APIRouter(prefix="/agent", tags=["agent"])

# ── Agent Cache with TTL & Invalidation ──────────────────────────

class AgentCache:
    """In-memory agent cache with TTL and explicit invalidation."""

    def __init__(self, default_ttl: int = 300):
        self._cache: dict[str, dict[str, Any]] = {}
        self._expiry: dict[str, float] = {}
        self._ttl = default_ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> dict[str, Any] | None:
        async with self._lock:
            if key in self._cache:
                if time.time() < self._expiry[key]:
                    return self._cache[key]
                # Atomic check-and-delete to prevent race
                self._cache.pop(key, None)
                self._expiry.pop(key, None)
            return None

    async def set(self, key: str, value: dict[str, Any], ttl: int | None = None):
        async with self._lock:
            self._cache[key] = value
            self._expiry[key] = time.time() + (ttl or self._ttl)

    async def invalidate(self, key: str):
        async with self._lock:
            self._cache.pop(key, None)
            self._expiry.pop(key, None)

    async def invalidate_prefix(self, prefix: str):
        """Invalidate all keys starting with a prefix (e.g. 'tenant:TENANT-ID')."""
        async with self._lock:
            expired = [k for k in list(self._cache.keys()) if k.startswith(prefix)]
            for k in expired:
                self._cache.pop(k, None)
                self._expiry.pop(k, None)

    async def cleanup(self):
        """Remove all expired entries."""
        now = time.time()
        async with self._lock:
            expired = [k for k, exp in list(self._expiry.items()) if now >= exp]
            for k in expired:
                self._cache.pop(k, None)
                self._expiry.pop(k, None)

    async def start_cleanup_loop(self, interval: int = 60):
        """Background task to periodically clean expired entries."""
        while True:
            await asyncio.sleep(interval)
            await self.cleanup()


agent_cache = AgentCache(default_ttl=300)


class Hub:
    """Thread-safe WebSocket hub for agent connections."""

    def __init__(self):
        self.sockets: dict[str, WebSocket] = {}
        self._lock = threading.Lock()  # For thread-safe access

    async def connect(self, agent_id: str, ws: WebSocket):
        with self._lock:
            self.sockets[agent_id] = ws

    async def disconnect(self, agent_id: str):
        with self._lock:
            ws = self.sockets.pop(agent_id, None)
        if ws is not None:
            try:
                await ws.close()
            except Exception as e:
                logger.warning("hub_disconnect_failed", agent_id=agent_id, error=str(e))

    async def send(self, agent_id: str, payload: dict):
        with self._lock:
            ws = self.sockets.get(agent_id)
        if ws is not None:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.warning("hub_send_failed", agent_id=agent_id, error=str(e))

    async def broadcast(self, payload: dict):
        with self._lock:
            sockets_copy = list(self.sockets.values())
        for ws in sockets_copy:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.warning("hub_broadcast_failed", error=str(e))


hub = Hub()

@router.get("/peek")
def peek_queue(request: Request, queue: str = "general", n: int = 50):
    qm = QueueManager(request.app.state.redis)
    return {"items": qm.peek(queue, n)}

@router.post("/token")
async def get_ws_token(agent_id: str):
    from api.services.auth import generate_websocket_token
    token = await generate_websocket_token(agent_id)
    return {"token": token}

@router.post("/claim")
async def claim_next(request: Request, queue: str, agent_id: str):
    qm = QueueManager(request.app.state.redis)
    item = qm.claim(queue, agent_id)
    if not item:
        return {"ok": False, "reason": "empty"}
    await hub.send(agent_id, {"type": "claimed", "item": item})
    await hub.broadcast({"type": "queue_updated"})
    return {"ok": True, "item": item}

@router.post("/disposition")
async def disposition(request: Request, session_id: str, code: str, notes: str = ""):
    r = request.app.state.redis
    if not session_id.isalnum() and "_" not in session_id:
        return {"ok": False, "error": "Invalid session ID format"}
    if not hasattr(request.app.state, 'call_sessions') or session_id not in request.app.state.call_sessions:
        if not await r.exists(f"log:{session_id}"):
            # We allow disposition if the log already exists or the session is active.
            return {"ok": False, "error": "Session not found"}
    await r.rpush(f"log:{session_id}", json.dumps({"event":"disposition","code":code,"notes":notes,"ts":time.time()}))
    return {"ok": True}

@router.websocket("/ws")
async def ws_agent(websocket: WebSocket):
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
    agent_id = websocket.query_params.get("agent_id") or f"agent-{int(time.time())}"
    await hub.connect(agent_id, websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        logger.info(f"Agent {agent_id} disconnected")
        await hub.disconnect(agent_id)
