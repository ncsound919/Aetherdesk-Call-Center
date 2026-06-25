import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def auth_bearer():
    cred = MagicMock()
    cred.credentials = "valid_test_token"
    return cred


class TestScriptCRUD:
    @pytest.mark.asyncio
    async def test_create_script_success(self, auth_bearer):
        from api.routers.scripts import create_script, ScriptCreate

        with patch("api.services.db_tenants.create_script_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"id": "script-123"}

            req = ScriptCreate(
                name="Sales Pitch",
                content={"blocks": [{"type": "greeting", "text": "Hi"}]},
                variables=[{"name": "first_name", "type": "string", "source": "lead"}],
            )
            result = await create_script(req, tenant_id="tenant-1")
            assert result["id"] == "script-123"
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_scripts_with_filter(self, auth_bearer):
        from api.routers.scripts import list_scripts

        with patch("api.services.db_tenants.list_scripts_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [
                {"id": "s1", "name": "Test", "content": {"blocks": []}, "variables": [], "is_active": True, "version": 1, "created_at": "2026-01-01"}
            ]
            result = await list_scripts(tenant_id="tenant-1", is_active=True, limit=10, offset=0)
            assert result["count"] == 1
            mock_list.assert_called_once_with("tenant-1", is_active=True, limit=10, offset=0)

    @pytest.mark.asyncio
    async def test_get_script_success(self, auth_bearer):
        from api.routers.scripts import get_script

        with patch("api.services.db_tenants.get_script_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "script-1", "name": "Test", "content": {"blocks": []}, "variables": []}
            result = await get_script("script-1", tenant_id="tenant-1")
            assert result["id"] == "script-1"

    @pytest.mark.asyncio
    async def test_update_script_increments_version(self, auth_bearer):
        from api.routers.scripts import update_script, ScriptUpdate

        with patch("api.services.db_tenants.update_script_db", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = {"id": "script-1", "version": 2}
            req = ScriptUpdate(content={"blocks": [{"type": "greeting", "text": "Updated"}]})
            result = await update_script("script-1", req, tenant_id="tenant-1")
            assert "message" in result
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_script(self, auth_bearer):
        from api.routers.scripts import delete_script

        with patch("api.services.db_tenants.delete_script_db", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = True
            result = await delete_script("script-1", tenant_id="tenant-1")
            assert "message" in result


class TestTemplateOperations:
    @pytest.mark.asyncio
    async def test_list_templates(self, auth_bearer):
        from api.routers.scripts import list_templates

        with patch("api.services.db_tenants.list_script_templates_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [
                {"id": "TPL-1", "name": "B2B Sales", "industry": "sales", "description": "Cold outreach", "content": {}, "variables": []},
            ]
            result = await list_templates(industry="sales", limit=50, offset=0)
            assert result["count"] == 1
            mock_list.assert_called_once_with(industry="sales", limit=50, offset=0)

    @pytest.mark.asyncio
    async def test_get_template(self, auth_bearer):
        from api.routers.scripts import get_template

        with patch("api.services.db_tenants.get_script_template_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "TPL-1", "name": "B2B Sales", "content": {"blocks": []}}
            result = await get_template("TPL-1")
            assert result["id"] == "TPL-1"

    @pytest.mark.asyncio
    async def test_clone_template(self, auth_bearer):
        from api.routers.scripts import clone_template

        with patch("api.services.db_tenants.get_script_template_db", new_callable=AsyncMock) as mock_get, \
             patch("api.services.db_tenants.create_script_db", new_callable=AsyncMock) as mock_create:

            mock_get.return_value = {
                "id": "TPL-1",
                "name": "B2B Sales",
                "content": {"blocks": [{"type": "greeting", "text": "Hi"}]},
                "variables": [{"name": "first_name", "type": "string"}],
            }
            mock_create.return_value = {"id": "script-cloned"}

            result = await clone_template("TPL-1", tenant_id="tenant-1")
            assert result["script_id"] == "script-cloned"
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_clone_template_not_found(self, auth_bearer):
        from fastapi import HTTPException
        from api.routers.scripts import clone_template

        with patch("api.services.db_tenants.get_script_template_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            with pytest.raises(HTTPException) as exc:
                await clone_template("TPL-INVALID", tenant_id="tenant-1")
            assert exc.value.status_code == 404


class TestScriptValidation:
    @pytest.mark.asyncio
    async def test_script_with_blocks(self, auth_bearer):
        from api.routers.scripts import create_script, ScriptCreate

        with patch("api.services.db_tenants.create_script_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"id": "script-multi"}

            req = ScriptCreate(
                name="Multi-block",
                content={
                    "blocks": [
                        {"type": "greeting", "text": "Hi {{first_name}}"},
                        {"type": "pitch", "text": "We help with..."},
                        {"type": "branch", "condition": 'industry == "tech"', "text": "Tech pitch"},
                        {"type": "objection", "trigger": "too expensive", "response": "Let me explain value."},
                        {"type": "close", "text": "Can I schedule a demo?"},
                    ]
                },
                variables=[{"name": "first_name", "type": "string", "source": "lead"}],
            )
            result = await create_script(req, tenant_id="tenant-1")
            assert result["id"] == "script-multi"
            # Verify all 5 blocks passed through
            call_args = mock_create.call_args
            assert len(call_args.kwargs["content"]["blocks"]) == 5