"""Tests for Fonoster and Twilio webhook routers."""

import hashlib
import hmac
import json
import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════
# Fonoster Webhook Tests
# ═══════════════════════════════════════════════════════════════════

class TestFonsterHMAC:
    def test_deterministic_signature(self):
        secret = "test-secret"
        body = b'{"event_type":"call.answered"}'
        sig1 = hmac.HMAC(secret.encode(), body, hashlib.sha256).hexdigest()
        sig2 = hmac.HMAC(secret.encode(), body, hashlib.sha256).hexdigest()
        assert sig1 == sig2
        assert len(sig1) == 64

    def test_different_body_different_sig(self):
        secret = "test-secret"
        sig1 = hmac.HMAC(secret.encode(), b'{"a":1}', hashlib.sha256).hexdigest()
        sig2 = hmac.HMAC(secret.encode(), b'{"a":2}', hashlib.sha256).hexdigest()
        assert sig1 != sig2

    def test_compare_digest_match(self):
        sig = hmac.HMAC(b"secret", b"body", hashlib.sha256).hexdigest()
        assert hmac.compare_digest(sig, sig) is True


class TestFonsterHandleWebhook:
    def _make_request(self, redis_client=None):
        req = MagicMock()
        req.app.state.redis = redis_client
        return req

    @pytest.mark.asyncio
    async def test_updates_call_status_in_db(self):
        with patch("api.routers.webhooks_fonster.db_update_call_status", new_callable=AsyncMock) as mock_db:
            from api.routers.webhooks_fonster import handle_fonster_webhook
            req = self._make_request()
            await handle_fonster_webhook(req, "CA-001", "active", "SR-001")
            mock_db.assert_awaited_once_with("CA-001", "active")

    @pytest.mark.asyncio
    async def test_publishes_redis_status(self):
        mock_redis = AsyncMock()
        with patch("api.routers.webhooks_fonster.db_update_call_status", new_callable=AsyncMock):
            from api.routers.webhooks_fonster import handle_fonster_webhook
            req = self._make_request(redis_client=mock_redis)
            await handle_fonster_webhook(req, "CA-002", "completed")
            mock_redis.publish.assert_awaited_once()
            channel, msg = mock_redis.publish.await_args[0]
            assert channel == "call:CA-002:status"
            payload = json.loads(msg)
            assert payload["status"] == "completed"

    @pytest.mark.asyncio
    async def test_no_crash_when_redis_none(self):
        with patch("api.routers.webhooks_fonster.db_update_call_status", new_callable=AsyncMock):
            from api.routers.webhooks_fonster import handle_fonster_webhook
            req = self._make_request(redis_client=None)
            await handle_fonster_webhook(req, "CA-005", "failed")

    @pytest.mark.asyncio
    async def test_no_crash_when_db_fails(self):
        with patch("api.routers.webhooks_fonster.db_update_call_status", new_callable=AsyncMock, side_effect=Exception("DB down")):
            from api.routers.webhooks_fonster import handle_fonster_webhook
            req = self._make_request()
            await handle_fonster_webhook(req, "CA-006", "completed")


