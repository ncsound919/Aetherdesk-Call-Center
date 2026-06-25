from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.services.auth import verify_tenant_access
from api.services.supervisor import supervisor_service
from api.services.training import training_service
from api.services.wfm_metrics import wfm_metrics_service

router = APIRouter(prefix="/wfm-final", tags=["wfm-final"])


class AHTTrackRequest(BaseModel):
    call_id: str
    agent_id: str
    duration_seconds: int


class FCRTrackRequest(BaseModel):
    call_id: str
    customer_id: str
    resolved: bool
    follow_up_call_id: str | None = None


class CSATTrackRequest(BaseModel):
    call_id: str
    customer_id: str
    rating: int = Field(..., ge=1, le=5)


class NPSTrackRequest(BaseModel):
    call_id: str
    customer_id: str
    score: int = Field(..., ge=0, le=10)


class CourseCreateRequest(BaseModel):
    title: str
    description: str | None = None
    modules: list[dict] = []
    duration_hours: float = 0


class EnrollRequest(BaseModel):
    agent_id: str
    course_id: str


class ProgressRequest(BaseModel):
    enrollment_id: str
    module_id: str
    status: str


class CoachingCreateRequest(BaseModel):
    agent_id: str
    coach_id: str
    focus_area: str
    notes: str | None = None


@router.post("/metrics/aht")
async def track_aht(data: AHTTrackRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await wfm_metrics_service.track_aht(data.call_id, data.agent_id, data.duration_seconds, tenant_id)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to track AHT")
    return result


@router.post("/metrics/fcr")
async def track_fcr(data: FCRTrackRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await wfm_metrics_service.track_fcr(data.call_id, data.customer_id, data.resolved, tenant_id, data.follow_up_call_id)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to track FCR")
    return result


@router.post("/metrics/csat")
async def track_csat(data: CSATTrackRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await wfm_metrics_service.track_csat(data.call_id, data.customer_id, data.rating, tenant_id)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to track CSAT")
    return result


@router.post("/metrics/nps")
async def track_nps(data: NPSTrackRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await wfm_metrics_service.track_nps(data.call_id, data.customer_id, data.score, tenant_id)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to track NPS")
    return result


@router.get("/metrics/summary")
async def get_metrics_summary(
    tenant_id: str = Depends(verify_tenant_access),
    period: str = Query("7d", regex="^(24h|7d|30d|90d)$"),
):
    aht = await wfm_metrics_service.get_aht_stats(tenant_id, period)
    fcr = await wfm_metrics_service.get_fcr_rate(tenant_id, period)
    csat = await wfm_metrics_service.get_csat_trend(tenant_id, period)
    nps = await wfm_metrics_service.get_nps_score(tenant_id, period)
    return {
        "aht": aht,
        "fcr": fcr,
        "csat_trend": csat,
        "nps": nps,
    }


@router.get("/wallboard")
async def get_wallboard(tenant_id: str = Depends(verify_tenant_access)):
    return await supervisor_service.get_wallboard_data(tenant_id)


@router.get("/wallboard/agents")
async def get_wallboard_agents(tenant_id: str = Depends(verify_tenant_access)):
    return await supervisor_service.get_live_agent_status(tenant_id)


@router.get("/wallboard/team")
async def get_team_performance(
    tenant_id: str = Depends(verify_tenant_access),
    period: str = Query("7d"),
):
    return await supervisor_service.get_team_performance(tenant_id, period)


@router.get("/wallboard/alerts")
async def get_wallboard_alerts(tenant_id: str = Depends(verify_tenant_access)):
    return await supervisor_service.get_recent_alerts(tenant_id)


@router.get("/training/courses")
async def list_courses(tenant_id: str = Depends(verify_tenant_access)):
    return await training_service.list_courses(tenant_id)


@router.post("/training/courses")
async def create_course(data: CourseCreateRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await training_service.create_course(tenant_id, data.title, data.description, data.modules, data.duration_hours)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create course")
    return result


@router.post("/training/enroll")
async def enroll_agent(data: EnrollRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await training_service.enroll_agent(tenant_id, data.agent_id, data.course_id)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to enroll agent")
    return result


@router.post("/training/progress")
async def track_progress(data: ProgressRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await training_service.track_progress(data.enrollment_id, data.module_id, data.status)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to track progress")
    return result


@router.get("/training/certifications/{agent_id}")
async def get_certifications(agent_id: str, tenant_id: str = Depends(verify_tenant_access)):
    return await training_service.get_agent_certifications(tenant_id, agent_id)


@router.post("/training/coaching")
async def create_coaching(data: CoachingCreateRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await training_service.create_coaching_session(tenant_id, data.agent_id, data.coach_id, data.focus_area, data.notes)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create coaching session")
    return result


@router.get("/training/coaching")
async def list_coaching(
    tenant_id: str = Depends(verify_tenant_access),
    agent_id: str | None = Query(None),
):
    return await training_service.list_coaching_sessions(tenant_id, agent_id)
