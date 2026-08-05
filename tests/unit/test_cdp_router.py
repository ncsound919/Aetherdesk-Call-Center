"""Tests for the CDP router."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.cdp import router
from api.services.auth import verify_tenant_access


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)

    async def _override_tenant():
        return "TENANT-001"

    application.dependency_overrides[verify_tenant_access] = _override_tenant
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestUnifyCustomer:
    def test_unify_success(self, client):
        with patch(
            "api.routers.cdp.cdp_service.unify_customer",
            new_callable=AsyncMock,
            return_value={"id": "C-1", "matched": True},
        ) as mock_unify:
            resp = client.post(
                "/cdp/customers/unify",
                json={"email": "a@b.com", "phone": "+15551234567"},
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "C-1"
        assert mock_unify.call_args.args[0] == "TENANT-001"

    def test_unify_failure_400(self, client):
        with patch(
            "api.routers.cdp.cdp_service.unify_customer",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post("/cdp/customers/unify", json={"email": "a@b.com"})
        assert resp.status_code == 400


class TestGetUnifiedProfile:
    def test_get_profile_success(self, client):
        with patch(
            "api.routers.cdp.cdp_service.get_unified_profile",
            new_callable=AsyncMock,
            return_value={"customer_id": "C-1", "tags": ["vip"]},
        ):
            resp = client.get("/cdp/customers/C-1")
        assert resp.status_code == 200
        assert resp.json()["customer_id"] == "C-1"

    def test_get_profile_not_found(self, client):
        with patch(
            "api.routers.cdp.cdp_service.get_unified_profile",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/cdp/customers/C-MISSING")
        assert resp.status_code == 404


class TestAddTags:
    def test_add_tags_success(self, client):
        with patch(
            "api.routers.cdp.cdp_service.tag_customer",
            new_callable=AsyncMock,
            return_value={"customer_id": "C-1", "tags": ["vip"]},
        ) as mock_tag:
            resp = client.post(
                "/cdp/customers/C-1/tags",
                json={"tags": ["vip", "black-community"]},
            )
        assert resp.status_code == 200
        assert mock_tag.call_args.args[0] == "TENANT-001"
        assert mock_tag.call_args.args[2] == ["vip", "black-community"]

    def test_add_tags_empty(self, client):
        with patch(
            "api.routers.cdp.cdp_service.tag_customer",
            new_callable=AsyncMock,
            return_value={"customer_id": "C-1", "tags": []},
        ) as mock_tag:
            resp = client.post("/cdp/customers/C-1/tags", json={})
        assert resp.status_code == 200
        assert mock_tag.call_args.args[2] == []


class TestSearchCustomers:
    def test_search_success(self, client):
        with patch(
            "api.routers.cdp.cdp_service.search_customers",
            new_callable=AsyncMock,
            return_value=[{"customer_id": "C-1"}],
        ):
            resp = client.get("/cdp/customers/search", params={"q": "acme"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestListSegments:
    def test_list_segments_success(self, client):
        with patch(
            "api.routers.cdp.cdp_service.get_segments",
            new_callable=AsyncMock,
            return_value=[{"id": "seg-1", "name": "Donors"}],
        ):
            resp = client.get("/cdp/segments")
        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "Donors"
