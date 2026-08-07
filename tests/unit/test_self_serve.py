"""Unit tests for api.services.self_serve.SelfServeOnboardingService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.self_serve import self_serve_service


class FakePgConn:
    def __init__(self):
        self.execute = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
class TestSelfServeOnboardingService:
    async def test_create_trial_tenant_sqlite(self):
        conn = MagicMock()
        with patch(
            "api.services.self_serve._get_sqlite_conn", return_value=conn
        ), patch(
            "api.services.self_serve.create_onboarding_progress_db",
            new_callable=AsyncMock,
        ) as mock_progress:
            result = await self_serve_service.create_trial_tenant(
                "admin@acme.com", "Acme Corp", "pw12345"
            )
        assert result["email"] == "admin@acme.com"
        assert result["company_name"] == "Acme Corp"
        assert result["tenant_id"]
        assert result["api_key"]
        assert result["slug"].startswith("acme-corp-")
        assert conn.execute.call_count == 2
        conn.commit.assert_called_once()
        conn.close.assert_called_once()
        mock_progress.assert_awaited_once_with(result["tenant_id"])

    async def test_create_trial_tenant_postgres(self):
        conn = FakePgConn()
        pool = MagicMock()
        pool.acquire.return_value = conn
        with patch("api.services.self_serve.USE_POSTGRES", True), patch(
            "api.services.self_serve.get_pg_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ), patch(
            "api.services.self_serve.create_onboarding_progress_db",
            new_callable=AsyncMock,
        ):
            result = await self_serve_service.create_trial_tenant(
                "admin@acme.com", "Acme Corp", "pw12345"
            )
        assert result["tenant_id"]
        assert result["api_key"]
        assert conn.execute.await_count == 2

    async def test_get_onboarding_status_no_progress(self):
        with patch(
            "api.services.self_serve.get_onboarding_progress_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await self_serve_service.get_onboarding_status("t1")
        assert result == {
            "tenant_id": "t1",
            "steps_completed": [],
            "current_step": "welcome",
            "completed": False,
        }

    async def test_get_onboarding_status_with_progress(self):
        with patch(
            "api.services.self_serve.get_onboarding_progress_db",
            new_callable=AsyncMock,
            return_value={
                "steps_completed_json": '["welcome", "phone_number"]',
                "current_step": "quickstart",
                "completed": True,
            },
        ):
            result = await self_serve_service.get_onboarding_status("t1")
        assert result["steps_completed"] == ["welcome", "phone_number"]
        assert result["current_step"] == "quickstart"
        assert result["completed"] is True

    async def test_get_onboarding_status_invalid_json_defaults(self):
        with patch(
            "api.services.self_serve.get_onboarding_progress_db",
            new_callable=AsyncMock,
            return_value={"completed": 0},
        ):
            result = await self_serve_service.get_onboarding_status("t1")
        assert result["steps_completed"] == []
        assert result["current_step"] == "welcome"
        assert result["completed"] is False

    async def test_complete_step(self):
        with patch(
            "api.services.self_serve.complete_onboarding_step_db",
            new_callable=AsyncMock,
            return_value={
                "steps_completed_json": '["welcome"]',
                "current_step": "phone_number",
                "completed": False,
            },
        ) as mock_db:
            result = await self_serve_service.complete_step("t1", "welcome")
        mock_db.assert_awaited_once_with("t1", "welcome")
        assert result["steps_completed"] == ["welcome"]
        assert result["current_step"] == "phone_number"
        assert result["completed"] is False

    async def test_get_quickstart_guide(self):
        result = await self_serve_service.get_quickstart_guide("t1")
        assert result["tenant_id"] == "t1"
        assert len(result["steps"]) == 6
        assert result["steps"][0]["id"] == "configure_greetings"

    async def test_provision_phone_number(self):
        with patch(
            "api.services.self_serve.set_tenant_config_value_db",
            new_callable=AsyncMock,
        ) as mock_set:
            result = await self_serve_service.provision_phone_number("t1", "212")
        assert result["area_code"] == "212"
        assert result["status"] == "reserved"
        assert result["phone_number"].startswith("+1212")
        mock_set.assert_awaited_once()
        key = mock_set.await_args.args[1]
        assert key == "provisioned_number"

    async def test_run_health_check(self):
        result = await self_serve_service.run_health_check("t1")
        assert result["tenant_id"] == "t1"
        assert result["overall_status"] == "passed"
        assert set(result["checks"].keys()) == {
            "database",
            "api",
            "phone",
            "ai_agents",
            "billing",
        }

    async def test_get_setup_progress_empty(self):
        with patch(
            "api.services.self_serve.SelfServeOnboardingService.get_onboarding_status",
            new_callable=AsyncMock,
            return_value={
                "steps_completed": [],
                "current_step": "welcome",
                "completed": False,
            },
        ):
            result = await self_serve_service.get_setup_progress("t1")
        assert result["percent_complete"] == 0
        assert result["onboarding_complete"] is False
        assert len(result["remaining_steps"]) == 4
        assert result["remaining_steps"][0] == "Set up company info"

    async def test_get_setup_progress_partial(self):
        with patch(
            "api.services.self_serve.SelfServeOnboardingService.get_onboarding_status",
            new_callable=AsyncMock,
            return_value={
                "steps_completed": ["welcome", "phone_number"],
                "current_step": "quickstart",
                "completed": False,
            },
        ):
            result = await self_serve_service.get_setup_progress("t1")
        assert result["percent_complete"] == 50
        assert len(result["completed_steps"]) == 2
        assert result["remaining_steps"] == ["Complete quickstart guide", "Run health check"]

    async def test_get_setup_progress_complete(self):
        with patch(
            "api.services.self_serve.SelfServeOnboardingService.get_onboarding_status",
            new_callable=AsyncMock,
            return_value={
                "steps_completed": [
                    "welcome",
                    "phone_number",
                    "quickstart",
                    "health_check",
                ],
                "current_step": "done",
                "completed": True,
            },
        ):
            result = await self_serve_service.get_setup_progress("t1")
        assert result["percent_complete"] == 100
        assert result["onboarding_complete"] is True
        assert result["remaining_steps"] == []
