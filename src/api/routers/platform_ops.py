import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.services.auth import verify_tenant_access
from api.services.self_serve import self_serve_service
from api.services.white_label import white_label_service

logger = structlog.get_logger()

router = APIRouter(prefix="/platform", tags=["platform"])


# ── Pydantic Models ───────────────────────────────────────────────

class BrandingConfig(BaseModel):
    company_name: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    favicon_url: str | None = None


class DomainConfig(BaseModel):
    domain: str
    ssl_status: str = "pending"


class SignupRequest(BaseModel):
    email: str
    company_name: str
    password: str


class CompleteStepRequest(BaseModel):
    step: str


class ProvisionNumberRequest(BaseModel):
    area_code: str


# ── White-Label Endpoints ─────────────────────────────────────────

@router.get("/branding")
async def get_branding(tenant_id: str = Depends(verify_tenant_access)):
    return await white_label_service.get_branding(tenant_id)


@router.put("/branding")
async def update_branding(
    data: BrandingConfig,
    tenant_id: str = Depends(verify_tenant_access),
):
    config = {k: v for k, v in data.model_dump().items() if v is not None}
    result = await white_label_service.set_branding(tenant_id, config)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to update branding")
    return result


@router.get("/domain")
async def get_domain(tenant_id: str = Depends(verify_tenant_access)):
    domain = await white_label_service.get_custom_domain(tenant_id)
    if not domain:
        return {"tenant_id": tenant_id, "domain": None, "ssl_status": None, "verified": False}
    return {
        "tenant_id": tenant_id,
        "domain": domain.get("domain"),
        "ssl_status": domain.get("ssl_status", "pending"),
        "verified": bool(domain.get("verified", False)),
    }


@router.put("/domain")
async def set_domain(
    data: DomainConfig,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await white_label_service.set_custom_domain(tenant_id, data.domain, data.ssl_status)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to set custom domain")
    return result


@router.post("/domain/verify")
async def verify_domain(
    domain: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await white_label_service.verify_domain(tenant_id, domain)


# ── Self-Serve Onboarding Endpoints ───────────────────────────────

@router.post("/signup")
async def signup(data: SignupRequest):
    result = await self_serve_service.create_trial_tenant(data.email, data.company_name, data.password)
    from api.services.security_guard import mask_email
    logger.info("self_serve_signup", email=mask_email(data.email), company=data.company_name)
    return result


@router.get("/onboarding/status")
async def get_onboarding_status(tenant_id: str = Depends(verify_tenant_access)):
    return await self_serve_service.get_onboarding_status(tenant_id)


@router.post("/onboarding/step")
async def complete_onboarding_step(
    data: CompleteStepRequest,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await self_serve_service.complete_step(tenant_id, data.step)


@router.get("/onboarding/quickstart")
async def get_quickstart(tenant_id: str = Depends(verify_tenant_access)):
    return await self_serve_service.get_quickstart_guide(tenant_id)


@router.post("/provision/number")
async def provision_number(
    data: ProvisionNumberRequest,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await self_serve_service.provision_phone_number(tenant_id, data.area_code)


@router.get("/setup/progress")
async def get_setup_progress(tenant_id: str = Depends(verify_tenant_access)):
    return await self_serve_service.get_setup_progress(tenant_id)


@router.post("/health-check")
async def run_health_check(tenant_id: str = Depends(verify_tenant_access)):
    return await self_serve_service.run_health_check(tenant_id)
