"""Tests for the AI ops router (evaluations, experiments, confidence)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.ai_ops import router
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


@pytest.fixture(autouse=True)
def _clear_thresholds():
    from api.routers import ai_ops
    before = dict(ai_ops._tenant_thresholds)
    ai_ops._tenant_thresholds.clear()
    yield
    ai_ops._tenant_thresholds.clear()
    ai_ops._tenant_thresholds.update(before)


class TestRecordEvaluation:
    def test_record_correct_evaluation(self, client):
        with patch(
            "api.routers.ai_ops.create_evaluation_db",
            new_callable=AsyncMock,
            return_value={"id": "ev-1", "is_correct": 1},
        ) as mock_create:
            resp = client.post(
                "/ai-ops/evaluate",
                json={
                    "predicted_intent": "billing",
                    "actual_intent": "billing",
                    "confidence": 0.9,
                    "model_used": "deepseek-v4-flash",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "ev-1"
        assert mock_create.call_args.kwargs["is_correct"] == 1

    def test_record_incorrect_evaluation(self, client):
        with patch(
            "api.routers.ai_ops.create_evaluation_db",
            new_callable=AsyncMock,
            return_value={"id": "ev-2", "is_correct": 0},
        ) as mock_create:
            resp = client.post(
                "/ai-ops/evaluate",
                json={"predicted_intent": "billing", "actual_intent": "support", "confidence": 0.6},
            )
        assert resp.status_code == 200
        assert mock_create.call_args.kwargs["is_correct"] == 0

    def test_record_evaluation_failed(self, client):
        with patch(
            "api.routers.ai_ops.create_evaluation_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/ai-ops/evaluate",
                json={"predicted_intent": "billing", "confidence": 0.5},
            )
        assert resp.status_code == 400

    def test_record_evaluation_validation(self, client):
        # confidence > 1.0 rejected
        resp = client.post(
            "/ai-ops/evaluate",
            json={"predicted_intent": "x", "confidence": 1.5},
        )
        assert resp.status_code == 422


class TestGetAccuracy:
    def test_get_accuracy(self, client):
        with patch(
            "api.routers.ai_ops.get_accuracy_metrics_db",
            new_callable=AsyncMock,
            return_value={"accuracy": 0.85, "total": 100},
        ):
            resp = client.get("/ai-ops/accuracy")
        assert resp.status_code == 200
        assert resp.json()["accuracy"] == 0.85


class TestExperiments:
    def test_create_experiment(self, client):
        with patch(
            "api.routers.ai_ops.create_experiment_db",
            new_callable=AsyncMock,
            return_value={"id": "exp-1", "name": "A/B test"},
        ) as mock_create:
            resp = client.post(
                "/ai-ops/experiments",
                json={"name": "A/B test", "model_a": "v3", "model_b": "v4", "traffic_split": 0.5},
            )
        assert resp.status_code == 200
        assert mock_create.call_args.kwargs["traffic_split"] == 0.5

    def test_create_experiment_validation(self, client):
        resp = client.post("/ai-ops/experiments", json={"name": "", "model_a": "a", "model_b": "b"})
        assert resp.status_code == 422

    def test_list_experiments(self, client):
        with patch(
            "api.routers.ai_ops.list_experiments_db",
            new_callable=AsyncMock,
            return_value=[{"id": "exp-1"}],
        ):
            resp = client.get("/ai-ops/experiments")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_experiment_found(self, client):
        with patch(
            "api.routers.ai_ops.get_experiment_db",
            new_callable=AsyncMock,
            return_value={"id": "exp-1", "name": "A/B", "model_a": "v3", "model_b": "v4"},
        ), patch(
            "api.routers.ai_ops.list_evaluations_db",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.get("/ai-ops/experiments/exp-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "exp-1"

    def test_get_experiment_not_found(self, client):
        with patch(
            "api.routers.ai_ops.get_experiment_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/ai-ops/experiments/missing")
        assert resp.status_code == 404

    def test_stop_experiment(self, client):
        with patch(
            "api.routers.ai_ops.get_experiment_db",
            new_callable=AsyncMock,
            return_value={"id": "exp-1", "status": "active", "model_a": "v3", "model_b": "v4"},
        ), patch(
            "api.routers.ai_ops.list_evaluations_db",
            new_callable=AsyncMock,
            return_value=[
                {"model_used": "v3", "is_correct": True},
                {"model_used": "v4", "is_correct": False},
            ],
        ), patch(
            "api.routers.ai_ops.update_experiment_db",
            new_callable=AsyncMock,
            return_value={"id": "exp-1", "status": "stopped", "winner": "v3"},
        ) as mock_stop:
            resp = client.post("/ai-ops/experiments/exp-1/stop")
        assert resp.status_code == 200
        assert mock_stop.call_args.kwargs["status"] == "stopped"
        assert mock_stop.call_args.kwargs["winner"] == "v3"

    def test_stop_experiment_not_active(self, client):
        with patch(
            "api.routers.ai_ops.get_experiment_db",
            new_callable=AsyncMock,
            return_value={"id": "exp-1", "status": "stopped", "model_a": "a", "model_b": "b"},
        ):
            resp = client.post("/ai-ops/experiments/exp-1/stop")
        assert resp.status_code == 400

    def test_stop_experiment_not_found(self, client):
        with patch(
            "api.routers.ai_ops.get_experiment_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post("/ai-ops/experiments/missing/stop")
        assert resp.status_code == 404


class TestConfidence:
    def test_set_threshold(self, client):
        resp = client.post(
            "/ai-ops/confidence/thresholds",
            json={"proceed": 0.9, "review": 0.6, "escalate": 0.1},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["thresholds"]["proceed"] == 0.9

    def test_get_default_threshold(self, client):
        resp = client.get("/ai-ops/confidence/thresholds")
        assert resp.status_code == 200
        assert resp.json()["proceed"] == 0.8

    def test_set_threshold_validation(self, client):
        resp = client.post(
            "/ai-ops/confidence/thresholds",
            json={"proceed": 1.5},
        )
        assert resp.status_code == 422

    def test_get_confidence_distribution(self, client):
        with patch(
            "api.routers.ai_ops.get_confidence_distribution_db",
            new_callable=AsyncMock,
            return_value={"high": 5, "low": 2},
        ):
            resp = client.get("/ai-ops/confidence/distribution")
        assert resp.status_code == 200
        assert resp.json()["high"] == 5
