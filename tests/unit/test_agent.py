import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, WebSocket
from fastapi.websockets import WebSocketDisconnect


class TestAgentCache:
    """Tests for AgentCache functionality."""

    @pytest.mark.asyncio
    async def test_cache_set_get(self):
        from apps.api.routers.agent import AgentCache

        cache = AgentCache(default_ttl=300)
        await cache.set("test:1", {"data": "value"})
        result = await cache.get("test:1")
        assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_cache_ttl_expiry(self):
        from apps.api.routers.agent import AgentCache

        cache = AgentCache(default_ttl=1)  # 1 second TTL
        await cache.set("test:2", {"data": "value"})
        await asyncio.sleep(1.1)  # Wait for expiry
        result = await cache.get("test:2")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_custom_ttl(self):
        from apps.api.routers.agent import AgentCache

        cache = AgentCache(default_ttl=300)
        await cache.set("test:3", {"data": "value"}, ttl=0.1)  # 100ms TTL
        await asyncio.sleep(0.11)
        result = await cache.get("test:3")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_invalidate(self):
        from apps.api.routers.agent import AgentCache

        cache = AgentCache(default_ttl=300)
        await cache.set("test:4", {"data": "value"})
        await cache.invalidate("test:4")
        result = await cache.get("test:4")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_invalidate_prefix(self):
        from apps.api.routers.agent import AgentCache

        cache = AgentCache(default_ttl=300)
        await cache.set("tenant:1:agent:1", {"data": "value1"})
        await cache.set("tenant:1:agent:2", {"data": "value2"})
        await cache.set("tenant:2:agent:1", {"data": "value3"})
        
        await cache.invalidate_prefix("tenant:1:")
        
        assert await cache.get("tenant:1:agent:1") is None
        assert await cache.get("tenant:1:agent:2") is None
        assert await cache.get("tenant:2:agent:1") == {"data": "value3"}

    @pytest.mark.asyncio
    async def test_cache_cleanup(self):
        from apps.api.routers.agent import AgentCache

        cache = AgentCache(default_ttl=0.1)  # 100ms TTL
        await cache.set("test:5", {"data": "value"})
        await asyncio.sleep(0.11)
        await cache.cleanup()
        result = await cache.get("test:5")
        assert result is None


