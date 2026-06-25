import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta
import time


class TestRateLimiter:
    def test_constructor_defaults(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        assert middleware.max_connections == 100
        assert middleware.window == 60
        assert middleware.requests == {}
        assert middleware._redis is None

    def test_get_client_ip_from_forwarded_header(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.headers.get.return_value = "203.0.113.1, 10.0.0.1"
        request.client.host = "10.0.0.1"

        ip = middleware._get_client_ip(request)
        assert ip == "203.0.113.1"
        request.headers.get.assert_called_once_with("X-Forwarded-For")

    def test_get_client_ip_fallback_to_remote(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.headers.get.return_value = None
        request.client.host = "192.168.1.1"

        ip = middleware._get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_get_client_ip_unknown(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.headers.get.return_value = None
        request.client = None

        ip = middleware._get_client_ip(request)
        assert ip == "unknown"

    def test_clean_old_requests_removes_expired(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        key = "test:127.0.0.1"
        old_ts = (datetime.now().timestamp() - 120)  # 2 minutes ago (beyond 60s window)
        current_ts = datetime.now().timestamp()
        middleware.requests[key] = [old_ts, current_ts]

        middleware._clean_old_requests(key)
        assert len(middleware.requests[key]) == 1
        assert middleware.requests[key][0] == current_ts

    def test_clean_old_requests_removes_key_if_empty(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        key = "test:127.0.0.1"
        old_ts = datetime.now().timestamp() - 120
        middleware.requests[key] = [old_ts]

        middleware._clean_old_requests(key)
        assert key not in middleware.requests

    def test_clean_old_requests_keeps_recent(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        key = "test:127.0.0.1"
        recent_ts = datetime.now().timestamp()
        middleware.requests[key] = [recent_ts]

        middleware._clean_old_requests(key)
        assert len(middleware.requests[key]) == 1

    @pytest.mark.asyncio
    async def test_dispatch_skips_static_paths(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.url.path = "/static/file.js"
        request.headers.get.return_value = None
        request.client.host = "127.0.0.1"
        call_next = AsyncMock()

        await middleware.dispatch(request, call_next)
        call_next.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_skips_health_path(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.url.path = "/health"
        request.headers.get.return_value = None
        request.client.host = "127.0.0.1"
        call_next = AsyncMock()

        await middleware.dispatch(request, call_next)
        call_next.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_in_memory_rate_limited(self, monkeypatch):
        from api.services.rate_limit import RateLimitMiddleware, HTTPException

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("REDIS_URL", raising=False)

        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.url.path = "/api/test"
        request.headers.get.return_value = None
        request.client.host = "127.0.0.1"
        call_next = AsyncMock()

        client_ip = "127.0.0.1"
        middleware.requests[client_ip] = [time.time()] * middleware.max_connections

        with pytest.raises(HTTPException) as excinfo:
            await middleware.dispatch(request, call_next)
        assert excinfo.value.status_code == 429
        call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_in_memory_ok(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.url.path = "/api/test"
        request.headers.get.return_value = None
        request.client.host = "127.0.0.1"
        call_next = AsyncMock()

        await middleware.dispatch(request, call_next)
        call_next.assert_awaited_once_with(request)
        assert "127.0.0.1" in middleware.requests

    @pytest.mark.asyncio
    async def test_dispatch_development_mode_high_limit(self, monkeypatch):
        from api.services.rate_limit import RateLimitMiddleware

        monkeypatch.setenv("APP_ENV", "development")
        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.url.path = "/api/test"
        request.headers.get.return_value = None
        request.client.host = "127.0.0.1"
        call_next = AsyncMock()

        client_ip = "127.0.0.1"
        middleware.requests[client_ip] = [time.time()] * 5000

        await middleware.dispatch(request, call_next)
        call_next.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_auth_path_lower_limit(self, monkeypatch):
        from api.services.rate_limit import RateLimitMiddleware, HTTPException

        monkeypatch.setenv("APP_ENV", "production")
        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.url.path = "/auth/login"
        request.headers.get.return_value = None
        request.client.host = "127.0.0.1"
        call_next = AsyncMock()

        client_ip = "127.0.0.1"
        middleware.requests[client_ip] = [time.time()] * 10

        with pytest.raises(HTTPException) as excinfo:
            await middleware.dispatch(request, call_next)
        assert excinfo.value.status_code == 429

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back_to_memory(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        redis_mock = MagicMock()
        redis_mock.pipeline.side_effect = Exception("Redis down")
        middleware._redis = redis_mock
        request = MagicMock()
        request.url.path = "/api/test"
        request.headers.get.return_value = None
        request.client.host = "127.0.0.1"
        call_next = AsyncMock()

        await middleware.dispatch(request, call_next)
        call_next.assert_awaited_once_with(request)

    def test_voice_connection_tracker_can_accept(self):
        from api.services.rate_limit import VoiceConnectionTracker

        tracker = VoiceConnectionTracker(max_concurrent=2)
        tracker.add_call("call-1")
        assert tracker.can_accept_call() is True

    def test_voice_connection_tracker_full(self):
        from api.services.rate_limit import VoiceConnectionTracker

        tracker = VoiceConnectionTracker(max_concurrent=2)
        tracker.add_call("call-1")
        tracker.add_call("call-2")
        assert tracker.can_accept_call() is False

    def test_voice_connection_tracker_remove(self):
        from api.services.rate_limit import VoiceConnectionTracker

        tracker = VoiceConnectionTracker(max_concurrent=2)
        tracker.add_call("call-1")
        tracker.add_call("call-2")
        tracker.remove_call("call-1")
        assert tracker.can_accept_call() is True

    def test_voice_connection_tracker_cleanup(self):
        from api.services.rate_limit import VoiceConnectionTracker

        tracker = VoiceConnectionTracker(max_concurrent=2)
        old_ts = time.time() - 7200
        tracker.active_calls["stale-call"] = old_ts
        tracker._cleanup()
        assert "stale-call" not in tracker.active_calls

    def test_rate_limit_middleware_max_connections_custom(self):
        from api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None, max_connections=200)
        assert middleware.max_connections == 200
        assert middleware.window == 60
