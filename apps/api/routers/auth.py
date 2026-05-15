import os
import secrets
import structlog
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from apps.api.services.database import db_context
from apps.api.services.auth import generate_access_token, token_store, INTERNAL_API_KEY

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

# For dev mode - hardcoded admin credentials (never used in production)
# Passwords are configurable via environment variables
DEV_USERS_CONFIGURED = bool(os.getenv("DEV_USERS_CONFIGURED", "false").lower() == "true")

if DEV_USERS_CONFIGURED:
    DEV_USERS = {
        "admin@aetherdesk.com": {
            "password": os.environ["DEV_ADMIN_PASSWORD"],
            "tenant_id": "TENANT-001",
            "user_id": "USER-ADMIN-001",
            "role": "admin",
            "name": "Admin User"
        },
        "agent@aetherdesk.com": {
            "password": os.environ["DEV_AGENT_PASSWORD"],
            "tenant_id": "TENANT-001",
            "user_id": "USER-AGENT-001",
            "role": "agent",
            "name": "Test Agent"
        },
    }
else:
    DEV_USERS = {}


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    tenantId: str
    userId: str
    role: str
    name: str


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    """Login endpoint - validates credentials and returns JWT token.

    In dev mode, accepts hardcoded credentials. In production,
    validates against database users table.
    """
    email = credentials.email.strip().lower()
    password = credentials.password

    # Dev mode: check hardcoded users
    env = os.getenv("APP_ENV", "development")
    if env == "development" and DEV_USERS_CONFIGURED:
        user = DEV_USERS.get(email)
        if user and user["password"] == password:
            token = generate_access_token({
                "sub": user["user_id"],
                "tenant_id": user["tenant_id"],
                "email": email,
                "role": user["role"],
                "exp": datetime.now(timezone.utc) + timedelta(hours=24)
            })
            return LoginResponse(
                token=token,
                tenantId=user["tenant_id"],
                userId=user["user_id"],
                role=user["role"],
                name=user["name"]
            )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Production mode: validate against database
    with db_context() as conn:
        if not conn:
            raise HTTPException(status_code=503, detail="Database unavailable")

        row = conn.execute(
            "SELECT id, tenant_id, email, password_hash, role, display_name FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        # Verify password hash
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
            token=token,
            tenantId=row["tenant_id"],
            userId=row["id"],
            role=row["role"],
            name=row["display_name"] or row["email"]
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