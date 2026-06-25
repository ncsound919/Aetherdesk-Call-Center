import asyncio
import time
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger()


class RedisCacheService:
    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url
        self._redis = None
        self._local: dict[str, bytes] = {}
        self._local_expiry: dict[str, float] = {}
        self._hits = 0
        self._misses = 0
        self._local_max_size = 1000

    async def _ensure_redis(self):
        if self._redis is None and self.redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
                await self._redis.ping()
                logger.info("redis_cache_connected")
            except Exception as e:
                logger.warning("redis_cache_connection_failed, using in-memory fallback", error=str(e))
                self._redis = False

    async def get(self, key: str) -> Any | None:
        await self._ensure_redis()
        if self._redis and self._redis is not False:
            try:
                val = await self._redis.get(key)
                if val is not None:
                    self._hits += 1
                    return val
                self._misses += 1
                return None
            except Exception as e:
                logger.warning("redis_get_failed, falling back to local", error=str(e))

        now = time.time()
        if key in self._local:
            if self._local_expiry.get(key, 0) > now:
                self._hits += 1
                return self._local[key]
            else:
                del self._local[key]
                self._local_expiry.pop(key, None)
        self._misses += 1
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        await self._ensure_redis()
        if self._redis and self._redis is not False:
            try:
                await self._redis.setex(key, ttl, value)
                return True
            except Exception as e:
                logger.warning("redis_set_failed, falling back to local", error=str(e))

        self._local[key] = value
        self._local_expiry[key] = time.time() + ttl

        if len(self._local) > self._local_max_size:
            oldest = min(self._local_expiry.keys(), key=lambda k: self._local_expiry.get(k, 0))
            self._local.pop(oldest, None)
            self._local_expiry.pop(oldest, None)

        return True

    async def delete(self, key: str) -> bool:
        await self._ensure_redis()
        if self._redis and self._redis is not False:
            try:
                await self._redis.delete(key)
                return True
            except Exception as e:
                logger.warning("redis_delete_failed", error=str(e))

        self._local.pop(key, None)
        self._local_expiry.pop(key, None)
        return True

    async def get_stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = round((self._hits / total * 100), 2) if total > 0 else 0.0
        miss_rate = round((self._misses / total * 100), 2) if total > 0 else 0.0

        stats = {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": hit_rate,
            "miss_rate_pct": miss_rate,
            "total_requests": total,
            "local_cache_size": len(self._local),
        }

        if self._redis and self._redis is not False:
            try:
                info = await self._redis.info("memory")
                stats["redis_memory_used_bytes"] = info.get("used_memory", 0)
                stats["redis_memory_peak_bytes"] = info.get("used_memory_peak", 0)
                stats["redis_keys"] = await self._redis.dbsize()
            except Exception:
                stats["redis_connected"] = True
        else:
            import sys
            local_size = sum(sys.getsizeof(v) for v in self._local.values()) if self._local else 0
            stats["local_memory_used_bytes"] = local_size

        return stats

    async def warm(self, key: str, data_func: Callable, ttl: int = 300) -> Any:
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = data_func() if not asyncio.iscoroutinefunction(data_func) else await data_func()
        await self.set(key, value, ttl)
        return value

    async def clear(self) -> bool:
        await self._ensure_redis()
        if self._redis and self._redis is not False:
            try:
                await self._redis.flushdb()
                return True
            except Exception as e:
                logger.warning("redis_clear_failed", error=str(e))
        self._local.clear()
        self._local_expiry.clear()
        self._hits = 0
        self._misses = 0
        return True


redis_cache_service = RedisCacheService()
