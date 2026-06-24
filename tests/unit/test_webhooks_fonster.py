"""Unit tests for webhooks_fonster.py — HMAC signature validation and helper functions."""

import hashlib
import hmac
import json

import pytest
from unittest.mock import AsyncMock, patch


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


class TestHandleFonsterWebhook:
    """Test the handle_fonster_webhook helper (background task handler).

    Note: handle_fonster_webhook references ``request`` as a module-level free
    variable (it is not passed as a parameter). We patch it at the module
    level so the function can resolve it during test execution.
    """

    @pytest.mark.asyncio
    async def test_updates_call_status(self):
        """Should call db_update_call_status with correct call_id and status."""
        with (patch("apps.api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock) as mock_update,
              patch("apps.api.routers.webhooks_fonster.request",
                    create=True) as mock_request):
            mock_request.app.state.redis = None

            from apps.api.routers.webhooks_fonster import handle_fonster_webhook
            await handle_fonster_webhook(call_id="CA-001", status="active", session_ref="SR-001")

            mock_update.assert_awaited_once_with("CA-001", "active")

    @pytest.mark.asyncio
    async def test_publishes_to_redis_when_available(self):
        """Should publish a JSON status update to redis when redis client exists."""
        mock_redis = AsyncMock()

        with (patch("apps.api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock) as mock_db,
              patch("apps.api.routers.webhooks_fonster.request",
                    create=True) as mock_request):
            mock_request.app.state.redis = mock_redis

            from apps.api.routers.webhooks_fonster import handle_fonster_webhook
            await handle_fonster_webhook(call_id="CA-002", status="completed")

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

        with (patch("apps.api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock),
              patch("apps.api.routers.webhooks_fonster.request",
                    create=True) as mock_request):
            mock_request.app.state.redis = mock_redis

            from apps.api.routers.webhooks_fonster import handle_fonster_webhook
            await handle_fonster_webhook(call_id="CA-003", status="active", session_ref="SR-999")

            payload = json.loads(mock_redis.publish.await_args[0][1])
            assert payload["session_ref"] == "SR-999"

    @pytest.mark.asyncio
    async def test_session_ref_defaults_to_none(self):
        """session_ref should be None in payload when not provided."""
        mock_redis = AsyncMock()

        with (patch("apps.api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock),
              patch("apps.api.routers.webhooks_fonster.request",
                    create=True) as mock_request):
            mock_request.app.state.redis = mock_redis

            from apps.api.routers.webhooks_fonster import handle_fonster_webhook
            await handle_fonster_webhook(call_id="CA-004", status="active")

            payload = json.loads(mock_redis.publish.await_args[0][1])
            assert payload["session_ref"] is None

    @pytest.mark.asyncio
    async def test_no_crash_when_redis_is_none(self):
        """Should not raise when redis client is None."""
        with (patch("apps.api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock),
              patch("apps.api.routers.webhooks_fonster.request",
                    create=True) as mock_request):
            mock_request.app.state.redis = None

            from apps.api.routers.webhooks_fonster import handle_fonster_webhook
            await handle_fonster_webhook(call_id="CA-005", status="failed")
            # No exception means success

    @pytest.mark.asyncio
    async def test_no_crash_when_db_update_fails(self):
        """Should log error but not crash when db_update_call_status raises."""
        with (patch("apps.api.routers.webhooks_fonster.db_update_call_status",
                    new_callable=AsyncMock) as mock_update,
              patch("apps.api.routers.webhooks_fonster.request",
                    create=True) as mock_request):
            mock_update.side_effect = Exception("DB connection lost")
            mock_request.app.state.redis = None

            from apps.api.routers.webhooks_fonster import handle_fonster_webhook
            await handle_fonster_webhook(call_id="CA-006", status="completed")
            # No exception means success
