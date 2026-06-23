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