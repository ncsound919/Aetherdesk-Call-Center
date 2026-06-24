import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta


class TestRateLimiter:
    def test_constructor_defaults(self):
        from apps.api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        assert middleware.max_connections == 100
        assert middleware.window == 60
        assert middleware.requests == {}
        assert middleware._redis is None

    def test_get_client_ip_from_forwarded_header(self):
        from apps.api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.headers.get.return_value = "203.0.113.1, 10.0.0.1"
        request.client.host = "10.0.0.1"

        ip = middleware._get_client_ip(request)
        assert ip == "203.0.113.1"
        request.headers.get.assert_called_once_with("X-Forwarded-For")

    def test_get_client_ip_fallback_to_remote(self):
        from apps.api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.headers.get.return_value = None
        request.client.host = "192.168.1.1"

        ip = middleware._get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_get_client_ip_unknown(self):
        from apps.api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        request = MagicMock()
        request.headers.get.return_value = None
        request.client = None

        ip = middleware._get_client_ip(request)
        assert ip == "unknown"

    def test_clean_old_requests_removes_expired(self):
        from apps.api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        key = "test:127.0.0.1"
        old_ts = (datetime.now().timestamp() - 120)  # 2 minutes ago (beyond 60s window)
        current_ts = datetime.now().timestamp()
        middleware.requests[key] = [old_ts, current_ts]

        middleware._clean_old_requests(key)
        assert len(middleware.requests[key]) == 1
        assert middleware.requests[key][0] == current_ts

    def test_clean_old_requests_removes_key_if_empty(self):
        from apps.api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        key = "test:127.0.0.1"
        old_ts = datetime.now().timestamp() - 120
        middleware.requests[key] = [old_ts]

        middleware._clean_old_requests(key)
        assert key not in middleware.requests

    def test_clean_old_requests_keeps_recent(self):
        from apps.api.services.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(None)
        key = "test:127.0.0.1"
        recent_ts = datetime.now().timestamp()
        middleware.requests[key] = [recent_ts]

        middleware._clean_old_requests(key)
        assert len(middleware.requests[key]) == 1
