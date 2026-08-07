"""Unit tests for src/api/services/redis_cache.py.

Covers ``RedisCacheService`` get/set/delete/stats/warm/clear, local in-memory
fallback (eviction, expiry), mocked redis client interaction, connection
handling (success + failure fallback) and error-path fallbacks. No real redis
connection is made.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.redis_cache import RedisCacheService, redis_cache_service


@pytest.fixture
def service():
    return RedisCacheService()


@pytest.fixture
def redis_service(service):
    client = AsyncMock()
    service._redis = client
    return service, client


@pytest.fixture
def module_service():
    return redis_cache_service


class TestLocalFallback:
    @pytest.mark.asyncio
    async def test_get_miss(self, service):
        assert await service.get("missing") is None
        assert service._hits == 0
        assert service._misses == 1

    @pytest.mark.asyncio
    async def test_set_then_get_hit(self, service):
        assert await service.set("k", "v", ttl=300) is True
        assert await service.get("k") == "v"
        assert service._hits == 1

    @pytest.mark.asyncio
    async def test_get_returns_bytes_value(self, service):
        await service.set("k", b"raw", ttl=300)
        assert await service.get("k") == b"raw"

    @pytest.mark.asyncio
    async def test_get_evicts_expired_entry(self, service):
        await service.set("k", "v", ttl=300)
        service._local_expiry["k"] = time.time() - 1
        assert await service.get("k") is None
        assert "k" not in service._local
        assert service._misses == 1

    @pytest.mark.asyncio
    async def test_delete_removes_key(self, service):
        await service.set("k", "v")
        assert await service.delete("k") is True
        assert await service.get("k") is None

    @pytest.mark.asyncio
    async def test_delete_missing_key(self, service):
        assert await service.delete("nope") is True

    @pytest.mark.asyncio
    async def test_eviction_when_over_max_size(self, service):
        service._local_max_size = 2
        await service.set("a", "1")
        await service.set("b", "2")
        await service.set("c", "3")
        assert len(service._local) == 2
        assert "a" not in service._local

    @pytest.mark.asyncio
    async def test_stats_empty(self, service):
        stats = await service.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate_pct"] == 0.0
        assert stats["miss_rate_pct"] == 0.0
        assert stats["total_requests"] == 0
        assert stats["local_cache_size"] == 0
        assert stats["local_memory_used_bytes"] == 0

    @pytest.mark.asyncio
    async def test_stats_with_requests_and_local_size(self, service):
        await service.set("a", "x" * 100)
        await service.get("a")  # hit
        await service.get("b")  # miss
        stats = await service.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate_pct"] == 50.0
        assert stats["miss_rate_pct"] == 50.0
        assert stats["total_requests"] == 2
        assert stats["local_cache_size"] == 1
        assert stats["local_memory_used_bytes"] > 0

    @pytest.mark.asyncio
    async def test_clear_resets_local_and_stats(self, service):
        await service.set("a", "1")
        await service.get("a")
        assert await service.clear() is True
        assert await service.get("a") is None
        stats = await service.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 1  # clear reset counters before this get

    @pytest.mark.asyncio
    async def test_warm_sync_function(self, service):
        calls = []

        def load():
            calls.append(1)
            return "computed"

        value = await service.warm("k", load, ttl=60)
        assert value == "computed"
        assert calls == [1]
        assert await service.get("k") == "computed"

    @pytest.mark.asyncio
    async def test_warm_async_function(self, service):
        async def load():
            return "async-value"

        value = await service.warm("k", load, ttl=60)
        assert value == "async-value"
        assert await service.get("k") == "async-value"

    @pytest.mark.asyncio
    async def test_warm_returns_cached_without_calling_func(self, service):
        await service.set("k", "cached")

        def load():
            raise AssertionError("should not be called")

        assert await service.warm("k", load) == "cached"

    @pytest.mark.asyncio
    async def test_warm_negative_cached_value_returns_it(self, service):
        await service.set("k", 0)
        assert await service.warm("k", lambda: 99) == 0


class TestRedisMode:
    @pytest.mark.asyncio
    async def test_get_hit_from_redis(self, redis_service):
        service, client = redis_service
        client.get.return_value = "cached"
        assert await service.get("k") == "cached"
        client.get.assert_awaited_once_with("k")
        assert service._hits == 1

    @pytest.mark.asyncio
    async def test_get_miss_from_redis(self, redis_service):
        service, client = redis_service
        client.get.return_value = None
        assert await service.get("k") is None
        assert service._misses == 1

    @pytest.mark.asyncio
    async def test_get_redis_error_falls_back_to_local(self, redis_service):
        service, client = redis_service
        service._local["k"] = "local"
        service._local_expiry["k"] = time.time() + 60
        client.get.side_effect = RuntimeError("boom")
        assert await service.get("k") == "local"

    @pytest.mark.asyncio
    async def test_set_uses_setex(self, redis_service):
        service, client = redis_service
        assert await service.set("k", "v", ttl=120) is True
        client.setex.assert_awaited_once_with("k", 120, "v")

    @pytest.mark.asyncio
    async def test_set_redis_error_falls_back_to_local(self, redis_service):
        service, client = redis_service
        client.setex.side_effect = RuntimeError("boom")
        assert await service.set("k", "v", ttl=120) is True
        assert service._local["k"] == "v"
        assert service._local_expiry["k"] > time.time()

    @pytest.mark.asyncio
    async def test_delete_uses_redis(self, redis_service):
        service, client = redis_service
        assert await service.delete("k") is True
        client.delete.assert_awaited_once_with("k")

    @pytest.mark.asyncio
    async def test_delete_redis_error_falls_back_to_local(self, redis_service):
        service, client = redis_service
        client.setex.side_effect = RuntimeError("boom")
        await service.set("k", "v")
        assert service._local["k"] == "v"
        client.delete.side_effect = RuntimeError("boom")
        assert await service.delete("k") is True
        assert "k" not in service._local

    @pytest.mark.asyncio
    async def test_stats_with_redis_info_and_dbsize(self, redis_service):
        service, client = redis_service
        client.info.return_value = {
            "used_memory": 1024,
            "used_memory_peak": 2048,
        }
        client.dbsize.return_value = 7
        stats = await service.get_stats()
        assert stats["redis_memory_used_bytes"] == 1024
        assert stats["redis_memory_peak_bytes"] == 2048
        assert stats["redis_keys"] == 7
        client.info.assert_awaited_once_with("memory")

    @pytest.mark.asyncio
    async def test_stats_redis_info_error_reports_connected(self, redis_service):
        service, client = redis_service
        client.info.side_effect = RuntimeError("boom")
        stats = await service.get_stats()
        assert stats["redis_connected"] is True

    @pytest.mark.asyncio
    async def test_clear_uses_flushdb(self, redis_service):
        service, client = redis_service
        assert await service.clear() is True
        client.flushdb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_redis_error_falls_back_to_local(self, redis_service):
        service, client = redis_service
        client.flushdb.side_effect = RuntimeError("boom")
        await service.set("k", "v")
        await service.get("k")
        assert await service.clear() is True
        assert service._hits == 0
        assert service._misses == 0


class TestConnectionHandling:
    @pytest.mark.asyncio
    async def test_connect_success_creates_client_and_pings(self):
        service = RedisCacheService(redis_url="redis://localhost:6379/0")
        client = AsyncMock()
        client.get.return_value = None
        with patch("redis.asyncio.from_url", return_value=client) as from_url:
            assert await service.get("k") is None  # ping'd, then miss
        from_url.assert_called_once_with(
            "redis://localhost:6379/0", decode_responses=True
        )
        client.ping.assert_awaited_once()
        assert service._redis is client

    @pytest.mark.asyncio
    async def test_connect_failure_disables_redis_and_uses_local(self):
        service = RedisCacheService(redis_url="redis://localhost:6379/0")
        with patch(
            "redis.asyncio.from_url", side_effect=RuntimeError("no redis")
        ) as from_url:
            assert await service.set("k", "v") is True
            assert await service.get("k") == "v"
        assert service._redis is False
        assert from_url.call_count == 1  # no retry once marked False

    @pytest.mark.asyncio
    async def test_disabled_redis_never_reconnects(self):
        service = RedisCacheService(redis_url="redis://localhost:6379/0")
        service._redis = False
        with patch("redis.asyncio.from_url") as from_url:
            assert await service.get("k") is None
            assert await service.set("k", "v") is True
        from_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_module_singleton_is_instance(self, module_service):
        assert isinstance(module_service, RedisCacheService)
