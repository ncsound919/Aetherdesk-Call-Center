import structlog
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
import json
import csv
import io
import uuid

logger = structlog.get_logger()
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class BusinessInfoRequest(BaseModel):
    company_name: str
    industry: str
    timezone: str = "UTC"
    phone_number: str | None = None


class ScriptSaveRequest(BaseModel):
    name: str
    content: str
    variables: list[dict] = []


@router.post("/business-info")
async def save_business_info(
    info: BusinessInfoRequest,
    credentials=None  # Will be JWT auth
):
    """Step 1: Save business info and create tenant."""
    from apps.api.services.db_tenants import create_tenant, get_user_by_id_db, update_user_onboarding_db

    # For now, use dev user. JWT auth will replace this.
    user_id = "USER-ADMIN-001"
    user = await get_user_by_id_db(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Create or update tenant
    tenant = await create_tenant(
        name=info.company_name,
        email=user.get("email", ""),
        slug=info.company_name.lower().replace(" ", "-").replace("'", "")[:50],
        phone=info.phone_number,
        settings={"industry": info.industry, "timezone": info.timezone}
    )

    # Update onboarding step
    await update_user_onboarding_db(user_id, step=1)

    logger.info("onboarding_business_info", user_id=user_id, tenant_id=tenant["id"])
    return {"message": "Business info saved", "tenant_id": tenant["id"]}


@router.post("/import-leads")
async def import_leads(
    file: UploadFile = File(...),
    mapping: str = "{}",
):
    """Step 2: Upload and import leads from CSV/Excel."""
    from apps.api.services.db_tenants import update_user_onboarding_db

    user_id = "USER-ADMIN-001"

    # Validate file type
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="File must be CSV or Excel")

    # Read file content
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    # Parse CSV
    text = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if len(rows) > 10000:
        raise HTTPException(status_code=400, detail="Too many rows (max 10,000)")

    # Parse column mapping
    col_mapping = json.loads(mapping)

    # Map rows to lead format
    leads = []
    errors = []
    for i, row in enumerate(rows):
        lead = {}
        for csv_col, lead_field in col_mapping.items():
            if csv_col in row:
                lead[lead_field] = row[csv_col]

        # Validate required fields
        if not lead.get("phone") and not lead.get("company"):
            errors.append({"row": i + 1, "error": "Missing phone or company"})
            continue

        leads.append(lead)

    await update_user_onboarding_db(user_id, step=2)

    logger.info("onboarding_leads_imported", user_id=user_id, count=len(leads), errors=len(errors))
    return {
        "message": f"Imported {len(leads)} leads",
        "total": len(leads),
        "errors": errors,
        "preview": leads[:5]
    }


@router.post("/save-script")
async def save_script(script: ScriptSaveRequest):
    """Step 3: Save call script."""
    from apps.api.services.db_tenants import update_user_onboarding_db

    user_id = "USER-ADMIN-001"

    # Save script to database (using existing agent_profiles table for now)
    from apps.api.services.db_tenants import create_agent_profile_db
    import uuid

    profile_id = f"PROF-{uuid.uuid4().hex[:6].upper()}"
    await create_agent_profile_db(
        profile_id=profile_id,
        tenant_id="TENANT-001",
        name=script.name,
        prompt=script.content,
        parameters=json.dumps({"variables": script.variables})
    )

    await update_user_onboarding_db(user_id, step=3)

    logger.info("onboarding_script_saved", user_id=user_id, script_name=script.name)
    return {"message": "Script saved", "script_id": profile_id}


@router.post("/complete")
async def complete_onboarding():
    """Step 5: Mark onboarding as complete."""
    from apps.api.services.db_tenants import update_user_onboarding_db

    user_id = "USER-ADMIN-001"
    await update_user_onboarding_db(user_id, step=5, completed=True)

    logger.info("onboarding_completed", user_id=user_id)
    return {"message": "Onboarding completed"}


@router.get("/status")
async def get_onboarding_status():
    """Get current onboarding status."""
    from apps.api.services.db_tenants import get_user_by_id_db

    user_id = "USER-ADMIN-001"
    user = await get_user_by_id_db(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "completed": user.get("onboarding_completed", False),
        "current_step": user.get("onboarding_step", 0)
    }
