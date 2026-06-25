from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from structlog import get_logger

from api.models.dto import (
    DatasetCreate,
    EmotionDetectRequest,
    EvalMetricsIngest,
    ExternalJobSubmit,
    ModelRegister,
    TrainingJobCreate,
    TurnLabel,
    VoiceProfileCreate,
)
from api.services.ai_training import AITrainingService
from api.services.auth import verify_tenant_access
from api.services.model_registry import ModelRegistry
from api.services.voice_biometrics import VoiceBiometricsService

logger = get_logger()
router = APIRouter(prefix="/ai-platform", tags=["ai-platform"])

training_service = AITrainingService()
registry = ModelRegistry()
voice_svc = VoiceBiometricsService()


# ── Training Endpoints ─────────────────────────────────────────────

@router.post("/training/collect")
async def collect_training_data(
    start_date: str = Query(..., description="Start date ISO"),
    end_date: str = Query(..., description="End date ISO"),
    tenant_id: str = Depends(verify_tenant_access),
):
    data = await training_service.collect_training_data(tenant_id, start_date, end_date)
    return {"total": len(data), "examples": data}


@router.post("/training/jobs")
async def create_training_job(
    data: TrainingJobCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    job = await training_service.create_training_job(
        tenant_id=tenant_id,
        name=data.name,
        model_base=data.model_base,
        hyperparams=data.hyperparams,
    )
    if not job:
        raise HTTPException(status_code=400, detail="Failed to create training job")
    return job


@router.get("/training/jobs")
async def list_training_jobs(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await training_service.list_training_jobs(tenant_id)


@router.get("/training/jobs/{job_id}")
async def get_training_job_status(
    job_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await training_service.get_training_status(job_id)


@router.get("/training/export", response_class=PlainTextResponse)
async def export_training_data(
    format: str = Query("jsonl"),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await training_service.export_for_fine_tuning(tenant_id, format=format)


# ── Model Registry Endpoints ──────────────────────────────────────

@router.post("/models")
async def register_model(
    data: ModelRegister,
    tenant_id: str = Depends(verify_tenant_access),
):
    model = await registry.register_model(
        tenant_id=tenant_id,
        name=data.name,
        version=data.version,
        model_type=data.model_type,
        config=data.config,
        metrics=data.metrics,
    )
    if not model:
        raise HTTPException(status_code=400, detail="Failed to register model")
    return model


@router.get("/models")
async def list_models(
    model_type: str | None = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await registry.get_models(tenant_id, model_type=model_type)


@router.get("/models/{model_id}/versions")
async def get_model_versions(
    model_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    from api.services.db_ai_platform import list_models_db
    all_models = await list_models_db(tenant_id)
    versions = [m for m in all_models if m.get("id") == model_id or m.get("name") in [am.get("name") for am in all_models if am.get("id") == model_id]]
    return versions


@router.post("/models/{model_id}/versions/{version}/promote")
async def promote_model(
    model_id: str,
    version: str,
    environment: str = Query("production"),
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await registry.promote_model(tenant_id, model_id, version, environment)
    if not result:
        raise HTTPException(status_code=404, detail="Model version not found")
    return result


@router.post("/models/{model_id}/versions/{version}/rollback")
async def rollback_model(
    model_id: str,
    version: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await registry.rollback_model(tenant_id, model_id, version)
    if not result:
        raise HTTPException(status_code=404, detail="Model version not found")
    return result


@router.get("/models/active")
async def get_active_models(
    model_type: str | None = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    if model_type:
        return await registry.get_active_model(tenant_id, model_type) or {}
    return {
        "intent": await registry.get_active_model(tenant_id, "intent") or {},
        "sentiment": await registry.get_active_model(tenant_id, "sentiment") or {},
    }


@router.get("/models/compare")
async def compare_models(
    model_id: str = Query(...),
    version_a: str = Query(...),
    version_b: str = Query(...),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await registry.compare_models(tenant_id, model_id, version_a, version_b)


# ── Dataset Endpoints ──────────────────────────────────────────────

@router.post("/datasets")
async def create_dataset(
    data: DatasetCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    from api.services.ai_training import AITrainingService
    examples = await training_service.collect_training_data(
        tenant_id,
        data.source_start_date or (datetime.now(UTC).isoformat()),
        data.source_end_date or (datetime.now(UTC).isoformat()),
    )
    training_examples = AITrainingService.generate_training_examples(examples)
    dataset = await training_service.create_dataset(
        tenant_id=tenant_id,
        name=data.name,
        recipe_type=data.recipe_type,
        examples=training_examples,
    )
    return dataset


@router.get("/datasets")
async def list_datasets(
    recipe_type: str | None = Query(None),
    limit: int = Query(50),
    tenant_id: str = Depends(verify_tenant_access),
):
    from api.services.db_ai_platform import list_datasets_db
    return await list_datasets_db(tenant_id, recipe_type=recipe_type, limit=limit)


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    from api.services.db_ai_platform import get_dataset_db
    ds = await get_dataset_db(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


# ── Turn & Label Endpoints ────────────────────────────────────────

@router.get("/datasets/{dataset_id}/turns")
async def list_turns(
    dataset_id: str,
    limit: int = Query(500),
    offset: int = Query(0),
    tenant_id: str = Depends(verify_tenant_access),
):
    from api.services.db_ai_platform import list_turns_db
    return await list_turns_db(dataset_id, limit=limit, offset=offset)


@router.post("/turns/{turn_id}/labels")
async def create_label(
    turn_id: str,
    data: TurnLabel,
    tenant_id: str = Depends(verify_tenant_access),
):
    from api.services.db_ai_platform import create_label_db
    label = await create_label_db(
        tenant_id=tenant_id,
        turn_id=turn_id,
        label_type=data.label_type,
        label_value=data.label_value,
        confidence=data.confidence,
        notes=data.notes,
    )
    if not label:
        raise HTTPException(status_code=400, detail="Failed to create label")
    return label


@router.get("/turns/{turn_id}/labels")
async def list_labels(
    turn_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    from api.services.db_ai_platform import list_labels_db
    return await list_labels_db(turn_id)


# ── External Job Endpoints ─────────────────────────────────────────

@router.post("/training/external-jobs")
async def submit_external_job(
    data: ExternalJobSubmit,
    tenant_id: str = Depends(verify_tenant_access),
):
    job = await training_service.submit_external_job(
        tenant_id=tenant_id,
        dataset_id=data.dataset_id,
        model_name=data.model_name,
        hyperparams=data.hyperparams,
        provider=data.provider,
    )
    return job


@router.get("/training/external-jobs/{external_job_id}")
async def get_external_job_status(
    external_job_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await training_service.get_external_job_status(external_job_id)


@router.post("/training/external-jobs/{external_job_id}/cancel")
async def cancel_external_job(
    external_job_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await training_service.cancel_external_job(external_job_id)


# ── Eval Metrics Endpoints ─────────────────────────────────────────

@router.post("/models/eval-metrics")
async def ingest_eval_metrics(
    data: EvalMetricsIngest,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await registry.ingest_evaluation_metrics(
        tenant_id=tenant_id,
        model_id=data.model_id,
        version=data.version,
        metrics=data.metrics,
    )
    if not result:
        raise HTTPException(status_code=400, detail="Failed to ingest metrics")
    return result


@router.get("/models/{model_id}/eval-metrics/{version}")
async def get_eval_metrics(
    model_id: str,
    version: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await registry.get_evaluation_metrics(tenant_id, model_id, version)


# ── Model Audit Log Endpoints ──────────────────────────────────────

@router.get("/models/{model_id}/audit-log")
async def get_model_audit_log(
    model_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    from api.services.model_registry import get_model_audit_log
    return await get_model_audit_log(tenant_id, model_id)


# ── Model Family Endpoints ─────────────────────────────────────────

@router.get("/models/family/{family}")
async def get_model_family(
    family: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await registry.get_model_family(tenant_id, family)


# ── External Job Links Endpoints ───────────────────────────────────

@router.get("/models/{model_id}/external-jobs")
async def list_model_external_jobs(
    model_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await registry.list_external_jobs(tenant_id, model_id)


# ── Transition Model State Endpoint ────────────────────────────────

@router.post("/models/{model_id}/versions/{version}/transition")
async def transition_model_state(
    model_id: str,
    version: str,
    new_state: str = Query(...),
    tenant_id: str = Depends(verify_tenant_access),
):
    try:
        result = await registry.transition_model_state(
            tenant_id=tenant_id,
            model_id=model_id,
            version=version,
            new_state=new_state,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Model version not found")
        return dict(result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Voice Biometrics Endpoints ─────────────────────────────────────

@router.post("/voice-profiles")
async def create_voice_profile(
    data: VoiceProfileCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    profile = await voice_svc.create_voice_profile(
        tenant_id=tenant_id,
        speaker_name=data.speaker_name,
        audio_features=data.features,
    )
    if not profile:
        raise HTTPException(status_code=400, detail="Failed to create voice profile")
    return profile


@router.get("/voice-profiles")
async def list_voice_profiles(
    tenant_id: str = Depends(verify_tenant_access),
):
    from api.services.db_ai_platform import list_voice_profiles_db
    return await list_voice_profiles_db(tenant_id)


@router.post("/voice-profiles/identify")
async def identify_speaker(
    data: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await voice_svc.identify_speaker(tenant_id, data.get("audio_sample", data))


@router.post("/voice-profiles/emotion")
async def detect_emotion(
    data: EmotionDetectRequest,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = voice_svc.detect_emotion(data.audio_features)
    if data.call_id:
        await voice_svc.log_emotion(
            tenant_id=tenant_id,
            call_id=data.call_id,
            speaker="customer",
            emotion=result["emotion"],
            confidence=result["confidence"],
        )
    return result


@router.get("/voice-profiles/emotion-trends/{call_id}")
async def get_emotion_trends(
    call_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await voice_svc.get_emotion_trends(tenant_id, call_id)
