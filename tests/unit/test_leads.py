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
        from api.routers.leads import create_lead, LeadCreate

        with patch("api.services.db_tenants.create_lead_db", new_callable=AsyncMock) as mock_create, \
             patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"tenant_id": "tenant-1"}
            mock_create.return_value = {"id": "lead-123"}

            req = LeadCreate(phone="+15551234567", company_name="Acme Corp")
            result = await create_lead(req, tenant_id="tenant-1")
            assert result["id"] == "lead-123"
            mock_create.assert_called_once()


class TestLeadList:
    @pytest.mark.asyncio
    async def test_list_leads_with_filters(self, auth_bearer):
        from api.routers.leads import list_leads

        with patch("api.services.db_tenants.list_leads_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [
                {"id": "lead-1", "tenant_id": "tenant-1", "phone": "+1", "company_name": "X", "status": "new", "priority": 5, "score": 0.0, "custom_fields": "{}", "created_at": "2026-01-01"}
            ]
            result = await list_leads(tenant_id="tenant-1", status="new", industry="tech", limit=10, offset=0)
            assert result["count"] == 1
            mock_list.assert_called_once_with("tenant-1", status="new", industry="tech", limit=10, offset=0)


class TestLeadUpdate:
    @pytest.mark.asyncio
    async def test_update_lead_success(self, auth_bearer):
        from api.routers.leads import update_lead, LeadUpdate

        with patch("api.services.db_tenants.update_lead_db", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = {"id": "lead-1"}
            req = LeadUpdate(status="interested")
            result = await update_lead("lead-1", req, tenant_id="tenant-1")
            assert "message" in result
            mock_update.assert_called_once()


class TestLeadDelete:
    @pytest.mark.asyncio
    async def test_delete_lead_success(self, auth_bearer):
        from api.routers.leads import delete_lead

        with patch("api.services.db_tenants.delete_lead_db", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = True
            result = await delete_lead("lead-1", tenant_id="tenant-1")
            assert "message" in result


class TestBulkLeadOps:
    @pytest.mark.asyncio
    async def test_bulk_update_leads(self, auth_bearer):
        from api.routers.leads import bulk_update_leads, BulkUpdateRequest, LeadUpdate

        with patch("api.services.db_tenants.bulk_update_leads_db", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = 3
            req = BulkUpdateRequest(lead_ids=["lead-1", "lead-2", "lead-3"], updates=LeadUpdate(status="do_not_call"))
            result = await bulk_update_leads(req, tenant_id="tenant-1")
            assert result["updated"] == 3

    @pytest.mark.asyncio
    async def test_bulk_delete_leads(self, auth_bearer):
        from api.routers.leads import bulk_delete_leads, BulkUpdateRequest, LeadUpdate

        with patch("api.services.db_tenants.bulk_delete_leads_db", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = 2
            req = BulkUpdateRequest(lead_ids=["lead-1", "lead-2"], updates=LeadUpdate())
            result = await bulk_delete_leads(req, tenant_id="tenant-1")
            assert result["deleted"] == 2


class TestCSVUpload:
    @pytest.mark.asyncio
    async def test_upload_csv_success(self, auth_bearer):
        from fastapi import UploadFile

        with patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"tenant_id": "tenant-1"}

            csv_content = b"company,phone\nAcme,+15551234567\nGlobex,+15559876543"
            file = UploadFile(filename="leads.csv", file=io.BytesIO(csv_content))

            from api.routers.leads import upload_leads_csv
            result = await upload_leads_csv(file=file, tenant_id="tenant-1")
            assert result["row_count"] == 2
            assert "company" in result["headers"]
            assert "phone" in result["headers"]
            assert len(result["preview"]) == 2

    @pytest.mark.asyncio
    async def test_upload_rejects_non_csv(self, auth_bearer):
        from fastapi import UploadFile, HTTPException

        from api.routers.leads import upload_leads_csv
        file = UploadFile(filename="leads.xlsx", file=io.BytesIO(b""))
        with pytest.raises(HTTPException) as exc:
            await upload_leads_csv(file=file, tenant_id="tenant-1")
        assert exc.value.status_code == 400


class TestCSVImport:
    @pytest.mark.asyncio
    async def test_import_leads_with_mapping(self, auth_bearer):
        from api.routers.leads import import_leads, ImportRequest

        with patch("api.services.db_tenants.create_lead_db", new_callable=AsyncMock) as mock_create:
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
        from api.routers.leads import import_leads, ImportRequest

        with patch("api.services.db_tenants.create_lead_db", new_callable=AsyncMock) as mock_create:
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
        from api.routers.leads import import_leads, ImportRequest

        req = ImportRequest(
            mapping={},  # empty mapping -> auto-detect
            rows=[
                {"Phone Number": "+15551111111", "Company Name": "Acme"},
            ],
        )
        with patch("api.services.db_tenants.create_lead_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"id": "lead-auto"}
            result = await import_leads(req, tenant_id="tenant-1")
            assert result["imported"] == 1
            # Verify the auto-mapping correctly mapped phone
            call_args = mock_create.call_args
            assert call_args.kwargs.get("phone") == "+15551111111" or call_args.args[1] == "+15551111111"


class TestLeadGet:
    @pytest.mark.asyncio
    async def test_get_lead_success(self):
        from api.routers.leads import get_lead

        with patch("api.services.db_tenants.get_lead_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "lead-1", "tenant_id": "tenant-1", "phone": "+1", "company_name": "Acme", "custom_fields": "{}"}
            result = await get_lead("lead-1", tenant_id="tenant-1")
            assert result["id"] == "lead-1"
            assert isinstance(result["custom_fields"], dict)

    @pytest.mark.asyncio
    async def test_get_lead_custom_fields_json(self):
        from api.routers.leads import get_lead

        with patch("api.services.db_tenants.get_lead_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "lead-1", "custom_fields": '{"source": "web", "campaign": "summer"}'}
            result = await get_lead("lead-1", tenant_id="tenant-1")
            assert result["custom_fields"] == {"source": "web", "campaign": "summer"}

    @pytest.mark.asyncio
    async def test_get_lead_custom_fields_invalid_json(self):
        from api.routers.leads import get_lead

        with patch("api.services.db_tenants.get_lead_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "lead-1", "custom_fields": "not-json-at-all"}
            result = await get_lead("lead-1", tenant_id="tenant-1")
            assert result["custom_fields"] == {}

    @pytest.mark.asyncio
    async def test_get_lead_not_found(self):
        from api.routers.leads import get_lead
        from fastapi import HTTPException

        with patch("api.services.db_tenants.get_lead_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            with pytest.raises(HTTPException) as exc:
                await get_lead("lead-999", tenant_id="tenant-1")
            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_lead_invalid_row_format(self):
        from api.routers.leads import get_lead
        from fastapi import HTTPException

        with patch("api.services.db_tenants.get_lead_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "not_a_dict"
            with pytest.raises(HTTPException) as exc:
                await get_lead("lead-1", tenant_id="tenant-1")
            assert exc.value.status_code == 500


class TestLeadListExtended:
    @pytest.mark.asyncio
    async def test_list_leads_with_row_like_objects(self):
        from api.routers.leads import list_leads

        mock_row = MagicMock()
        mock_row.keys.return_value = ["id", "tenant_id", "phone", "company_name", "custom_fields"]
        mock_row.__getitem__.side_effect = lambda k: {
            "id": "lead-1", "tenant_id": "tenant-1",
            "phone": "+15551234567", "company_name": "Acme",
            "custom_fields": '{"source": "web"}'
        }[k]

        with patch("api.services.db_tenants.list_leads_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [mock_row]
            result = await list_leads(tenant_id="tenant-1")
            assert result["count"] == 1
            assert result["items"][0]["custom_fields"] == {"source": "web"}

    @pytest.mark.asyncio
    async def test_list_leads_skips_non_dict_rows(self):
        from api.routers.leads import list_leads

        with patch("api.services.db_tenants.list_leads_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [42, "string", None]
            result = await list_leads(tenant_id="tenant-1")
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_list_leads_custom_fields_invalid_json(self):
        from api.routers.leads import list_leads

        with patch("api.services.db_tenants.list_leads_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [{
                "id": "lead-1", "tenant_id": "t-1", "phone": "+1",
                "company_name": "X", "custom_fields": "bad-json{{{"
            }]
            result = await list_leads(tenant_id="tenant-1", limit=10, offset=0)
            assert result["count"] == 1
            assert result["items"][0]["custom_fields"] == {}


class TestLeadUpdateExtended:
    @pytest.mark.asyncio
    async def test_update_lead_no_fields(self):
        from api.routers.leads import update_lead, LeadUpdate
        from fastapi import HTTPException

        req = LeadUpdate()
        with pytest.raises(HTTPException) as exc:
            await update_lead("lead-1", req, tenant_id="tenant-1")
        assert exc.value.status_code == 400
        assert "No fields" in exc.value.detail

    @pytest.mark.asyncio
    async def test_update_lead_not_found(self):
        from api.routers.leads import update_lead, LeadUpdate
        from fastapi import HTTPException

        with patch("api.services.db_tenants.update_lead_db", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = None
            req = LeadUpdate(status="interested")
            with pytest.raises(HTTPException) as exc:
                await update_lead("lead-999", req, tenant_id="tenant-1")
            assert exc.value.status_code == 404


class TestLeadDeleteExtended:
    @pytest.mark.asyncio
    async def test_delete_lead_not_found(self):
        from api.routers.leads import delete_lead
        from fastapi import HTTPException

        with patch("api.services.db_tenants.delete_lead_db", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = False
            with pytest.raises(HTTPException) as exc:
                await delete_lead("lead-999", tenant_id="tenant-1")
            assert exc.value.status_code == 404


class TestBulkLeadOpsExtended:
    @pytest.mark.asyncio
    async def test_bulk_update_empty_ids(self):
        from api.routers.leads import bulk_update_leads, BulkUpdateRequest, LeadUpdate
        from fastapi import HTTPException

        req = BulkUpdateRequest(lead_ids=[], updates=LeadUpdate(status="new"))
        with pytest.raises(HTTPException) as exc:
            await bulk_update_leads(req, tenant_id="tenant-1")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_update_empty_updates(self):
        from api.routers.leads import bulk_update_leads, BulkUpdateRequest, LeadUpdate
        from fastapi import HTTPException

        req = BulkUpdateRequest(lead_ids=["lead-1"], updates=LeadUpdate())
        with pytest.raises(HTTPException) as exc:
            await bulk_update_leads(req, tenant_id="tenant-1")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_ids(self):
        from api.routers.leads import bulk_delete_leads, BulkUpdateRequest, LeadUpdate
        from fastapi import HTTPException

        req = BulkUpdateRequest(lead_ids=[], updates=LeadUpdate())
        with pytest.raises(HTTPException) as exc:
            await bulk_delete_leads(req, tenant_id="tenant-1")
        assert exc.value.status_code == 400


class TestCSVUploadExtended:
    @pytest.mark.asyncio
    async def test_upload_rejects_no_filename(self):
        from api.routers.leads import upload_leads_csv
        from fastapi import UploadFile, HTTPException

        file = UploadFile(filename="", file=io.BytesIO(b"data"))
        with pytest.raises(HTTPException) as exc:
            await upload_leads_csv(file=file, tenant_id="tenant-1")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_rejects_too_large(self):
        from api.routers.leads import upload_leads_csv
        from fastapi import UploadFile, HTTPException

        file = UploadFile(filename="leads.csv", file=io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)))
        with pytest.raises(HTTPException) as exc:
            await upload_leads_csv(file=file, tenant_id="tenant-1")
        assert exc.value.status_code == 400
        assert "too large" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_upload_latin1_fallback(self):
        from api.routers.leads import upload_leads_csv
        from fastapi import UploadFile

        # 0xFF and 0xFE are invalid UTF-8 but valid Latin-1
        content = bytes([0xFF, 0xFE]) + b"company,phone\nAcme,+15551234567"
        file = UploadFile(filename="leads.csv", file=io.BytesIO(content))
        result = await upload_leads_csv(file=file, tenant_id="tenant-1")
        assert result["row_count"] == 1  # Latin-1 fallback succeeded

    @pytest.mark.asyncio
    async def test_upload_csv_no_data_rows(self):
        from api.routers.leads import upload_leads_csv
        from fastapi import UploadFile, HTTPException

        file = UploadFile(filename="leads.csv", file=io.BytesIO(b"company,phone"))
        with pytest.raises(HTTPException) as exc:
            await upload_leads_csv(file=file, tenant_id="tenant-1")
        assert exc.value.status_code == 400
        assert "no data" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_upload_too_many_rows(self):
        from api.routers.leads import upload_leads_csv
        from fastapi import UploadFile, HTTPException

        header = b"company,phone\n"
        rows = b"\n".join([f"Co{i},+1555{i:07d}".encode() for i in range(10001)])
        file = UploadFile(filename="leads.csv", file=io.BytesIO(header + rows))
        with pytest.raises(HTTPException) as exc:
            await upload_leads_csv(file=file, tenant_id="tenant-1")
        assert exc.value.status_code == 400


class TestCSVImportExtended:
    @pytest.mark.asyncio
    async def test_import_no_rows(self):
        from api.routers.leads import import_leads, ImportRequest
        from fastapi import HTTPException

        req = ImportRequest(mapping={}, rows=[])
        with pytest.raises(HTTPException) as exc:
            await import_leads(req, tenant_id="tenant-1")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_import_too_many_rows(self):
        from api.routers.leads import import_leads, ImportRequest
        from fastapi import HTTPException

        req = ImportRequest(mapping={}, rows=[{"phone": str(i)} for i in range(10001)])
        with pytest.raises(HTTPException) as exc:
            await import_leads(req, tenant_id="tenant-1")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_import_with_error_row(self):
        from api.routers.leads import import_leads, ImportRequest

        with patch("api.services.db_tenants.create_lead_db", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [{"id": "lead-1"}, Exception("DB constraint failed")]

            req = ImportRequest(
                mapping={"phone": "phone"},
                rows=[
                    {"phone": "+15551111111"},
                    {"phone": "+15552222222"},
                ],
            )
            result = await import_leads(req, tenant_id="tenant-1")
            assert result["imported"] == 1
            assert len(result["errors"]) == 1
            assert "DB constraint" in result["errors"][0]["error"]

    @pytest.mark.asyncio
    async def test_import_auto_maps_surname_to_last_name(self):
        from api.routers.leads import import_leads, ImportRequest

        req = ImportRequest(
            mapping={},
            rows=[{"Surname": "Smith", "Phone": "+15551234567"}],
        )
        with patch("api.services.db_tenants.create_lead_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"id": "lead-1"}
            result = await import_leads(req, tenant_id="tenant-1")
            assert result["imported"] == 1
            assert mock_create.call_args.kwargs.get("last_name") == "Smith"


class TestGetTenantId:
    @pytest.mark.asyncio
    async def test_get_tenant_id_success(self):
        from api.routers.leads import get_tenant_id
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        creds = MagicMock()
        creds.credentials = "valid_tok"
        with patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = {"tenant_id": "tenant-1"}
            result = await get_tenant_id(credentials=creds)
            assert result == "tenant-1"

    @pytest.mark.asyncio
    async def test_get_tenant_id_no_credentials(self):
        from api.routers.leads import get_tenant_id
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_tenant_id(credentials=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_tenant_id_invalid_token(self):
        from api.routers.leads import get_tenant_id
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        creds = MagicMock()
        creds.credentials = "bad_tok"
        with patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = None
            with pytest.raises(HTTPException) as exc:
                await get_tenant_id(credentials=creds)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_tenant_id_missing_tenant_id(self):
        from api.routers.leads import get_tenant_id
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        creds = MagicMock()
        creds.credentials = "valid_tok"
        with patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = {"sub": "user-1"}
            with pytest.raises(HTTPException) as exc:
                await get_tenant_id(credentials=creds)
            assert exc.value.status_code == 400