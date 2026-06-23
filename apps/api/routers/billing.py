from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Query

from apps.api.services.auth import verify_tenant_access
from apps.api.services.database import get_billing_summary

router = APIRouter(tags=["billing"])

@router.get("/api/v1/billing")
async def get_billing(
    tenant_id: str = Query(default="TENANT-001", description="Tenant ID"),
    x_api_key: str = Header(default="dev-api-key"),
    period_start: datetime = Query(default=None),
    period_end: datetime = Query(default=None),
    _=Depends(verify_tenant_access),
):
    """Get billing summary"""
    # Use verify_tenant_access for authorization

    # Default to last 7 days if not specified
    now = datetime.now(UTC)
    if period_start is None:
        period_start = now - timedelta(days=7)
    if period_end is None:
        period_end = now

    summary = await get_billing_summary(tenant_id, period_start, period_end)
    return {
        "total_calls": summary["total_calls"],
        "total_minutes": summary["total_minutes"],
        "total_cost": summary["total_cost"],
        "currency": summary["currency"],
        "breakdown": {
            "per_minute": 0.015,
            "ai_minutes": summary["total_minutes"] * 0.5,
            "standard_minutes": summary["total_minutes"] * 0.5,
        },
    }
