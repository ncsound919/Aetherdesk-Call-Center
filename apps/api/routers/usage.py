from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Query

from apps.api.models.dto import UsageResponse
from apps.api.services.auth import verify_tenant_access
from apps.api.services.database import get_pg_pool, get_usage_stats

router = APIRouter(tags=["usage"])

@router.get("/api/v1/usage", response_model=UsageResponse)
async def get_usage(
    tenant_id: str = Query(default="TENANT-001", description="Tenant ID"),
    x_api_key: str = Header(default="dev-api-key"),
    period_start: datetime = Query(default=None),
    period_end: datetime = Query(default=None),
    _=Depends(verify_tenant_access),
):
    """Get usage analytics for a tenant"""
    # Use verify_tenant_access for authorization

    # Default to last 7 days if not specified
    now = datetime.now(UTC)
    if period_start is None:
        period_start = now - timedelta(days=7)
    if period_end is None:
        period_end = now

    stats = await get_usage_stats(tenant_id)

    # Guard against division by zero
    active = stats.get("active_agents", 0) or 0
    avg_duration = (
        round(stats["total_minutes"] / active, 2)
        if active > 0 else 0.0
    )

    pool = await get_pg_pool()
    queue_depth = 0
    if pool:
        queue_depth = await pool.fetchval(
            "SELECT COUNT(*) FROM call_queue WHERE tenant_id = $1 AND status = 'waiting'",
            tenant_id
        )

    return UsageResponse(
        total_agents=stats["total_agents"],
        active_agents=stats["active_agents"],
        total_calls=stats["total_calls"],
        active_calls=stats["active_calls"],
        total_minutes=stats["total_minutes"],
        avg_call_duration=avg_duration,
        queue_depth=queue_depth,
        total_cost=stats["total_minutes"] * 0.015,
        by_agent=[],
        by_day=[],
    )
