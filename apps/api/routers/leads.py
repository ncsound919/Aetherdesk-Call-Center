import csv
import io
import json
import uuid
from datetime import datetime, UTC
from typing import Optional, List

import structlog
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

logger = structlog.get_logger()
router = APIRouter(prefix="/leads", tags=["leads"])


# --- Pydantic models ---

class LeadCreate(BaseModel):
    phone: str
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    industry: Optional[str] = None
    notes: Optional[str] = None
    priority: int = 5
    score: float = 0.0
    custom_fields: dict = Field(default_factory=dict)


class LeadUpdate(BaseModel):
    phone: Optional[str] = None
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    industry: Optional[str] = None
    notes: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[str] = None
    score: Optional[float] = None
    custom_fields: Optional[dict] = None


class BulkUpdateRequest(BaseModel):
    lead_ids: List[str]
    updates: LeadUpdate


class ImportRequest(BaseModel):
    mapping: dict
    rows: List[dict]


# --- Auth helper ---

async def get_tenant_id(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))) -> str:
    """Extract tenant_id from JWT token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    from apps.api.services.auth import verify_access_token
    payload = await verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Token missing tenant_id")
    return tenant_id


# --- Endpoints ---

@router.post("")
async def create_lead(lead: LeadCreate, tenant_id: str = Depends(get_tenant_id)):
    """Create a new lead."""
    from apps.api.services.db_tenants import create_lead_db
    result = await create_lead_db(
        tenant_id=tenant_id,
        phone=lead.phone,
        company_name=lead.company_name,
        contact_name=lead.contact_name,
        first_name=lead.first_name,
        last_name=lead.last_name,
        email=lead.email,
        industry=lead.industry,
        notes=lead.notes,
        priority=lead.priority,
        score=lead.score,
        source="manual",
        custom_fields=lead.custom_fields,
    )
    logger.info("lead_created", lead_id=result["id"], tenant_id=tenant_id)
    return result


@router.get("")
async def list_leads(
    tenant_id: str = Depends(get_tenant_id),
    status: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List leads with optional filters."""
    from apps.api.services.db_tenants import list_leads_db
    rows = await list_leads_db(tenant_id, status=status, industry=industry, limit=limit, offset=offset)
    items = []
    for row in rows:
        if isinstance(row, dict):
            item = dict(row)
        elif hasattr(row, 'keys'):
            item = {k: row[k] for k in row.keys()}
        else:
            continue
        if isinstance(item.get("custom_fields"), str):
            try:
                item["custom_fields"] = json.loads(item["custom_fields"])
            except json.JSONDecodeError:
                item["custom_fields"] = {}
        items.append(item)
    return {"items": items, "count": len(items), "limit": limit, "offset": offset}


