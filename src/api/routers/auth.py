import logging
import os

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from api.services.auth import (
    create_mfa_session_token,
    generate_access_token,
    is_mfa_required,
)
from api.services.database import get_user_by_email_db

logger = structlog.get_logger()
_auth_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

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
if os.getenv("ENABLE_DEV_USERS", "false").lower() == "true":
    _auth_logger.warning(
        "DEV_USERS are active (ENABLE_DEV_USERS=true). "
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


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    company_name: str | None = None


class RegisterResponse(BaseModel):
    message: str
    user_id: str
    verification_token: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    """Login endpoint — validates credentials and returns JWT token."""
    email = credentials.email.strip().lower()
    password = credentials.password

    enable_dev_users = os.getenv("ENABLE_DEV_USERS", "false").lower() == "true"

    # Dev mode: check hardcoded users
    if enable_dev_users:
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
                token_type="bearer",  # nosec B106 — OAuth2 standard token type, not a password
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
        raise HTTPException(status_code=503, detail="Database unavailable") from e

    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    from api.services.auth import verify_password
    if not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check if MFA is required for this user
    user_id = row["id"]
    mfa_enabled = await is_mfa_required(user_id)
    if mfa_enabled:
        # Return temporary token with mfa_pending flag
        temp_token = await create_mfa_session_token(user_id, row["tenant_id"], row["email"], row["role"])
        return {
            "mfa_required": True,
            "temp_token": temp_token,
            "message": "MFA verification required"
        }

    # If MFA not required, proceed normally with full token
    token = generate_access_token({
        "sub": row["id"],
        "tenant_id": row["tenant_id"],
        "email": row["email"],
        "role": row["role"],
    })

    return LoginResponse(
        access_token=token,
        token_type="bearer",  # nosec B106 — OAuth2 standard token type
        token=token,
        tenantId=row["tenant_id"],
        userId=row["id"],
        role=row["role"],
        name=row.get("display_name") or row["email"],
    )


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))):
    """Logout endpoint - invalidates JWT token."""
    if credentials:
        token = credentials.credentials
        from api.services.auth import verify_access_token
        payload = await verify_access_token(token)
        if payload:
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                import time

                from api.main import redis_client
                ttl = int(exp - time.time())
                if ttl > 0:
                    if redis_client:
                        await redis_client.setex(f"jwt_blocklist:{jti}", ttl, "1")
                    else:
                        from api.services.auth import _fallback_blocklist
                        _fallback_blocklist.add(jti)
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))):
    """Get current user info from JWT token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="No token provided")

    from api.services.auth import verify_access_token
    payload = await verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "userId": payload.get("sub"),
        "tenantId": payload.get("tenant_id"),
        "email": payload.get("email"),
        "role": payload.get("role"),
    }


@router.post("/register", response_model=RegisterResponse)
async def register(credentials: RegisterRequest):
    """Register a new user account."""
    from api.services.db_tenants import (
        create_tenant,
        create_user_db,
        get_user_by_email_db,
    )

    # Check if user already exists
    existing = await get_user_by_email_db(credentials.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate password strength
    if len(credentials.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Hash password
    from api.services.auth import get_password_hash
    password_hash = get_password_hash(credentials.password)

    # Create tenant if company name provided
    tenant_id = None
    if credentials.company_name:
        tenant = await create_tenant(
            name=credentials.company_name,
            email=credentials.email,
            slug=credentials.company_name.lower().replace(" ", "-").replace("'", "")[:50]
        )
        tenant_id = tenant["id"]

    # Create user
    result = await create_user_db(
        email=credentials.email,
        password_hash=password_hash,
        full_name=credentials.full_name,
        tenant_id=tenant_id,
        role="owner"
    )

    logger.info("user_registered", user_id=result["id"], email=credentials.email)

    return RegisterResponse(
        message="Account created. Please check your email to verify your account.",
        user_id=result["id"],
        verification_token=result["verification_token"]
    )


@router.post("/verify-email")
async def verify_email(credentials: VerifyEmailRequest):
    """Verify email address with token."""
    from api.services.db_tenants import verify_user_email_db

    user_id = await verify_user_email_db(credentials.token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    logger.info("email_verified", user_id=user_id)
    return {"message": "Email verified successfully"}


@router.post("/forgot-password")
async def forgot_password(credentials: ForgotPasswordRequest):
    """Request password reset email."""
    from api.services.db_tenants import set_password_reset_token_db

    user_id, token = await set_password_reset_token_db(credentials.email)
    if user_id:
        logger.info("password_reset_requested", user_id=user_id)
        response = {"message": "If the email exists, a reset link has been sent."}
        if os.getenv("APP_ENV", "development") != "production":
            response["dev_token"] = token
        return response
    return {"message": "If the email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(credentials: ResetPasswordRequest):
    """Reset password with token."""
    from api.services.auth import get_password_hash
    from api.services.db_tenants import reset_password_db

    new_hash = get_password_hash(credentials.new_password)
    user_id = await reset_password_db(credentials.token, new_hash)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    logger.info("password_reset_completed", user_id=user_id)
    return {"message": "Password reset successfully"}
