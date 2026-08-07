"""Unit tests for api.routers.voice_quality."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.models.dto import VoiceQualityMetricCreate
from api.routers import voice_quality
from api.routers.voice_quality import record_metric, router
from api.services.auth import verify_tenant_access


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)

    async def _override_verify_tenant_access(tenant_id: str = "TENANT-001"):
        return tenant_id

    app.dependency_overrides[verify_tenant_access] = _override_verify_tenant_access
    with TestClient(app) as c:
        yield c


class TestRecordMetric:
    def test_success_with_explicit_mos(self, client):
        scoring = {"quality_rating": "good", "recommendations": ["some advice"]}
        with patch(
            "api.routers.voice_quality.score_call_quality",
            return_value=scoring,
        ) as score_mock, patch(
            "api.routers.voice_quality.calculate_mos",
            new_callable=AsyncMock,
        ) as mos_mock, patch(
            "api.routers.voice_quality.create_quality_metric_db",
            new_callable=AsyncMock,
            return_value={"id": "m1", "call_id": "C1"},
        ) as create_mock:
            resp = client.post(
                "/voice-quality/metrics",
                json={
                    "call_id": "C1",
                    "agent_id": "A1",
                    "mos": 3.8,
                    "jitter_ms": 20.0,
                    "packet_loss_pct": 2.0,
                    "latency_ms": 150.0,
                    "rtt_samples": [10.0, 12.0],
                    "codec": "opus",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "m1"
        assert body["recommendations"] == ["some advice"]
        mos_mock.assert_not_called()
        score_mock.assert_called_once_with(3.8, 20.0, 2.0, 150.0)
        create_mock.assert_awaited_once_with(
            "TENANT-001",
            "C1",
            "A1",
            3.8,
            20.0,
            2.0,
            150.0,
            [10.0, 12.0],
            "opus",
            "good",
        )

    def test_computed_mos_branch(self):
        """mos <= 0 (constructed model bypassing validation) uses calculate_mos."""
        scoring = {"quality_rating": "fair", "recommendations": []}
        data = VoiceQualityMetricCreate.model_construct(
            call_id="C1",
            agent_id=None,
            mos=0.0,
            jitter_ms=5.0,
            packet_loss_pct=1.0,
            latency_ms=100.0,
            rtt_samples=[],
            codec="opus",
        )
        with patch(
            "api.routers.voice_quality.calculate_mos", return_value=3.2
        ) as mos_mock, patch(
            "api.routers.voice_quality.score_call_quality",
            return_value=scoring,
        ), patch(
            "api.routers.voice_quality.create_quality_metric_db",
            new_callable=AsyncMock,
            return_value={"id": "m2"},
        ) as create_mock:
            import asyncio

            asyncio.run(record_metric(data, tenant_id="TENANT-001"))

        mos_mock.assert_called_once_with(100.0, 5.0, 1.0)
        create_mock.assert_awaited_once_with(
            "TENANT-001",
            "C1",
            None,
            3.2,
            5.0,
            1.0,
            100.0,
            [],
            "opus",
            "fair",
        )

    def test_create_metric_failure_400(self, client):
        with patch(
            "api.routers.voice_quality.score_call_quality",
            return_value={"quality_rating": "good", "recommendations": []},
        ), patch(
            "api.routers.voice_quality.create_quality_metric_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/voice-quality/metrics",
                json={
                    "call_id": "C1",
                    "mos": 4.0,
                    "jitter_ms": 0.0,
                    "packet_loss_pct": 0.0,
                    "latency_ms": 0.0,
                },
            )
        assert resp.status_code == 400
        assert resp.json() == {"detail": "Failed to record quality metric"}

    def test_validation_error_422(self, client):
        resp = client.post(
            "/voice-quality/metrics",
            json={"call_id": "C1", "mos": 0.5, "jitter_ms": -1},
        )
        assert resp.status_code == 422


class TestListMetrics:
    def test_defaults(self, client):
        with patch(
            "api.routers.voice_quality.list_quality_metrics_db",
            new_callable=AsyncMock,
            return_value=[{"id": "m1"}],
        ) as m:
            resp = client.get("/voice-quality/metrics")
        assert resp.status_code == 200
        assert resp.json() == [{"id": "m1"}]
        m.assert_awaited_once_with(
            "TENANT-001",
            limit=50,
            offset=0,
            min_mos=None,
            start_date=None,
            end_date=None,
        )

    def test_with_filters(self, client):
        with patch(
            "api.routers.voice_quality.list_quality_metrics_db",
            new_callable=AsyncMock,
            return_value=[],
        ) as m:
            resp = client.get(
                "/voice-quality/metrics?limit=10&offset=5&min_mos=3.5&start_date=2026-01-01&end_date=2026-01-31"
            )
        assert resp.status_code == 200
        m.assert_awaited_once_with(
            "TENANT-001",
            limit=10,
            offset=5,
            min_mos=3.5,
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

    def test_invalid_limit_422(self, client):
        resp = client.get("/voice-quality/metrics?limit=0")
        assert resp.status_code == 422


class TestGetSummary:
    def test_success(self, client):
        with patch(
            "api.routers.voice_quality.get_quality_summary_db",
            new_callable=AsyncMock,
            return_value={"avg_mos": 4.1},
        ) as m:
            resp = client.get("/voice-quality/summary")
        assert resp.status_code == 200
        assert resp.json() == {"avg_mos": 4.1}
        m.assert_awaited_once_with(
            "TENANT-001", start_date=None, end_date=None
        )


class TestGetTrends:
    def test_success(self, client):
        with patch(
            "api.routers.voice_quality.get_quality_trends_db",
            new_callable=AsyncMock,
            return_value=[{"hour": "h1"}],
        ) as m:
            resp = client.get("/voice-quality/trends?granularity=day")
        assert resp.status_code == 200
        assert resp.json() == [{"hour": "h1"}]
        m.assert_awaited_once_with(
            "TENANT-001", start_date=None, end_date=None, granularity="day"
        )

    def test_invalid_granularity_422(self, client):
        resp = client.get("/voice-quality/trends?granularity=week")
        assert resp.status_code == 422


class TestGetCallQuality:
    def test_success(self, client):
        with patch(
            "api.routers.voice_quality.get_call_quality_db",
            new_callable=AsyncMock,
            return_value={"call_id": "C1", "mos": 4.0},
        ) as m:
            resp = client.get("/voice-quality/calls/C1")
        assert resp.status_code == 200
        assert resp.json() == {"call_id": "C1", "mos": 4.0}
        m.assert_awaited_once_with("TENANT-001", "C1")

    def test_not_found_404(self, client):
        with patch(
            "api.routers.voice_quality.get_call_quality_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/voice-quality/calls/MISSING")
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Call quality metrics not found"}
