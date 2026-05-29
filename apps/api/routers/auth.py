import os
import structlog
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from apps.api.services.database import get_user_by_email_db
from apps.api.services.auth import generate_access_token, token_store

logger = structlog.get_logger()
_auth_logger = logging.getLogger(__name__)

router = APIRouter()

# Dev mode credentials — only active when APP_ENV=development
# Override via DEV_ADMIN_PASSWORD / DEV_AGENT_PASSWORD env vars
DEV_USERS = {
    "admin@aetherdesk.com": {
        "password": os.getenv("DEV_ADMIN_PASSWORD", "admin123"),
        "tenant_id": "TENANT-001",
        "user_id": "USER-ADMIN-001",
        "role": "admin",
        "name": "Admin User",
    },
    "agent@aetherdesk.com": {
        "password": os.getenv("DEV_AGENT_PASSWORD", "agent123"),
        "tenant_id": "TENANT-001",
        "user_id": "USER-AGENT-001",
        "role": "agent",
        "name": "Test Agent",
    },
    }

# Startup warning — log once at import time
if os.getenv("APP_ENV", "development") == "development":
    _auth_logger.warning(
        "DEV_USERS are active (APP_ENV=development). "
        "These accounts (admin@aetherdesk.com, agent@aetherdesk.com) "
        "must NEVER be reachable in production."
    )


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    # OAuth2-compatible fields (used by frontend and E2E tests)
    access_token: str
    token_type: str = "bearer"
    # Legacy fields (kept for backward compatibility)
    token: str
    tenantId: str
    userId: str
    role: str
    name: str


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    """Login endpoint — validates credentials and returns JWT token."""
    email = credentials.email.strip().lower()
    password = credentials.password

    env = os.getenv("APP_ENV", "development")

    # Dev mode: check hardcoded users
    if env == "development":
        user = DEV_USERS.get(email)
        if user and user["password"] == password:
            token = generate_access_token({
                "sub": user["user_id"],
                "tenant_id": user["tenant_id"],
                "email": email,
                "role": user["role"],
            })
            return LoginResponse(
                access_token=token,
                token_type="bearer",
                token=token,
                tenantId=user["tenant_id"],
                userId=user["user_id"],
                role=user["role"],
                name=user["name"],
            )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Production mode: validate against database
    try:
        row = await get_user_by_email_db(email)
    except Exception as e:
        logger.error("login_db_error", error=str(e))
        raise HTTPException(status_code=503, detail="Database unavailable")

    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    from apps.api.services.auth import verify_password
    if not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = generate_access_token({
        "sub": row["id"],
        "tenant_id": row["tenant_id"],
        "email": row["email"],
        "role": row["role"],
    })

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        token=token,
        tenantId=row["tenant_id"],
        userId=row["id"],
        role=row["role"],
        name=row.get("display_name") or row["email"],
    )


@router.post("/logout")
async def logout():
    """Logout endpoint - clears session."""
    # Client-side: remove localStorage token
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))):
    """Get current user info from JWT token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="No token provided")

    from apps.api.services.auth import verify_access_token
    payload = await verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "userId": payload.get("sub"),
        "tenantId": payload.get("tenant_id"),
        "email": payload.get("email"),
        "role": payload.get("role"),
    }