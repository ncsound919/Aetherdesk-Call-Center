import time
from collections import defaultdict

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from api.services.db_reliability import get_rate_limit_config_db

logger = structlog.get_logger()


class PerTenantRateLimiter:
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._local_store = defaultdict(lambda: defaultdict(list))
        self._local_configs = defaultdict(dict)

    async def check_limit(self, tenant_id: str, route_key: str, max_requests: int = 100, window_seconds: int = 60) -> dict:
        config = await self._get_config(tenant_id, route_key)
        if config:
            max_requests = config["max_requests"]
            window_seconds = config["window_seconds"]

        now = time.time()
        window_start = now - window_seconds

        if self.redis:
            key = f"ratelimit:{tenant_id}:{route_key}"
            try:
                async with self.redis.pipeline(transaction=True) as pipe:
                    await pipe.zremrangebyscore(key, 0, window_start)
                    await pipe.zcard(key)
                    results = await pipe.execute()
                    count = results[1]
                    await pipe.zadd(key, {str(now): now})
                    await pipe.expire(key, window_seconds + 10)
                    await pipe.execute()
            except Exception as e:
                logger.warning("redis_rate_limit_failed", error=str(e))
                return {"allowed": True, "remaining": 1, "reset_in": 0, "total": max_requests}
        else:
            tenant_store = self._local_store[tenant_id]
            timestamps = tenant_store.get(route_key, [])
            timestamps = [t for t in timestamps if t > window_start]
            count = len(timestamps)
            timestamps.append(now)
            tenant_store[route_key] = timestamps

        allowed = count < max_requests
        remaining = max(0, max_requests - count - 1)
        reset_in = max(0, int(window_seconds - (now - window_start)))

        if not allowed:
            logger.warning("rate_limit_exceeded", tenant_id=tenant_id, route=route_key, count=count)

        return {
            "allowed": allowed,
            "remaining": remaining,
            "reset_in": reset_in,
            "total": max_requests,
            "tenant_id": tenant_id,
            "route_key": route_key,
        }

    async def _get_config(self, tenant_id: str, route_key: str) -> dict | None:
        cached = self._local_configs.get(tenant_id, {}).get(route_key)
        if cached:
            return cached
        try:
            config = await get_rate_limit_config_db(tenant_id, route_key)
            if config:
                self._local_configs[tenant_id][route_key] = config
                return config
        except Exception:
            pass
        return None

    async def get_limits(self, tenant_id: str) -> list[dict]:
        from api.services.db_reliability import list_rate_limit_configs_db
        try:
            return await list_rate_limit_configs_db(tenant_id)
        except Exception:
            return []

    async def set_limits(self, tenant_id: str, route_key: str, max_requests: int, window_seconds: int):
        from api.services.db_reliability import set_rate_limit_config_db
        result = await set_rate_limit_config_db(tenant_id, route_key, max_requests, window_seconds)
        self._local_configs[tenant_id][route_key] = result
        return result

    async def get_all_limits(self) -> list[dict]:
        from api.services.db_reliability import list_rate_limit_configs_db
        try:
            return await list_rate_limit_configs_db()
        except Exception:
            return []


rate_limiter = PerTenantRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        tenant_id = getattr(request.state, "tenant_id", None) or request.query_params.get("tenant_id")
        if not tenant_id:
            return await call_next(request)

        route_key = request.url.path

        result = await rate_limiter.check_limit(tenant_id, route_key)
        if not result["allowed"]:
            logger.warning("rate_limit_blocked", tenant_id=tenant_id, route=route_key)
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": "Rate limit exceeded",
                    "retry_after": result["reset_in"],
                    "code": "rate_limited",
                },
                headers={
                    "X-RateLimit-Limit": str(result["total"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result["reset_in"]),
                    "Retry-After": str(result["reset_in"]),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result["total"])
        response.headers["X-RateLimit-Remaining"] = str(result["remaining"])
        response.headers["X-RateLimit-Reset"] = str(result["reset_in"])
        return response
