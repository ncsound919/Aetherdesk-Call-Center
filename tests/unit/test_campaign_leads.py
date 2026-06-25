"""Tests for campaign and leads routers."""

import io
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════
# Campaign Leads CRUD Tests
# ═══════════════════════════════════════════════════════════════════

def _make_campaign_app():
    from api.routers.campaign import router
    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    return application


class TestCampaignLeadsList:
    @pytest.fixture
    def app(self):
        return _make_campaign_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_list_leads(self, client):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": "L-1", "tenant_id": "T-001", "company_name": "Acme", "phone": "+15551111111", "priority": 3}
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        with patch("api.routers.campaign.db_context_sync") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.get("/api/v1/campaign/leads", headers={"X-Api-Key": "dev-api-key"})
            assert resp.status_code == 200
            assert len(resp.json()) == 1
            assert resp.json()[0]["company_name"] == "Acme"

    def test_list_leads_with_status_filter(self, client):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{"id": "L-2", "status": "new"}]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        with patch("api.routers.campaign.db_context_sync") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.get("/api/v1/campaign/leads?status=new", headers={"X-Api-Key": "dev-api-key"})
            assert resp.status_code == 200

    def test_list_leads_requires_api_key(self, client):
        resp = client.get("/api/v1/campaign/leads")
        assert resp.status_code == 401


