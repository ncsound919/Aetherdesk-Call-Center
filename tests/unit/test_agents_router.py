import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.services.auth import verify_tenant_access, get_current_user


class TestBuildAgentResponse:
    @pytest.mark.asyncio
    async def test_build_agent_response_basic(self):
        from api.routers.agents import build_agent_response

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
        from api.routers.agents import build_agent_response

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
        from api.routers.agents import build_agent_response

        agent_data = {
            "id": "A-3",
            "name": "Agent 3",
            "skills": ["sales", "billing"],
        }

        result = await build_agent_response(agent_data, "T-1")
        assert result["skills"] == ["sales", "billing"]

    @pytest.mark.asyncio
    async def test_build_agent_response_empty_skills(self):
        from api.routers.agents import build_agent_response

        agent_data = {"id": "A-4", "name": "Agent 4", "skills": None}

        result = await build_agent_response(agent_data, "T-1")
        assert result["skills"] == []

    @pytest.mark.asyncio
    async def test_build_agent_response_invalid_json_skills(self):
        from api.routers.agents import build_agent_response

        agent_data = {"id": "A-5", "name": "Agent 5", "skills": "not valid json"}

        result = await build_agent_response(agent_data, "T-1")
        assert result["skills"] == []

    @pytest.mark.asyncio
    async def test_build_agent_response_empty_string_skills(self):
        from api.routers.agents import build_agent_response

        agent_data = {"id": "A-6", "name": "Agent 6", "skills": "[]"}

        result = await build_agent_response(agent_data, "T-1")
        assert result["skills"] == []

    @pytest.mark.asyncio
    async def test_build_agent_response_missing_optional_fields(self):
        from api.routers.agents import build_agent_response

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
        from api.routers.agents import build_agent_response

        agent_data = {"id": "A-8", "name": "Agent 8", "display_name": None}

        result = await build_agent_response(agent_data, "T-1")
        assert result["display_name"] == "Agent 8"

    @pytest.mark.asyncio
    async def test_build_agent_response_none_avg_rating(self):
        from api.routers.agents import build_agent_response

        agent_data = {"id": "A-9", "name": "Agent 9", "avg_rating": None}

        result = await build_agent_response(agent_data, "T-1")
        assert result["avg_rating"] == 0.0

    @pytest.mark.asyncio
    async def test_build_agent_response_zero_counts(self):
        from api.routers.agents import build_agent_response

        agent_data = {
            "id": "A-10",
            "name": "Agent 10",
            "total_calls": 0,
            "total_talk_time_seconds": 0,
        }

        result = await build_agent_response(agent_data, "T-1")
        assert result["total_calls"] == 0
        assert result["total_talk_time_seconds"] == 0


class TestSafeRedisPublish:
    """Tests for safe_redis_publish helper."""

    @pytest.mark.asyncio
    async def test_safe_redis_publish_success(self):
        from api.routers.agents import safe_redis_publish
        mock_request = MagicMock()
        mock_redis = AsyncMock()
        mock_request.app.state.redis = mock_redis

        result = await safe_redis_publish(mock_request, "test:channel", "test-msg")
        assert result is True
        mock_redis.publish.assert_awaited_once_with("test:channel", "test-msg")

    @pytest.mark.asyncio
    async def test_safe_redis_publish_failure_logs_error(self):
        from api.routers.agents import safe_redis_publish
        mock_request = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.publish.side_effect = Exception("Redis connection lost")
        mock_request.app.state.redis = mock_redis

        result = await safe_redis_publish(mock_request, "bad:channel", "bad-msg")
        assert result is False
        mock_redis.publish.assert_awaited_once()


