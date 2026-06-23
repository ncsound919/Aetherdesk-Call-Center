import os
import secrets
import time
from datetime import UTC

import structlog
from fastapi import Header, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

logger = structlog.get_logger()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    env = os.getenv("APP_ENV", "development")
    if env == "production":
        raise RuntimeError("JWT_SECRET environment variable must be set for production.")
    SECRET_KEY = "dev-jwt-secret-do-not-use-in-production"  # nosec B105 — dev fallback, never used in production
TOKEN_EXPIRY_SECONDS = 3600


class TokenStore:
    async def create_token(self, user_id: str, metadata: dict = None) -> str:
        token = secrets.token_urlsafe(32)
        token_data = {
            "user_id": user_id,
            "created_at": time.time(),
            "metadata": metadata or {}
        }
        import json

        from apps.api.main import redis_client
        if redis_client:
            await redis_client.setex(f"ws_token:{token}", TOKEN_EXPIRY_SECONDS, json.dumps(token_data))
        else:
            if not hasattr(self, "_fallback_tokens"):
                self._fallback_tokens = {}
            self.cleanup_expired()
            self._fallback_tokens[token] = token_data
        return token

    async def validate_token(self, token: str) -> dict | None:
        import json

        from apps.api.main import redis_client
        if redis_client:
            data = await redis_client.get(f"ws_token:{token}")
            if data:
                return json.loads(data)
            return None
        else:
            if not hasattr(self, "_fallback_tokens"):
                return None
            token_data = self._fallback_tokens.get(token)
            if token_data and time.time() - token_data["created_at"] <= TOKEN_EXPIRY_SECONDS:
                return token_data
            if token in self._fallback_tokens:
                del self._fallback_tokens[token]
            return None

    async def revoke_token(self, token: str):
        from apps.api.main import redis_client
        if redis_client:
            await redis_client.delete(f"ws_token:{token}")
        else:
            if hasattr(self, "_fallback_tokens") and token in self._fallback_tokens:
                del self._fallback_tokens[token]

    def cleanup_expired(self):
        if hasattr(self, "_fallback_tokens"):
            now = time.time()
            expired = [
                t for t, data in self._fallback_tokens.items()
                if now - data["created_at"] > TOKEN_EXPIRY_SECONDS
            ]
            for t in expired:
                del self._fallback_tokens[t]


token_store = TokenStore()


async def generate_websocket_token(user_id: str, metadata: dict = None) -> str:
    return await token_store.create_token(user_id, metadata)


def generate_access_token(data: dict, expires_delta_seconds: int = 3600) -> str:
    """Generate JWT access token signed with RS256."""
    from datetime import timedelta

    from apps.api.services.jwt_utils import create_access_token as _create_rs256_token
    return _create_rs256_token(data, timedelta(seconds=expires_delta_seconds))


_fallback_blocklist: set[str] = set()


async def verify_access_token(token: str) -> dict | None:
    """Verify JWT access token (supports RS256 and legacy HS256) and check blocklist."""
    from apps.api.services.jwt_utils import verify_access_token as _verify_rs256_token
    payload = _verify_rs256_token(token)
    if not payload:
        return None
    jti = payload.get("jti")
    if jti:
        from apps.api.main import redis_client
        if redis_client:
            is_blocked = await redis_client.get(f"jwt_blocklist:{jti}")
            if is_blocked:
                return None
        else:
            if jti in _fallback_blocklist:
                return None
    return payload


async def verify_websocket_token(token: str) -> dict | None:
    return await token_store.validate_token(token)


class WebSocketAuthMiddleware:
    def __init__(self, app, exclude_paths: list = None):
        self.app = app
        self.exclude_paths = exclude_paths or ["/api/v1/voice/incoming", "/health", "/"]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        for exclude in self.exclude_paths:
            if exclude == "/" and path == "/":
                await self.app(scope, receive, send)
                return
            elif exclude != "/" and path.startswith(exclude):
                await self.app(scope, receive, send)
                return

        query_params = scope.get("query_string", b"").decode()
        token = None

        # Prefer Authorization header (sec-websocket-protocol) over query string
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        # Fallback: query string (deprecated, kept for backward compat)
        if not token and "token=" in query_params:
            for param in query_params.split("&"):
                if param.startswith("token="):
                    token = param[6:]
                    break

        if not token:
            await self._reject(scope, receive, send, "Missing authentication token")
            return

        token_data = await verify_websocket_token(token)
        if not token_data:
            await self._reject(scope, receive, send, "Invalid or expired token")
            return

        scope["websocket_token_data"] = token_data
        await self.app(scope, receive, send)

    async def _reject(self, scope, receive, send, message: str):
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [[b"content-type", b"application/json"]],
        })
        await send({
            "type": "http.response.body",
            "body": b'{"error": "' + message.encode() + b'"}',
        })


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Verify JWT token and return user payload"""
    from apps.api.services.jwt_utils import verify_access_token as _verify_rs256_token
    payload = _verify_rs256_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")
if not INTERNAL_API_KEY:
    env = os.getenv("APP_ENV", "development")
    if env == "production":
        raise RuntimeError("INTERNAL_API_KEY environment variable must be set for production.")
    INTERNAL_API_KEY = "dev-api-key"

async def verify_api_key(x_api_key: str = Header(default=None)) -> str:
     """Verifies API key and returns tenant_id."""
     if not x_api_key:
         env = os.getenv("APP_ENV", "development")
         if env != "production":
             x_api_key = "dev-api-key"
         else:
             raise HTTPException(status_code=401, detail="API key required")
     if x_api_key == INTERNAL_API_KEY or (os.getenv("APP_ENV", "development") != "production" and x_api_key == "dev-api-key"):
         return "TENANT-001" # Default tenant for internal/dev

     from apps.api.services.database import get_tenant_by_api_key
     row = await get_tenant_by_api_key(x_api_key)
     if not row:
         raise HTTPException(status_code=403, detail="Invalid API Key")
     return row["id"]


async def verify_tenant_access(
    tenant_id: str,
    x_api_key: str = Header(default="dev-api-key"),
) -> str:
     """Validates that the requesting tenant's API key owns the target tenant_id.

     Prevents IDOR (Insecure Direct Object Reference) by ensuring the
     authenticated tenant can only access its own resources.

     Dev mode (ENV != production) bypasses this check for internal keys.
     """
     # Dev/internal key bypass - check FIRST before any DB calls
     is_dev = os.getenv("APP_ENV", "development") != "production"
     if x_api_key == INTERNAL_API_KEY or (is_dev and x_api_key == "dev-api-key"):
         return tenant_id  # Allow access in dev mode

     try:
         from apps.api.services.database import verify_tenant_api_key
         valid = await verify_tenant_api_key(tenant_id, x_api_key)
         if not valid:
             raise HTTPException(
                 status_code=403,
                 detail="Access denied: tenant does not own the requested resource",
             )
         return tenant_id
     except HTTPException:
         raise
     except Exception:
         # If DB fails in production-like mode, deny access
         raise HTTPException(
             status_code=403,
             detail="Access denied: tenant verification failed",
         ) from None
