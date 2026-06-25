
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.services.auth import verify_tenant_access
from api.services.db_wfm import (
    create_qa_rubric_db,
    create_shift_db,
    delete_shift_db,
    list_qa_rubrics_db,
    list_qa_scores_db,
    list_schedules_db,
    list_shifts_db,
    update_shift_db,
)
from api.services.forecasting import compute_forecast
from api.services.qa_scoring import qa_engine

router = APIRouter(prefix="/wfm", tags=["wfm"])


# ── Pydantic Models ───────────────────────────────────────────────

class ShiftCreate(BaseModel):
    agent_id: str
    start_time: str
    end_time: str
    shift_type: str = "regular"
    notes: str | None = None


class ShiftResponse(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    agent_name: str | None = None
    start_time: str
    end_time: str
    shift_type: str
    status: str
    notes: str | None


class ScheduleCreate(BaseModel):
    date: str
    forecasted_volume: int
    forecasted_agents: int
    notes: str | None = None


class QAScoreCreate(BaseModel):
    call_id: str
    agent_id: str
    rubric_id: str
    scores_per_criterion: dict
    notes: str | None = None


class QAScoreResponse(BaseModel):
    id: str
    call_id: str
    agent_id: str
    agent_name: str | None = None
    reviewer_id: str
    total_score: float
    max_score: float
    scores_per_criterion: dict
    notes: str | None
    reviewed_at: str


class QARubricCreate(BaseModel):
    name: str
    description: str | None = None
    criteria: list[dict]


class QARubricResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str | None
    criteria: list[dict]
    created_at: str


class ForecastResponse(BaseModel):
    forecast: list[dict]
    staffing_recommendation: dict
    model_accuracy: float | None


class AdherenceResponse(BaseModel):
    date: str
    overall_adherence_pct: float
    agents: list[dict]
    schedule_summary: dict


# ── Shift Routes ──────────────────────────────────────────────────

@router.get("/shifts")
async def list_shifts(
    tenant_id: str = Depends(verify_tenant_access),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    agent_id: str | None = Query(None),
):
    return await list_shifts_db(tenant_id, date_from=date_from, date_to=date_to, agent_id=agent_id)


@router.post("/shifts")
async def create_shift(
    data: ShiftCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await create_shift_db(
        tenant_id, data.agent_id, data.start_time, data.end_time,
        shift_type=data.shift_type, notes=data.notes
    )
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create shift")
    return result


@router.put("/shifts/{shift_id}")
async def update_shift(
    shift_id: str,
    data: ShiftCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await update_shift_db(
        shift_id, tenant_id,
        start_time=data.start_time, end_time=data.end_time,
        shift_type=data.shift_type, notes=data.notes
    )
    if not result:
        raise HTTPException(status_code=404, detail="Shift not found")
    return result


@router.delete("/shifts/{shift_id}")
async def delete_shift(
    shift_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    deleted = await delete_shift_db(shift_id, tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Shift not found")
    return {"success": True}


# ── Schedule Routes ───────────────────────────────────────────────

@router.get("/schedules")
async def list_schedules(
    tenant_id: str = Depends(verify_tenant_access),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    return await list_schedules_db(tenant_id, date_from=date_from, date_to=date_to)


@router.post("/schedules/forecast")
async def get_forecast(
    tenant_id: str = Depends(verify_tenant_access),
    hours_ahead: int = Query(24, ge=1, le=168),
):
    result = await compute_forecast(tenant_id, hours_ahead)
    return result


@router.get("/adherence")
async def get_adherence(
    tenant_id: str = Depends(verify_tenant_access),
    date: str | None = Query(None),
):

    from api.services.db_wfm import list_schedules_db

    if not date:
        date = datetime.now(UTC).strftime("%Y-%m-%d")

    schedules = await list_schedules_db(tenant_id, date_from=date, date_to=date)
    schedule = schedules[0] if schedules else None

    overall = float(schedule["adherence_pct"]) if schedule and schedule.get("adherence_pct") else 0.0

    return {
        "date": date,
        "overall_adherence_pct": overall,
        "agents": [],
        "schedule_summary": {
            "forecasted_volume": schedule["forecasted_volume"] if schedule else 0,
            "forecasted_agents": schedule["forecasted_agents"] if schedule else 0,
            "actual_volume": schedule["actual_volume"] if schedule else 0,
            "actual_agents": schedule["actual_agents"] if schedule else 0,
        },
    }


# ── QA Routes ─────────────────────────────────────────────────────

@router.get("/qa/scores")
async def list_qa_scores(
    tenant_id: str = Depends(verify_tenant_access),
    agent_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    return await list_qa_scores_db(tenant_id, agent_id=agent_id, date_from=date_from, date_to=date_to, limit=limit)


@router.post("/qa/scores")
async def create_qa_score(
    data: QAScoreCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await qa_engine.score_call(
        tenant_id, data.call_id, data.agent_id, "reviewer",
        data.rubric_id, data.scores_per_criterion, data.notes
    )
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create QA score")
    return result


@router.get("/qa/rubrics")
async def list_qa_rubrics(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await list_qa_rubrics_db(tenant_id)


@router.post("/qa/rubrics")
async def create_qa_rubric(
    data: QARubricCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await create_qa_rubric_db(tenant_id, data.name, data.criteria, data.description)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create QA rubric")
    return result


@router.get("/qa/agent-summary/{agent_id}")
async def get_agent_qa_summary(
    agent_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await qa_engine.get_agent_summary(agent_id)
