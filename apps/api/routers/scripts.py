import json
from typing import Optional, List

import structlog
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

logger = structlog.get_logger()
router = APIRouter(prefix="/scripts", tags=["scripts"])


# --- Pydantic models ---

class ScriptCreate(BaseModel):
    name: str
    content: dict = Field(default_factory=dict)
    variables: List[dict] = Field(default_factory=list)
    is_active: bool = False


class ScriptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[dict] = None
    variables: Optional[List[dict]] = None
    is_active: Optional[bool] = None


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    content: dict = Field(default_factory=dict)
    variables: List[dict] = Field(default_factory=list)
    is_public: bool = True


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
async def create_script(script: ScriptCreate, tenant_id: str = Depends(get_tenant_id)):
    """Create a new script."""
    from apps.api.services.db_tenants import create_script_db
    result = await create_script_db(
        tenant_id=tenant_id,
        name=script.name,
        content=script.content,
        variables=script.variables,
    )
    if script.is_active:
        from apps.api.services.db_tenants import update_script_db
        await update_script_db(result["id"], tenant_id, {"is_active": True})
    logger.info("script_created", script_id=result["id"], tenant_id=tenant_id)
    return result


@router.get("")
async def list_scripts(
    tenant_id: str = Depends(get_tenant_id),
    is_active: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List scripts for the tenant."""
    from apps.api.services.db_tenants import list_scripts_db
    rows = await list_scripts_db(tenant_id, is_active=is_active, limit=limit, offset=offset)
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset}


@router.get("/{script_id}")
async def get_script(script_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Get a single script."""
    from apps.api.services.db_tenants import get_script_db
    row = await get_script_db(script_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="Script not found")
    return row


@router.patch("/{script_id}")
async def update_script(script_id: str, updates: ScriptUpdate, tenant_id: str = Depends(get_tenant_id)):
    """Update a script."""
    from apps.api.services.db_tenants import update_script_db
    update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}
    row = await update_script_db(script_id, tenant_id, update_dict)
    if not row:
        raise HTTPException(status_code=404, detail="Script not found")
    logger.info("script_updated", script_id=script_id, tenant_id=tenant_id)
    return {"message": "Script updated", "script_id": script_id}


@router.delete("/{script_id}")
async def delete_script(script_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Delete a script."""
    from apps.api.services.db_tenants import delete_script_db
    success = await delete_script_db(script_id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Script not found")
    logger.info("script_deleted", script_id=script_id, tenant_id=tenant_id)
    return {"message": "Script deleted", "script_id": script_id}


# --- Template endpoints ---

@router.get("/templates/list")
async def list_templates(
    industry: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List public script templates (no auth required)."""
    from apps.api.services.db_tenants import list_script_templates_db
    rows = await list_script_templates_db(industry=industry, limit=limit, offset=offset)
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset}


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """Get a single template (no auth required)."""
    from apps.api.services.db_tenants import get_script_template_db
    row = await get_script_template_db(template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return row


@router.post("/templates/clone/{template_id}")
async def clone_template(template_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Clone a public template into tenant's scripts."""
    from apps.api.services.db_tenants import get_script_template_db, create_script_db
    template = await get_script_template_db(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    result = await create_script_db(
        tenant_id=tenant_id,
        name=f"{template['name']} (cloned)",
        content=template["content"],
        variables=template["variables"],
    )
    logger.info("template_cloned", template_id=template_id, script_id=result["id"], tenant_id=tenant_id)
    return {"script_id": result["id"], "message": "Template cloned"}


@router.post("/templates/publish")
async def publish_template(template: TemplateCreate):
    """Publish a new template (no auth required for now, but should be admin-only in production)."""
    from apps.api.services.db_tenants import create_script_template_db
    result = await create_script_template_db(
        name=template.name,
        description=template.description,
        industry=template.industry,
        content=template.content,
        variables=template.variables,
        is_public=template.is_public,
    )
    logger.info("template_published", template_id=result["id"])
    return result