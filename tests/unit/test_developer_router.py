"""Tests for the developer router (API keys, webhooks, event catalog)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.developer import router
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


class TestApiKeys:
    def test_create_api_key(self, client):
        with patch(
            "api.routers.developer.api_key_service.create_key",
            new_callable=AsyncMock,
            return_value={
                "id": "key-1",
                "name": "prod-key",
                "key_prefix": "ak_abc",
                "full_key": "ak_abc123secret",
                "created_at": "2026-01-01",
                "expires_at": "2027-01-01",
            },
        ) as mock_create:
            resp = client.post(
                "/developer/api-keys",
                json={"name": "prod-key", "scopes": ["read", "write"], "expires_in_days": 365},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "key-1"
        assert body["full_key"] == "ak_abc123secret"
        assert body["masked_key"] == "ak_abc****"
        assert mock_create.call_args.args[0] == "TENANT-001"

    def test_list_api_keys(self, client):
        with patch(
            "api.routers.developer.api_key_service.list_keys",
            new_callable=AsyncMock,
            return_value=[
                {"id": "k1", "name": "a", "masked_key": "ak***", "scopes": ["read"], "is_active": True}
            ],
        ):
            resp = client.get("/developer/api-keys")
        assert resp.status_code == 200
        assert resp.json()[0]["id"] == "k1"

    def test_revoke_api_key_success(self, client):
        with patch(
            "api.routers.developer.api_key_service.revoke_key",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = client.delete("/developer/api-keys/key-1")
        assert resp.status_code == 200
        assert resp.json() == {"success": True}

    def test_revoke_api_key_not_found(self, client):
        with patch(
            "api.routers.developer.api_key_service.revoke_key",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = client.delete("/developer/api-keys/missing")
        assert resp.status_code == 404

    def test_rotate_api_key(self, client):
        with patch(
            "api.routers.developer.api_key_service.rotate_key",
            new_callable=AsyncMock,
            return_value={
                "id": "key-2",
                "name": "prod-key",
                "key_prefix": "ak_new",
                "full_key": "ak_newsecret",
                "scopes": ["read"],
                "created_at": "2026-01-01",
                "expires_at": "2027-01-01",
            },
        ):
            resp = client.post("/developer/api-keys/key-1/rotate")
        assert resp.status_code == 200
        assert resp.json()["full_key"] == "ak_newsecret"

    def test_rotate_api_key_not_found(self, client):
        with patch(
            "api.routers.developer.api_key_service.rotate_key",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post("/developer/api-keys/missing/rotate")
        assert resp.status_code == 404

    def test_get_api_key_usage(self, client):
        with patch(
            "api.routers.developer.api_key_service.get_key_usage",
            new_callable=AsyncMock,
            return_value={
                "key_id": "k1",
                "name": "prod-key",
                "is_active": True,
                "period": "7d",
                "call_count": 10,
            },
        ):
            resp = client.get("/developer/api-keys/k1/usage?period=7d")
        assert resp.status_code == 200

    def test_get_api_key_usage_not_found(self, client):
        with patch(
            "api.routers.developer.api_key_service.get_key_usage",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/developer/api-keys/missing/usage")
        assert resp.status_code == 404


class TestWebhooks:
    def test_register_webhook(self, client):
        with patch(
            "api.routers.developer.webhook_engine.register_webhook",
            new_callable=AsyncMock,
            return_value={
                "id": "wh-1",
                "url": "https://example.com/hook",
                "events_json": '["call.completed"]',
                "secret": "sec",
                "is_active": True,
                "created_at": "2026-01-01",
            },
        ):
            resp = client.post(
                "/developer/webhooks",
                json={"url": "https://example.com/hook", "events": ["call.completed"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "wh-1"
        assert body["events"] == ["call.completed"]

    def test_register_webhook_failed(self, client):
        with patch(
            "api.routers.developer.webhook_engine.register_webhook",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/developer/webhooks",
                json={"url": "https://example.com/hook", "events": ["call.completed"]},
            )
        assert resp.status_code == 400

    def test_list_webhooks(self, client):
        with patch(
            "api.routers.developer.webhook_engine.list_webhooks",
            new_callable=AsyncMock,
            return_value=[
                {"id": "wh-1", "url": "https://x.com", "events_json": "[]", "is_active": True}
            ],
        ):
            resp = client.get("/developer/webhooks")
        assert resp.status_code == 200
        assert resp.json()[0]["id"] == "wh-1"

    def test_unregister_webhook(self, client):
        with patch(
            "api.routers.developer.webhook_engine.unregister_webhook",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = client.delete("/developer/webhooks/wh-1")
        assert resp.status_code == 200
        assert resp.json() == {"success": True}

    def test_unregister_webhook_not_found(self, client):
        with patch(
            "api.routers.developer.webhook_engine.unregister_webhook",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = client.delete("/developer/webhooks/missing")
        assert resp.status_code == 404

    def test_test_webhook_delivery(self, client):
        with patch(
            "api.routers.developer.webhook_engine.get_webhook",
            new_callable=AsyncMock,
            return_value={"id": "wh-1", "url": "https://x.com", "secret": None},
        ), patch(
            "api.services.webhook_engine.create_webhook_delivery_log_db",
            new_callable=AsyncMock,
            return_value={"id": "log-1"},
        ), patch(
            "api.services.webhook_engine._deliver_webhook",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = client.post("/developer/webhooks/wh-1/test")
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "log_id": "log-1"}

    def test_test_webhook_not_found(self, client):
        with patch(
            "api.routers.developer.webhook_engine.get_webhook",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post("/developer/webhooks/missing/test")
        assert resp.status_code == 404

    def test_get_webhook_logs(self, client):
        with patch(
            "api.routers.developer.webhook_engine.get_delivery_logs",
            new_callable=AsyncMock,
            return_value=[
                {"id": "l1", "webhook_id": "wh-1", "event_type": "call.completed", "status": "delivered"}
            ],
        ):
            resp = client.get("/developer/webhooks/wh-1/logs")
        assert resp.status_code == 200
        assert resp.json()[0]["status"] == "delivered"

    def test_retry_webhook_delivery(self, client):
        with patch(
            "api.routers.developer.webhook_engine.retry_delivery",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = client.post("/developer/webhooks/logs/log-1/retry")
        assert resp.status_code == 200
        assert resp.json() == {"success": True}


class TestEventCatalog:
    def test_get_event_catalog(self, client):
        with patch(
            "api.routers.developer.webhook_engine.get_event_catalog",
            return_value={
                "call.completed": {"description": "Call ended", "schema": {"call_id": "str"}},
            },
        ):
            resp = client.get("/developer/events")
        assert resp.status_code == 200
        assert "call.completed" in resp.json()["events"]