@router.get("/{lead_id}")
async def get_lead(lead_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Get a single lead by ID."""
    from apps.api.services.db_tenants import get_lead_db
    row = await get_lead_db(lead_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    if isinstance(row, dict):
        item = dict(row)
    elif hasattr(row, 'keys'):
        item = {k: row[k] for k in row.keys()}
    else:
        raise HTTPException(status_code=500, detail="Invalid row format")
    if isinstance(item.get("custom_fields"), str):
        try:
            item["custom_fields"] = json.loads(item["custom_fields"])
        except json.JSONDecodeError:
            item["custom_fields"] = {}
    return item


@router.patch("/{lead_id}")
async def update_lead(lead_id: str, updates: LeadUpdate, tenant_id: str = Depends(get_tenant_id)):
    """Update a lead."""
    from apps.api.services.db_tenants import update_lead_db
    update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    row = await update_lead_db(lead_id, tenant_id, update_dict)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    logger.info("lead_updated", lead_id=lead_id, tenant_id=tenant_id)
    return {"message": "Lead updated", "lead_id": lead_id}


@router.delete("/{lead_id}")
async def delete_lead(lead_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Delete a lead."""
    from apps.api.services.db_tenants import delete_lead_db
    success = await delete_lead_db(lead_id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Lead not found")
    logger.info("lead_deleted", lead_id=lead_id, tenant_id=tenant_id)
    return {"message": "Lead deleted", "lead_id": lead_id}


@router.post("/bulk-update")
async def bulk_update_leads(req: BulkUpdateRequest, tenant_id: str = Depends(get_tenant_id)):
    """Bulk update leads by IDs."""
    from apps.api.services.db_tenants import bulk_update_leads_db
    update_dict = {k: v for k, v in req.updates.model_dump().items() if v is not None}
    if not req.lead_ids or not update_dict:
        raise HTTPException(status_code=400, detail="lead_ids and updates required")
    count = await bulk_update_leads_db(tenant_id, req.lead_ids, update_dict)
    logger.info("leads_bulk_updated", count=count, tenant_id=tenant_id)
    return {"updated": count}


@router.post("/bulk-delete")
async def bulk_delete_leads(req: BulkUpdateRequest, tenant_id: str = Depends(get_tenant_id)):
    """Bulk delete leads by IDs."""
    from apps.api.services.db_tenants import bulk_delete_leads_db
    if not req.lead_ids:
        raise HTTPException(status_code=400, detail="lead_ids required")
    count = await bulk_delete_leads_db(tenant_id, req.lead_ids)
    logger.info("leads_bulk_deleted", count=count, tenant_id=tenant_id)
    return {"deleted": count}


# --- CSV Import ---

@router.post("/upload")
async def upload_leads_csv(
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
):
    """Upload and parse CSV file. Returns rows, headers, preview for mapping."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    # Accept CSV only for now
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported currently")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="File encoding not supported")

    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    if not rows:
        raise HTTPException(status_code=400, detail="CSV has no data rows")
    if len(rows) > 10000:
        raise HTTPException(status_code=400, detail="Too many rows (max 10,000)")

    headers = list(rows[0].keys()) if rows else []

    return {
        "headers": headers,
        "row_count": len(rows),
        "preview": rows[:5],
    }


@router.post("/import")
async def import_leads(
    req: ImportRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """Import leads from parsed CSV rows + column mapping."""
    from apps.api.services.db_tenants import create_lead_db

    if not req.rows:
        raise HTTPException(status_code=400, detail="No rows to import")
    if len(req.rows) > 10000:
        raise HTTPException(status_code=400, detail="Too many rows (max 10,000)")

    # Auto-suggest mapping if user didn't provide one (None or empty)
    if not req.mapping or len(req.mapping) == 0:
        sample = req.rows[0]
        auto_map = {}
        for col in sample.keys():
            col_lower = col.lower().strip()
            if "phone" in col_lower or "mobile" in col_lower or "tel" in col_lower:
                auto_map[col] = "phone"
            elif "company" in col_lower or "organization" in col_lower:
                auto_map[col] = "company_name"
            elif "first" in col_lower and "name" in col_lower:
                auto_map[col] = "first_name"
            elif "last" in col_lower and "name" in col_lower or "surname" in col_lower:
                auto_map[col] = "last_name"
            elif "email" in col_lower:
                auto_map[col] = "email"
            elif "industry" in col_lower or "sector" in col_lower:
                auto_map[col] = "industry"
        req.mapping = auto_map

    imported = 0
    errors = []
    now = datetime.now(UTC).isoformat()

    for i, row in enumerate(req.rows):
        lead_data = {}
        for csv_col, lead_field in req.mapping.items():
            if csv_col in row:
                lead_data[lead_field] = row[csv_col]

        if not lead_data.get("phone"):
            errors.append({"row": i + 1, "error": "Missing phone number"})
            continue

        try:
            await create_lead_db(
                tenant_id=tenant_id,
                phone=lead_data.get("phone"),
                company_name=lead_data.get("company_name"),
                contact_name=lead_data.get("contact_name"),
                first_name=lead_data.get("first_name"),
                last_name=lead_data.get("last_name"),
                email=lead_data.get("email"),
                industry=lead_data.get("industry"),
                notes=lead_data.get("notes"),
                priority=int(lead_data.get("priority", 5)) if lead_data.get("priority") else 5,
                source="csv",
            )
            imported += 1
        except Exception as e:
            errors.append({"row": i + 1, "error": str(e)})

    logger.info("leads_imported", imported=imported, errors=len(errors), tenant_id=tenant_id)
    return {
        "imported": imported,
        "errors": errors,
        "total": len(req.rows),
    }