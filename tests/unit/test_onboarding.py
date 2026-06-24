import pytest
import json
from unittest.mock import AsyncMock, patch


class TestOnboardingBusinessInfo:
    @pytest.mark.asyncio
    async def test_save_business_info(self):
        from apps.api.routers.onboarding import save_business_info, BusinessInfoRequest

        with patch("apps.api.services.db_tenants.get_user_by_id_db", new_callable=AsyncMock) as mock_user, \
             patch("apps.api.services.db_tenants.create_tenant", new_callable=AsyncMock) as mock_tenant, \
             patch("apps.api.services.db_tenants.update_user_onboarding_db", new_callable=AsyncMock):

            mock_user.return_value = {"id": "user-1", "email": "test@example.com"}
            mock_tenant.return_value = {"id": "tenant-123"}

            info = BusinessInfoRequest(
                company_name="Test Corp",
                industry="sales",
                timezone="America/New_York"
            )
            result = await save_business_info(info)

            assert result["tenant_id"] == "tenant-123"
            mock_tenant.assert_called_once()


class TestOnboardingImportLeads:
    @pytest.mark.asyncio
    async def test_import_csv_leads(self):
        from apps.api.routers.onboarding import import_leads
        from fastapi import UploadFile
        import io

        with patch("apps.api.services.db_tenants.update_user_onboarding_db", new_callable=AsyncMock):

            csv_content = b"company,phone,industry\nAcme Corp,+15551234567,tech\nGlobex Inc,+15559876543,healthcare"
            file = UploadFile(filename="leads.csv", file=io.BytesIO(csv_content))

            mapping = json.dumps({"company": "company", "phone": "phone", "industry": "industry"})
            result = await import_leads(file=file, mapping=mapping)

            assert result["total"] == 2
            assert len(result["errors"]) == 0


class TestOnboardingCompletion:
    @pytest.mark.asyncio
    async def test_complete_onboarding(self):
        from apps.api.routers.onboarding import complete_onboarding

        with patch("apps.api.services.db_tenants.update_user_onboarding_db", new_callable=AsyncMock) as mock_update:
            result = await complete_onboarding()
            assert result["message"] == "Onboarding completed"
            mock_update.assert_called_once_with("USER-ADMIN-001", step=5, completed=True)


class TestSaveScript:
    @pytest.mark.asyncio
    async def test_save_script_success(self):
        from apps.api.routers.onboarding import save_script, ScriptSaveRequest

        with patch("apps.api.services.db_tenants.update_user_onboarding_db", new_callable=AsyncMock), \
             patch("apps.api.services.db_tenants.create_agent_profile_db", new_callable=AsyncMock) as mock_profile:

            script = ScriptSaveRequest(
                name="Sales Script",
                content="Hello {{name}}, this is {{agent}}",
                variables=[{"name": "name"}, {"name": "agent"}]
            )
            result = await save_script(script)
            assert "script_id" in result
            assert result["script_id"].startswith("PROF-")
            mock_profile.assert_called_once()
            args = mock_profile.call_args
            assert args.kwargs["name"] == "Sales Script"
            assert args.kwargs["prompt"] == script.content


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_get_onboarding_status_success(self):
        from apps.api.routers.onboarding import get_onboarding_status

        with patch("apps.api.services.db_tenants.get_user_by_id_db", new_callable=AsyncMock) as mock_user:
            mock_user.return_value = {"onboarding_completed": False, "onboarding_step": 2}
            result = await get_onboarding_status()
            assert result["completed"] is False
            assert result["current_step"] == 2

    @pytest.mark.asyncio
    async def test_get_onboarding_status_completed(self):
        from apps.api.routers.onboarding import get_onboarding_status

        with patch("apps.api.services.db_tenants.get_user_by_id_db", new_callable=AsyncMock) as mock_user:
            mock_user.return_value = {"onboarding_completed": True, "onboarding_step": 5}
            result = await get_onboarding_status()
            assert result["completed"] is True
            assert result["current_step"] == 5

    @pytest.mark.asyncio
    async def test_get_onboarding_status_user_not_found(self):
        from apps.api.routers.onboarding import get_onboarding_status
        from fastapi import HTTPException

        with patch("apps.api.services.db_tenants.get_user_by_id_db", new_callable=AsyncMock) as mock_user:
            mock_user.return_value = None
            with pytest.raises(HTTPException) as exc:
                await get_onboarding_status()
            assert exc.value.status_code == 404


class TestOnboardingBusinessInfoExtended:
    @pytest.mark.asyncio
    async def test_save_business_info_user_not_found(self):
        from apps.api.routers.onboarding import save_business_info, BusinessInfoRequest
        from fastapi import HTTPException

        with patch("apps.api.services.db_tenants.get_user_by_id_db", new_callable=AsyncMock) as mock_user:
            mock_user.return_value = None
            info = BusinessInfoRequest(company_name="Test", industry="tech")
            with pytest.raises(HTTPException) as exc:
                await save_business_info(info)
            assert exc.value.status_code == 404


class TestOnboardingImportLeadsExtended:
    @pytest.mark.asyncio
    async def test_import_rejects_non_csv(self):
        from apps.api.routers.onboarding import import_leads
        from fastapi import UploadFile, HTTPException
        import io

        with patch("apps.api.services.db_tenants.update_user_onboarding_db", new_callable=AsyncMock):
            file = UploadFile(filename="data.pdf", file=io.BytesIO(b"data"))
            with pytest.raises(HTTPException) as exc:
                await import_leads(file=file)
            assert exc.value.status_code == 400
            assert "CSV or Excel" in exc.value.detail

    @pytest.mark.asyncio
    async def test_import_rejects_too_large(self):
        from apps.api.routers.onboarding import import_leads
        from fastapi import UploadFile, HTTPException
        import io

        with patch("apps.api.services.db_tenants.update_user_onboarding_db", new_callable=AsyncMock):
            file = UploadFile(filename="leads.csv", file=io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)))
            with pytest.raises(HTTPException) as exc:
                await import_leads(file=file)
            assert exc.value.status_code == 400
            assert "too large" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_import_too_many_rows(self):
        from apps.api.routers.onboarding import import_leads
        from fastapi import UploadFile, HTTPException
        import io

        with patch("apps.api.services.db_tenants.update_user_onboarding_db", new_callable=AsyncMock):
            header = b"company,phone\n"
            rows = b"\n".join([f"Co{i},+1555{i:07d}".encode() for i in range(10001)])
            file = UploadFile(filename="leads.csv", file=io.BytesIO(header + rows))
            with pytest.raises(HTTPException) as exc:
                await import_leads(file=file)
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_import_missing_phone_and_company(self):
        from apps.api.routers.onboarding import import_leads
        from fastapi import UploadFile
        import io, json

        with patch("apps.api.services.db_tenants.update_user_onboarding_db", new_callable=AsyncMock):
            csv_content = b"email,industry\na@b.com,tech\nc@d.com,health"
            file = UploadFile(filename="leads.csv", file=io.BytesIO(csv_content))
            mapping = json.dumps({"email": "email", "industry": "industry"})
            result = await import_leads(file=file, mapping=mapping)
            assert result["total"] == 0
            assert len(result["errors"]) == 2