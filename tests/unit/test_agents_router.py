import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


class TestBuildAgentResponse:
    @pytest.mark.asyncio
    async def test_build_agent_response_basic(self):
        from apps.api.routers.agents import build_agent_response

        agent_data = {
            "id": "A-1",
            "tenant_id": "T-1",
            "name": "Test Agent",
            "display_name": "Test Agent Display",
            "agent_type": "ai",
            "status": "offline",
            "skills": '["sales", "support"]',
            "sip_extension": "1001",
            "total_calls": 50,
            "total_talk_time_seconds": 3600,
            "avg_rating": 4.5,
            "created_at": "2026-01-01T00:00:00",
        }

        result = await build_agent_response(agent_data, "T-1")
        assert result["id"] == "A-1"
        assert result["name"] == "Test Agent"
        assert result["display_name"] == "Test Agent Display"
        assert result["agent_type"] == "ai"
        assert result["status"] == "offline"
        assert result["skills"] == ["sales", "support"]
        assert result["sip_extension"] == "1001"
        assert result["total_calls"] == 50
        assert result["total_talk_time_seconds"] == 3600
        assert result["avg_rating"] == 4.5
        assert result["created_at"] == "2026-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_build_agent_response_parses_json_skills(self):
        from apps.api.routers.agents import build_agent_response

        agent_data = {
            "id": "A-2",
            "name": "Agent 2",
            "skills": '["technical"]',
        }

        result = await build_agent_response(agent_data, "T-1")
        assert result["skills"] == ["technical"]
        assert result["tenant_id"] == "T-1"

    @pytest.mark.asyncio
    async def test_build_agent_response_handles_list_skills(self):
        from apps.api.routers.agents import build_agent_response

        agent_data = {
            "id": "A-3",
            "name": "Agent 3",
            "skills": ["sales", "billing"],
        }

        result = await build_agent_response(agent_data, "T-1")
        assert result["skills"] == ["sales", "billing"]

    @pytest.mark.asyncio
    async def test_build_agent_response_empty_skills(self):
        from apps.api.routers.agents import build_agent_response

        agent_data = {"id": "A-4", "name": "Agent 4", "skills": None}

        result = await build_agent_response(agent_data, "T-1")
        assert result["skills"] == []

    @pytest.mark.asyncio
    async def test_build_agent_response_invalid_json_skills(self):
        from apps.api.routers.agents import build_agent_response

        agent_data = {"id": "A-5", "name": "Agent 5", "skills": "not valid json"}

        result = await build_agent_response(agent_data, "T-1")
        assert result["skills"] == []

    @pytest.mark.asyncio
    async def test_build_agent_response_empty_string_skills(self):
        from apps.api.routers.agents import build_agent_response

        agent_data = {"id": "A-6", "name": "Agent 6", "skills": "[]"}

        result = await build_agent_response(agent_data, "T-1")
        assert result["skills"] == []

    @pytest.mark.asyncio
    async def test_build_agent_response_missing_optional_fields(self):
        from apps.api.routers.agents import build_agent_response

        agent_data = {"id": "A-7", "name": "Minimal Agent"}

        result = await build_agent_response(agent_data)
        assert result["id"] == "A-7"
        assert result["name"] == "Minimal Agent"
        assert result["display_name"] == "Minimal Agent"
        assert result["agent_type"] == "ai"
        assert result["status"] == "offline"
        assert result["skills"] == []
        assert result["sip_extension"] is None
        assert result["total_calls"] == 0
        assert result["total_talk_time_seconds"] == 0
        assert result["avg_rating"] == 0.0
        assert result["created_at"] is not None

    @pytest.mark.asyncio
    async def test_build_agent_response_display_name_falls_back(self):
        from apps.api.routers.agents import build_agent_response

        agent_data = {"id": "A-8", "name": "Agent 8", "display_name": None}

        result = await build_agent_response(agent_data, "T-1")
        assert result["display_name"] == "Agent 8"

    @pytest.mark.asyncio
    async def test_build_agent_response_none_avg_rating(self):
        from apps.api.routers.agents import build_agent_response

        agent_data = {"id": "A-9", "name": "Agent 9", "avg_rating": None}

        result = await build_agent_response(agent_data, "T-1")
        assert result["avg_rating"] == 0.0

    @pytest.mark.asyncio
    async def test_build_agent_response_zero_counts(self):
        from apps.api.routers.agents import build_agent_response

        agent_data = {
            "id": "A-10",
            "name": "Agent 10",
            "total_calls": 0,
            "total_talk_time_seconds": 0,
        }

        result = await build_agent_response(agent_data, "T-1")
        assert result["total_calls"] == 0
        assert result["total_talk_time_seconds"] == 0
