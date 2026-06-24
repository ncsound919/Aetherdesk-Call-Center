import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.services.auth import verify_api_key, verify_tenant_access


@pytest.fixture
def app():
    """Create a minimal FastAPI app with just the tenants router."""
    from apps.api.routers.tenants import router

    application = FastAPI()
    application.include_router(router)

    fonster = AsyncMock()
    fonster.create_application = AsyncMock(return_value={"success": True})
    application.state.fonster_client = fonster
    application.state.redis = AsyncMock()

    async def _override_api_key():
        return "TENANT-001"

    application.dependency_overrides[verify_api_key] = _override_api_key

    async def _override_tenant():
        return "TENANT-001"

    application.dependency_overrides[verify_tenant_access] = _override_tenant

    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestCreateTenant:
    """Tests for POST /api/v1/tenants."""

    def test_create_tenant_success(self, client):
        with patch("apps.api.routers.tenants.create_tenant_db", new_callable=AsyncMock) as mock_create, \
             patch("apps.api.routers.tenants.get_pg_pool", new_callable=AsyncMock) as mock_pool:

            mock_create.return_value = {
                "id": "tenant-1",
                "plan_id": "plan-abc",
            }
            mock_pool.return_value.fetchrow = AsyncMock(return_value={"name": "Professional"})

            resp = client.post(
                "/api/v1/tenants",
                json={
                    "name": "Acme Corp",
                    "email": "admin@acme.com",
                    "phone": "+15551234567",
                    "gdpr_consent": True,
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["name"] == "Acme Corp"
            assert body["email"] == "admin@acme.com"
            assert body["phone"] == "+15551234567"
            assert body["plan_name"] == "Professional"
            assert body["status"] == "active"
            assert body["gdpr_consent"] is True

    def test_create_tenant_without_fonster(self, app, client):
        app.state.fonster_client = None

        with patch("apps.api.routers.tenants.create_tenant_db", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {
                "id": "tenant-2",
                "plan_id": None,
            }

            resp = client.post(
                "/api/v1/tenants",
                json={
                    "name": "Startup Inc",
                    "email": "hello@startup.io",
                    "gdpr_consent": False,
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["name"] == "Startup Inc"
            assert body["plan_name"] == "Starter"

    def test_create_tenant_plan_name_fallback(self, client):
        with patch("apps.api.routers.tenants.create_tenant_db", new_callable=AsyncMock) as mock_create, \
             patch("apps.api.routers.tenants.get_pg_pool", new_callable=AsyncMock) as mock_pool:

            mock_create.return_value = {
                "id": "tenant-3",
                "plan_id": "plan-xyz",
            }
            mock_pool.return_value.fetchrow = AsyncMock(side_effect=Exception("DB error"))

            resp = client.post(
                "/api/v1/tenants",
                json={
                    "name": "Resilient Co",
                    "email": "ops@resilient.co",
                },
            )
            assert resp.status_code == 201
            assert resp.json()["plan_name"] == "Starter"

    def test_create_tenant_validation_error(self, client):
        resp = client.post(
            "/api/v1/tenants",
            json={"name": "AB", "email": "not-an-email"},
        )
        assert resp.status_code == 422


class TestGetTenant:
    """Tests for GET /api/v1/tenants/{tenant_id}."""

    def test_get_tenant_found(self, client):
        with patch("apps.api.routers.tenants.get_tenant_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "tenant-1",
                "name": "Acme Corp",
                "email": "admin@acme.com",
                "phone": "+15551234567",
                "is_active": True,
                "settings": {"maxConcurrentCalls": 10},
                "gdpr_consent": True,
                "created_at": "2026-01-01T00:00:00",
            }

            resp = client.get("/api/v1/tenants/tenant-1")
            assert resp.status_code == 200
            body = resp.json()
            assert body["id"] == "tenant-1"
            assert body["name"] == "Acme Corp"
            assert body["email"] == "admin@acme.com"
            assert body["phone"] == "+15551234567"
            assert body["status"] == "active"
            assert body["gdpr_consent"] is True

    def test_get_tenant_inactive(self, client):
        with patch("apps.api.routers.tenants.get_tenant_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "tenant-1",
                "name": "Inactive Co",
                "email": "inactive@co.com",
                "phone": None,
                "is_active": False,
                "settings": {},
                "gdpr_consent": False,
                "created_at": "2026-01-01T00:00:00",
            }

            resp = client.get("/api/v1/tenants/tenant-1")
            assert resp.status_code == 200
            assert resp.json()["status"] == "inactive"

    def test_get_tenant_not_found(self, client):
        with patch("apps.api.routers.tenants.get_tenant_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            resp = client.get("/api/v1/tenants/missing-tenant")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Tenant not found"
