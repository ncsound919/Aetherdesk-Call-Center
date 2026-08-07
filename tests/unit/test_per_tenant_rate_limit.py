"""Unit tests for src/api/services/per_tenant_rate_limit.py.

Covers PerTenantRateLimiter (in-memory sliding window + mocked redis zset
sliding window), config loading/caching, and RateLimitMiddleware dispatch.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.services.per_tenant_rate_limit as module
from api.services.per_tenant_rate_limit import (
    PerTenantRateLimiter,
    RateLimitMiddleware,
    rate_limiter,
)


class FakePipe:
    """Fake redis pipeline for the sliding-window zset branch."""

    def __init__(self, count=0, fail=False):
        self.count = count
        self.fail = fail
        self.calls = []

    async def __aenter__(self):
        if self.fail:
            raise Exception("redis down")
        return self

    async def __aexit__(self, *exc):
        return False

    async def zremrangebyscore(self, *a, **k):
        self.calls.append(("zremrangebyscore", a, k))
        return 0

    async def zcard(self, *a, **k):
        self.calls.append(("zcard", a, k))
        return self.count

    async def zadd(self, *a, **k):
        self.calls.append(("zadd", a, k))
        return 1

    async def expire(self, *a, **k):
        self.calls.append(("expire", a, k))
        return True

    async def execute(self, *a, **k):
        self.calls.append(("execute", a, k))
        return [0, self.count]


def _fake_redis(count=0, fail=False):
    redis = MagicMock()
    redis.pipeline.return_value = FakePipe(count=count, fail=fail)
    return redis


class TestConstructor:
    def test_defaults(self):
        limiter = PerTenantRateLimiter()
        assert limiter.redis is None
        assert limiter._local_store == {}
        assert limiter._local_configs == {}

    def test_with_redis(self):
        redis = MagicMock()
        limiter = PerTenantRateLimiter(redis_client=redis)
        assert limiter.redis is redis

    def test_module_singleton(self):
        assert isinstance(rate_limiter, PerTenantRateLimiter)


class TestCheckLimitLocal:
    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        limiter = PerTenantRateLimiter()
        result = await limiter.check_limit("t1", "/api/x", max_requests=100)
        assert result["allowed"] is True
        assert result["remaining"] == 99
        assert result["total"] == 100
        assert result["tenant_id"] == "t1"
        assert result["route_key"] == "/api/x"
        assert result["reset_in"] == 0
        assert len(limiter._local_store["t1"]["/api/x"]) == 1

    @pytest.mark.asyncio
    async def test_exceeds_limit_blocks(self):
        limiter = PerTenantRateLimiter()
        for _ in range(2):
            await limiter.check_limit("t1", "/api/x", max_requests=2)
        result = await limiter.check_limit("t1", "/api/x", max_requests=2)
        assert result["allowed"] is False
        assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_at_limit_boundary(self):
        limiter = PerTenantRateLimiter()
        for _ in range(3):
            result = await limiter.check_limit("t1", "/api/x", max_requests=3)
        assert result["allowed"] is True
        assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_per_tenant_isolation(self):
        limiter = PerTenantRateLimiter()
        await limiter.check_limit("t1", "/api/x", max_requests=1)
        assert (await limiter.check_limit("t2", "/api/x", max_requests=1))["allowed"] is True

    @pytest.mark.asyncio
    async def test_per_route_isolation(self):
        limiter = PerTenantRateLimiter()
        await limiter.check_limit("t1", "/api/x", max_requests=1)
        assert (await limiter.check_limit("t1", "/api/y", max_requests=1))["allowed"] is True

    @pytest.mark.asyncio
    async def test_expired_timestamps_pruned(self, monkeypatch):
        limiter = PerTenantRateLimiter()
        now = 1000.0
        monkeypatch.setattr(module.time, "time", lambda: now)
        await limiter.check_limit("t1", "/api/x", max_requests=10)
        limiter._local_store["t1"]["/api/x"] = [900.0, 950.0]
        monkeypatch.setattr(module.time, "time", lambda: now + 100)
        result = await limiter.check_limit("t1", "/api/x", max_requests=10)
        # stale timestamps (> window 60s) pruned; only the new one remains
        assert len(limiter._local_store["t1"]["/api/x"]) == 1

    @pytest.mark.asyncio
    async def test_config_overrides_defaults(self):
        limiter = PerTenantRateLimiter()
        with patch(
            "api.services.per_tenant_rate_limit.get_rate_limit_config_db",
            new_callable=AsyncMock,
            return_value={"max_requests": 2, "window_seconds": 10},
        ):
            for _ in range(2):
                result = await limiter.check_limit("t1", "/api/x")
            blocked = await limiter.check_limit("t1", "/api/x")
        assert result["allowed"] is True
        assert result["total"] == 2
        assert blocked["allowed"] is False

    @pytest.mark.asyncio
    async def test_config_db_error_falls_back(self):
        limiter = PerTenantRateLimiter()
        with patch(
            "api.services.per_tenant_rate_limit.get_rate_limit_config_db",
            new_callable=AsyncMock,
            side_effect=Exception("db down"),
        ):
            result = await limiter.check_limit("t1", "/api/x", max_requests=5)
        assert result["allowed"] is True
        assert result["total"] == 5


class TestCheckLimitRedis:
    @pytest.mark.asyncio
    async def test_redis_allowed(self):
        limiter = PerTenantRateLimiter(redis_client=_fake_redis(count=5))
        result = await limiter.check_limit("t1", "/api/x", max_requests=10)
        assert result["allowed"] is True
        assert result["remaining"] == 4
        assert result["total"] == 10
        assert result["tenant_id"] == "t1"

    @pytest.mark.asyncio
    async def test_redis_blocked(self):
        limiter = PerTenantRateLimiter(redis_client=_fake_redis(count=10))
        result = await limiter.check_limit("t1", "/api/x", max_requests=10)
        assert result["allowed"] is False
        assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_redis_uses_key_and_expiry(self):
        pipe = FakePipe(count=0)
        redis = MagicMock()
        redis.pipeline.return_value = pipe
        limiter = PerTenantRateLimiter(redis_client=redis)
        await limiter.check_limit("t1", "/api/x", max_requests=10)
        names = [c[0] for c in pipe.calls]
        assert "zremrangebyscore" in names
        assert "zcard" in names
        assert "zadd" in names
        assert "expire" in names
        zadd_call = next(c for c in pipe.calls if c[0] == "zadd")
        assert "/api/x" in zadd_call[1][0] or "ratelimit:t1" in zadd_call[1][0]

    @pytest.mark.asyncio
    async def test_redis_failure_fails_open(self):
        limiter = PerTenantRateLimiter(redis_client=_fake_redis(fail=True))
        result = await limiter.check_limit("t1", "/api/x", max_requests=7)
        assert result["allowed"] is True
        assert result["remaining"] == 1
        assert result["total"] == 7

    @pytest.mark.asyncio
    async def test_redis_pipeline_exception(self):
        redis = MagicMock()
        redis.pipeline.side_effect = Exception("connection refused")
        limiter = PerTenantRateLimiter(redis_client=redis)
        result = await limiter.check_limit("t1", "/api/x")
        assert result["allowed"] is True


class TestGetConfig:
    @pytest.mark.asyncio
    async def test_cached_config_short_circuits(self):
        limiter = PerTenantRateLimiter()
        limiter._local_configs["t1"]["/api/x"] = {"max_requests": 3}
        with patch(
            "api.services.per_tenant_rate_limit.get_rate_limit_config_db",
            new_callable=AsyncMock,
        ) as db:
            config = await limiter._get_config("t1", "/api/x")
        assert config == {"max_requests": 3}
        db.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_db_hit_caches(self):
        limiter = PerTenantRateLimiter()
        with patch(
            "api.services.per_tenant_rate_limit.get_rate_limit_config_db",
            new_callable=AsyncMock,
            return_value={"max_requests": 9},
        ) as db:
            config = await limiter._get_config("t1", "/api/x")
            await limiter._get_config("t1", "/api/x")
        assert config == {"max_requests": 9}
        db.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_db_miss_returns_none(self):
        limiter = PerTenantRateLimiter()
        with patch(
            "api.services.per_tenant_rate_limit.get_rate_limit_config_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await limiter._get_config("t1", "/api/x") is None

    @pytest.mark.asyncio
    async def test_db_exception_returns_none(self):
        limiter = PerTenantRateLimiter()
        with patch(
            "api.services.per_tenant_rate_limit.get_rate_limit_config_db",
            new_callable=AsyncMock,
            side_effect=Exception("boom"),
        ):
            assert await limiter._get_config("t1", "/api/x") is None


class TestGetLimits:
    @pytest.mark.asyncio
    async def test_returns_rows(self):
        limiter = PerTenantRateLimiter()
        with patch(
            "api.services.db_reliability.list_rate_limit_configs_db",
            new_callable=AsyncMock,
            return_value=[{"route_key": "/api/x"}],
        ) as db:
            result = await limiter.get_limits("t1")
        assert result == [{"route_key": "/api/x"}]
        db.assert_awaited_once_with("t1")

    @pytest.mark.asyncio
    async def test_db_exception_returns_empty(self):
        limiter = PerTenantRateLimiter()
        with patch(
            "api.services.db_reliability.list_rate_limit_configs_db",
            new_callable=AsyncMock,
            side_effect=Exception("boom"),
        ):
            assert await limiter.get_limits("t1") == []


class TestSetLimits:
    @pytest.mark.asyncio
    async def test_sets_and_caches(self):
        limiter = PerTenantRateLimiter()
        with patch(
            "api.services.db_reliability.set_rate_limit_config_db",
            new_callable=AsyncMock,
            return_value={"max_requests": 5, "window_seconds": 30},
        ) as db:
            result = await limiter.set_limits("t1", "/api/x", 5, 30)
        assert result == {"max_requests": 5, "window_seconds": 30}
        db.assert_awaited_once_with("t1", "/api/x", 5, 30)
        assert limiter._local_configs["t1"]["/api/x"] == result


class TestGetAllLimits:
    @pytest.mark.asyncio
    async def test_returns_rows(self):
        limiter = PerTenantRateLimiter()
        with patch(
            "api.services.db_reliability.list_rate_limit_configs_db",
            new_callable=AsyncMock,
            return_value=[{"tenant_id": "t1"}],
        ):
            assert await limiter.get_all_limits() == [{"tenant_id": "t1"}]

    @pytest.mark.asyncio
    async def test_db_exception_returns_empty(self):
        limiter = PerTenantRateLimiter()
        with patch(
            "api.services.db_reliability.list_rate_limit_configs_db",
            new_callable=AsyncMock,
            side_effect=Exception("boom"),
        ):
            assert await limiter.get_all_limits() == []


class _Req:
    def __init__(self, path="/api/test", tenant_id=None, query_tenant=None):
        self.url = SimpleNamespace(path=path)
        self.state = SimpleNamespace(tenant_id=tenant_id)
        self.query_params = (
            {"tenant_id": query_tenant} if query_tenant is not None else {}
        )


class TestRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_no_tenant_passes_through(self):
        middleware = RateLimitMiddleware(None)
        request = _Req()
        call_next = AsyncMock(return_value=MagicMock(headers={}))
        with patch.object(module.rate_limiter, "check_limit", new_callable=AsyncMock) as cl:
            await middleware.dispatch(request, call_next)
        cl.assert_not_awaited()
        call_next.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    async def test_tenant_from_query_param(self):
        middleware = RateLimitMiddleware(None)
        request = _Req(query_tenant="t1")
        call_next = AsyncMock(return_value=MagicMock(headers={}))
        with patch.object(
            module.rate_limiter,
            "check_limit",
            new_callable=AsyncMock,
            return_value={
                "allowed": True,
                "remaining": 50,
                "reset_in": 0,
                "total": 100,
            },
        ) as cl:
            await middleware.dispatch(request, call_next)
        cl.assert_awaited_once()
        assert cl.await_args.args == ("t1", "/api/test")

    @pytest.mark.asyncio
    async def test_blocked_returns_429(self):
        middleware = RateLimitMiddleware(None)
        request = _Req(tenant_id="t1")
        call_next = AsyncMock()
        with patch.object(
            module.rate_limiter,
            "check_limit",
            new_callable=AsyncMock,
            return_value={
                "allowed": False,
                "remaining": 0,
                "reset_in": 30,
                "total": 100,
            },
        ):
            response = await middleware.dispatch(request, call_next)
        assert response.status_code == 429
        body = response.body.decode()
        assert "Rate limit exceeded" in body
        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["X-RateLimit-Reset"] == "30"
        assert response.headers["Retry-After"] == "30"
        call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_allowed_sets_rate_limit_headers(self):
        middleware = RateLimitMiddleware(None)
        request = _Req(tenant_id="t1")
        inner = MagicMock(headers={})
        call_next = AsyncMock(return_value=inner)
        with patch.object(
            module.rate_limiter,
            "check_limit",
            new_callable=AsyncMock,
            return_value={
                "allowed": True,
                "remaining": 42,
                "reset_in": 0,
                "total": 100,
            },
        ):
            response = await middleware.dispatch(request, call_next)
        assert response is inner
        assert inner.headers["X-RateLimit-Limit"] == "100"
        assert inner.headers["X-RateLimit-Remaining"] == "42"
        assert inner.headers["X-RateLimit-Reset"] == "0"
