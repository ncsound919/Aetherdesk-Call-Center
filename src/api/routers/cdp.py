import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from api.services.auth import verify_tenant_access
from api.services.cdp import cdp_service
from api.services.customer_analytics import customer_analytics_service

logger = structlog.get_logger()

router = APIRouter(prefix="/cdp", tags=["cdp"])


@router.post("/customers/unify")
async def unify_customer(
    identifiers: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await cdp_service.unify_customer(tenant_id, identifiers)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to unify customer")
    logger.info("customer_unified", tenant_id=tenant_id, customer_id=result["id"])
    return result


@router.get("/customers/{customer_id}")
async def get_unified_profile(
    customer_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await cdp_service.get_unified_profile(tenant_id, customer_id)
    if not result:
        raise HTTPException(status_code=404, detail="Customer not found")
    return result


@router.post("/customers/{customer_id}/tags")
async def add_tags(
    customer_id: str,
    body: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    tags = body.get("tags", [])
    result = await cdp_service.tag_customer(tenant_id, customer_id, tags)
    return result


@router.get("/customers/search")
async def search_customers(
    q: str = Query("", description="Search query"),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await cdp_service.search_customers(tenant_id, q)


@router.get("/segments")
async def list_segments(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await cdp_service.get_segments(tenant_id)


@router.post("/segments")
async def create_segment(
    body: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    name = body.get("name", "")
    criteria = body.get("criteria", {})
    result = await cdp_service.create_segment(tenant_id, name, criteria)
    return result


@router.post("/segments/{segment_id}/evaluate")
async def evaluate_segment(
    segment_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await cdp_service.evaluate_segment(tenant_id, segment_id)


@router.get("/customers/{customer_id}/timeline")
async def get_interaction_timeline(
    customer_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await cdp_service.get_interaction_timeline(tenant_id, customer_id)


@router.get("/customers/{customer_id}/rfm")
async def get_rfm_scores(
    customer_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await cdp_service.get_rfm_scores(tenant_id, customer_id)


@router.get("/analytics/cohort")
async def get_cohort_analysis(
    tenant_id: str = Depends(verify_tenant_access),
    cohort_period: str = Query("month"),
    metric: str = Query("retention"),
):
    return await customer_analytics_service.get_cohort_analysis(tenant_id, cohort_period, metric)


@router.get("/analytics/churn-risk/{customer_id}")
async def get_churn_risk(
    customer_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await customer_analytics_service.get_churn_risk(tenant_id, customer_id)


@router.get("/analytics/ltv/{customer_id}")
async def get_lifetime_value(
    customer_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await customer_analytics_service.get_lifetime_value(tenant_id, customer_id)


@router.get("/analytics/overview")
async def get_aggregate_metrics(
    tenant_id: str = Depends(verify_tenant_access),
    period: str = Query("30d"),
):
    return await customer_analytics_service.get_aggregate_metrics(tenant_id, period)
