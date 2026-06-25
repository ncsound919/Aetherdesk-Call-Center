import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from api.models.dto import LineageEntryCreate
from api.services.auth import verify_tenant_access
from api.services.data_lineage import lineage_service

logger = structlog.get_logger()

router = APIRouter(prefix="/data-governance", tags=["data-governance"])


@router.get("/lineage/record")
async def get_record_lineage(
    table: str = Query(..., description="Source or target table name"),
    record_id: str = Query(..., description="Record ID"),
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await lineage_service.get_lineage_for_record(tenant_id, table, record_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Lineage not found"))
    return result


@router.get("/lineage/graph")
async def get_lineage_graph(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await lineage_service.get_lineage_graph(tenant_id, start_date=start_date, end_date=end_date)


@router.get("/lineage/column")
async def get_column_lineage(
    table: str = Query(..., description="Table name"),
    column: str = Query(..., description="Column name"),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await lineage_service.get_column_lineage(tenant_id, table, column)


@router.get("/health-score")
async def get_health_score(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await lineage_service.get_data_health_score(tenant_id)


@router.post("/lineage")
async def record_lineage(
    data: LineageEntryCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await lineage_service.record_lineage(
        tenant_id,
        source_table=data.source_table,
        source_id=data.source_id,
        target_table=data.target_table,
        target_id=data.target_id,
        operation=data.operation,
        metadata=data.metadata,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to record lineage"))
    return result
