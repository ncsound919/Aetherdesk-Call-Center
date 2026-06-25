from fastapi import APIRouter, Depends, HTTPException, Query

from api.services.api_versioning import api_versioning_service
from api.services.auth import verify_tenant_access
from api.services.conversation_quality import conversation_quality_service
from api.services.failover_testing import failover_service
from api.services.self_service_portal import self_service_portal_service

router = APIRouter(prefix="/enterprise", tags=["enterprise"])


# ── Failover Testing ──────────────────────────────────────────────

@router.post("/failover/test")
async def run_failover_test(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await failover_service.test_telephony_failover()


@router.get("/failover/status")
async def get_failover_status(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await failover_service.get_failover_status()


@router.get("/failover/history")
async def get_failover_history(
    limit: int = Query(20, ge=1, le=100),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await failover_service.get_failover_history(limit=limit)


@router.get("/failover/config")
async def get_failover_config(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await failover_service.get_failover_config()


# ── Conversation Quality ──────────────────────────────────────────

@router.post("/conversation-quality/score")
async def score_conversation(
    transcript: str,
    rubric_name: str = Query("standard"),
    tenant_id: str = Depends(verify_tenant_access),
):
    return conversation_quality_service.score_conversation(transcript, rubric_name)


@router.get("/conversation-quality/scores")
async def get_quality_scores(
    agent_id: str | None = Query(None),
    period: str = Query("30d"),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await conversation_quality_service.get_quality_scores(tenant_id, agent_id, period)


@router.get("/conversation-quality/trends")
async def get_quality_trends(
    period: str = Query("30d"),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await conversation_quality_service.get_quality_trends(tenant_id, period)


@router.get("/conversation-quality/coaching")
async def get_coaching_opportunities(
    agent_id: str,
    period: str = Query("30d"),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await conversation_quality_service.identify_coaching_opportunities(agent_id, period)


# ── API Versioning ────────────────────────────────────────────────

@router.get("/api-versions")
async def list_api_versions(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await api_versioning_service.get_api_versions()


@router.post("/api-versions/{version}/deprecate")
async def deprecate_api_version(
    version: str,
    sunset_date: str = Query(..., description="Expected sunset date (YYYY-MM-DD)"),
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await api_versioning_service.deprecate_version(version, sunset_date)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/api-versions/migration-guide")
async def get_migration_guide(
    from_version: str = Query(...),
    to_version: str = Query(...),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await api_versioning_service.get_migration_guide(from_version, to_version)


@router.get("/api-versions/changelog")
async def get_changelog(
    version: str | None = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await api_versioning_service.get_changelog(version)


@router.get("/api-versions/usage-stats")
async def get_api_usage_stats(
    version: str | None = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await api_versioning_service.get_usage_stats(version)


# ── Customer Self-Service Portal ──────────────────────────────────

@router.get("/customer-portal/{customer_id}")
async def get_customer_portal(
    customer_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await self_service_portal_service.get_customer_portal_data(customer_id)


@router.post("/customer-portal/complaint")
async def submit_complaint(
    customer_id: str = Query(...),
    subject: str = Query(...),
    description: str = Query(...),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await self_service_portal_service.submit_complaint(customer_id, subject, description)


@router.post("/customer-portal/callback")
async def schedule_callback(
    customer_id: str = Query(...),
    preferred_time: str = Query(...),
    reason: str = Query(...),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await self_service_portal_service.schedule_call_back(customer_id, preferred_time, reason)


@router.put("/customer-portal/{customer_id}/preferences")
async def update_customer_preferences(
    customer_id: str,
    preferences: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await self_service_portal_service.update_preferences(customer_id, preferences)
