"""Unit tests for api.routers.wfm_final."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import wfm_final as wfm_final_module
from api.services.auth import verify_tenant_access


@pytest.fixture
def app():
    from api.routers.wfm_final import router

    application = FastAPI()
    application.include_router(router)

    async def _override_tenant():
        return "tenant-1"

    application.dependency_overrides[verify_tenant_access] = _override_tenant
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestMetrics:
    def test_track_aht_success(self, client):
        with patch.object(
            wfm_final_module.wfm_metrics_service,
            "track_aht",
            new=AsyncMock(return_value={"call_id": "c1"}),
        ) as mock_track:
            resp = client.post(
                "/wfm-final/metrics/aht",
                json={"call_id": "c1", "agent_id": "a1", "duration_seconds": 120},
            )

        assert resp.status_code == 200
        assert resp.json() == {"call_id": "c1"}
        mock_track.assert_called_once_with("c1", "a1", 120, "tenant-1")

    def test_track_aht_failure(self, client):
        with patch.object(
            wfm_final_module.wfm_metrics_service, "track_aht", new=AsyncMock(return_value=None)
        ):
            resp = client.post(
                "/wfm-final/metrics/aht",
                json={"call_id": "c1", "agent_id": "a1", "duration_seconds": 120},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to track AHT"

    def test_track_fcr_success(self, client):
        with patch.object(
            wfm_final_module.wfm_metrics_service,
            "track_fcr",
            new=AsyncMock(return_value={"call_id": "c1"}),
        ) as mock_track:
            resp = client.post(
                "/wfm-final/metrics/fcr",
                json={
                    "call_id": "c1",
                    "customer_id": "cust-1",
                    "resolved": True,
                    "follow_up_call_id": "c2",
                },
            )

        assert resp.status_code == 200
        mock_track.assert_called_once_with("c1", "cust-1", True, "tenant-1", "c2")

    def test_track_fcr_without_follow_up(self, client):
        with patch.object(
            wfm_final_module.wfm_metrics_service,
            "track_fcr",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_track:
            resp = client.post(
                "/wfm-final/metrics/fcr",
                json={"call_id": "c1", "customer_id": "cust-1", "resolved": False},
            )

        assert resp.status_code == 200
        mock_track.assert_called_once_with("c1", "cust-1", False, "tenant-1", None)

    def test_track_fcr_failure(self, client):
        with patch.object(
            wfm_final_module.wfm_metrics_service, "track_fcr", new=AsyncMock(return_value=None)
        ):
            resp = client.post(
                "/wfm-final/metrics/fcr",
                json={"call_id": "c1", "customer_id": "cust-1", "resolved": True},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to track FCR"

    def test_track_csat_success(self, client):
        with patch.object(
            wfm_final_module.wfm_metrics_service,
            "track_csat",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_track:
            resp = client.post(
                "/wfm-final/metrics/csat",
                json={"call_id": "c1", "customer_id": "cust-1", "rating": 4},
            )

        assert resp.status_code == 200
        mock_track.assert_called_once_with("c1", "cust-1", 4, "tenant-1")

    def test_track_csat_validation_fails(self, client):
        resp = client.post(
            "/wfm-final/metrics/csat",
            json={"call_id": "c1", "customer_id": "cust-1", "rating": 6},
        )
        assert resp.status_code == 422

    def test_track_csat_failure(self, client):
        with patch.object(
            wfm_final_module.wfm_metrics_service, "track_csat", new=AsyncMock(return_value=None)
        ):
            resp = client.post(
                "/wfm-final/metrics/csat",
                json={"call_id": "c1", "customer_id": "cust-1", "rating": 3},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to track CSAT"

    def test_track_nps_success(self, client):
        with patch.object(
            wfm_final_module.wfm_metrics_service,
            "track_nps",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_track:
            resp = client.post(
                "/wfm-final/metrics/nps",
                json={"call_id": "c1", "customer_id": "cust-1", "score": 9},
            )

        assert resp.status_code == 200
        mock_track.assert_called_once_with("c1", "cust-1", 9, "tenant-1")

    def test_track_nps_validation_fails(self, client):
        resp = client.post(
            "/wfm-final/metrics/nps",
            json={"call_id": "c1", "customer_id": "cust-1", "score": 11},
        )
        assert resp.status_code == 422

    def test_track_nps_failure(self, client):
        with patch.object(
            wfm_final_module.wfm_metrics_service, "track_nps", new=AsyncMock(return_value=None)
        ):
            resp = client.post(
                "/wfm-final/metrics/nps",
                json={"call_id": "c1", "customer_id": "cust-1", "score": 5},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to track NPS"

    def test_get_metrics_summary(self, client):
        with (
            patch.object(
                wfm_final_module.wfm_metrics_service,
                "get_aht_stats",
                new=AsyncMock(return_value={"avg": 100}),
            ),
            patch.object(
                wfm_final_module.wfm_metrics_service,
                "get_fcr_rate",
                new=AsyncMock(return_value={"rate": 0.8}),
            ),
            patch.object(
                wfm_final_module.wfm_metrics_service,
                "get_csat_trend",
                new=AsyncMock(return_value=[{"rating": 4}]),
            ),
            patch.object(
                wfm_final_module.wfm_metrics_service,
                "get_nps_score",
                new=AsyncMock(return_value={"score": 70}),
            ),
        ):
            resp = client.get("/wfm-final/metrics/summary?period=30d")

        assert resp.status_code == 200
        body = resp.json()
        assert body["aht"] == {"avg": 100}
        assert body["fcr"] == {"rate": 0.8}
        assert body["csat_trend"] == [{"rating": 4}]
        assert body["nps"] == {"score": 70}

    def test_get_metrics_summary_invalid_period(self, client):
        resp = client.get("/wfm-final/metrics/summary?period=1d")
        assert resp.status_code == 422


class TestWallboard:
    def test_get_wallboard(self, client):
        with patch.object(
            wfm_final_module.supervisor_service,
            "get_wallboard_data",
            new=AsyncMock(return_value={"active_calls": 3}),
        ) as mock_wb:
            resp = client.get("/wfm-final/wallboard")

        assert resp.status_code == 200
        assert resp.json() == {"active_calls": 3}
        mock_wb.assert_called_once_with("tenant-1")

    def test_get_wallboard_agents(self, client):
        with patch.object(
            wfm_final_module.supervisor_service,
            "get_live_agent_status",
            new=AsyncMock(return_value=[{"id": "a1"}]),
        ) as mock_agents:
            resp = client.get("/wfm-final/wallboard/agents")

        assert resp.status_code == 200
        assert resp.json() == [{"id": "a1"}]
        mock_agents.assert_called_once_with("tenant-1")

    def test_get_team_performance(self, client):
        with patch.object(
            wfm_final_module.supervisor_service,
            "get_team_performance",
            new=AsyncMock(return_value={"agents": [], "total_agents": 0}),
        ) as mock_team:
            resp = client.get("/wfm-final/wallboard/team?period=30d")

        assert resp.status_code == 200
        mock_team.assert_called_once_with("tenant-1", "30d")

    def test_get_team_performance_default_period(self, client):
        with patch.object(
            wfm_final_module.supervisor_service,
            "get_team_performance",
            new=AsyncMock(return_value={"agents": [], "total_agents": 0}),
        ) as mock_team:
            resp = client.get("/wfm-final/wallboard/team")

        assert resp.status_code == 200
        mock_team.assert_called_once_with("tenant-1", "7d")

    def test_get_wallboard_alerts(self, client):
        with patch.object(
            wfm_final_module.supervisor_service,
            "get_recent_alerts",
            new=AsyncMock(return_value=[{"type": "sla_breach"}]),
        ) as mock_alerts:
            resp = client.get("/wfm-final/wallboard/alerts")

        assert resp.status_code == 200
        assert resp.json() == [{"type": "sla_breach"}]
        mock_alerts.assert_called_once_with("tenant-1")


class TestTraining:
    def test_list_courses(self, client):
        with patch.object(
            wfm_final_module.training_service,
            "list_courses",
            new=AsyncMock(return_value=[{"id": "course-1"}]),
        ) as mock_list:
            resp = client.get("/wfm-final/training/courses")

        assert resp.status_code == 200
        assert resp.json() == [{"id": "course-1"}]
        mock_list.assert_called_once_with("tenant-1")

    def test_create_course_success(self, client):
        with patch.object(
            wfm_final_module.training_service,
            "create_course",
            new=AsyncMock(return_value={"id": "course-1"}),
        ) as mock_create:
            resp = client.post(
                "/wfm-final/training/courses",
                json={
                    "title": "Refunds 101",
                    "description": "desc",
                    "modules": [{"id": "m1"}],
                    "duration_hours": 2.5,
                },
            )

        assert resp.status_code == 200
        mock_create.assert_called_once_with(
            "tenant-1", "Refunds 101", "desc", [{"id": "m1"}], 2.5
        )

    def test_create_course_failure(self, client):
        with patch.object(
            wfm_final_module.training_service, "create_course", new=AsyncMock(return_value=None)
        ):
            resp = client.post(
                "/wfm-final/training/courses", json={"title": "Refunds 101"}
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to create course"

    def test_enroll_agent_success(self, client):
        with patch.object(
            wfm_final_module.training_service,
            "enroll_agent",
            new=AsyncMock(return_value={"id": "enroll-1"}),
        ) as mock_enroll:
            resp = client.post(
                "/wfm-final/training/enroll",
                json={"agent_id": "a1", "course_id": "course-1"},
            )

        assert resp.status_code == 200
        mock_enroll.assert_called_once_with("tenant-1", "a1", "course-1")

    def test_enroll_agent_failure(self, client):
        with patch.object(
            wfm_final_module.training_service, "enroll_agent", new=AsyncMock(return_value=None)
        ):
            resp = client.post(
                "/wfm-final/training/enroll",
                json={"agent_id": "a1", "course_id": "course-1"},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to enroll agent"

    def test_track_progress_success(self, client):
        with patch.object(
            wfm_final_module.training_service,
            "track_progress",
            new=AsyncMock(return_value={"id": "enroll-1"}),
        ) as mock_progress:
            resp = client.post(
                "/wfm-final/training/progress",
                json={"enrollment_id": "enroll-1", "module_id": "m1", "status": "completed"},
            )

        assert resp.status_code == 200
        mock_progress.assert_called_once_with("enroll-1", "m1", "completed")

    def test_track_progress_failure(self, client):
        with patch.object(
            wfm_final_module.training_service, "track_progress", new=AsyncMock(return_value=None)
        ):
            resp = client.post(
                "/wfm-final/training/progress",
                json={"enrollment_id": "enroll-1", "module_id": "m1", "status": "completed"},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to track progress"

    def test_get_certifications(self, client):
        with patch.object(
            wfm_final_module.training_service,
            "get_agent_certifications",
            new=AsyncMock(return_value=[{"id": "cert-1"}]),
        ) as mock_certs:
            resp = client.get("/wfm-final/training/certifications/a1")

        assert resp.status_code == 200
        assert resp.json() == [{"id": "cert-1"}]
        mock_certs.assert_called_once_with("tenant-1", "a1")

    def test_create_coaching_success(self, client):
        with patch.object(
            wfm_final_module.training_service,
            "create_coaching_session",
            new=AsyncMock(return_value={"id": "coach-1"}),
        ) as mock_coach:
            resp = client.post(
                "/wfm-final/training/coaching",
                json={
                    "agent_id": "a1",
                    "coach_id": "c1",
                    "focus_area": "objection handling",
                    "notes": "n",
                },
            )

        assert resp.status_code == 200
        mock_coach.assert_called_once_with(
            "tenant-1", "a1", "c1", "objection handling", "n"
        )

    def test_create_coaching_failure(self, client):
        with patch.object(
            wfm_final_module.training_service,
            "create_coaching_session",
            new=AsyncMock(return_value=None),
        ):
            resp = client.post(
                "/wfm-final/training/coaching",
                json={"agent_id": "a1", "coach_id": "c1", "focus_area": "f"},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to create coaching session"

    def test_list_coaching_with_agent(self, client):
        with patch.object(
            wfm_final_module.training_service,
            "list_coaching_sessions",
            new=AsyncMock(return_value=[{"id": "coach-1"}]),
        ) as mock_list:
            resp = client.get("/wfm-final/training/coaching?agent_id=a1")

        assert resp.status_code == 200
        assert resp.json() == [{"id": "coach-1"}]
        mock_list.assert_called_once_with("tenant-1", "a1")

    def test_list_coaching_without_agent(self, client):
        with patch.object(
            wfm_final_module.training_service,
            "list_coaching_sessions",
            new=AsyncMock(return_value=[]),
        ) as mock_list:
            resp = client.get("/wfm-final/training/coaching")

        assert resp.status_code == 200
        assert resp.json() == []
        mock_list.assert_called_once_with("tenant-1", None)
