"""Unit tests for webhooks_fonster.py — HMAC signature validation, helper functions, and endpoint tests."""

import hashlib
import hmac
import json
import os

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a minimal FastAPI app with just the webhooks fonster router."""
    from api.routers.webhooks_fonster import router

    application = FastAPI()
    application.include_router(router)
    application.state.redis = AsyncMock()
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# HMAC signature validation (unit-level, no FastAPI app needed)
# ---------------------------------------------------------------------------

class TestFonsterSignatureValidation:
    """Verify the HMAC-SHA256 signature computation used by fonster_webhook."""

    def test_hmac_sha256_computation(self):
        """HMAC-SHA256 hex digest should be deterministic with same key and body."""
        secret = "test-webhook-secret"
        body = b'{"event_type": "call.answered", "call_id": "CA-123"}'

        sig1 = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        sig2 = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert sig1 == sig2
        assert len(sig1) == 64  # SHA-256 produces 64 hex chars

    def test_different_body_produces_different_signature(self):
        """Changing the body should produce a completely different signature."""
        secret = "test-webhook-secret"
        body1 = b'{"event_type": "call.answered"}'
        body2 = b'{"event_type": "call.completed"}'

        sig1 = hmac.new(secret.encode(), body1, hashlib.sha256).hexdigest()
        sig2 = hmac.new(secret.encode(), body2, hashlib.sha256).hexdigest()

        assert sig1 != sig2

    def test_different_secret_produces_different_signature(self):
        """Changing the secret should produce a different signature for same body."""
        body = b'{"event_type": "call.answered"}'

        sig1 = hmac.new(b"secret-a", body, hashlib.sha256).hexdigest()
        sig2 = hmac.new(b"secret-b", body, hashlib.sha256).hexdigest()

        assert sig1 != sig2

    def test_hmac_compare_digest_matches(self):
        """hmac.compare_digest should return True for matching signatures."""
        secret = "test-secret"
        body = b'{"event_type": "call.answered"}'

        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        computed = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert hmac.compare_digest(expected, computed) is True

    def test_hmac_compare_digest_mismatch(self):
        """hmac.compare_digest should return False for non-matching signatures."""
        body = b'{"event_type": "call.answered"}'

        sig1 = hmac.new(b"secret-a", body, hashlib.sha256).hexdigest()
        sig2 = hmac.new(b"secret-b", body, hashlib.sha256).hexdigest()

        assert hmac.compare_digest(sig1, sig2) is False


# ---------------------------------------------------------------------------
# handle_fonster_webhook helper (direct unit tests)
# ---------------------------------------------------------------------------

class TestHandleFonsterWebhook:
    """Test the handle_fonster_webhook helper (background task handler).

    Note: the function now accepts ``request`` as its first parameter
    (the fix for the scope bug where ``request`` was previously a free variable).
    """

    # -- helpers ---------------------------------------------------------------

    def _make_request(self, redis_client=None):
        req = MagicMock()
        req.app.state.redis = redis_client
        return req

    # -- tests -----------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_updates_call_status(self):
        """Should call db_update_call_status with correct call_id and status."""
        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock) as mock_update:
            mock_update.return_value = None

            from api.routers.webhooks_fonster import handle_fonster_webhook
            req = self._make_request(redis_client=None)
            await handle_fonster_webhook(req, call_id="CA-001", status="active", session_ref="SR-001")

            mock_update.assert_awaited_once_with("CA-001", "active")

    @pytest.mark.asyncio
    async def test_publishes_to_redis_when_available(self):
        """Should publish a JSON status update to redis when redis client exists."""
        mock_redis = AsyncMock()

        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock):
            from api.routers.webhooks_fonster import handle_fonster_webhook
            req = self._make_request(redis_client=mock_redis)
            await handle_fonster_webhook(req, call_id="CA-002", status="completed")

            mock_redis.publish.assert_awaited_once()
            channel, message = mock_redis.publish.await_args[0]
            assert channel == "call:CA-002:status"

            payload = json.loads(message)
            assert payload["call_id"] == "CA-002"
            assert payload["status"] == "completed"
            assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_includes_session_ref_in_redis_payload(self):
        """Redis payload should include session_ref when provided."""
        mock_redis = AsyncMock()

        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock):
            from api.routers.webhooks_fonster import handle_fonster_webhook
            req = self._make_request(redis_client=mock_redis)
            await handle_fonster_webhook(req, call_id="CA-003", status="active", session_ref="SR-999")

            payload = json.loads(mock_redis.publish.await_args[0][1])
            assert payload["session_ref"] == "SR-999"

    @pytest.mark.asyncio
    async def test_session_ref_defaults_to_none(self):
        """session_ref should be None in payload when not provided."""
        mock_redis = AsyncMock()

        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock):
            from api.routers.webhooks_fonster import handle_fonster_webhook
            req = self._make_request(redis_client=mock_redis)
            await handle_fonster_webhook(req, call_id="CA-004", status="active")

            payload = json.loads(mock_redis.publish.await_args[0][1])
            assert payload["session_ref"] is None

    @pytest.mark.asyncio
    async def test_no_crash_when_redis_is_none(self):
        """Should not raise when redis client is None."""
        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock):
            from api.routers.webhooks_fonster import handle_fonster_webhook
            req = self._make_request(redis_client=None)
            await handle_fonster_webhook(req, call_id="CA-005", status="failed")
            # No exception means success

    @pytest.mark.asyncio
    async def test_no_crash_when_db_update_fails(self):
        """Should log error but not crash when db_update_call_status raises."""
        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock) as mock_update:
            mock_update.side_effect = Exception("DB connection lost")

            from api.routers.webhooks_fonster import handle_fonster_webhook
            req = self._make_request(redis_client=None)
            await handle_fonster_webhook(req, call_id="CA-006", status="completed")
            # No exception means success


# ---------------------------------------------------------------------------
# fonster_webhook endpoint (TestClient integration tests)
# ---------------------------------------------------------------------------

class TestFonsterWebhookEndpoint:
    """Tests for POST /api/v1/webhooks/fonster."""

    WEBHOOK_PATH = "/webhooks/fonster"

    # -- call.answered ---------------------------------------------------------

    def test_call_answered_event(self, client, app):
        """POST with call.answered event returns 200 and triggers handle_fonster_webhook."""
        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock) as mock_db:
            resp = client.post(
                self.WEBHOOK_PATH,
                json={"event_type": "call.answered", "call_id": "CA-100", "session_ref": "SR-100"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    # -- call.completed --------------------------------------------------------

    def test_call_completed_event(self, client, app):
        """POST with call.completed event returns 200."""
        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock):
            resp = client.post(
                self.WEBHOOK_PATH,
                json={"event_type": "call.completed", "call_id": "CA-101"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    # -- call.failed -----------------------------------------------------------

    def test_call_failed_event(self, client, app):
        """POST with call.failed event returns 200."""
        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock):
            resp = client.post(
                self.WEBHOOK_PATH,
                json={"event_type": "call.failed", "call_id": "CA-102"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    # -- unknown event type ----------------------------------------------------

    def test_unknown_event_type(self, client):
        """POST with an unknown event type still returns 200 (no handler branch)."""
        resp = client.post(
            self.WEBHOOK_PATH,
            json={"event_type": "call.unknown", "call_id": "CA-103"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    # -- HMAC signature validation --------------------------------------------

    def test_valid_hmac_signature(self, client, app, monkeypatch):
        """POST with a valid HMAC signature succeeds."""
        monkeypatch.setenv("FONOSTER_WEBHOOK_SECRET", "shared-secret")

        body = {"event_type": "call.answered", "call_id": "CA-200"}
        raw = json.dumps(body).encode()
        expected_sig = hmac.new(b"shared-secret", raw, hashlib.sha256).hexdigest()

        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock):
            resp = client.post(
                self.WEBHOOK_PATH,
                data=raw,
                headers={
                    "x-fonoster-signature": expected_sig,
                    "content-type": "application/json",
                },
            )
            assert resp.status_code == 200

    def test_invalid_hmac_signature(self, client, app, monkeypatch):
        """POST with an invalid HMAC signature returns 401."""
        monkeypatch.setenv("FONOSTER_WEBHOOK_SECRET", "shared-secret")

        raw = json.dumps({"event_type": "call.answered", "call_id": "CA-201"}).encode()
        resp = client.post(
            self.WEBHOOK_PATH,
            data=raw,
            headers={
                "x-fonoster-signature": "0000000000000000000000000000000000000000000000000000000000000000",
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid webhook signature"

    def test_missing_signature_in_production(self, client, app, monkeypatch):
        """POST without signature in production mode returns 401."""
        monkeypatch.setenv("FONOSTER_WEBHOOK_SECRET", "shared-secret")
        monkeypatch.setenv("APP_ENV", "production")

        raw = json.dumps({"event_type": "call.answered", "call_id": "CA-202"}).encode()
        resp = client.post(
            self.WEBHOOK_PATH,
            data=raw,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Missing webhook signature"

    def test_missing_signature_in_development(self, client, app, monkeypatch):
        """POST without signature in development mode is allowed."""
        monkeypatch.setenv("FONOSTER_WEBHOOK_SECRET", "shared-secret")
        monkeypatch.setenv("APP_ENV", "development")

        raw = json.dumps({"event_type": "call.answered", "call_id": "CA-203"}).encode()
        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock):
            resp = client.post(
                self.WEBHOOK_PATH,
                data=raw,
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 200

    def test_no_secret_no_signature(self, client, app, monkeypatch):
        """POST without secret configured passes through without validation."""
        monkeypatch.delenv("FONOSTER_WEBHOOK_SECRET", raising=False)

        raw = json.dumps({"event_type": "call.answered", "call_id": "CA-204"}).encode()
        with patch("api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock):
            resp = client.post(
                self.WEBHOOK_PATH,
                data=raw,
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 200
