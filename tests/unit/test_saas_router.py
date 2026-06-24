import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


class TestSaasDashboard:
    """Tests for GET /saas/dashboard"""

    @pytest.mark.asyncio
    async def test_get_dashboard_returns_data(self):
        from apps.api.routers.saas import get_saas_dashboard

        mock_data = {"agents_count": 5, "calls_today": 100, "active_calls": 3}
        with patch("apps.api.routers.saas.get_saas_dashboard_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = mock_data

            result = await get_saas_dashboard(tenant_id="TENANT-001")
            assert result == mock_data
            mock_db.assert_called_once_with("TENANT-001")

    @pytest.mark.asyncio
    async def test_get_dashboard_empty_tenant(self):
        from apps.api.routers.saas import get_saas_dashboard

        with patch("apps.api.routers.saas.get_saas_dashboard_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = {}

            result = await get_saas_dashboard(tenant_id="TENANT-999")
            assert result == {}


class TestCreateProfile:
    """Tests for POST /saas/profile"""

    @pytest.mark.asyncio
    async def test_create_profile_success(self):
        from apps.api.routers.saas import create_profile

        with patch("apps.api.routers.saas.create_agent_profile_db", new_callable=AsyncMock) as mock_db:
            result = await create_profile(
                name="Sales Agent",
                prompt="Be helpful and persuasive",
                parameters={"voice": "friendly", "language": "en"},
                tenant_id="TENANT-001",
            )
            assert result["ok"] is True
            assert result["profile_id"].startswith("PROF-")
            mock_db.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_profile_calls_db_with_correct_params(self):
        from apps.api.routers.saas import create_profile

        with patch("apps.api.routers.saas.create_agent_profile_db", new_callable=AsyncMock) as mock_db:
            result = await create_profile(
                name="Support Agent",
                prompt="Be patient",
                parameters={"tone": "empathetic"},
                tenant_id="TENANT-002",
            )
            assert result["ok"] is True
            # Verify the DB was called with the right args (profile_id is dynamic)
            call_args = mock_db.call_args[0]
            assert call_args[0].startswith("PROF-")  # profile_id
            assert call_args[1] == "TENANT-002"  # tenant_id
            assert call_args[2] == "Support Agent"  # name
            assert call_args[3] == "Be patient"  # prompt
            assert call_args[4] == {"tone": "empathetic"}  # parameters


class TestRentAgent:
    """Tests for POST /saas/rent"""

    @pytest.mark.asyncio
    async def test_rent_agent_hour(self):
        from apps.api.routers.saas import rent_agent

        with patch("apps.api.routers.saas.rent_agent_db", new_callable=AsyncMock) as mock_db:
            result = await rent_agent(
                profile_id="PROF-ABC123",
                duration_type="hour",
                tenant_id="TENANT-001",
            )
            assert result["ok"] is True
            assert result["rental_id"].startswith("RENT-")
            assert "end_time" in result
            mock_db.assert_called_once()

    @pytest.mark.asyncio
    async def test_rent_agent_day(self):
        from apps.api.routers.saas import rent_agent

        with patch("apps.api.routers.saas.rent_agent_db", new_callable=AsyncMock) as mock_db:
            result = await rent_agent(
                profile_id="PROF-DEF456",
                duration_type="day",
                tenant_id="TENANT-001",
            )
            assert result["ok"] is True
            assert "end_time" in result

    @pytest.mark.asyncio
    async def test_rent_agent_week(self):
        from apps.api.routers.saas import rent_agent

        with patch("apps.api.routers.saas.rent_agent_db", new_callable=AsyncMock) as mock_db:
            result = await rent_agent(
                profile_id="PROF-GHI789",
                duration_type="week",
                tenant_id="TENANT-001",
            )
            assert result["ok"] is True
            assert "end_time" in result

    @pytest.mark.asyncio
    async def test_rent_agent_month(self):
        from apps.api.routers.saas import rent_agent

        with patch("apps.api.routers.saas.rent_agent_db", new_callable=AsyncMock) as mock_db:
            result = await rent_agent(
                profile_id="PROF-JKL012",
                duration_type="month",
                tenant_id="TENANT-001",
            )
            assert result["ok"] is True
            assert "end_time" in result

    @pytest.mark.asyncio
    async def test_rent_agent_invalid_duration(self):
        from apps.api.routers.saas import rent_agent
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await rent_agent(
                profile_id="PROF-ABC123",
                duration_type="year",
                tenant_id="TENANT-001",
            )
        assert exc_info.value.status_code == 400
        assert "Invalid duration type" in str(exc_info.value.detail)


class TestSettings:
    """Tests for GET and POST /saas/settings"""

    @pytest.mark.asyncio
    async def test_get_settings_returns_row(self):
        from apps.api.routers.saas import get_settings

        mock_row = {
            "api_feeds": '{"feed1": "url1", "feed2": "url2"}',
            "auto_mode_enabled": 1,
            "redact_pii": 0,
            "require_consent": 1,
            "sync_dnc": 0,
            "mcp_servers": '{"server1": "http://mcp1"}',
        }
        with patch("apps.api.routers.saas.get_tenant_settings_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = mock_row

            result = await get_settings(tenant_id="TENANT-001")
            assert result["api_feeds"] == '{"feed1": "url1", "feed2": "url2"}'
            assert result["auto_mode_enabled"] is True
            assert result["redact_pii"] is False
            assert result["require_consent"] is True
            assert result["sync_dnc"] is False
            assert result["mcp_servers"] == '{"server1": "http://mcp1"}'

    @pytest.mark.asyncio
    async def test_get_settings_defaults_when_no_row(self):
        from apps.api.routers.saas import get_settings

        with patch("apps.api.routers.saas.get_tenant_settings_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = None

            result = await get_settings(tenant_id="TENANT-999")
            assert result["api_feeds"] == "{}"
            assert result["auto_mode_enabled"] is False
            assert result["redact_pii"] is True
            assert result["require_consent"] is True
            assert result["sync_dnc"] is False
            assert result["mcp_servers"] == "{}"

    @pytest.mark.asyncio
    async def test_update_settings(self):
        from apps.api.routers.saas import update_settings

        with patch("apps.api.routers.saas.update_tenant_settings_db", new_callable=AsyncMock) as mock_db:
            result = await update_settings(
                settings={"auto_mode_enabled": True, "redact_pii": False},
                tenant_id="TENANT-001",
            )
            assert result["ok"] is True
            mock_db.assert_called_once_with(
                "TENANT-001",
                {"auto_mode_enabled": True, "redact_pii": False},
            )


class TestGenerateScript:
    """Tests for POST /saas/generate-script"""

    @pytest.mark.asyncio
    async def test_generate_script_success(self):
        from apps.api.routers.saas import generate_script
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "You are an AI agent for customer support."}
        }

        with patch("apps.api.routers.saas.httpx.AsyncClient") as mock_client_class:
            mock_instance = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_instance
            mock_instance.post = AsyncMock(return_value=mock_response)

            result = await generate_script(
                goal={"objective": "customer support"},
                tenant_id="TENANT-001",
            )
            assert result["script"] == "You are an AI agent for customer support."

    @pytest.mark.asyncio
    async def test_generate_script_fallback_on_ollama_error(self):
        from apps.api.routers.saas import generate_script

        with patch("apps.api.routers.saas.httpx.AsyncClient") as mock_client_class:
            mock_instance = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = Exception("Ollama connection refused")

            result = await generate_script(
                goal={"objective": "customer support"},
                tenant_id="TENANT-001",
            )
            assert "script" in result
            assert "customer support" in result["script"]

    @pytest.mark.asyncio
    async def test_generate_script_handles_empty_objective(self):
        from apps.api.routers.saas import generate_script

        with patch("apps.api.routers.saas.httpx.AsyncClient") as mock_client_class:
            mock_instance = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = Exception("Ollama connection refused")

            result = await generate_script(
                goal={},
                tenant_id="TENANT-001",
            )
            assert "script" in result
            assert "general sales" in result["script"]


class TestRecordings:
    """Tests for GET /saas/recordings"""

    @pytest.mark.asyncio
    async def test_get_recordings_returns_list(self):
        from apps.api.routers.saas import get_recordings

        mock_recordings = [
            {"id": "rec-001", "url": "https://example.com/rec1.mp3", "duration": 120},
            {"id": "rec-002", "url": "https://example.com/rec2.mp3", "duration": 60},
        ]
        with patch("apps.api.routers.saas.get_session_recordings_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = mock_recordings

            result = await get_recordings(tenant_id="TENANT-001")
            assert result == mock_recordings
            mock_db.assert_called_once_with("TENANT-001")

    @pytest.mark.asyncio
    async def test_get_recordings_empty(self):
        from apps.api.routers.saas import get_recordings

        with patch("apps.api.routers.saas.get_session_recordings_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = []

            result = await get_recordings(tenant_id="TENANT-001")
            assert result == []


class TestApprovals:
    """Tests for GET and POST /saas/approvals"""

    @pytest.mark.asyncio
    async def test_get_approvals_returns_list(self):
        from apps.api.routers.saas import get_approvals

        mock_approvals = [
            {"id": "app-001", "status": "pending", "requested_by": "TENANT-001"},
        ]
        with patch("apps.api.routers.saas.get_pending_approvals_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = mock_approvals

            result = await get_approvals(tenant_id="TENANT-001")
            assert result == mock_approvals
            mock_db.assert_called_once_with("TENANT-001")

    @pytest.mark.asyncio
    async def test_process_approval_approved(self):
        from apps.api.routers.saas import process_approval

        with patch("apps.api.routers.saas.process_approval_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = True

            result = await process_approval(
                approval_id="APP-001",
                status="approved",
                tenant_id="TENANT-001",
            )
            assert result["ok"] is True
            mock_db.assert_called_once_with("APP-001", "approved", "TENANT-001")

    @pytest.mark.asyncio
    async def test_process_approval_rejected(self):
        from apps.api.routers.saas import process_approval

        with patch("apps.api.routers.saas.process_approval_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = True

            result = await process_approval(
                approval_id="APP-002",
                status="rejected",
                tenant_id="TENANT-001",
            )
            assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_process_approval_invalid_status(self):
        from apps.api.routers.saas import process_approval
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await process_approval(
                approval_id="APP-003",
                status="invalid_status",
                tenant_id="TENANT-001",
            )
        assert exc_info.value.status_code == 400
        assert "approved" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_process_approval_not_found(self):
        from apps.api.routers.saas import process_approval
        from fastapi import HTTPException

        with patch("apps.api.routers.saas.process_approval_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = False

            with pytest.raises(HTTPException) as exc_info:
                await process_approval(
                    approval_id="APP-999",
                    status="approved",
                    tenant_id="TENANT-001",
                )
            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value.detail).lower()


class TestGetTenantId:
    """Tests for the get_tenant_id dependency function"""

    @pytest.mark.asyncio
    async def test_get_tenant_id_returns_dev_key_in_test_env(self):
        with patch("apps.api.routers.saas.os.getenv", return_value="test"):
            from apps.api.routers.saas import get_tenant_id

            result = await get_tenant_id(x_api_key="any-key")
            assert result == "TENANT-001"

    @pytest.mark.asyncio
    async def test_get_tenant_id_returns_dev_key_in_dev_env_with_dev_api_key(self):
        def getenv_side_effect(key, default=None):
            envs = {
                "ENV": "development",
                "DEV_API_KEY": "my-dev-key",
            }
            return envs.get(key, default)

        with patch("apps.api.routers.saas.os.getenv", side_effect=getenv_side_effect):
            from apps.api.routers.saas import get_tenant_id

            result = await get_tenant_id(x_api_key="my-dev-key")
            assert result == "TENANT-001"

    @pytest.mark.asyncio
    async def test_get_tenant_id_looks_up_real_tenant_in_production(self):
        def getenv_side_effect(key, default=None):
            envs = {
                "ENV": "production",
            }
            return envs.get(key, default)

        with patch("apps.api.routers.saas.os.getenv", side_effect=getenv_side_effect), \
             patch("apps.api.routers.saas.get_tenant_by_api_key", new_callable=AsyncMock) as mock_lookup:

            mock_lookup.return_value = {"id": "TENANT-REAL-001"}

            from apps.api.routers.saas import get_tenant_id

            result = await get_tenant_id(x_api_key="real-api-key-123")
            assert result == "TENANT-REAL-001"
            mock_lookup.assert_called_once_with("real-api-key-123")

    @pytest.mark.asyncio
    async def test_get_tenant_id_raises_401_when_invalid(self):
        def getenv_side_effect(key, default=None):
            envs = {
                "ENV": "production",
            }
            return envs.get(key, default)

        from fastapi import HTTPException

        with patch("apps.api.routers.saas.os.getenv", side_effect=getenv_side_effect), \
             patch("apps.api.routers.saas.get_tenant_by_api_key", new_callable=AsyncMock) as mock_lookup:

            mock_lookup.return_value = None

            from apps.api.routers.saas import get_tenant_id

            with pytest.raises(HTTPException) as exc_info:
                await get_tenant_id(x_api_key="invalid-key")
            assert exc_info.value.status_code == 401
            assert "Invalid Tenant API Key" in str(exc_info.value.detail)
