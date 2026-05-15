import os
import secrets
import time

import structlog
from fastapi import Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.services.database import db_context

logger = structlog.get_logger()

SECRET_KEY = os.getenv("JWT_SECRET", "your-jwt-secret-key")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET environment variable must be set.")
TOKEN_EXPIRY_SECONDS = 3600


class TokenStore:
    def __init__(self):
        self._tokens: dict[str, dict] = {}

    def create_token(self, user_id: str, metadata: dict = None) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = {
            "user_id": user_id,
            "created_at": time.time(),
            "metadata": metadata or {}
        }
        return token

    def validate_token(self, token: str) -> dict | None:
        if token not in self._tokens:
            return None

        token_data = self._tokens[token]
        if time.time() - token_data["created_at"] > TOKEN_EXPIRY_SECONDS:
            del self._tokens[token]
            return None

        return token_data

    def revoke_token(self, token: str):
        if token in self._tokens:
            del self._tokens[token]

    def cleanup_expired(self):
        now = time.time()
        expired = [
            t for t, data in self._tokens.items()
            if now - data["created_at"] > TOKEN_EXPIRY_SECONDS
        ]
        for t in expired:
            del self._tokens[t]


token_store = TokenStore()


def generate_websocket_token(user_id: str, metadata: dict = None) -> str:
    return token_store.create_token(user_id, metadata)


def generate_access_token(data: dict, expires_delta_seconds: int = 3600) -> str:
    """Generate JWT access token (for API authentication)."""
    import jwt
    from datetime import datetime, timezone, timedelta
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(seconds=expires_delta_seconds)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")


async def verify_access_token(token: str) -> dict | None:
    """Verify JWT access token."""
    import jwt
    from datetime import datetime, timezone
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("exp", 0) < datetime.now(timezone.utc).timestamp():
            return None
        return payload
    except jwt.InvalidTokenError:
        return None


async def verify_websocket_token(token: str) -> dict | None:
    return token_store.validate_token(token)


class WebSocketAuthMiddleware:
    def __init__(self, app, exclude_paths: list = None):
        self.app = app
        self.exclude_paths = exclude_paths or ["/api/v1/voice/incoming", "/health", "/"]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if any(path.startswith(exclude) for exclude in self.exclude_paths):
            await self.app(scope, receive, send)
            return

        query_params = scope.get("query_string", b"").decode()
        token = None

        if "token=" in query_params:
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


security = HTTPBearer(auto_error=False)


async def get_optional_token(credentials: HTTPAuthorizationCredentials = None) -> str | None:
    if credentials:
        return credentials.credentials
    return None

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev-api-key")

async def verify_api_key(x_api_key: str = Header(default="dev-api-key")) -> str:
     """Verifies API key and returns tenant_id."""
     # Check internal key first
     if x_api_key == INTERNAL_API_KEY or (os.getenv("ENV") != "production" and x_api_key == "dev-api-key"):
         return "TENANT-001" # Default tenant for internal/dev

     # Use synchronous db_context since SQLite connections are sync
     from apps.api.services.database import db_context_sync
     with db_context_sync() as conn:
         cursor = conn.cursor()
         cursor.execute("SELECT id FROM tenants WHERE api_key = ?", (x_api_key,))
         row = cursor.fetchone()
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
     is_dev = os.getenv("ENV", "development") != "production"
     if x_api_key == INTERNAL_API_KEY or (is_dev and x_api_key == "dev-api-key"):
         return tenant_id  # Allow access in dev mode

     try:
         # Use synchronous db_context since SQLite connections are sync
         from apps.api.services.database import db_context_sync
         with db_context_sync() as conn:
             cursor = conn.cursor()
             # Verify the API key maps to a tenant, and that tenant matches the requested tenant_id
             cursor.execute(
                 "SELECT id FROM tenants WHERE api_key = ? AND id = ?",
                 (x_api_key, tenant_id),
             )
             row = cursor.fetchone()
             if not row:
                 raise HTTPException(
                     status_code=403,
                     detail="Access denied: tenant does not own the requested resource",
                 )
             return row["id"]
     except HTTPException:
         raise
     except Exception:
         # If DB fails in production-like mode, deny access
         raise HTTPException(
             status_code=403,
             detail="Access denied: tenant verification failed",
         )
