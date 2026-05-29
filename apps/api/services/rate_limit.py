import os
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
        # Apply rate limiting to all endpoints except static files and health checks
        if any(skip in request.url.path for skip in ["/static/", "/docs", "/redoc", "/metrics"]):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        self._clean_old_requests(client_ip)

        # For development/testing, disable rate limiting or set a very high limit
        app_env = os.getenv("APP_ENV", "production")
        if app_env in ("development", "test"):
            max_req = 10000 # Effectively disable rate limiting
        elif "/auth/" in request.url.path or "/login" in request.url.path:
            rate_limit_env = os.getenv("AUTH_RATE_LIMIT", "10")
            max_req = int(rate_limit_env)  # 10 per window by default; increase for testing
        else:
            max_req = self.max_connections

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
