"""Unit tests for api.services.supervisor."""

from unittest.mock import AsyncMock, patch

import pytest

from api.services.supervisor import SupervisorService, supervisor_service


@pytest.fixture
def db_calls_mock():
    with patch(
        "api.services.db_calls.list_calls", new_callable=AsyncMock
    ) as m:
        yield m


@pytest.fixture
def db_agents_mock():
    with patch(
        "api.services.db_tenants.list_agents", new_callable=AsyncMock
    ) as m:
        yield m


@pytest.fixture
def db_agent_mock():
    with patch(
        "api.services.db_tenants.get_agent_db", new_callable=AsyncMock
    ) as m:
        yield m


class TestGetWallboardData:
    @pytest.mark.asyncio
    async def test_aggregates_counts(self, db_calls_mock, db_agents_mock):
        db_calls_mock.return_value = [
            {"call_status": "active", "duration_seconds": 120},
            {"call_status": "ringing", "duration_seconds": 60},
            {"call_status": "initiated", "duration_seconds": 30},
            {"call_status": "queued", "wait_time_seconds": 100},
            {"call_status": "queued", "wait_time_seconds": 200},
            {"call_status": "completed", "duration_seconds": 500},
        ]
        db_agents_mock.return_value = [
            {"status": "available"},
            {"status": "online"},
            {"status": "busy"},
            {"status": "on_call"},
            {"status": "offline"},
            {"status": "lunch"},
        ]
        result = await supervisor_service.get_wallboard_data("T1")
        assert result["active_calls"] == 3
        assert result["waiting_queue"] == 2
        assert result["agents_online"] == 4
        assert result["agents_offline"] == 1
        assert result["agents_total"] == 6
        assert result["avg_wait_seconds"] == 150.0
        assert result["longest_wait_seconds"] == 200
        assert result["avg_call_duration_seconds"] == 70.0
        db_calls_mock.assert_awaited_once_with("T1", limit=500)
        db_agents_mock.assert_awaited_once_with("T1")

    @pytest.mark.asyncio
    async def test_empty_data_returns_zeros(self, db_calls_mock, db_agents_mock):
        db_calls_mock.return_value = []
        db_agents_mock.return_value = []
        result = await supervisor_service.get_wallboard_data("T1")
        assert result["active_calls"] == 0
        assert result["waiting_queue"] == 0
        assert result["agents_online"] == 0
        assert result["agents_offline"] == 0
        assert result["agents_total"] == 0
        assert result["avg_wait_seconds"] == 0
        assert result["longest_wait_seconds"] == 0
        assert result["avg_call_duration_seconds"] == 0

    @pytest.mark.asyncio
    async def test_missing_keys_use_defaults(self, db_calls_mock, db_agents_mock):
        db_calls_mock.return_value = [
            {"call_status": "active"},
            {"call_status": "queued"},
        ]
        db_agents_mock.return_value = [{"status": "online"}, {"status": "offline"}]
        result = await supervisor_service.get_wallboard_data("T1")
        assert result["avg_wait_seconds"] == 0
        assert result["avg_call_duration_seconds"] == 0


class TestGetLiveAgentStatus:
    @pytest.mark.asyncio
    async def test_agent_fields(self, db_agents_mock):
        db_agents_mock.return_value = [
            {
                "id": "A1",
                "name": "Alice",
                "status": "available",
                "current_call_duration": 45,
                "total_calls": 12,
                "adherence_pct": 0.95,
            },
            {"id": "A2", "name": "Bob", "status": "offline"},
        ]
        result = await supervisor_service.get_live_agent_status("T1")
        assert result == [
            {
                "id": "A1",
                "name": "Alice",
                "status": "available",
                "current_call_duration": 45,
                "calls_today": 12,
                "adherence_pct": 0.95,
            },
            {
                "id": "A2",
                "name": "Bob",
                "status": "offline",
                "current_call_duration": 0,
                "calls_today": 0,
                "adherence_pct": 0,
            },
        ]

    @pytest.mark.asyncio
    async def test_empty_agents(self, db_agents_mock):
        db_agents_mock.return_value = []
        assert await supervisor_service.get_live_agent_status("T1") == []


