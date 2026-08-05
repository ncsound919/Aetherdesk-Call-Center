"""Tests for the Overlay365 admin router."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.admin_ops import admin_router, public_router
from api.routers.admin_ops import require_admin


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(admin_router)
    application.include_router(public_router)

    async def _override_admin():
        return {"sub": "admin-1", "tenant_id": "TENANT-001"}

    application.dependency_overrides[require_admin] = _override_admin
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestSEOContent:
    def test_list_seo(self, client):
        with patch(
            "api.routers.admin_ops.list_seo_content_db",
            new_callable=AsyncMock,
            return_value=[{"slug": "home", "status": "published"}],
        ):
            resp = client.get("/api/v1/admin/seo/content")
        assert resp.status_code == 200
        assert resp.json()[0]["slug"] == "home"

    def test_upsert_seo(self, client):
        with patch(
            "api.routers.admin_ops.upsert_seo_content_db",
            new_callable=AsyncMock,
            return_value={"slug": "home", "status": "published"},
        ) as mock_upsert:
            resp = client.put(
                "/api/v1/admin/seo/content/home",
                json={"slug": "home", "meta_title": "T", "status": "published"},
            )
        assert resp.status_code == 200
        assert mock_upsert.call_args.args[0] == "home"

    def test_generate_seo_returns_content(self, client):
        with patch(
            "api.routers.admin_ops.llm_client.chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.return_value = type("R", (), {
                "text": '{"meta_title": "T", "meta_description": "D", "og_title": "T", "og_description": "D", "keywords": "a,b"}',
            })()
            resp = client.post("/api/v1/admin/seo/generate", json={"topic": "health"})
        assert resp.status_code == 200
        assert resp.json()["meta_title"] == "T"

    def test_generate_seo_fallback(self, client):
        with patch(
            "api.routers.admin_ops.llm_client.chat",
            new_callable=AsyncMock,
            side_effect=Exception("down"),
        ):
            resp = client.post("/api/v1/admin/seo/generate", json={"topic": "health"})
        assert resp.status_code == 200
        assert "meta_title" in resp.json()


class TestCRM:
    def test_unified_contacts(self, client):
        with patch(
            "api.routers.admin_ops.list_leads_db",
            new_callable=AsyncMock,
            return_value=[
                {"id": "L1", "contact_name": "Alice", "email": "a@b.com", "phone": "555", "company_name": "Acme"}
            ],
        ), patch(
            "api.routers.admin_ops.list_donors_db",
            new_callable=AsyncMock,
            return_value=[{"id": "D1", "name": "Bob", "email": "b@c.com", "amount": 100}],
        ):
            resp = client.get("/api/v1/admin/crm/contacts")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_add_note_requires_note(self, client):
        resp = client.post(
            "/api/v1/admin/crm/contacts/lead/L1/notes",
            json={},
        )
        assert resp.status_code == 400


class TestCoupons:
    def test_list_coupons(self, client):
        with patch(
            "api.routers.admin_ops.list_coupons_db",
            new_callable=AsyncMock,
            return_value=[{"code": "WELCOME20", "status": "local_only"}],
        ):
            resp = client.get("/api/v1/admin/coupons")
        assert resp.status_code == 200

    def test_create_coupon_local_only_without_stripe(self, client):
        with patch.dict("os.environ", {}, clear=True), patch(
            "api.routers.admin_ops.create_coupon_db",
            new_callable=AsyncMock,
            return_value={"code": "TEST10", "status": "local_only"},
        ) as mock_create:
            resp = client.post(
                "/api/v1/admin/coupons",
                json={"code": "test10", "type": "percent", "value": 10},
            )
        assert resp.status_code == 200
        assert mock_create.call_args.kwargs["status"] == "local_only"

    def test_create_coupon_with_stripe(self, client):
        mock_coupon = type("C", (), {"id": "TEST10"})()
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_live_123"}, clear=True), \
             patch("stripe.Coupon.create", return_value=mock_coupon), patch(
            "api.routers.admin_ops.create_coupon_db",
            new_callable=AsyncMock,
            return_value={"code": "TEST10", "status": "active", "stripe_coupon_id": "TEST10"},
        ) as mock_create:
            resp = client.post(
                "/api/v1/admin/coupons",
                json={"code": "TEST10", "type": "percent", "value": 10},
            )
        assert resp.status_code == 200
        assert mock_create.call_args.kwargs["status"] == "active"

    def test_disable_coupon(self, client):
        with patch(
            "api.routers.admin_ops.set_coupon_status_db",
            new_callable=AsyncMock,
        ) as mock_set:
            resp = client.post("/api/v1/admin/coupons/c1/disable")
        assert resp.status_code == 200
        assert mock_set.call_args.args[1] == "disabled"


class TestFlyers:
    def test_list_flyers(self, client):
        with patch(
            "api.routers.admin_ops.list_flyer_saves_db",
            new_callable=AsyncMock,
            return_value=[{"template_id": "t1"}],
        ):
            resp = client.get("/api/v1/admin/flyers")
        assert resp.status_code == 200

    def test_save_flyer(self, client):
        with patch(
            "api.routers.admin_ops.create_flyer_save_db",
            new_callable=AsyncMock,
            return_value={"id": "f1", "template_id": "t1"},
        ) as mock_save:
            resp = client.post(
                "/api/v1/admin/flyers",
                json={"template_id": "t1", "title": "Health Fair"},
            )
        assert resp.status_code == 200
        assert mock_save.call_args.kwargs["template_id"] == "t1"

    def test_generate_flyer_copy(self, client):
        with patch(
            "api.routers.admin_ops.llm_client.chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.return_value = type("R", (), {
                "text": '{"title": "Health Fair", "subtitle": "Free screenings", "cta_text": "Register Now"}',
            })()
            resp = client.post(
                "/api/v1/admin/flyers/generate-copy",
                json={"topic": "health fair", "cta": "Register"},
            )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Health Fair"


class TestPublicSEO:
    def test_public_only_published(self, client):
        with patch(
            "api.routers.admin_ops.list_seo_content_db",
            new_callable=AsyncMock,
            return_value=[{"slug": "home", "status": "published"}],
        ) as mock_list:
            resp = client.get("/api/v1/public/seo/content")
        assert resp.status_code == 200
        assert mock_list.call_args.kwargs["status"] == "published"
