"""Tests for src/api/routers/ai_platform.py — FastAPI router over the AI
training / model-registry / voice-biometrics services."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.routers.ai_platform as mod  # noqa: E402
from api.services.auth import verify_tenant_access  # noqa: E402


@pytest.fixture
def ctx(monkeypatch):
    training = MagicMock()
    training.collect_training_data = AsyncMock(return_value=[{"x": 1}])
    training.create_training_job = AsyncMock(return_value={"id": "job-1"})
    training.list_training_jobs = AsyncMock(return_value=[])
    training.get_training_status = AsyncMock(return_value={"status": "running"})
    training.export_for_fine_tuning = AsyncMock(return_value="line1\nline2")
    training.submit_external_job = AsyncMock(return_value={"id": "ej-1"})
    training.get_external_job_status = AsyncMock(return_value={"status": "done"})
    training.cancel_external_job = AsyncMock(return_value={"cancelled": True})
    training.create_dataset = AsyncMock(return_value={"id": "ds-1"})

    registry = MagicMock()
    registry.register_model = AsyncMock(return_value={"id": "m-1"})
    registry.get_models = AsyncMock(return_value=[])
    registry.promote_model = AsyncMock(return_value={"promoted": True})
    registry.rollback_model = AsyncMock(return_value={"rolled_back": True})
    registry.get_active_model = AsyncMock(return_value={"id": "active"})
    registry.compare_models = AsyncMock(return_value={"diff": []})
    registry.ingest_evaluation_metrics = AsyncMock(return_value={"ok": True})
    registry.get_evaluation_metrics = AsyncMock(return_value={})
    registry.get_model_family = AsyncMock(return_value=[])
    registry.list_external_jobs = AsyncMock(return_value=[])
    registry.transition_model_state = AsyncMock(return_value={"state": "prod"})

    voice_svc = MagicMock()
    voice_svc.create_voice_profile = AsyncMock(return_value={"id": "vp-1"})
    voice_svc.identify_speaker = AsyncMock(return_value={"speaker": "s"})
    voice_svc.detect_emotion = MagicMock(
        return_value={"emotion": "happy", "confidence": 0.9}
    )
    voice_svc.log_emotion = AsyncMock()
    voice_svc.get_emotion_trends = AsyncMock(return_value=[])

    monkeypatch.setattr(mod, "training_service", training)
    monkeypatch.setattr(mod, "registry", registry)
    monkeypatch.setattr(mod, "voice_svc", voice_svc)

    import api.services.db_ai_platform as dap

    monkeypatch.setattr(dap, "list_models_db", AsyncMock(return_value=[]))
    monkeypatch.setattr(dap, "list_datasets_db", AsyncMock(return_value=[]))
    monkeypatch.setattr(dap, "get_dataset_db", AsyncMock(return_value={"id": "ds-1"}))
    monkeypatch.setattr(dap, "list_turns_db", AsyncMock(return_value=[]))
    monkeypatch.setattr(dap, "create_label_db", AsyncMock(return_value={"id": "lab-1"}))
    monkeypatch.setattr(dap, "list_labels_db", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        dap, "list_voice_profiles_db", AsyncMock(return_value=[])
    )

    import api.services.model_registry as mr

    monkeypatch.setattr(mr, "get_model_audit_log", AsyncMock(return_value=[]))

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[verify_tenant_access] = lambda: "tenant-1"
    client = TestClient(app)

    yield client, training, registry, voice_svc
    client.close()


def test_collect_training_data(ctx):
    client, training, _, _ = ctx
    resp = client.post(
        "/ai-platform/training/collect?start_date=2026-01-01&end_date=2026-01-02"
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    training.collect_training_data.assert_awaited_once()


def test_create_training_job_success_and_failure(ctx):
    client, training, _, _ = ctx
    ok = client.post(
        "/ai-platform/training/jobs",
        json={"name": "job", "model_base": "gpt", "hyperparams": {}},
    )
    assert ok.status_code == 200
    assert ok.json()["id"] == "job-1"

    training.create_training_job = AsyncMock(return_value=None)
    bad = client.post(
        "/ai-platform/training/jobs",
        json={"name": "job", "model_base": "gpt", "hyperparams": {}},
    )
    assert bad.status_code == 400


def test_list_and_get_training_jobs(ctx):
    client, training, _, _ = ctx
    assert client.get("/ai-platform/training/jobs").status_code == 200
    assert client.get("/ai-platform/training/jobs/job-1").status_code == 200
    training.list_training_jobs.assert_awaited_once()
    training.get_training_status.assert_awaited_once_with("job-1")


def test_export_training_data(ctx):
    client, training, _, _ = ctx
    resp = client.get("/ai-platform/training/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    training.export_for_fine_tuning.assert_awaited_once()


def test_register_model_success_and_failure(ctx):
    client, _, registry, _ = ctx
    ok = client.post(
        "/ai-platform/models",
        json={"name": "m", "version": "1.0", "model_type": "intent", "config": {}, "metrics": {}},
    )
    assert ok.status_code == 200

    registry.register_model = AsyncMock(return_value=None)
    bad = client.post(
        "/ai-platform/models",
        json={"name": "m", "version": "1.0", "model_type": "intent", "config": {}, "metrics": {}},
    )
    assert bad.status_code == 400


def test_list_models_and_versions(ctx):
    client, _, registry, _ = ctx
    assert client.get("/ai-platform/models").status_code == 200
    assert client.get("/ai-platform/models?model_type=intent").status_code == 200
    assert client.get("/ai-platform/models/m-1/versions").status_code == 200
    registry.get_models.assert_awaited()


def test_promote_and_rollback_model(ctx):
    client, _, registry, _ = ctx
    ok = client.post("/ai-platform/models/m-1/versions/1.0/promote")
    assert ok.status_code == 200

    registry.promote_model = AsyncMock(return_value=None)
    not_found = client.post("/ai-platform/models/m-1/versions/1.0/promote")
    assert not_found.status_code == 404

    assert client.post("/ai-platform/models/m-1/versions/1.0/rollback").status_code == 200
    registry.rollback_model = AsyncMock(return_value=None)
    assert client.post("/ai-platform/models/m-1/versions/1.0/rollback").status_code == 404


def test_active_models(ctx):
    client, _, registry, _ = ctx
    resp = client.get("/ai-platform/models/active?model_type=intent")
    assert resp.status_code == 200
    resp_all = client.get("/ai-platform/models/active")
    assert resp_all.status_code == 200
    assert registry.get_active_model.await_count == 3


def test_compare_models(ctx):
    client, _, registry, _ = ctx
    resp = client.get("/ai-platform/models/compare?model_id=m-1&version_a=1&version_b=2")
    assert resp.status_code == 200
    registry.compare_models.assert_awaited()


def test_create_dataset(ctx):
    client, training, _, _ = ctx
    resp = client.post(
        "/ai-platform/datasets",
        json={"name": "ds", "recipe_type": "qa", "source_start_date": "2026-01-01", "source_end_date": "2026-01-02"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == "ds-1"
    training.create_dataset.assert_awaited()


def test_list_and_get_datasets(ctx):
    client, _, _, _ = ctx
    import api.services.db_ai_platform as dap

    dap.get_dataset_db = AsyncMock(
        side_effect=lambda did: {"id": "ds-1"} if did == "ds-1" else None
    )
    assert client.get("/ai-platform/datasets").status_code == 200
    assert client.get("/ai-platform/datasets/ds-1").status_code == 200
    assert client.get("/ai-platform/datasets/missing").status_code == 404


def test_turns_and_labels(ctx):
    client, _, _, _ = ctx
    assert client.get("/ai-platform/datasets/ds-1/turns").status_code == 200
    ok = client.post(
        "/ai-platform/turns/turn-1/labels",
        json={"turn_id": "turn-1", "label_type": "intent", "label_value": "billing", "confidence": 0.9, "notes": ""},
    )
    assert ok.status_code == 200
    assert client.get("/ai-platform/turns/turn-1/labels").status_code == 200

    import api.services.db_ai_platform as dap

    dap.create_label_db = AsyncMock(return_value=None)
    bad = client.post(
        "/ai-platform/turns/turn-1/labels",
        json={"turn_id": "turn-1", "label_type": "intent", "label_value": "billing"},
    )
    assert bad.status_code == 400


def test_external_jobs(ctx):
    client, training, _, _ = ctx
    ok = client.post(
        "/ai-platform/training/external-jobs",
        json={"dataset_id": "ds-1", "model_name": "m", "hyperparams": {}, "provider": "openai"},
    )
    assert ok.status_code == 200
    assert client.get("/ai-platform/training/external-jobs/ej-1").status_code == 200
    assert client.post("/ai-platform/training/external-jobs/ej-1/cancel").status_code == 200


def test_eval_metrics(ctx):
    client, _, registry, _ = ctx
    ok = client.post(
        "/ai-platform/models/eval-metrics",
        json={"model_id": "m-1", "version": "1.0", "metrics": {}},
    )
    assert ok.status_code == 200
    registry.ingest_evaluation_metrics = AsyncMock(return_value=None)
    assert client.post(
        "/ai-platform/models/eval-metrics",
        json={"model_id": "m-1", "version": "1.0", "metrics": {}},
    ).status_code == 400
    assert client.get("/ai-platform/models/m-1/eval-metrics/1.0").status_code == 200


def test_model_audit_and_family(ctx):
    client, _, _, _ = ctx
    assert client.get("/ai-platform/models/m-1/audit-log").status_code == 200
    assert client.get("/ai-platform/models/family/intent").status_code == 200
    assert client.get("/ai-platform/models/m-1/external-jobs").status_code == 200


def test_transition_model_state(ctx):
    client, _, registry, _ = ctx
    ok = client.post("/ai-platform/models/m-1/versions/1.0/transition?new_state=prod")
    assert ok.status_code == 200

    registry.transition_model_state = AsyncMock(return_value=None)
    # The endpoint raises 404 inside the try, which its broad except converts to 400.
    assert client.post("/ai-platform/models/m-1/versions/1.0/transition?new_state=prod").status_code == 400

    registry.transition_model_state = AsyncMock(side_effect=RuntimeError("boom"))
    bad = client.post("/ai-platform/models/m-1/versions/1.0/transition?new_state=prod")
    assert bad.status_code == 400


def test_voice_profiles(ctx):
    client, _, _, voice_svc = ctx
    ok = client.post(
        "/ai-platform/voice-profiles",
        json={"speaker_name": "Alice", "features": {"mfcc": [0.1, 0.2]}},
    )
    assert ok.status_code == 200
    assert client.get("/ai-platform/voice-profiles").status_code == 200

    voice_svc.create_voice_profile = AsyncMock(return_value=None)
    bad = client.post(
        "/ai-platform/voice-profiles",
        json={"speaker_name": "Alice", "features": {"mfcc": [0.1, 0.2]}},
    )
    assert bad.status_code == 400


def test_identify_speaker(ctx):
    client, _, _, voice_svc = ctx
    resp = client.post("/ai-platform/voice-profiles/identify", json={"audio_sample": [0.5]})
    assert resp.status_code == 200
    assert resp.json()["speaker"] == "s"
    voice_svc.identify_speaker.assert_awaited_once()


def test_detect_emotion_with_and_without_call(ctx):
    client, _, _, voice_svc = ctx
    resp = client.post("/ai-platform/voice-profiles/emotion", json={"audio_features": {"mfcc": [0.1]}, "call_id": "c-1"})
    assert resp.status_code == 200
    assert resp.json()["emotion"] == "happy"
    voice_svc.log_emotion.assert_awaited_once()

    resp2 = client.post("/ai-platform/voice-profiles/emotion", json={"audio_features": {"mfcc": [0.1]}})
    assert resp2.status_code == 200
    assert voice_svc.log_emotion.await_count == 1


def test_emotion_trends(ctx):
    client, _, _, voice_svc = ctx
    assert client.get("/ai-platform/voice-profiles/emotion-trends/c-1").status_code == 200
    voice_svc.get_emotion_trends.assert_awaited_once()



