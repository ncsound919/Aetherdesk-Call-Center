import io
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def auth_bearer():
    cred = MagicMock()
    cred.credentials = "valid_test_token"
    return cred


class TestLeadCreate:
    @pytest.mark.asyncio
    async def test_create_lead_success(self, auth_bearer):
        from apps.api.routers.leads import create_lead, LeadCreate

        with patch("apps.api.services.db_tenants.create_lead_db", new_callable=AsyncMock) as mock_create, \
             patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"tenant_id": "tenant-1"}
            mock_create.return_value = {"id": "lead-123"}

            req = LeadCreate(phone="+15551234567", company_name="Acme Corp")
            result = await create_lead(req, tenant_id="tenant-1")
            assert result["id"] == "lead-123"
            mock_create.assert_called_once()


class TestLeadList:
    @pytest.mark.asyncio
    async def test_list_leads_with_filters(self, auth_bearer):
        from apps.api.routers.leads import list_leads

        with patch("apps.api.services.db_tenants.list_leads_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [
                {"id": "lead-1", "tenant_id": "tenant-1", "phone": "+1", "company_name": "X", "status": "new", "priority": 5, "score": 0.0, "custom_fields": "{}", "created_at": "2026-01-01"}
            ]
            result = await list_leads(tenant_id="tenant-1", status="new", industry="tech", limit=10, offset=0)
            assert result["count"] == 1
            mock_list.assert_called_once_with("tenant-1", status="new", industry="tech", limit=10, offset=0)


class TestLeadUpdate:
    @pytest.mark.asyncio
    async def test_update_lead_success(self, auth_bearer):
        from apps.api.routers.leads import update_lead, LeadUpdate

        with patch("apps.api.services.db_tenants.update_lead_db", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = {"id": "lead-1"}
            req = LeadUpdate(status="interested")
            result = await update_lead("lead-1", req, tenant_id="tenant-1")
            assert "message" in result
            mock_update.assert_called_once()


class TestLeadDelete:
    @pytest.mark.asyncio
    async def test_delete_lead_success(self, auth_bearer):
        from apps.api.routers.leads import delete_lead

        with patch("apps.api.services.db_tenants.delete_lead_db", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = True
            result = await delete_lead("lead-1", tenant_id="tenant-1")
            assert "message" in result


class TestBulkLeadOps:
    @pytest.mark.asyncio
    async def test_bulk_update_leads(self, auth_bearer):
        from apps.api.routers.leads import bulk_update_leads, BulkUpdateRequest, LeadUpdate

        with patch("apps.api.services.db_tenants.bulk_update_leads_db", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = 3
            req = BulkUpdateRequest(lead_ids=["lead-1", "lead-2", "lead-3"], updates=LeadUpdate(status="do_not_call"))
            result = await bulk_update_leads(req, tenant_id="tenant-1")
            assert result["updated"] == 3

    @pytest.mark.asyncio
    async def test_bulk_delete_leads(self, auth_bearer):
        from apps.api.routers.leads import bulk_delete_leads, BulkUpdateRequest, LeadUpdate

        with patch("apps.api.services.db_tenants.bulk_delete_leads_db", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = 2
            req = BulkUpdateRequest(lead_ids=["lead-1", "lead-2"], updates=LeadUpdate())
            result = await bulk_delete_leads(req, tenant_id="tenant-1")
            assert result["deleted"] == 2


class TestCSVUpload:
    @pytest.mark.asyncio
    async def test_upload_csv_success(self, auth_bearer):
        from fastapi import UploadFile

        with patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"tenant_id": "tenant-1"}

            csv_content = b"company,phone\nAcme,+15551234567\nGlobex,+15559876543"
            file = UploadFile(filename="leads.csv", file=io.BytesIO(csv_content))

            from apps.api.routers.leads import upload_leads_csv
            result = await upload_leads_csv(file=file, tenant_id="tenant-1")
            assert result["row_count"] == 2
            assert "company" in result["headers"]
            assert "phone" in result["headers"]
            assert len(result["preview"]) == 2

    @pytest.mark.asyncio
    async def test_upload_rejects_non_csv(self, auth_bearer):
        from fastapi import UploadFile, HTTPException

        from apps.api.routers.leads import upload_leads_csv
        file = UploadFile(filename="leads.xlsx", file=io.BytesIO(b""))
        with pytest.raises(HTTPException) as exc:
            await upload_leads_csv(file=file, tenant_id="tenant-1")
        assert exc.value.status_code == 400


class TestCSVImport:
    @pytest.mark.asyncio
    async def test_import_leads_with_mapping(self, auth_bearer):
        from apps.api.routers.leads import import_leads, ImportRequest

        with patch("apps.api.services.db_tenants.create_lead_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"id": "lead-1"}

            req = ImportRequest(
                mapping={"company": "company_name", "phone": "phone"},
                rows=[
                    {"company": "Acme", "phone": "+15551111111"},
                    {"company": "Globex", "phone": "+15552222222"},
                ],
            )
            result = await import_leads(req, tenant_id="tenant-1")
            assert result["imported"] == 2
            assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_import_skips_rows_missing_phone(self, auth_bearer):
        from apps.api.routers.leads import import_leads, ImportRequest

        with patch("apps.api.services.db_tenants.create_lead_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"id": "lead-1"}

            req = ImportRequest(
                mapping={"company": "company_name", "phone": "phone"},
                rows=[
                    {"company": "Acme", "phone": "+15551111111"},
                    {"company": "NoPhone"},  # missing phone
                ],
            )
            result = await import_leads(req, tenant_id="tenant-1")
            assert result["imported"] == 1
            assert len(result["errors"]) == 1
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_auto_maps_columns(self, auth_bearer):
        from apps.api.routers.leads import import_leads, ImportRequest

        req = ImportRequest(
            mapping={},  # empty mapping -> auto-detect
            rows=[
                {"Phone Number": "+15551111111", "Company Name": "Acme"},
            ],
        )
        with patch("apps.api.services.db_tenants.create_lead_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"id": "lead-auto"}
            result = await import_leads(req, tenant_id="tenant-1")
            assert result["imported"] == 1
            # Verify the auto-mapping correctly mapped phone
            call_args = mock_create.call_args
            assert call_args.kwargs.get("phone") == "+15551111111" or call_args.args[1] == "+15551111111"