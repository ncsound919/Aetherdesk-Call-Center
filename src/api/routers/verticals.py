import structlog
from fastapi import APIRouter, Depends, HTTPException

from api.services.auth import verify_tenant_access
from api.services.vertical_templates import vertical_templates_service

logger = structlog.get_logger()

router = APIRouter(prefix="/verticals", tags=["verticals"])


@router.get("/")
async def list_verticals():
    return vertical_templates_service.get_verticals()


@router.get("/{vertical_id}")
async def get_vertical_config(vertical_id: str):
    result = vertical_templates_service.get_vertical_config(vertical_id)
    if not result:
        raise HTTPException(status_code=404, detail="Vertical not found")
    return result


@router.post("/{vertical_id}/apply")
async def apply_vertical(
    vertical_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await vertical_templates_service.apply_vertical_template(tenant_id, vertical_id)
    if not result:
        raise HTTPException(status_code=404, detail="Vertical not found")
    logger.info("vertical_applied", tenant_id=tenant_id, vertical_id=vertical_id)
    return result


@router.get("/{vertical_id}/compliance")
async def get_vertical_compliance(vertical_id: str):
    result = vertical_templates_service.get_vertical_compliance(vertical_id)
    if not result:
        raise HTTPException(status_code=404, detail="Vertical not found")
    return result


@router.get("/{vertical_id}/scripts")
async def get_vertical_scripts(vertical_id: str):
    result = vertical_templates_service.get_vertical_scripts(vertical_id)
    if not result:
        raise HTTPException(status_code=404, detail="Vertical not found")
    return result
