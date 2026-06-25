from datetime import UTC

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.services.ai_evaluation import AIEvaluationService
from api.services.auth import verify_tenant_access
from api.services.db_ai_evaluation import (
    create_evaluation_db,
    create_experiment_db,
    get_accuracy_metrics_db,
    get_confidence_distribution_db,
    get_experiment_db,
    list_evaluations_db,
    list_experiments_db,
    update_experiment_db,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/ai-ops", tags=["ai-ops"])

# In-memory confidence thresholds per tenant
_tenant_thresholds: dict[str, dict] = {}


# ── Pydantic Models ───────────────────────────────────────────────

class AIEvaluationCreate(BaseModel):
    experiment_id: str | None = None
    call_id: str | None = None
    predicted_intent: str = Field(..., min_length=1)
    actual_intent: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    model_used: str | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)


class AIExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    model_a: str = Field(..., min_length=1)
    model_b: str = Field(..., min_length=1)
    traffic_split: float = Field(default=0.5, ge=0.0, le=1.0)


class ConfidenceThresholdSet(BaseModel):
    proceed: float = Field(default=0.8, ge=0.0, le=1.0)
    review: float = Field(default=0.5, ge=0.0, le=1.0)
    escalate: float = Field(default=0.0, ge=0.0, le=1.0)


# ── Evaluation Routes ─────────────────────────────────────────────

@router.post("/evaluate")
async def record_evaluation(
    data: AIEvaluationCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    is_correct = 1 if (data.actual_intent and data.predicted_intent == data.actual_intent) else 0
    result = await create_evaluation_db(
        tenant_id=tenant_id,
        experiment_id=data.experiment_id,
        call_id=data.call_id,
        predicted_intent=data.predicted_intent,
        actual_intent=data.actual_intent,
        confidence=data.confidence,
        is_correct=is_correct,
        model_used=data.model_used,
        latency_ms=data.latency_ms,
    )
    if not result:
        raise HTTPException(status_code=400, detail="Failed to record evaluation")
    logger.info("evaluation_recorded", tenant_id=tenant_id, predicted=data.predicted_intent, is_correct=is_correct)
    return result


@router.get("/accuracy")
async def get_accuracy(
    tenant_id: str = Depends(verify_tenant_access),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    return await get_accuracy_metrics_db(tenant_id, start_date=start_date, end_date=end_date)


# ── Experiment Routes ─────────────────────────────────────────────

@router.post("/experiments")
async def create_experiment(
    data: AIExperimentCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await create_experiment_db(
        tenant_id=tenant_id,
        name=data.name,
        description=data.description,
        model_a=data.model_a,
        model_b=data.model_b,
        traffic_split=data.traffic_split,
    )
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create experiment")
    logger.info("experiment_created", tenant_id=tenant_id, name=data.name)
    return result


@router.get("/experiments")
async def list_experiments(
    tenant_id: str = Depends(verify_tenant_access),
    status: str | None = Query(None),
):
    return await list_experiments_db(tenant_id, status=status)


@router.get("/experiments/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    exp = await get_experiment_db(tenant_id, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    # Build evaluation results for this experiment
    evaluations = await list_evaluations_db(tenant_id, experiment_id=experiment_id, limit=10000)
    metrics = AIEvaluationService.calculate_accuracy_metrics(evaluations)
    return {**exp, "metrics": metrics}


@router.post("/experiments/{experiment_id}/stop")
async def stop_experiment(
    experiment_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    exp = await get_experiment_db(tenant_id, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp["status"] != "active":
        raise HTTPException(status_code=400, detail="Experiment is not active")

    # Evaluate to determine winner
    evaluations = await list_evaluations_db(tenant_id, experiment_id=experiment_id, limit=10000)
    metrics = AIEvaluationService.calculate_accuracy_metrics(evaluations)

    # Determine winner by highest F1
    intents = metrics.get("intents", {})
    winner = exp.get("model_a")  # default
    if intents:
        best_f1 = 0.0
        for intent, m in intents.items():
            if m.get("f1", 0) > best_f1:
                best_f1 = m["f1"]
        # For A/B, use overall accuracy comparison
        a_results = [e for e in evaluations if e.get("model_used") == exp["model_a"]]
        b_results = [e for e in evaluations if e.get("model_used") == exp["model_b"]]
        a_acc = sum(1 for e in a_results if e.get("is_correct")) / len(a_results) if a_results else 0
        b_acc = sum(1 for e in b_results if e.get("is_correct")) / len(b_results) if b_results else 0
        winner = exp["model_a"] if a_acc >= b_acc else exp["model_b"]

    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    result = await update_experiment_db(
        tenant_id, experiment_id,
        winner=winner, status="stopped", stopped_at=now
    )
    if not result:
        raise HTTPException(status_code=400, detail="Failed to stop experiment")
    logger.info("experiment_stopped", tenant_id=tenant_id, experiment_id=experiment_id, winner=winner)
    return result


# ── Confidence Routes ─────────────────────────────────────────────

@router.get("/confidence/distribution")
async def get_confidence_distribution(
    tenant_id: str = Depends(verify_tenant_access),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    return await get_confidence_distribution_db(tenant_id, start_date=start_date, end_date=end_date)


@router.post("/confidence/thresholds")
async def set_confidence_thresholds(
    data: ConfidenceThresholdSet,
    tenant_id: str = Depends(verify_tenant_access),
):
    _tenant_thresholds[tenant_id] = {
        "proceed": data.proceed,
        "review": data.review,
        "escalate": data.escalate,
    }
    logger.info("confidence_thresholds_set", tenant_id=tenant_id)
    return {"success": True, "thresholds": _tenant_thresholds[tenant_id]}


@router.get("/confidence/thresholds")
async def get_confidence_thresholds(
    tenant_id: str = Depends(verify_tenant_access),
):
    return _tenant_thresholds.get(tenant_id, {
        "proceed": 0.8,
        "review": 0.5,
        "escalate": 0.0,
    })
