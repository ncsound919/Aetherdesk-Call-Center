import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from api.models.dto import VoiceQualityMetricCreate
from api.services.audio_quality import calculate_mos, score_call_quality
from api.services.auth import verify_tenant_access
from api.services.db_audio_quality import (
    create_quality_metric_db,
    get_call_quality_db,
    get_quality_summary_db,
    get_quality_trends_db,
    list_quality_metrics_db,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/voice-quality", tags=["voice-quality"])


@router.post("/metrics")
async def record_metric(
    data: VoiceQualityMetricCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    mos = data.mos
    if mos <= 0:
        mos = calculate_mos(data.latency_ms, data.jitter_ms, data.packet_loss_pct)
    scoring = score_call_quality(mos, data.jitter_ms, data.packet_loss_pct, data.latency_ms)

    result = await create_quality_metric_db(
        tenant_id, data.call_id, data.agent_id,
        mos, data.jitter_ms, data.packet_loss_pct,
        data.latency_ms, data.rtt_samples, data.codec,
        scoring["quality_rating"],
    )
    if not result:
        raise HTTPException(status_code=400, detail="Failed to record quality metric")
    result["recommendations"] = scoring["recommendations"]
    return result


@router.get("/metrics")
async def list_metrics(
    tenant_id: str = Depends(verify_tenant_access),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_mos: float | None = Query(None, ge=1.0, le=5.0),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    return await list_quality_metrics_db(
        tenant_id, limit=limit, offset=offset,
        min_mos=min_mos, start_date=start_date, end_date=end_date,
    )


@router.get("/summary")
async def get_summary(
    tenant_id: str = Depends(verify_tenant_access),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    return await get_quality_summary_db(tenant_id, start_date=start_date, end_date=end_date)


@router.get("/trends")
async def get_trends(
    tenant_id: str = Depends(verify_tenant_access),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    granularity: str = Query("hour", pattern=r"^(hour|day)$"),
):
    return await get_quality_trends_db(tenant_id, start_date=start_date, end_date=end_date, granularity=granularity)


@router.get("/calls/{call_id}")
async def get_call_quality(
    call_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await get_call_quality_db(tenant_id, call_id)
    if not result:
        raise HTTPException(status_code=404, detail="Call quality metrics not found")
    return result