class TestCampaignLeadsCreate:
    @pytest.fixture
    def app(self):
        return _make_campaign_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_create_lead(self, client):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        with patch("api.routers.campaign.db_context_sync") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.post("/api/v1/campaign/leads", json={
                "company_name": "Acme Corp", "phone": "+15551234567",
                "contact_name": "John Doe", "priority": 3,
            }, headers={"X-Api-Key": "dev-api-key"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "created"
            assert resp.json()["id"].startswith("LEAD-")

    def test_create_lead_validates_phone_e164(self, client):
        resp = client.post("/api/v1/campaign/leads", json={
            "company_name": "Bad Phone", "phone": "not-a-phone",
        }, headers={"X-Api-Key": "dev-api-key"})
        assert resp.status_code == 422

    def test_create_lead_priority_bounds(self, client):
        resp = client.post("/api/v1/campaign/leads", json={
            "company_name": "High", "phone": "+15551234567", "priority": 11,
        }, headers={"X-Api-Key": "dev-api-key"})
        assert resp.status_code == 422


class TestCampaignLaunch:
    @pytest.fixture
    def app(self):
        return _make_campaign_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_launch_returns_no_leads_when_empty(self, client):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        with patch("api.routers.campaign.db_context_sync") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.post("/api/v1/campaign/launch", json={
                "profile_id": "PROF-TEST", "max_concurrent": 2,
                "delay_between_calls": 5.0, "filter_status": "new",
            }, headers={"X-Api-Key": "dev-api-key"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "no_leads"

    def test_launch_rejects_duplicate_when_running(self, client):
        import api.routers.campaign as cm
        cm._campaign_running = True
        try:
            resp = client.post("/api/v1/campaign/launch", json={
                "profile_id": "PROF-TEST", "max_concurrent": 2, "delay_between_calls": 5.0,
            }, headers={"X-Api-Key": "dev-api-key"})
            assert resp.status_code == 409
        finally:
            cm._campaign_running = False


class TestCampaignStats:
    @pytest.fixture
    def app(self):
        return _make_campaign_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_stats_returns_conversion_rate(self, client):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "total_leads": 10, "new_leads": 5, "total_calls": 20,
            "interested": 4, "needs_human": 1,
        }
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        with patch("api.routers.campaign.db_context_sync") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.get("/api/v1/campaign/stats", headers={"X-Api-Key": "dev-api-key"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_leads"] == 10
            assert data["conversion_rate"] == "20.0%"

    def test_stats_zero_calls(self, client):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "total_leads": 0, "new_leads": 0, "total_calls": 0,
            "interested": 0, "needs_human": 0,
        }
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        with patch("api.routers.campaign.db_context_sync") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.get("/api/v1/campaign/stats", headers={"X-Api-Key": "dev-api-key"})
            assert resp.json()["conversion_rate"] == "0%"


# ═══════════════════════════════════════════════════════════════════
# Leads CRUD Tests — uses dependency_overrides for JWT auth bypass
# ═══════════════════════════════════════════════════════════════════

def _make_leads_app():
    from api.routers.leads import router, get_tenant_id
    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.dependency_overrides[get_tenant_id] = lambda: "T-001"
    return application


class TestLeadsCreate:
    @pytest.fixture
    def app(self):
        return _make_leads_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_create_lead_success(self, client, app):
        from api.routers.leads import get_tenant_id
        app.dependency_overrides[get_tenant_id] = lambda: "TENANT-001"
        with patch("api.services.db_tenants.create_lead_db", new_callable=AsyncMock, return_value={"id": "lead-abc"}):
            resp = client.post("/api/v1/leads", json={"phone": "+15551234567", "company_name": "Acme"})
            assert resp.status_code == 200
            assert resp.json()["id"] == "lead-abc"

    def test_create_lead_no_auth(self):
        from api.routers.leads import router, get_tenant_id
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        with TestClient(app) as c:
            resp = c.post("/api/v1/leads", json={"phone": "+15551234567"})
            assert resp.status_code == 401


class TestLeadsList:
    @pytest.fixture
    def app(self):
        return _make_leads_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_list_leads(self, client):
        with patch("api.services.db_tenants.list_leads_db", new_callable=AsyncMock, return_value=[
            {"id": "L-1", "phone": "+15551111111", "company_name": "A", "status": "new", "priority": 5, "score": 0.0, "custom_fields": "{}"},
        ]):
            resp = client.get("/api/v1/leads")
            assert resp.status_code == 200
            assert resp.json()["count"] == 1

    def test_list_leads_empty(self, client):
        with patch("api.services.db_tenants.list_leads_db", new_callable=AsyncMock, return_value=[]):
            resp = client.get("/api/v1/leads")
            assert resp.json()["count"] == 0

    def test_list_leads_parses_custom_fields_json(self, client):
        with patch("api.services.db_tenants.list_leads_db", new_callable=AsyncMock, return_value=[
            {"id": "L-1", "phone": "+1", "company_name": "X", "custom_fields": '{"key": "val"}'},
        ]):
            resp = client.get("/api/v1/leads")
            assert resp.json()["items"][0]["custom_fields"] == {"key": "val"}

    def test_list_leads_handles_invalid_custom_fields(self, client):
        with patch("api.services.db_tenants.list_leads_db", new_callable=AsyncMock, return_value=[
            {"id": "L-1", "phone": "+1", "company_name": "X", "custom_fields": "not-json"},
        ]):
            resp = client.get("/api/v1/leads")
            assert resp.json()["items"][0]["custom_fields"] == {}


class TestLeadsGet:
    @pytest.fixture
    def app(self):
        return _make_leads_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_get_lead_success(self, client):
        with patch("api.services.db_tenants.get_lead_db", new_callable=AsyncMock, return_value={"id": "L-1", "phone": "+15551234567", "custom_fields": "{}"}):
            resp = client.get("/api/v1/leads/L-1")
            assert resp.status_code == 200
            assert resp.json()["id"] == "L-1"

    def test_get_lead_not_found(self, client):
        with patch("api.services.db_tenants.get_lead_db", new_callable=AsyncMock, return_value=None):
            resp = client.get("/api/v1/leads/FAKE-ID")
            assert resp.status_code == 404


class TestLeadsUpdate:
    @pytest.fixture
    def app(self):
        return _make_leads_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_update_lead_success(self, client):
        with patch("api.services.db_tenants.update_lead_db", new_callable=AsyncMock, return_value={"id": "L-1"}):
            resp = client.patch("/api/v1/leads/L-1", json={"status": "interested"})
            assert resp.status_code == 200
            assert resp.json()["lead_id"] == "L-1"

    def test_update_lead_not_found(self, client):
        with patch("api.services.db_tenants.update_lead_db", new_callable=AsyncMock, return_value=None):
            resp = client.patch("/api/v1/leads/FAKE-ID", json={"status": "new"})
            assert resp.status_code == 404


class TestLeadsDelete:
    @pytest.fixture
    def app(self):
        return _make_leads_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_delete_lead_success(self, client):
        with patch("api.services.db_tenants.delete_lead_db", new_callable=AsyncMock, return_value=True):
            resp = client.delete("/api/v1/leads/L-1")
            assert resp.status_code == 200
            assert resp.json()["lead_id"] == "L-1"

    def test_delete_lead_not_found(self, client):
        with patch("api.services.db_tenants.delete_lead_db", new_callable=AsyncMock, return_value=False):
            resp = client.delete("/api/v1/leads/FAKE-ID")
            assert resp.status_code == 404


class TestLeadsCSVUpload:
    @pytest.fixture
    def app(self):
        return _make_leads_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_upload_csv_success(self, client):
        csv_content = b"company,phone\nAcme,+15551234567\nGlobex,+15559876543"
        resp = client.post("/api/v1/leads/upload", files={"file": ("leads.csv", io.BytesIO(csv_content), "text/csv")})
        assert resp.status_code == 200
        assert resp.json()["row_count"] == 2

    def test_upload_rejects_non_csv(self, client):
        resp = client.post("/api/v1/leads/upload", files={"file": ("leads.xlsx", io.BytesIO(b""), "application/octet-stream")})
        assert resp.status_code == 400

    def test_upload_empty_csv(self, client):
        resp = client.post("/api/v1/leads/upload", files={"file": ("empty.csv", io.BytesIO(b"company,phone\n"), "text/csv")})
        assert resp.status_code == 400


class TestLeadsBulkOperations:
    @pytest.fixture
    def app(self):
        return _make_leads_app()

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_bulk_update_success(self, client):
        with patch("api.services.db_tenants.bulk_update_leads_db", new_callable=AsyncMock, return_value=3):
            resp = client.post("/api/v1/leads/bulk-update", json={"lead_ids": ["L-1", "L-2", "L-3"], "updates": {"status": "do_not_call"}})
            assert resp.status_code == 200
            assert resp.json()["updated"] == 3

    def test_bulk_update_empty_ids(self, client):
        resp = client.post("/api/v1/leads/bulk-update", json={"lead_ids": [], "updates": {"status": "new"}})
        assert resp.status_code == 400

    def test_bulk_delete_success(self, client):
        with patch("api.services.db_tenants.bulk_delete_leads_db", new_callable=AsyncMock, return_value=2):
            resp = client.post("/api/v1/leads/bulk-delete", json={"lead_ids": ["L-1", "L-2"], "updates": {}})
            assert resp.status_code == 200
            assert resp.json()["deleted"] == 2
