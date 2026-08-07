"""Unit tests for api.routers.wfm."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import wfm as wfm_module
from api.services.auth import verify_tenant_access


@pytest.fixture
def app():
    from api.routers.wfm import router

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


class TestShifts:
    def test_list_shifts(self, client):
        with patch.object(
            wfm_module, "list_shifts_db", new=AsyncMock(return_value=[{"id": "s1"}])
        ) as mock_list:
            resp = client.get(
                "/wfm/shifts?date_from=2026-01-01&date_to=2026-01-31&agent_id=a1"
            )

        assert resp.status_code == 200
        assert resp.json() == [{"id": "s1"}]
        mock_list.assert_called_once_with(
            "tenant-1", date_from="2026-01-01", date_to="2026-01-31", agent_id="a1"
        )

    def test_list_shifts_no_filters(self, client):
        with patch.object(
            wfm_module, "list_shifts_db", new=AsyncMock(return_value=[])
        ) as mock_list:
            resp = client.get("/wfm/shifts")

        assert resp.status_code == 200
        mock_list.assert_called_once_with(
            "tenant-1", date_from=None, date_to=None, agent_id=None
        )

    def test_create_shift_success(self, client):
        with patch.object(
            wfm_module, "create_shift_db", new=AsyncMock(return_value={"id": "s1"})
        ) as mock_create:
            resp = client.post(
                "/wfm/shifts",
                json={
                    "agent_id": "a1",
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "shift_type": "regular",
                    "notes": "note",
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"id": "s1"}
        mock_create.assert_called_once_with(
            "tenant-1", "a1", "09:00", "17:00", shift_type="regular", notes="note"
        )

    def test_create_shift_defaults(self, client):
        with patch.object(
            wfm_module, "create_shift_db", new=AsyncMock(return_value={"id": "s1"})
        ) as mock_create:
            resp = client.post(
                "/wfm/shifts",
                json={"agent_id": "a1", "start_time": "09:00", "end_time": "17:00"},
            )

        assert resp.status_code == 200
        mock_create.assert_called_once_with(
            "tenant-1", "a1", "09:00", "17:00", shift_type="regular", notes=None
        )

    def test_create_shift_failure(self, client):
        with patch.object(
            wfm_module, "create_shift_db", new=AsyncMock(return_value=None)
        ):
            resp = client.post(
                "/wfm/shifts",
                json={"agent_id": "a1", "start_time": "09:00", "end_time": "17:00"},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to create shift"

    def test_update_shift_success(self, client):
        with patch.object(
            wfm_module, "update_shift_db", new=AsyncMock(return_value={"id": "s1"})
        ) as mock_update:
            resp = client.put(
                "/wfm/shifts/s1",
                json={
                    "agent_id": "a1",
                    "start_time": "10:00",
                    "end_time": "18:00",
                    "notes": None,
                },
            )

        assert resp.status_code == 200
        mock_update.assert_called_once_with(
            "s1",
            "tenant-1",
            start_time="10:00",
            end_time="18:00",
            shift_type="regular",
            notes=None,
        )

    def test_update_shift_not_found(self, client):
        with patch.object(
            wfm_module, "update_shift_db", new=AsyncMock(return_value=None)
        ):
            resp = client.put(
                "/wfm/shifts/nope",
                json={
                    "agent_id": "a1",
                    "start_time": "10:00",
                    "end_time": "18:00",
                },
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Shift not found"

    def test_delete_shift_success(self, client):
        with patch.object(
            wfm_module, "delete_shift_db", new=AsyncMock(return_value=True)
        ) as mock_delete:
            resp = client.delete("/wfm/shifts/s1")

        assert resp.status_code == 200
        assert resp.json() == {"success": True}
        mock_delete.assert_called_once_with("s1", "tenant-1")

    def test_delete_shift_not_found(self, client):
        with patch.object(
            wfm_module, "delete_shift_db", new=AsyncMock(return_value=False)
        ):
            resp = client.delete("/wfm/shifts/nope")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Shift not found"


class TestSchedules:
    def test_list_schedules(self, client):
        with patch.object(
            wfm_module, "list_schedules_db", new=AsyncMock(return_value=[{"date": "2026-01-01"}])
        ) as mock_list:
            resp = client.get("/wfm/schedules?date_from=2026-01-01&date_to=2026-01-02")

        assert resp.status_code == 200
        assert resp.json() == [{"date": "2026-01-01"}]
        mock_list.assert_called_once_with(
            "tenant-1", date_from="2026-01-01", date_to="2026-01-02"
        )

    def test_list_schedules_no_filters(self, client):
        with patch.object(
            wfm_module, "list_schedules_db", new=AsyncMock(return_value=[])
        ) as mock_list:
            resp = client.get("/wfm/schedules")

        assert resp.status_code == 200
        mock_list.assert_called_once_with("tenant-1", date_from=None, date_to=None)

    def test_get_forecast(self, client):
        with patch.object(
            wfm_module,
            "compute_forecast",
            new=AsyncMock(return_value={"forecast": [{"hour": 1}]}),
        ) as mock_forecast:
            resp = client.post("/wfm/schedules/forecast?hours_ahead=48")

        assert resp.status_code == 200
        assert resp.json() == {"forecast": [{"hour": 1}]}
        mock_forecast.assert_called_once_with("tenant-1", 48)

    def test_get_forecast_default_hours(self, client):
        with patch.object(
            wfm_module,
            "compute_forecast",
            new=AsyncMock(return_value={"forecast": []}),
        ) as mock_forecast:
            resp = client.post("/wfm/schedules/forecast")

        assert resp.status_code == 200
        mock_forecast.assert_called_once_with("tenant-1", 24)

    def test_get_forecast_invalid_hours(self, client):
        resp = client.post("/wfm/schedules/forecast?hours_ahead=200")
        assert resp.status_code == 422


class TestAdherence:
    def test_with_schedule_and_adherence(self, client):
        schedule = {
            "adherence_pct": 85,
            "forecasted_volume": 100,
            "forecasted_agents": 10,
            "actual_volume": 90,
            "actual_agents": 9,
        }
        with patch(
            "api.services.db_wfm.list_schedules_db", new=AsyncMock(return_value=[schedule])
        ):
            resp = client.get("/wfm/adherence?date=2026-01-01")

        assert resp.status_code == 200
        body = resp.json()
        assert body["date"] == "2026-01-01"
        assert body["overall_adherence_pct"] == 85.0
        assert body["agents"] == []
        assert body["schedule_summary"] == {
            "forecasted_volume": 100,
            "forecasted_agents": 10,
            "actual_volume": 90,
            "actual_agents": 9,
        }

    def test_with_schedule_missing_adherence(self, client):
        schedule = {
            "forecasted_volume": 10,
            "forecasted_agents": 2,
            "actual_volume": 8,
            "actual_agents": 2,
        }
        with patch(
            "api.services.db_wfm.list_schedules_db", new=AsyncMock(return_value=[schedule])
        ):
            resp = client.get("/wfm/adherence?date=2026-01-02")

        assert resp.status_code == 200
        assert resp.json()["overall_adherence_pct"] == 0.0

    def test_no_schedule(self, client):
        with patch(
            "api.services.db_wfm.list_schedules_db", new=AsyncMock(return_value=[])
        ):
            resp = client.get("/wfm/adherence?date=2026-01-03")

        assert resp.status_code == 200
        body = resp.json()
        assert body["overall_adherence_pct"] == 0.0
        assert body["schedule_summary"] == {
            "forecasted_volume": 0,
            "forecasted_agents": 0,
            "actual_volume": 0,
            "actual_agents": 0,
        }

    def test_defaults_to_today(self, client):
        expected_date = datetime.now(UTC).strftime("%Y-%m-%d")
        with patch(
            "api.services.db_wfm.list_schedules_db", new=AsyncMock(return_value=[])
        ) as mock_list:
            resp = client.get("/wfm/adherence")

        assert resp.status_code == 200
        assert resp.json()["date"] == expected_date
        mock_list.assert_called_once_with("tenant-1", date_from=expected_date, date_to=expected_date)


class TestQA:
    def test_list_qa_scores(self, client):
        with patch.object(
            wfm_module, "list_qa_scores_db", new=AsyncMock(return_value=[{"id": "q1"}])
        ) as mock_list:
            resp = client.get(
                "/wfm/qa/scores?agent_id=a1&date_from=2026-01-01&date_to=2026-01-02&limit=50"
            )

        assert resp.status_code == 200
        mock_list.assert_called_once_with(
            "tenant-1",
            agent_id="a1",
            date_from="2026-01-01",
            date_to="2026-01-02",
            limit=50,
        )

    def test_list_qa_scores_defaults(self, client):
        with patch.object(
            wfm_module, "list_qa_scores_db", new=AsyncMock(return_value=[])
        ) as mock_list:
            resp = client.get("/wfm/qa/scores")

        assert resp.status_code == 200
        mock_list.assert_called_once_with(
            "tenant-1", agent_id=None, date_from=None, date_to=None, limit=100
        )

    def test_list_qa_scores_invalid_limit(self, client):
        resp = client.get("/wfm/qa/scores?limit=2000")
        assert resp.status_code == 422

    def test_create_qa_score_success(self, client):
        with patch.object(
            wfm_module.qa_engine,
            "score_call",
            new=AsyncMock(return_value={"id": "q1"}),
        ) as mock_score:
            resp = client.post(
                "/wfm/qa/scores",
                json={
                    "call_id": "c1",
                    "agent_id": "a1",
                    "rubric_id": "r1",
                    "scores_per_criterion": {"greeting": 3},
                    "notes": "note",
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"id": "q1"}
        mock_score.assert_called_once_with(
            "tenant-1", "c1", "a1", "reviewer", "r1", {"greeting": 3}, "note"
        )

    def test_create_qa_score_failure(self, client):
        with patch.object(
            wfm_module.qa_engine, "score_call", new=AsyncMock(return_value=None)
        ):
            resp = client.post(
                "/wfm/qa/scores",
                json={
                    "call_id": "c1",
                    "agent_id": "a1",
                    "rubric_id": "r1",
                    "scores_per_criterion": {},
                },
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to create QA score"

    def test_list_qa_rubrics(self, client):
        with patch.object(
            wfm_module, "list_qa_rubrics_db", new=AsyncMock(return_value=[{"id": "r1"}])
        ) as mock_list:
            resp = client.get("/wfm/qa/rubrics")

        assert resp.status_code == 200
        assert resp.json() == [{"id": "r1"}]
        mock_list.assert_called_once_with("tenant-1")

    def test_create_qa_rubric_success(self, client):
        with patch.object(
            wfm_module, "create_qa_rubric_db", new=AsyncMock(return_value={"id": "r1"})
        ) as mock_create:
            resp = client.post(
                "/wfm/qa/rubrics",
                json={"name": "Basic", "description": "desc", "criteria": [{"name": "x"}]},
            )

        assert resp.status_code == 200
        mock_create.assert_called_once_with(
            "tenant-1", "Basic", [{"name": "x"}], "desc"
        )

    def test_create_qa_rubric_failure(self, client):
        with patch.object(
            wfm_module, "create_qa_rubric_db", new=AsyncMock(return_value=None)
        ):
            resp = client.post(
                "/wfm/qa/rubrics", json={"name": "Basic", "criteria": []}
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to create QA rubric"

    def test_get_agent_qa_summary(self, client):
        with patch.object(
            wfm_module.qa_engine,
            "get_agent_summary",
            new=AsyncMock(return_value={"avg_score": 75.0}),
        ) as mock_summary:
            resp = client.get("/wfm/qa/agent-summary/a1")

        assert resp.status_code == 200
        assert resp.json() == {"avg_score": 75.0}
        mock_summary.assert_called_once_with("a1")