class TestGetTeamPerformance:
    @pytest.mark.asyncio
    async def test_team_metrics(self, db_agents_mock):
        db_agents_mock.return_value = [
            {
                "id": "A1",
                "name": "Alice",
                "total_calls": 10,
                "total_talk_time_seconds": 6000,
                "avg_rating": 4.5,
                "status": "available",
            },
            {
                "id": "A2",
                "name": "Bob",
                "total_calls": 0,
                "total_talk_time_seconds": 0,
                "avg_rating": 0,
                "status": "offline",
            },
        ]
        result = await supervisor_service.get_team_performance("T1", period="30d")
        assert result["total_agents"] == 2
        agents = {a["agent_id"]: a for a in result["agents"]}
        assert agents["A1"]["calls_handled"] == 10
        assert agents["A1"]["avg_aht"] == 600.0
        assert agents["A1"]["csat"] == 4.5
        # Division-by-zero guard when total_calls is 0
        assert agents["A2"]["avg_aht"] == 0.0
        assert agents["A2"]["csat"] == 0.0

    @pytest.mark.asyncio
    async def test_empty_team(self, db_agents_mock):
        db_agents_mock.return_value = []
        result = await supervisor_service.get_team_performance("T1")
        assert result == {"agents": [], "total_agents": 0}


class TestGetAgentDetail:
    @pytest.mark.asyncio
    async def test_found(self, db_agent_mock):
        db_agent_mock.return_value = {
            "id": "A1",
            "name": "Alice",
            "status": "available",
            "total_calls": 20,
            "total_talk_time_seconds": 10000,
            "avg_rating": 4.8,
            "skills": ["sales", "support"],
        }
        result = await supervisor_service.get_agent_detail("A1", period="30d")
        assert result == {
            "id": "A1",
            "name": "Alice",
            "status": "available",
            "total_calls": 20,
            "total_talk_time": 10000,
            "avg_rating": 4.8,
            "skills": ["sales", "support"],
        }
        db_agent_mock.assert_awaited_once_with("A1")

    @pytest.mark.asyncio
    async def test_not_found(self, db_agent_mock):
        db_agent_mock.return_value = None
        assert await supervisor_service.get_agent_detail("MISSING") is None


class TestGetRecentAlerts:
    @pytest.mark.asyncio
    async def test_no_alerts(self, db_calls_mock, db_agents_mock):
        db_calls_mock.return_value = [
            {"call_status": "queued", "wait_time_seconds": 100}
        ]
        db_agents_mock.return_value = [
            {"status": "available"},
            {"status": "available"},
            {"status": "available"},
            {"status": "offline"},
        ]
        alerts = await supervisor_service.get_recent_alerts("T1")
        assert alerts == []

    @pytest.mark.asyncio
    async def test_all_alert_types(self, db_calls_mock, db_agents_mock):
        db_calls_mock.return_value = [
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
            {"call_status": "queued", "wait_time_seconds": 400},
        ]
        db_agents_mock.return_value = [
            {"status": "available"},
            {"status": "offline"},
            {"status": "offline"},
        ]
        alerts = await supervisor_service.get_recent_alerts("T1")
        types = {a["type"] for a in alerts}
        assert types == {"sla_breach", "long_wait", "agent_offline"}

    @pytest.mark.asyncio
    async def test_sla_breach_message(self, db_calls_mock, db_agents_mock):
        db_calls_mock.return_value = [
            {"call_status": "queued", "wait_time_seconds": 350}
        ]
        db_agents_mock.return_value = [{"status": "available"}]
        alerts = await supervisor_service.get_recent_alerts("T1")
        sla = [a for a in alerts if a["type"] == "sla_breach"]
        assert len(sla) == 1
        assert sla[0]["severity"] == "critical"
        assert "350s" in sla[0]["message"]