@pytest.fixture
def app():
    """Create a minimal FastAPI app with just the agents router."""
    from api.routers.agents import router
    from fastapi import FastAPI

    application = FastAPI()
    application.include_router(router)

    fonster = AsyncMock()
    fonster.create_application = AsyncMock(return_value={"success": True})
    application.state.fonster_client = fonster
    application.state.redis = AsyncMock()

    async def _override_tenant():
        return "tenant-1"

    application.dependency_overrides[verify_tenant_access] = _override_tenant

    async def _override_user():
        return {"sub": "user-1", "tenant_id": "tenant-1"}

    application.dependency_overrides[get_current_user] = _override_user

    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestCreateAgent:
    """Tests for POST /tenants/{tenant_id}/agents."""

    def test_create_agent_success(self, client):
        with patch("api.routers.agents.create_agent_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {
                "id": "agent-1",
                "sip_extension": "1001",
            }

            resp = client.post(
                "/tenants/tenant-1/agents",
                json={"name": "Sales Agent", "skills": ["sales", "support"]},
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["id"] == "agent-1"
            assert body["name"] == "Sales Agent"
            assert body["sip_extension"] == "1001"
            assert body["tenant_id"] == "tenant-1"

    def test_create_agent_without_fonster(self, app, client):
        app.state.fonster_client = None
        with patch("api.routers.agents.create_agent_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {
                "id": "agent-2",
                "sip_extension": "1002",
            }

            resp = client.post(
                "/tenants/tenant-1/agents",
                json={"name": "No Fonster Agent", "skills": ["technical"]},
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["id"] == "agent-2"

    def test_create_agent_fonster_failure_logs_warning(self, app, client):
        app.state.fonster_client.create_application = AsyncMock(
            side_effect=Exception("Fonster timeout")
        )
        with patch("api.routers.agents.create_agent_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {
                "id": "agent-3",
                "sip_extension": "1003",
            }

            resp = client.post(
                "/tenants/tenant-1/agents",
                json={"name": "Fonster Fail Agent", "skills": ["support"]},
            )
            assert resp.status_code == 201

    def test_create_agent_validation_error(self, client):
        resp = client.post(
            "/tenants/tenant-1/agents",
            json={"name": "", "skills": []},
        )
        assert resp.status_code == 422


class TestListAgents:
    """Tests for GET /tenants/{tenant_id}/agents."""

    def test_list_agents_returns_list(self, client):
        with patch("api.routers.agents.list_agents_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [
                {"id": "agent-1", "name": "Agent One", "skills": '["sales"]'},
                {"id": "agent-2", "name": "Agent Two", "skills": '["support"]'},
            ]

            resp = client.get("/tenants/tenant-1/agents")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 2
            assert body[0]["id"] == "agent-1"
            assert body[1]["id"] == "agent-2"

    def test_list_agents_empty(self, client):
        with patch("api.routers.agents.list_agents_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            resp = client.get("/tenants/tenant-1/agents")
            assert resp.status_code == 200
            assert resp.json() == []


class TestGetAgent:
    """Tests for GET /tenants/{tenant_id}/agents/{agent_id}."""

    def test_get_agent_found(self, client):
        with patch("api.routers.agents.get_agent_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "agent-1",
                "tenant_id": "tenant-1",
                "name": "Test Agent",
                "display_name": "Test Display",
                "agent_type": "ai",
                "status": "online",
                "skills": '["sales"]',
                "sip_extension": "1001",
                "total_calls": 10,
                "total_talk_time_seconds": 600,
                "avg_rating": 4.2,
                "created_at": "2026-01-01T00:00:00",
            }

            resp = client.get("/tenants/tenant-1/agents/agent-1")
            assert resp.status_code == 200
            body = resp.json()
            assert body["id"] == "agent-1"
            assert body["name"] == "Test Agent"
            assert body["skills"] == ["sales"]

    def test_get_agent_not_found(self, client):
        with patch("api.routers.agents.get_agent_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            resp = client.get("/tenants/tenant-1/agents/missing-agent")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Agent not found"


class TestUpdateAgent:
    """Tests for PUT /tenants/{tenant_id}/agents/{agent_id}."""

    def test_update_agent_success(self, client):
        with patch("api.routers.agents.update_agent_db", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = {
                "id": "agent-1",
                "tenant_id": "tenant-1",
                "name": "Updated Agent",
                "display_name": "Updated Display",
                "agent_type": "ai",
                "status": "offline",
                "skills": '["billing"]',
                "sip_extension": "1001",
                "total_calls": 5,
                "total_talk_time_seconds": 300,
                "avg_rating": 3.8,
                "created_at": "2026-01-01T00:00:00",
            }

            resp = client.put(
                "/tenants/tenant-1/agents/agent-1",
                json={"name": "Updated Agent", "skills": ["billing"]},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["name"] == "Updated Agent"
            assert body["skills"] == ["billing"]

    def test_update_agent_not_found(self, client):
        with patch("api.routers.agents.update_agent_db", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = None

            resp = client.put(
                "/tenants/tenant-1/agents/missing-agent",
                json={"name": "Ghost", "skills": []},
            )
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Agent not found"


class TestDeleteAgent:
    """Tests for DELETE /tenants/{tenant_id}/agents/{agent_id}."""

    def test_delete_agent_success(self, client):
        with patch("api.routers.agents.delete_agent_db", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = True

            resp = client.delete("/tenants/tenant-1/agents/agent-1")
            assert resp.status_code == 200
            assert resp.json() == {"success": True, "agent_id": "agent-1"}

    def test_delete_agent_not_found(self, client):
        with patch("api.routers.agents.delete_agent_db", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = False

            resp = client.delete("/tenants/tenant-1/agents/missing-agent")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Agent not found"


class TestHandleUpdateAgentStatus:
    """Tests for PATCH /agents/{agent_id}/status."""

    def test_status_update_ownership_fail(self, client, app):
        async def _override_user_wrong():
            return {"sub": "user-2", "tenant_id": "tenant-other"}

        app.dependency_overrides[get_current_user] = _override_user_wrong

        with patch("api.routers.agents.update_agent_status", new_callable=AsyncMock) as mock_status, \
             patch("api.routers.agents.get_agent_db", new_callable=AsyncMock) as mock_get:

            mock_status.return_value = {"success": True}
            mock_get.return_value = {
                "id": "agent-1",
                "tenant_id": "tenant-1",
                "name": "Test",
            }

            resp = client.patch(
                "/agents/agent-1/status",
                json={"status": "online"},
            )
            assert resp.status_code == 403
            assert "Access denied" in resp.json()["detail"]

    def test_status_update_success(self, client):
        with patch("api.routers.agents.update_agent_status", new_callable=AsyncMock) as mock_status, \
             patch("api.routers.agents.get_agent_db", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.agents.safe_redis_publish", new_callable=AsyncMock) as mock_redis:

            mock_status.return_value = {"success": True}
            mock_get.return_value = {
                "id": "agent-1",
                "tenant_id": "tenant-1",
                "name": "Test",
            }

            resp = client.patch(
                "/agents/agent-1/status",
                json={"status": "online"},
            )
            assert resp.status_code == 200

    def test_status_update_agent_not_found(self, client):
        with patch("api.routers.agents.update_agent_status", new_callable=AsyncMock) as mock_status, \
             patch("api.routers.agents.get_agent_db", new_callable=AsyncMock) as mock_get:

            mock_status.return_value = {"success": False, "error": "Agent not found"}
            mock_get.return_value = {
                "id": "agent-1",
                "tenant_id": "tenant-1",
                "name": "Test",
            }

            resp = client.patch(
                "/agents/agent-1/status",
                json={"status": "online"},
            )
            assert resp.status_code == 404
