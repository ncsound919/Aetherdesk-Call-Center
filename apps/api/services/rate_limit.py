import os
import time

import structlog
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()

MAX_CONNECTIONS = 100
WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app=None, max_connections: int = MAX_CONNECTIONS, window: int = WINDOW_SECONDS):
        super().__init__(app)
        self.max_connections = max_connections
        self.window = window
        self.requests: dict[str, list] = {}
        self._redis = None

    def _get_redis(self):
        if self._redis is not None:
            return self._redis
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return None
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(redis_url, decode_responses=True)
            return self._redis
        except Exception:
            return None

    async def _is_rate_limited_redis(self, key: str, max_req: int) -> bool:
        r = self._get_redis()
        if not r:
            return False
        try:
            now = time.time()
            window_start = now - self.window
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, self.window)
            results = await pipe.execute()
            current_count = results[2]
            return current_count > max_req
        except Exception:
            return False

    async def _record_request_redis(self, key: str):
        r = self._get_redis()
        if not r:
            return
        try:
            now = time.time()
            await r.zadd(key, {str(now): now})
            await r.expire(key, self.window)
        except Exception:
            pass

    def _clean_old_requests(self, key: str):
        now = time.time()
        self.requests[key] = [
            ts for ts in self.requests.get(key, [])
            if now - ts < self.window
        ]
        if not self.requests[key]:
            self.requests.pop(key, None)
        if len(self.requests) > 10000:
            stale_keys = [k for k, v in self.requests.items() if not v or all(now - ts >= self.window for ts in v)]
            for k in stale_keys:
                self.requests.pop(k, None)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        if any(skip in request.url.path for skip in ["/static/", "/docs", "/redoc", "/metrics", "/health"]):
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        app_env = os.getenv("APP_ENV", "production")
        if app_env in ("development", "test"):
            max_req = 10000
        elif "/auth/" in request.url.path or "/login" in request.url.path:
            rate_limit_env = os.getenv("AUTH_RATE_LIMIT", "10")
            max_req = int(rate_limit_env)
        else:
            max_req = self.max_connections

        redis_key = f"rate_limit:{client_ip}"

        # Try Redis-backed rate limiting first
        r = self._get_redis()
        if r:
            try:
                if await self._is_rate_limited_redis(redis_key, max_req):
                    logger.warning("rate_limit_exceeded", client_ip=client_ip)
                    raise HTTPException(status_code=429, detail="Too Many Requests")
                await self._record_request_redis(redis_key)
                return await call_next(request)
            except HTTPException:
                raise
            except Exception:
                pass  # Fall back to in-memory

        # Fallback: in-memory rate limiting
        self._clean_old_requests(client_ip)
        if len(self.requests.get(client_ip, [])) >= max_req:
            logger.warning("rate_limit_exceeded", client_ip=client_ip)
            raise HTTPException(status_code=429, detail="Too Many Requests")

        self.requests.setdefault(client_ip, []).append(time.time())
        return await call_next(request)


class VoiceConnectionTracker:
    def __init__(self, max_concurrent: int = 50):
        self.max_concurrent = max_concurrent
        self.active_calls: dict[str, float] = {}

    def can_accept_call(self) -> bool:
        self._cleanup()
        return len(self.active_calls) < self.max_concurrent

    def add_call(self, call_id: str):
        self.active_calls[call_id] = time.time()

    def remove_call(self, call_id: str):
        if call_id in self.active_calls:
            del self.active_calls[call_id]

    def _cleanup(self):
        now = time.time()
        expired = [
            cid for cid, ts in self.active_calls.items()
            if now - ts > 3600
        ]
        for cid in expired:
            del self.active_calls[cid]


rate_limiter = RateLimitMiddleware()

def reset_rate_limiter():
    """Clear all tracked requests (used in testing)."""
    rate_limiter.requests.clear()