class TestFonsterWebhookEndpoint:
    PATH = "/webhooks/fonster"

    @pytest.fixture
    def app(self):
        from api.routers.webhooks_fonster import router
        application = FastAPI()
        application.include_router(router)
        application.state.redis = AsyncMock()
        return application

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_call_answered(self, client):
        with patch("api.routers.webhooks_fonster.db_update_call_status", new_callable=AsyncMock):
            resp = client.post(self.PATH, json={"event_type": "call.answered", "call_id": "CA-100"})
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    def test_call_completed(self, client):
        with patch("api.routers.webhooks_fonster.db_update_call_status", new_callable=AsyncMock):
            resp = client.post(self.PATH, json={"event_type": "call.completed", "call_id": "CA-101"})
            assert resp.status_code == 200

    def test_call_failed(self, client):
        with patch("api.routers.webhooks_fonster.db_update_call_status", new_callable=AsyncMock):
            resp = client.post(self.PATH, json={"event_type": "call.failed", "call_id": "CA-102"})
            assert resp.status_code == 200

    def test_valid_hmac_signature(self, client, monkeypatch):
        monkeypatch.setenv("FONOSTER_WEBHOOK_SECRET", "shared-secret")
        body = {"event_type": "call.answered", "call_id": "CA-200"}
        raw = json.dumps(body).encode()
        sig = hmac.HMAC(b"shared-secret", raw, hashlib.sha256).hexdigest()
        with patch("api.routers.webhooks_fonster.db_update_call_status", new_callable=AsyncMock):
            resp = client.post(self.PATH, data=raw, headers={"x-fonoster-signature": sig, "content-type": "application/json"})
            assert resp.status_code == 200

    def test_invalid_hmac_signature_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("FONOSTER_WEBHOOK_SECRET", "shared-secret")
        raw = json.dumps({"event_type": "call.answered", "call_id": "CA-201"}).encode()
        resp = client.post(self.PATH, data=raw, headers={"x-fonoster-signature": "0" * 64, "content-type": "application/json"})
        assert resp.status_code == 401

    def test_missing_signature_in_production_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("FONOSTER_WEBHOOK_SECRET", "shared-secret")
        monkeypatch.setenv("APP_ENV", "production")
        raw = json.dumps({"event_type": "call.answered", "call_id": "CA-202"}).encode()
        resp = client.post(self.PATH, data=raw, headers={"content-type": "application/json"})
        assert resp.status_code == 401

    def test_missing_signature_in_dev_allowed(self, client, monkeypatch):
        monkeypatch.setenv("FONOSTER_WEBHOOK_SECRET", "shared-secret")
        monkeypatch.setenv("APP_ENV", "development")
        raw = json.dumps({"event_type": "call.answered", "call_id": "CA-203"}).encode()
        with patch("api.routers.webhooks_fonster.db_update_call_status", new_callable=AsyncMock):
            resp = client.post(self.PATH, data=raw, headers={"content-type": "application/json"})
            assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# Twilio Webhook Tests
# ═══════════════════════════════════════════════════════════════════

class TestTwilioPing:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)

    def test_ping_returns_200(self):
        from api.routers.webhooks_twilio import router
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            resp = client.get("/webhooks/twilio/ping")
            assert resp.status_code == 200
            assert resp.json() == {"ok": True}


class TestTwilioVoice:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("APP_ENV", "development")

    @pytest.fixture
    def app(self):
        from api.routers.webhooks_twilio import router
        application = FastAPI()
        application.include_router(router)
        return application

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_returns_twiml_with_call_sid(self, client):
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-test123"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/xml"
        assert "CA-test123" in resp.text
        assert "<Stream" in resp.text

    def test_defaults_call_sid_to_unknown(self, client):
        resp = client.post("/webhooks/twilio/voice", data={})
        assert resp.status_code == 200
        assert "unknown" in resp.text

    def test_valid_twiml_structure(self, client):
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-001"})
        assert "<Response>" in resp.text
        assert "</Response>" in resp.text
        assert '<Say voice="alice">' in resp.text
        assert "<Connect>" in resp.text


class TestTwilioCallStatus:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("APP_ENV", "development")

    @pytest.fixture
    def app(self):
        from api.routers.webhooks_twilio import router
        application = FastAPI()
        application.include_router(router)
        return application

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_returns_ok(self, client):
        resp = client.post("/webhooks/twilio/call-status", data={"CallSid": "CA-s1", "CallStatus": "completed"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_defaults_when_fields_missing(self, client):
        resp = client.post("/webhooks/twilio/call-status", data={})
        assert resp.status_code == 200


class TestTwilioGather:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("APP_ENV", "development")

    @pytest.fixture
    def app(self):
        from api.routers.webhooks_twilio import router
        application = FastAPI()
        application.include_router(router)
        return application

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_returns_twiml_with_digits(self, client):
        resp = client.post("/webhooks/twilio/gather", data={"CallSid": "CA-g1", "Digits": "1234"})
        assert resp.status_code == 200
        assert "Thank you. Your input has been received." in resp.text

    def test_speech_result(self, client):
        resp = client.post("/webhooks/twilio/gather", data={"SpeechResult": "Yes, please"})
        assert resp.status_code == 200
        assert "Thank you" in resp.text


class TestTwilioValidation:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("APP_ENV", "development")

    @pytest.fixture
    def app(self):
        from api.routers.webhooks_twilio import router
        application = FastAPI()
        application.include_router(router)
        return application

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            yield c

    def test_dev_mode_bypasses_validation(self, client):
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-dev"})
        assert resp.status_code == 200

    def test_production_missing_signature_returns_403(self, client, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-prod"})
        assert resp.status_code == 403

    def test_production_enforced_on_call_status(self, client, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        resp = client.post("/webhooks/twilio/call-status", data={"CallSid": "CA-1"})
        assert resp.status_code == 403

    def test_production_enforced_on_gather(self, client, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        resp = client.post("/webhooks/twilio/gather", data={"CallSid": "CA-1"})
        assert resp.status_code == 403
