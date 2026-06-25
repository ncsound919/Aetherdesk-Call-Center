from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.services.auth import get_current_user
from api.services.mfa import mfa_service

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])


class MFASetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    backup_codes: list[str]


class MFAVerifyRequest(BaseModel):
    code: str


class MFALoginRequest(BaseModel):
    session_token: str  # from password auth
    code: str


class MFASetupRequest(BaseModel):
    user_id: str
    user_email: str


class MFADisableRequest(BaseModel):
    pass


class MFABackupCodeRequest(BaseModel):
    code: str


@router.post("/setup", response_model=MFASetupResponse)
async def setup_mfa(token_data: dict = Depends(get_current_user)):
    """Initiate MFA enrollment — returns TOTP secret + backup codes."""
    user_id = token_data.get("sub")
    user_email = token_data.get("email")
    if not user_id or not user_email:
        raise HTTPException(status_code=400, detail="Missing user info in token")
    result = await mfa_service.setup_mfa(user_id, user_email)
    return MFASetupResponse(
        secret=result["secret"],
        otpauth_url=result["otpauth_url"],
        backup_codes=result["backup_codes"],
    )


@router.post("/verify")
async def verify_mfa_setup(request: MFAVerifyRequest, token_data: dict = Depends(get_current_user)):
    """Verify TOTP code to complete MFA enrollment."""
    user_id = token_data.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user info in token")
    valid = await mfa_service.verify_totp(user_id, request.code)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    result = await mfa_service.enable_mfa(user_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to enable MFA"))
    return {"message": "MFA enabled successfully"}


@router.post("/disable")
async def disable_mfa(token_data: dict = Depends(get_current_user)):
    """Disable MFA (requires password re-authentication)."""
    user_id = token_data.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user info in token")
    result = await mfa_service.disable_mfa(user_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to disable MFA"))
    return {"message": "MFA disabled successfully"}


@router.post("/login")
async def mfa_login(request: MFALoginRequest):
    """MFA step 2 — verify TOTP after password auth."""
    from api.services.auth import create_full_token
    from api.services.jwt_utils import verify_access_token as _verify_token

    payload = _verify_token(request.session_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    if not payload.get("mfa_pending"):
        raise HTTPException(status_code=400, detail="Token is not an MFA pending session")

    user_id = payload.get("sub")
    valid = await mfa_service.verify_totp(user_id, request.code)
    if not valid:
        # Also try backup code
        valid = await mfa_service.verify_backup_code(user_id, request.code)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    # Issue full token
    token = await create_full_token(
        user_id=user_id,
        tenant_id=payload.get("tenant_id", ""),
        email=payload.get("email", ""),
        role=payload.get("role", ""),
    )
    return {
        "token": token,
        "access_token": token,
        "token_type": "bearer",
        "tenantId": payload.get("tenant_id"),
        "userId": user_id,
        "role": payload.get("role"),
        "email": payload.get("email"),
    }


@router.post("/backup-code")
async def mfa_backup_code(request: MFABackupCodeRequest, token_data: dict = Depends(get_current_user)):
    """Login with backup code."""
    user_id = token_data.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user info in token")
    valid = await mfa_service.verify_backup_code(user_id, request.code)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid backup code")
    return {"message": "Backup code verified successfully"}


@router.get("/status")
async def mfa_status(token_data: dict = Depends(get_current_user)):
    """Check MFA enrollment status."""
    user_id = token_data.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user info in token")
    status = await mfa_service.get_mfa_status(user_id)
    return status
