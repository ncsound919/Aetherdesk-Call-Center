"""Unit tests for api.routers.verticals."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.verticals import router
from api.services.auth import verify_tenant_access


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)

    async def _override_verify_tenant_access(tenant_id: str = "TENANT-001"):
        return tenant_id

    app.dependency_overrides[verify_tenant_access] = _override_verify_tenant_access
    with TestClient(app) as c:
        yield c


class TestListVerticals:
    def test_list_verticals_success(self, client):
        expected = [{"id": "healthcare", "name": "Healthcare", "intent_count": 7}]
        with patch(
            "api.routers.verticals.vertical_templates_service.get_verticals",
            return_value=expected,
        ):
            resp = client.get("/verticals/")
        assert resp.status_code == 200
        assert resp.json() == expected


class TestGetVerticalConfig:
    def test_success(self, client):
        expected = {"id": "healthcare", "name": "Healthcare"}
        with patch(
            "api.routers.verticals.vertical_templates_service.get_vertical_config",
            return_value=expected,
        ):
            resp = client.get("/verticals/healthcare")
        assert resp.status_code == 200
        assert resp.json() == expected

    def test_not_found(self, client):
        with patch(
            "api.routers.verticals.vertical_templates_service.get_vertical_config",
            return_value=None,
        ):
            resp = client.get("/verticals/missing")
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Vertical not found"}


class TestApplyVertical:
    def test_success(self, client):
        expected = {"deployment_id": "d1", "status": "active"}
        with patch(
            "api.routers.verticals.vertical_templates_service.apply_vertical_template",
            new_callable=AsyncMock,
            return_value=expected,
        ) as m:
            resp = client.post("/verticals/healthcare/apply", json={})
        assert resp.status_code == 200
        assert resp.json() == expected
        m.assert_awaited_once_with("TENANT-001", "healthcare")

    def test_not_found(self, client):
        with patch(
            "api.routers.verticals.vertical_templates_service.apply_vertical_template",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post("/verticals/missing/apply", json={})
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Vertical not found"}


class TestGetVerticalCompliance:
    def test_success(self, client):
        expected = {"vertical_id": "healthcare", "compliance_standards": ["HIPAA"]}
        with patch(
            "api.routers.verticals.vertical_templates_service.get_vertical_compliance",
            return_value=expected,
        ):
            resp = client.get("/verticals/healthcare/compliance")
        assert resp.status_code == 200
        assert resp.json() == expected

    def test_not_found(self, client):
        with patch(
            "api.routers.verticals.vertical_templates_service.get_vertical_compliance",
            return_value=None,
        ):
            resp = client.get("/verticals/missing/compliance")
        assert resp.status_code == 404


class TestGetVerticalScripts:
    def test_success(self, client):
        expected = {"vertical_id": "healthcare", "script_templates": ["TPL-HEALTHCARE"]}
        with patch(
            "api.routers.verticals.vertical_templates_service.get_vertical_scripts",
            return_value=expected,
        ):
            resp = client.get("/verticals/healthcare/scripts")
        assert resp.status_code == 200
        assert resp.json() == expected

    def test_not_found(self, client):
        with patch(
            "api.routers.verticals.vertical_templates_service.get_vertical_scripts",
            return_value=None,
        ):
            resp = client.get("/verticals/missing/scripts")
        assert resp.status_code == 404
