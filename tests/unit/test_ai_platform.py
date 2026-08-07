"""Unit tests for src/api/routers/ai_platform.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.ai_platform import registry, router, training_service, voice_svc
from api.services.auth import verify_tenant_access


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)

    async def _override_tenant():
        return "TENANT-001"

    application.dependency_overrides[verify_tenant_access] = _override_tenant
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestTrainingEndpoints:
    def test_collect_training_data(self, client):
        with patch.object(
            training_service,
            "collect_training_data",
            new_callable=AsyncMock,
            return_value=[{"call_id": "c1"}],
        ) as mock_collect:
            resp = client.post(
                "/ai-platform/training/collect",
                params={"start_date": "2024-01-01", "end_date": "2024-01-02"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"total": 1, "examples": [{"call_id": "c1"}]}
        mock_collect.assert_awaited_once_with(
            "TENANT-001", "2024-01-01", "2024-01-02"
        )

    def test_collect_training_data_missing_query(self, client):
        resp = client.post("/ai-platform/training/collect")
        assert resp.status_code == 422

    def test_create_training_job(self, client):
        with patch.object(
            training_service,
            "create_training_job",
            new_callable=AsyncMock,
            return_value={"id": "job-1", "status": "pending"},
        ) as mock_create:
            resp = client.post(
                "/ai-platform/training/jobs",
                json={"name": "job1", "model_base": "llama-3.1-8b"},
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "job-1"
        assert mock_create.call_args.kwargs["name"] == "job1"

    def test_create_training_job_failed(self, client):
        with patch.object(
            training_service,
            "create_training_job",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/ai-platform/training/jobs", json={"name": "job1"}
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to create training job"

    def test_create_training_job_validation(self, client):
        resp = client.post("/ai-platform/training/jobs", json={})
        assert resp.status_code == 422

    def test_list_training_jobs(self, client):
        with patch.object(
            training_service,
            "list_training_jobs",
            new_callable=AsyncMock,
            return_value=[{"id": "job-1"}],
        ):
            resp = client.get("/ai-platform/training/jobs")
        assert resp.status_code == 200
        assert resp.json() == [{"id": "job-1"}]

    def test_get_training_job_status(self, client):
        with patch.object(
            training_service,
            "get_training_status",
            new_callable=AsyncMock,
            return_value={"id": "job-1", "status": "completed"},
        ) as mock_status:
            resp = client.get("/ai-platform/training/jobs/job-1")
        assert resp.status_code == 200
        assert mock_status.call_args.args[0] == "job-1"

    def test_export_training_data(self, client):
        with patch.object(
            training_service,
            "export_for_fine_tuning",
            new_callable=AsyncMock,
            return_value='{"a": 1}',
        ) as mock_export:
            resp = client.get(
                "/ai-platform/training/export", params={"format": "jsonl"}
            )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert mock_export.call_args.kwargs["format"] == "jsonl"


class TestModelRegistryEndpoints:
    def test_register_model(self, client):
        with patch.object(
            registry,
            "register_model",
            new_callable=AsyncMock,
            return_value={"id": "m1", "name": "n"},
        ) as mock_register:
            resp = client.post(
                "/ai-platform/models",
                json={"name": "n", "version": "1.0.0", "model_type": "intent"},
            )
        assert resp.status_code == 200
        assert mock_register.call_args.kwargs["name"] == "n"

    def test_register_model_failed(self, client):
        with patch.object(
            registry,
            "register_model",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/ai-platform/models",
                json={"name": "n", "version": "1.0.0"},
            )
        assert resp.status_code == 400

    def test_register_model_validation(self, client):
        resp = client.post("/ai-platform/models", json={})
        assert resp.status_code == 422

    def test_list_models(self, client):
        with patch.object(
            registry,
            "get_models",
            new_callable=AsyncMock,
            return_value=[{"id": "m1"}],
        ):
            resp = client.get("/ai-platform/models")
        assert resp.status_code == 200
        assert resp.json() == [{"id": "m1"}]

    def test_get_model_versions(self, client):
        with patch(
            "api.services.db_ai_platform.list_models_db",
            new_callable=AsyncMock,
            return_value=[{"id": "m1", "name": "n", "version": "1.0.0"}],
        ):
            resp = client.get("/ai-platform/models/m1/versions")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_promote_model(self, client):
        with patch.object(
            registry,
            "promote_model",
            new_callable=AsyncMock,
            return_value={"id": "m1", "status": "production"},
        ) as mock_promote:
            resp = client.post(
                "/ai-platform/models/m1/versions/1.0.0/promote",
                params={"environment": "staging"},
            )
        assert resp.status_code == 200
        assert mock_promote.call_args.args == ("TENANT-001", "m1", "1.0.0", "staging")

    def test_promote_model_not_found(self, client):
        with patch.object(
            registry,
            "promote_model",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post("/ai-platform/models/m1/versions/1.0.0/promote")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Model version not found"

    def test_rollback_model(self, client):
        with patch.object(
            registry,
            "rollback_model",
            new_callable=AsyncMock,
            return_value={"id": "m1", "status": "staging"},
        ):
            resp = client.post("/ai-platform/models/m1/versions/1.0.0/rollback")
        assert resp.status_code == 200

    def test_rollback_model_not_found(self, client):
        with patch.object(
            registry,
            "rollback_model",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post("/ai-platform/models/m1/versions/1.0.0/rollback")
        assert resp.status_code == 404

    def test_get_active_models_with_type(self, client):
        with patch.object(
            registry,
            "get_active_model",
            new_callable=AsyncMock,
            return_value={"id": "m1"},
        ) as mock_get:
            resp = client.get(
                "/ai-platform/models/active", params={"model_type": "intent"}
            )
        assert resp.status_code == 200
        assert resp.json() == {"id": "m1"}
        assert mock_get.call_args.args == ("TENANT-001", "intent")

    def test_get_active_models_default(self, client):
        with patch.object(
            registry,
            "get_active_model",
            new_callable=AsyncMock,
            side_effect=[{"id": "i1"}, None],
        ):
            resp = client.get("/ai-platform/models/active")
        assert resp.status_code == 200
        assert resp.json() == {"intent": {"id": "i1"}, "sentiment": {}}

    def test_compare_models(self, client):
        with patch.object(
            registry,
            "compare_models",
            new_callable=AsyncMock,
            return_value={"diff": {}},
        ) as mock_compare:
            resp = client.get(
                "/ai-platform/models/compare",
                params={"model_id": "m1", "version_a": "1.0.0", "version_b": "2.0.0"},
            )
        assert resp.status_code == 200
        assert mock_compare.call_args.args == ("TENANT-001", "m1", "1.0.0", "2.0.0")

    def test_compare_models_missing_query(self, client):
        resp = client.get("/ai-platform/models/compare")
        assert resp.status_code == 422

    def test_transition_model_state(self, client):
        with patch.object(
            registry,
            "transition_model_state",
            new_callable=AsyncMock,
            return_value={"id": "m1", "status": "training"},
        ):
            resp = client.post(
                "/ai-platform/models/m1/versions/1.0.0/transition",
                params={"new_state": "training"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "training"

    def test_transition_model_state_not_found(self, client):
        with patch.object(
            registry,
            "transition_model_state",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/ai-platform/models/m1/versions/1.0.0/transition",
                params={"new_state": "training"},
            )
        # The endpoint raises 404 inside a try/except that re-wraps any
        # Exception as a 400, so the observable behaviour is a 400.
        assert resp.status_code == 400
        assert resp.json()["detail"] == "404: Model version not found"

    def test_transition_model_state_exception(self, client):
        with patch.object(
            registry,
            "transition_model_state",
            new_callable=AsyncMock,
            side_effect=ValueError("Cannot transition"),
        ):
            resp = client.post(
                "/ai-platform/models/m1/versions/1.0.0/transition",
                params={"new_state": "bad"},
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Cannot transition"


class TestDatasetEndpoints:
    def test_create_dataset(self, client):
        with patch.object(
            training_service,
            "collect_training_data",
            new_callable=AsyncMock,
            return_value=[
                {"call_id": "c1", "transcript": "Hello there customer support"}
            ],
        ), patch(
            "api.services.ai_training.AITrainingService.generate_training_examples",
            return_value=[{"input": "ctx", "output": "turn"}],
        ), patch.object(
            training_service,
            "create_dataset",
            new_callable=AsyncMock,
            return_value={"id": "ds-1", "name": "d"},
        ) as mock_dataset:
            resp = client.post(
                "/ai-platform/datasets",
                json={"name": "d", "recipe_type": "dialogue"},
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "ds-1"
        assert mock_dataset.call_args.kwargs["examples"] == [{"input": "ctx", "output": "turn"}]

    def test_list_datasets(self, client):
        with patch(
            "api.services.db_ai_platform.list_datasets_db",
            new_callable=AsyncMock,
            return_value=[{"id": "ds-1"}],
        ) as mock_list:
            resp = client.get(
                "/ai-platform/datasets", params={"recipe_type": "dialogue", "limit": 10}
            )
        assert resp.status_code == 200
        assert mock_list.call_args.kwargs["recipe_type"] == "dialogue"
        assert mock_list.call_args.kwargs["limit"] == 10

    def test_get_dataset_found(self, client):
        with patch(
            "api.services.db_ai_platform.get_dataset_db",
            new_callable=AsyncMock,
            return_value={"id": "ds-1"},
        ):
            resp = client.get("/ai-platform/datasets/ds-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "ds-1"

    def test_get_dataset_not_found(self, client):
        with patch(
            "api.services.db_ai_platform.get_dataset_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/ai-platform/datasets/missing")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Dataset not found"


class TestTurnEndpoints:
    def test_list_turns(self, client):
        with patch(
            "api.services.db_ai_platform.list_turns_db",
            new_callable=AsyncMock,
            return_value=[{"id": "t1"}],
        ) as mock_list:
            resp = client.get(
                "/ai-platform/datasets/ds-1/turns",
                params={"limit": 10, "offset": 5},
            )
        assert resp.status_code == 200
        assert mock_list.call_args.kwargs["limit"] == 10
        assert mock_list.call_args.kwargs["offset"] == 5

    def test_create_label(self, client):
        with patch(
            "api.services.db_ai_platform.create_label_db",
            new_callable=AsyncMock,
            return_value={"id": "l1"},
        ) as mock_create:
            resp = client.post(
                "/ai-platform/turns/t1/labels",
                json={
                    "turn_id": "t1",
                    "label_type": "intent",
                    "label_value": "billing",
                },
            )
        assert resp.status_code == 200
        assert mock_create.call_args.kwargs["confidence"] == 1.0

    def test_create_label_failed(self, client):
        with patch(
            "api.services.db_ai_platform.create_label_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/ai-platform/turns/t1/labels",
                json={
                    "turn_id": "t1",
                    "label_type": "intent",
                    "label_value": "billing",
                },
            )
        assert resp.status_code == 400

    def test_list_labels(self, client):
        with patch(
            "api.services.db_ai_platform.list_labels_db",
            new_callable=AsyncMock,
            return_value=[{"id": "l1"}],
        ):
            resp = client.get("/ai-platform/turns/t1/labels")
        assert resp.status_code == 200
        assert resp.json() == [{"id": "l1"}]


class TestExternalJobEndpoints:
    def test_submit_external_job(self, client):
        with patch.object(
            training_service,
            "submit_external_job",
            new_callable=AsyncMock,
            return_value={"external_job_id": "e1", "status": "submitted"},
        ) as mock_submit:
            resp = client.post(
                "/ai-platform/training/external-jobs",
                json={
                    "dataset_id": "ds-1",
                    "model_name": "llama",
                    "hyperparams": {"epochs": 3},
                    "provider": "modal",
                },
            )
        assert resp.status_code == 200
        assert mock_submit.call_args.kwargs["provider"] == "modal"

    def test_get_external_job_status(self, client):
        with patch.object(
            training_service,
            "get_external_job_status",
            new_callable=AsyncMock,
            return_value={"status": "running"},
        ):
            resp = client.get("/ai-platform/training/external-jobs/e1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_cancel_external_job(self, client):
        with patch.object(
            training_service,
            "cancel_external_job",
            new_callable=AsyncMock,
            return_value={"status": "cancelled"},
        ):
            resp = client.post("/ai-platform/training/external-jobs/e1/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"


class TestEvalMetricsEndpoints:
    def test_ingest_eval_metrics(self, client):
        with patch.object(
            registry,
            "ingest_evaluation_metrics",
            new_callable=AsyncMock,
            return_value={"id": "e1"},
        ) as mock_ingest:
            resp = client.post(
                "/ai-platform/models/eval-metrics",
                json={"model_id": "m1", "version": "1.0.0", "metrics": {"acc": 0.9}},
            )
        assert resp.status_code == 200
        assert mock_ingest.call_args.kwargs["metrics"] == {"acc": 0.9}

    def test_ingest_eval_metrics_failed(self, client):
        with patch.object(
            registry,
            "ingest_evaluation_metrics",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/ai-platform/models/eval-metrics",
                json={"model_id": "m1", "version": "1.0.0", "metrics": {}},
            )
        assert resp.status_code == 400

    def test_get_eval_metrics(self, client):
        with patch.object(
            registry,
            "get_evaluation_metrics",
            new_callable=AsyncMock,
            return_value=[{"acc": 0.9}],
        ):
            resp = client.get("/ai-platform/models/m1/eval-metrics/1.0.0")
        assert resp.status_code == 200
        assert resp.json() == [{"acc": 0.9}]


class TestAuditAndFamilyEndpoints:
    def test_get_model_audit_log(self, client):
        with patch(
            "api.services.model_registry.get_model_audit_log",
            new_callable=AsyncMock,
            return_value=[{"action": "registered"}],
        ):
            resp = client.get("/ai-platform/models/m1/audit-log")
        assert resp.status_code == 200
        assert resp.json() == [{"action": "registered"}]

    def test_get_model_family(self, client):
        with patch.object(
            registry,
            "get_model_family",
            new_callable=AsyncMock,
            return_value=[{"model_type": "llm"}],
        ) as mock_family:
            resp = client.get("/ai-platform/models/family/llm")
        assert resp.status_code == 200
        assert mock_family.call_args.args == ("TENANT-001", "llm")

    def test_list_model_external_jobs(self, client):
        with patch.object(
            registry,
            "list_external_jobs",
            new_callable=AsyncMock,
            return_value=[{"id": "j1"}],
        ):
            resp = client.get("/ai-platform/models/m1/external-jobs")
        assert resp.status_code == 200
        assert resp.json() == [{"id": "j1"}]


class TestVoiceBiometricsEndpoints:
    def test_create_voice_profile(self, client):
        with patch.object(
            voice_svc,
            "create_voice_profile",
            new_callable=AsyncMock,
            return_value={"id": "vp-1"},
        ) as mock_create:
            resp = client.post(
                "/ai-platform/voice-profiles",
                json={"speaker_name": "Alice", "features": {"mfcc": [1.0]}},
            )
        assert resp.status_code == 200
        assert mock_create.call_args.kwargs["speaker_name"] == "Alice"

    def test_create_voice_profile_failed(self, client):
        with patch.object(
            voice_svc,
            "create_voice_profile",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/ai-platform/voice-profiles",
                json={"speaker_name": "Alice"},
            )
        assert resp.status_code == 400

    def test_list_voice_profiles(self, client):
        with patch(
            "api.services.db_ai_platform.list_voice_profiles_db",
            new_callable=AsyncMock,
            return_value=[{"id": "vp-1"}],
        ):
            resp = client.get("/ai-platform/voice-profiles")
        assert resp.status_code == 200
        assert resp.json() == [{"id": "vp-1"}]

    def test_identify_speaker(self, client):
        with patch.object(
            voice_svc,
            "identify_speaker",
            new_callable=AsyncMock,
            return_value=[{"speaker": "Alice", "match": True}],
        ) as mock_identify:
            resp = client.post(
                "/ai-platform/voice-profiles/identify",
                json={"audio_sample": {"features": {"mfcc": [1.0]}}},
            )
        assert resp.status_code == 200
        assert mock_identify.call_args.args[1] == {"features": {"mfcc": [1.0]}}

    def test_identify_speaker_fallback_to_dict(self, client):
        with patch.object(
            voice_svc,
            "identify_speaker",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_identify:
            resp = client.post(
                "/ai-platform/voice-profiles/identify",
                json={"mfcc": [1.0]},
            )
        assert resp.status_code == 200
        assert mock_identify.call_args.args[1] == {"mfcc": [1.0]}

    def test_detect_emotion_no_call_id(self, client):
        with patch.object(
            voice_svc,
            "detect_emotion",
            return_value={"emotion": "happy", "confidence": 0.8},
        ), patch.object(
            voice_svc,
            "log_emotion",
            new_callable=AsyncMock,
        ) as mock_log:
            resp = client.post(
                "/ai-platform/voice-profiles/emotion",
                json={"audio_features": {"text": "awesome"}},
            )
        assert resp.status_code == 200
        assert resp.json()["emotion"] == "happy"
        mock_log.assert_not_awaited()

    def test_detect_emotion_with_call_id(self, client):
        with patch.object(
            voice_svc,
            "detect_emotion",
            return_value={"emotion": "happy", "confidence": 0.8},
        ), patch.object(
            voice_svc,
            "log_emotion",
            new_callable=AsyncMock,
        ) as mock_log:
            resp = client.post(
                "/ai-platform/voice-profiles/emotion",
                json={"call_id": "call-1", "audio_features": {"text": "awesome"}},
            )
        assert resp.status_code == 200
        assert mock_log.call_args.kwargs["call_id"] == "call-1"
        assert mock_log.call_args.kwargs["emotion"] == "happy"

    def test_get_emotion_trends(self, client):
        with patch.object(
            voice_svc,
            "get_emotion_trends",
            new_callable=AsyncMock,
            return_value=[{"emotion": "happy"}],
        ) as mock_trends:
            resp = client.get("/ai-platform/voice-profiles/emotion-trends/call-1")
        assert resp.status_code == 200
        assert mock_trends.call_args.args == ("TENANT-001", "call-1")
