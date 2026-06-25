import logging
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from api.models.dto import TenantCreate, TenantResponse
from api.services.auth import verify_api_key, verify_tenant_access
from api.services.database import (
    create_tenant as create_tenant_db,
)
from api.services.database import (
    get_pg_pool,
    get_tenant_db,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant_endpoint(
    tenant: TenantCreate,
    request: Request,
    _=Depends(verify_api_key),
):
    """Create a new tenant account with full setup"""
    slug = re.sub(r"[^a-z0-9-]", "", tenant.name.lower().replace(" ", "-"))[:50]

    # Create in database
    db_tenant = await create_tenant_db(
        name=tenant.name, slug=slug, email=tenant.email,
        phone=tenant.phone, plan_id=tenant.plan_id,
        settings={"maxConcurrentCalls": 10, "recordingRetention": 365,
                  "language": "en-US", "timezone": "America/New_York"},
        gdpr_consent=tenant.gdpr_consent,
    )
    actual_tenant_id = db_tenant["id"] if db_tenant else str(uuid.uuid4())

    # Create Fonster Voice Application for tenant
    fonster_client = getattr(request.app.state, "fonster_client", None)
    if fonster_client:
        try:
            await fonster_client.create_application({
                "name": f"{tenant.name} Voice App",
                "type": "EXTERNAL",
                "endpoint": "tcp://aetherdesk-voice:50061",
                "speechToText": {
                    "productRef": "stt.deepgram",
                    "config": {"model": "nova-2", "languageCode": "en-US", "enablePunctuations": True}
                },
                "textToSpeech": {
                    "productRef": "tts.chatterbox",
                    "config": {"voice": "default", "emotion": "neutral"}
                },
                "intelligence": {
                    "productRef": "llm.groq",
                    "config": {"model": "llama-3.1-70b-versatile", "temperature": 0.7}
                },
            })
        except Exception as e:
            logger.warning(f"Fonster app creation failed (non-fatal): {e}")

    # Fetch plan name
    plan_name = "Starter"
    if db_tenant and db_tenant.get("plan_id"):
        pool = await get_pg_pool()
        if pool:
            try:
                plan = await pool.fetchrow("SELECT name FROM plans WHERE id = $1", db_tenant["plan_id"])
                if plan:
                    plan_name = plan["name"]
            except Exception:
                pass  # Best-effort plan name lookup, defaults to "Starter"

    return TenantResponse(
        id=actual_tenant_id,
        name=tenant.name,
        email=tenant.email,
        phone=tenant.phone,
        plan_name=plan_name,
        status="active",
        settings={
            "maxConcurrentCalls": 10,
            "recordingRetention": 365,
            "language": "en-US",
            "timezone": "America/New_York",
        },
        gdpr_consent=tenant.gdpr_consent,
        created_at=datetime.now(UTC),
    )


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, _=Depends(verify_tenant_access)):
    """Get tenant details"""
    db_tenant = await get_tenant_db(tenant_id)
    if not db_tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return TenantResponse(
        id=db_tenant["id"],
        name=db_tenant["name"],
        email=db_tenant["email"],
        phone=db_tenant.get("phone"),
        plan_name="Starter",
        status="active" if db_tenant.get("is_active") else "inactive",
        settings=db_tenant.get("settings") or {},
        gdpr_consent=db_tenant.get("gdpr_consent", False),
        created_at=db_tenant.get("created_at") or datetime.now(UTC),
    )
