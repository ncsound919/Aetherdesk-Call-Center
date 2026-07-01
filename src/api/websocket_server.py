"""
AetherDesk Call Center - WebSocket Server
Real-time communication for agent dashboard and call monitoring
"""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime

import redis.asyncio as redis
import websockets
from websockets.server import serve

logger = logging.getLogger(__name__)

# Redis connection
redis_client = None

# Connected clients
connected_clients = {}

# Max connections from env var (default 1000)
MAX_CONNECTIONS = int(os.getenv("WS_MAX_CONNECTIONS", "1000"))

# Idle timeout in seconds (30 minutes)
IDLE_TIMEOUT = int(os.getenv("WS_IDLE_TIMEOUT", "1800"))

# Track fire-and-forget tasks
_background_tasks: set = set()


async def register_client(websocket, path):
    """Register a new client connection"""
    if len(connected_clients) >= MAX_CONNECTIONS:
        await websocket.close(1013, "Server at capacity")
        logger.warning("Connection rejected: server at capacity")
        return None
    client_id = f"client_{datetime.now(UTC).timestamp()}"
    now = datetime.now(UTC)
    connected_clients[client_id] = {
        "websocket": websocket,
        "tenant_id": None,
        "agent_id": None,
        "connected_at": now.isoformat(),
        "last_activity": now,
    }
    logger.info(f"Client registered: {client_id}")
    return client_id


async def unregister_client(client_id):
    """Unregister a client connection"""
    if client_id in connected_clients:
        del connected_clients[client_id]
        logger.info(f"Client unregistered: {client_id}")


async def handle_message(websocket, message, client_id):
    """Handle incoming messages from clients"""
    connected_clients[client_id]["last_activity"] = datetime.now(UTC)
    try:
        data = json.loads(message)
        message_type = data.get("type")

        if message_type == "auth":
            # Authenticate client
            tenant_id = data.get("tenant_id")
            token = data.get("token")

            if await verify_token(token):
                connected_clients[client_id]["tenant_id"] = tenant_id
                await websocket.send(json.dumps({
                    "type": "auth_success",
                    "timestamp": datetime.now(UTC).isoformat()
                }))
            else:
                await websocket.send(json.dumps({
                    "type": "auth_error",
                    "message": "Invalid token"
                }))

        elif message_type == "subscribe":
            # Subscribe to events
            event_type = data.get("event")
            connected_clients[client_id]["subscriptions"] = (
                connected_clients[client_id].get("subscriptions", [])
            )
            connected_clients[client_id]["subscriptions"].append(event_type)

            await websocket.send(json.dumps({
                "type": "subscribed",
                "event": event_type
            }))

        elif message_type == "call_action":
            # Handle call actions from agents
            action = data.get("action")
            call_id = data.get("call_id")

            await process_call_action(call_id, action)

        elif message_type == "ping":
            await websocket.send(json.dumps({
                "type": "pong",
                "timestamp": datetime.now(UTC).isoformat()
            }))

    except json.JSONDecodeError:
        logger.error(f"Invalid JSON from client {client_id}")
        await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Client {client_id} disconnected during message handling")
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        try:
            await websocket.send(json.dumps({"type": "error", "message": "Internal error"}))
        except websockets.exceptions.ConnectionClosed:
            pass  # Client already disconnected
        except Exception as e:
            logger.warning("error_notification_failed", error=str(e))


async def process_call_action(call_id, action):
    """Process call actions and notify relevant clients"""
    # Publish action to Redis for other services
    if redis_client:
        await redis_client.publish(
            f"call:{call_id}:actions",
            json.dumps({
                "action": action,
                "timestamp": datetime.now(UTC).isoformat()
            })
        )

    # Broadcast to all subscribed clients
    message = json.dumps({
        "type": "call_action",
        "call_id": call_id,
        "action": action,
        "timestamp": datetime.now(UTC).isoformat()
    })

    for _client_id, client in list(connected_clients.items()):
        if "call_updates" in client.get("subscriptions", []):
            try:
                await client["websocket"].send(message)
            except websockets.exceptions.ConnectionClosed:
                pass


async def verify_token(token):
    """Verify JWT token using RS256 (with HS256 fallback)."""
    from api.services.jwt_utils import verify_access_token
    return verify_access_token(token) is not None


async def redis_listener():
    """Listen for Redis pub/sub messages and forward to clients"""
    if not redis_client:
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("agent:status", "call:status", "call:assigned")

    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            event_type = message["channel"].decode()

            # Broadcast to all connected clients
            for _client_id, client in list(connected_clients.items()):
                try:
                    await client["websocket"].send(json.dumps({
                        "type": event_type,
                        "data": data,
                        "timestamp": datetime.now(UTC).isoformat()
                    }))
                except websockets.exceptions.ConnectionClosed:
                    pass


async def health_monitor():
    """Periodic health check and cleanup"""
    while True:
        await asyncio.sleep(60)
        now = datetime.now(UTC)
        disconnected = []
        idle_clients = []
        for client_id, client in connected_clients.items():
            if client["websocket"].closed:
                disconnected.append(client_id)
            else:
                last_activity = client.get("last_activity")
                if last_activity and (now - last_activity).total_seconds() > IDLE_TIMEOUT:
                    idle_clients.append(client_id)

        for client_id in idle_clients:
            logger.info(f"Evicting idle client: {client_id}")
            await unregister_client(client_id)

        for client_id in disconnected:
            await unregister_client(client_id)

        logger.info(f"Active clients: {len(connected_clients)}")


async def main():
    """Main WebSocket server entry point"""
    global redis_client

    # Connect to Redis
    redis_client = redis.from_url(
        "redis://aetherdesk-redis:6379",
        decode_responses=True
    )

    # Start Redis listener
    redis_task = asyncio.create_task(redis_listener())
    _background_tasks.add(redis_task)

    # Start health monitor
    health_task = asyncio.create_task(health_monitor())
    _background_tasks.add(health_task)

    # Start WebSocket server
    ws_host = os.getenv("WS_HOST", "0.0.0.0" if os.getenv("APP_ENV") == "production" else "127.0.0.1")
    async with serve(
        handle_message,
        ws_host,
        8765,
        ping_interval=20,
        ping_timeout=10,
    ):
        logger.info("WebSocket server started on port 8765")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