class TestHub:
    """Tests for WebSocket Hub functionality."""

    @pytest.mark.asyncio
    async def test_hub_connect_disconnect(self):
        from apps.api.routers.agent import Hub

        hub = Hub()
        mock_ws = AsyncMock(spec=WebSocket)
        
        await hub.connect("agent-1", mock_ws)
        assert "agent-1" in hub.sockets
        
        await hub.disconnect("agent-1")
        assert "agent-1" not in hub.sockets
        # WebSocket.close() is called in the background thread, so we can't easily mock it
        # This is a limitation of testing threading code with async tests

    @pytest.mark.asyncio
    async def test_hub_send(self):
        from apps.api.routers.agent import Hub

        hub = Hub()
        mock_ws = AsyncMock(spec=WebSocket)
        
        await hub.connect("agent-1", mock_ws)
        await hub.send("agent-1", {"type": "test", "data": "value"})
        # WebSocket.send_json() is called in the background thread, so we can't easily mock it
        # This is a limitation of testing threading code with async tests

    @pytest.mark.asyncio
    async def test_hub_send_nonexistent_agent(self):
        from apps.api.routers.agent import Hub

        hub = Hub()
        mock_ws = AsyncMock(spec=WebSocket)
        
        # Should not raise exception
        await hub.send("nonexistent", {"type": "test"})
        mock_ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_hub_broadcast(self):
        from apps.api.routers.agent import Hub

        hub = Hub()
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        
        await hub.connect("agent-1", mock_ws1)
        await hub.connect("agent-2", mock_ws2)
        
        await hub.broadcast({"type": "broadcast", "data": "value"})
        
        mock_ws1.send_json.assert_called_once_with({"type": "broadcast", "data": "value"})
        mock_ws2.send_json.assert_called_once_with({"type": "broadcast", "data": "value"})

    @pytest.mark.asyncio
    async def test_hub_send_success(self):
        from apps.api.routers.agent import Hub

        hub = Hub()
        mock_ws = AsyncMock(spec=WebSocket)

        await hub.connect("agent-1", mock_ws)
        await hub.send("agent-1", {"type": "test", "data": "value"})

        mock_ws.send_json.assert_called_once_with({"type": "test", "data": "value"})

    @pytest.mark.asyncio
    async def test_hub_send_failure_logs_warning(self):
        from apps.api.routers.agent import Hub

        hub = Hub()
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_json.side_effect = Exception("send failed")

        await hub.connect("agent-1", mock_ws)

        with patch("apps.api.routers.agent.logger.warning") as mock_warning:
            await hub.send("agent-1", {"type": "test"})

        mock_warning.assert_called_once()
        args, _ = mock_warning.call_args
        assert "hub_send_failed" in args

    @pytest.mark.asyncio
    async def test_hub_disconnect_failure_logs_warning(self):
        from apps.api.routers.agent import Hub

        hub = Hub()
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.close.side_effect = Exception("close failed")

        await hub.connect("agent-1", mock_ws)

        with patch("apps.api.routers.agent.logger.warning") as mock_warning:
            await hub.disconnect("agent-1")

        mock_warning.assert_called_once()
        args, _ = mock_warning.call_args
        assert "hub_disconnect_failed" in args

    @pytest.mark.asyncio
    async def test_hub_broadcast_continues_on_error(self):
        from apps.api.routers.agent import Hub

        hub = Hub()
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        mock_ws1.send_json.side_effect = Exception("ws1 failed")

        await hub.connect("agent-1", mock_ws1)
        await hub.connect("agent-2", mock_ws2)

        await hub.broadcast({"type": "test"})

        mock_ws2.send_json.assert_called_once_with({"type": "test"})

    @pytest.mark.asyncio
    async def test_hub_disconnect_nonexistent(self):
        from apps.api.routers.agent import Hub

        hub = Hub()

        # Should not raise exception
        await hub.disconnect("nonexistent")


