"""RBAC middleware for FastAPI.

Enforces role-based access control on all routes. Extracts the user role
from the JWT token and checks permissions via Casbin.

Skips: public endpoints (health, login, docs), internal API key auth.
"""

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = structlog.get_logger()

# Endpoints that bypass RBAC (public or use different auth)
_SKIP_PATHS = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/",
}

_SKIP_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/forgot-password",
    "/api/v1/voice/incoming",
    "/webhooks/",
)


# Map HTTP methods to Casbin actions
_METHOD_ACTION_MAP = {
    "GET": "read",
    "HEAD": "read",
    "OPTIONS": "read",
    "POST": "write",
    "PUT": "write",
    "PATCH": "write",
    "DELETE": "delete",
}

# Map URL path segments to Casbin resources
_RESOURCE_MAP = {
    "agents": "agents",
    "calls": "calls",
    "scripts": "scripts",
    "billing": "billing",
    "analytics": "analytics",
    "leads": "leads",
    "tenants": "tenants",
    "voice": "calls",
    "usage": "analytics",
    "health": "health",
}


class RBACMiddleware(BaseHTTPMiddleware):
    """Enforce Casbin RBAC on every request."""

    def __init__(self, app, exclude_paths: list[str] | None = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or []

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip public paths
        if path in _SKIP_PATHS:
            return await call_next(request)

        for prefix in _SKIP_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Skip custom exclusions
        for exc in self.exclude_paths:
            if path.startswith(exc):
                return await call_next(request)

        # Extract role from request state (set by auth middleware)
        user_role = getattr(request.state, "user_role", None)
        if not user_role:
            # No role set — fall through to auth middleware
            return await call_next(request)

        # Skip internal API key auth (dev mode)
        if user_role == "internal":
            return await call_next(request)

        # Determine resource and action
        resource = _resolve_resource(path)
        action = _METHOD_ACTION_MAP.get(request.method, "read")

        # Check permission
        from api.services.authorization import check_permission

        if not check_permission(user_role, resource, action):
            logger.warning(
                "rbac_access_denied",
                role=user_role,
                resource=resource,
                action=action,
                path=path,
                method=request.method,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "Insufficient permissions",
                    "code": "forbidden",
                    "required": f"{resource}:{action}",
                },
            )

        return await call_next(request)


def _resolve_resource(path: str) -> str:
    """Extract the Casbin resource name from the URL path."""
    # /api/v1/agents/xxx → agents
    # /api/v1/calls/xxx → calls
    parts = path.strip("/").split("/")

    # Skip 'api' and version prefix
    idx = 0
    for i, part in enumerate(parts):
        if part.startswith("v") and part[1:].isdigit():
            idx = i + 1
            break
        if part == "api":
            continue

    if idx < len(parts):
        segment = parts[idx]
        if not segment:
            return "root"
        return _RESOURCE_MAP.get(segment, segment)

    return "root"
