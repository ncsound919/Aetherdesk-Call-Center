import hashlib
import hmac
import json
import logging
import os
import secrets
import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from api.services.auth import (
    create_mfa_session_token,
    generate_access_token,
    is_mfa_required,
)
from api.services.database import get_user_by_email_db

logger = structlog.get_logger()
_auth_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Dev mode credentials — only active when ENABLE_DEV_USERS=true AND APP_ENV != production.
# Passwords MUST be supplied explicitly via DEV_ADMIN_PASSWORD / DEV_AGENT_PASSWORD;
# there are no hardcoded fallback passwords. If a password isn't configured, that
# dev account is disabled.
_dev_admin_password = os.getenv("DEV_ADMIN_PASSWORD")
_dev_agent_password = os.getenv("DEV_AGENT_PASSWORD")

DEV_USERS = {}
if _dev_admin_password:
    DEV_USERS["admin@aetherdesk.com"] = {
        "password": _dev_admin_password,
        "tenant_id": "TENANT-001",
        "user_id": "USER-ADMIN-001",
        "role": "admin",
        "name": "Admin User",
    }
if _dev_agent_password:
    DEV_USERS["agent@aetherdesk.com"] = {
        "password": _dev_agent_password,
        "tenant_id": "TENANT-001",
        "user_id": "USER-AGENT-001",
        "role": "agent",
        "name": "Test Agent",
    }


def _dev_users_enabled() -> bool:
    """Dev users are only ever enabled outside production, and only when
    explicitly requested via ENABLE_DEV_USERS with a configured password."""
    if os.getenv("APP_ENV", "development") == "production":
        return False
    return os.getenv("ENABLE_DEV_USERS", "false").lower() == "true"


# Startup warning — log once at import time
if _dev_users_enabled():
    if not DEV_USERS:
        _auth_logger.warning(
            "ENABLE_DEV_USERS=true but no DEV_ADMIN_PASSWORD/DEV_AGENT_PASSWORD "
            "configured; no dev accounts will be available."
        )
    else:
        _auth_logger.warning(
            "DEV_USERS are active (ENABLE_DEV_USERS=true). "
            "These accounts (admin@aetherdesk.com, agent@aetherdesk.com) "
            "must NEVER be reachable in production."
        )
elif os.getenv("ENABLE_DEV_USERS", "false").lower() == "true":
    _auth_logger.error(
        "ENABLE_DEV_USERS=true was set but APP_ENV=production; dev users "
        "are forcibly disabled in production."
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

    enable_dev_users = _dev_users_enabled()

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

    from api.services.security_guard import mask_email
    logger.info("user_registered", user_id=result["id"], email=mask_email(credentials.email))

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


# ── Overlay 365 Unified Auth ─────────────────────────────────────
# Shared token generation/validation used by BlockLabor, Jobclaw,
# AgentBrowser and any other Overlay service via overlay-365-shared/auth.js.

OVERLAY_MASTER_KEY = os.getenv("OVERLAY_MASTER_KEY", "")
if not OVERLAY_MASTER_KEY:
    _auth_logger.warning(
        "OVERLAY_MASTER_KEY is not set; Overlay 365 token endpoints "
        "(/v1/auth/token, /v1/auth/validate) will reject all requests "
        "with 503 until it is configured."
    )


class OverlayTokenRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=254)
    tier: str = Field(default="worker")
    services: list[str] = Field(default_factory=lambda: ["aetherdesk", "jobclaw", "blocklabor", "agent-browser"])
    expires_in: int = Field(default=86400 * 30, ge=60, le=86400 * 365)


class OverlayValidateRequest(BaseModel):
    pass  # Token is passed via Authorization header


def _sign_overlay_token(payload: dict, secret: str) -> str:
    """HMAC-SHA256 signed JWT-like token (compact, no dependency on PyJWT)."""
    header = {"alg": "HS256", "typ": "OVERLAY"}
    body = base64url_encode(json.dumps(header)) + "." + base64url_encode(json.dumps(payload))
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + sig


def base64url_encode(data: str) -> str:
    import base64
    return base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()


def _verify_overlay_token(token: str, secret: str) -> dict | None:
    """Verify HMAC-SHA256 signed overlay token. Returns payload or None."""
    import base64
    import binascii

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        body, sig = parts[0] + "." + parts[1], parts[2]
        expected_sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        # Decode payload
        payload_b64 = parts[1]
        # Add padding
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        # Check expiry
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError) as e:
        # Malformed token content after signature check passed — treat as invalid.
        logger.debug("overlay_token_malformed", error=str(e))
        return None
    except Exception as e:
        # Unexpected error — log for visibility but still deny the token.
        logger.error("overlay_token_verify_unexpected_error", error=str(e))
        return None


@router.post("/v1/auth/token")
async def generate_overlay_token(
    request: Request,
    payload: OverlayTokenRequest,
    authorization: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    """Generate a unified Overlay 365 auth token.
    Called by overlay-365-shared/auth.js -> generateOverlayToken().
    Requires OVERLAY_MASTER_KEY in Authorization header.
    """
    if not OVERLAY_MASTER_KEY:
        raise HTTPException(status_code=503, detail="OVERLAY_MASTER_KEY not configured on server")

    # Verify master key
    provided_key = authorization.credentials
    if not hmac.compare_digest(provided_key, OVERLAY_MASTER_KEY):
        raise HTTPException(status_code=401, detail="Invalid master key")

    if payload.tier not in ("worker", "business", "admin"):
        raise HTTPException(status_code=400, detail=f"Invalid tier: {payload.tier}")

    now = time.time()
    token_payload = {
        "sub": payload.user_id,
        "email": payload.email,
        "tier": payload.tier,
        "services": payload.services,
        "iat": now,
        "exp": now + payload.expires_in,
        "iss": "overlay365",
    }

    token = _sign_overlay_token(token_payload, OVERLAY_MASTER_KEY)

    logger.info("overlay_token_generated", user_id=payload.user_id, tier=payload.tier)

    return {
        "access_token": token,
        "token_type": "overlay",
        "expires_in": payload.expires_in,
        "user_id": payload.user_id,
        "tier": payload.tier,
        "services": payload.services,
    }


@router.post("/v1/auth/validate")
async def validate_overlay_token(
    request: Request,
    authorization: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    """Validate an Overlay 365 token.
    Called by overlay-365-shared/auth.js -> validateOverlayToken().
    """
    if not OVERLAY_MASTER_KEY:
        raise HTTPException(status_code=503, detail="OVERLAY_MASTER_KEY not configured")

    token = authorization.credentials
    payload = _verify_overlay_token(token, OVERLAY_MASTER_KEY)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "valid": True,
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "tier": payload.get("tier"),
        "services": payload.get("services", []),
        "expires_at": payload.get("exp"),
        "issued_at": payload.get("iat"),
    }