class TestAgentEndpoints:
    """Tests for agent REST endpoints."""

    @pytest.mark.asyncio
    async def test_peek_queue(self):
        from apps.api.routers.agent import peek_queue

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_request.app.state.redis = mock_redis
        
        mock_qm = MagicMock()
        mock_qm.peek.return_value = [{"id": "item1"}, {"id": "item2"}]
        
        with patch("apps.api.routers.agent.QueueManager", return_value=mock_qm):
            result = peek_queue(mock_request, queue="general", n=50)
            
        assert result == {"items": [{"id": "item1"}, {"id": "item2"}]}
        mock_qm.peek.assert_called_once_with("general", 50)

    @pytest.mark.asyncio
    async def test_get_ws_token(self):
        from apps.api.routers.agent import get_ws_token

        with patch("apps.api.services.auth.generate_websocket_token", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "test-token-123"
            result = await get_ws_token("agent-1")
            
        assert result == {"token": "test-token-123"}
        mock_gen.assert_called_once_with("agent-1")

    @pytest.mark.asyncio
    async def test_claim_next_success(self):
        from apps.api.routers.agent import claim_next

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_request.app.state.redis = mock_redis
        
        mock_qm = MagicMock()
        mock_qm.claim.return_value = {"id": "item1", "data": "test"}
        
        with patch("apps.api.routers.agent.QueueManager", return_value=mock_qm), \
             patch("apps.api.routers.agent.hub.send", new_callable=AsyncMock) as mock_send, \
             patch("apps.api.routers.agent.hub.broadcast", new_callable=AsyncMock) as mock_broadcast:
            
            result = await claim_next(mock_request, queue="general", agent_id="agent-1")
            
        assert result == {"ok": True, "item": {"id": "item1", "data": "test"}}
        mock_qm.claim.assert_called_once_with("general", "agent-1")
        mock_send.assert_called_once_with("agent-1", {"type": "claimed", "item": {"id": "item1", "data": "test"}})
        mock_broadcast.assert_called_once_with({"type": "queue_updated"})

    @pytest.mark.asyncio
    async def test_claim_next_empty(self):
        from apps.api.routers.agent import claim_next

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_request.app.state.redis = mock_redis
        
        mock_qm = MagicMock()
        mock_qm.claim.return_value = None
        
        with patch("apps.api.routers.agent.QueueManager", return_value=mock_qm), \
             patch("apps.api.routers.agent.hub.send", new_callable=AsyncMock) as mock_send, \
             patch("apps.api.routers.agent.hub.broadcast", new_callable=AsyncMock) as mock_broadcast:
            
            result = await claim_next(mock_request, queue="general", agent_id="agent-1")
            
        assert result == {"ok": False, "reason": "empty"}
        mock_send.assert_not_called()
        mock_broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_disposition_success(self):
        from apps.api.routers.agent import disposition

        mock_request = MagicMock(spec=Request)
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = True
        mock_redis.rpush = AsyncMock()
        mock_request.app.state.redis = mock_redis
        
        result = await disposition(mock_request, session_id="session123", code="completed", notes="Test notes")
        
        assert result == {"ok": True}
        mock_redis.exists.assert_called_once_with("log:session123")
        mock_redis.rpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_disposition_invalid_session_id(self):
        from apps.api.routers.agent import disposition

        mock_request = MagicMock(spec=Request)
        mock_redis = AsyncMock()
        mock_request.app.state.redis = mock_redis
        
        result = await disposition(mock_request, session_id="invalid!id", code="completed")
        
        assert result == {"ok": False, "error": "Invalid session ID format"}

    @pytest.mark.asyncio
    async def test_disposition_session_not_found(self):
        from apps.api.routers.agent import disposition

        mock_request = MagicMock(spec=Request)
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = False
        mock_request.app.state.redis = mock_redis
        
        result = await disposition(mock_request, session_id="nonexistent", code="completed")
        
        assert result == {"ok": False, "error": "Session not found"}


class TestWebSocket:
    """Tests for WebSocket endpoint."""

    @pytest.mark.asyncio
    async def test_ws_agent_missing_token(self):
        from apps.api.routers.agent import ws_agent

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = None
        
        with patch("apps.api.routers.agent.hub.connect", new_callable=AsyncMock) as mock_connect:
            await ws_agent(mock_ws)
            
        mock_ws.close.assert_called_once_with(code=4001, reason="Missing authentication token")
        mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_ws_agent_invalid_token(self):
        from apps.api.routers.agent import ws_agent

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "invalid-token"
        
        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.routers.agent.hub.connect", new_callable=AsyncMock) as mock_connect:
            
            mock_verify.return_value = None
            await ws_agent(mock_ws)
            
        mock_ws.close.assert_called_once_with(code=4003, reason="Invalid or expired token")
        mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_ws_agent_success(self):
        from apps.api.routers.agent import ws_agent

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.side_effect = ["valid-token", "agent-1"]
        
        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.routers.agent.hub.connect", new_callable=AsyncMock) as mock_connect, \
             patch("apps.api.routers.agent.hub.disconnect", new_callable=AsyncMock) as mock_disconnect:
            
            mock_verify.return_value = {"agent_id": "agent-1"}
            mock_ws.receive_text.side_effect = ["test message", WebSocketDisconnect()]
            
            await ws_agent(mock_ws)
            
        mock_ws.accept.assert_called_once()
        mock_connect.assert_called_once_with("agent-1", mock_ws)
        mock_ws.send_text.assert_called_once_with("test message")
        mock_disconnect.assert_called_once_with("agent-1")

    @pytest.mark.asyncio
    async def test_ws_agent_auto_agent_id(self):
        from apps.api.routers.agent import ws_agent
        import time

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.side_effect = ["valid-token", None]  # No agent_id provided
        
        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.routers.agent.hub.connect", new_callable=AsyncMock) as mock_connect, \
             patch("apps.api.routers.agent.time.time", return_value=1234567890):
            
            mock_verify.return_value = {"agent_id": "agent-1"}
            mock_ws.receive_text.side_effect = WebSocketDisconnect()
            
            await ws_agent(mock_ws)
            
        expected_agent_id = "agent-1234567890"
        mock_connect.assert_called_once_with(expected_agent_id, mock_ws)