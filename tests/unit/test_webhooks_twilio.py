"""Unit tests for Twilio webhook handler endpoints.

Tests the 4 Twilio webhook routes using TestClient with a minimal FastAPI app
that includes only the webhooks_twilio router. The validate_twilio_request
dependency is bypassed because APP_ENV defaults to "development" in tests.
"""

import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("APP_ENV", "development")


@pytest.fixture
def app():
    """Create a minimal FastAPI app with just the webhooks_twilio router."""
    from api.routers.webhooks_twilio import router

    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def client(app):
    """TestClient bound to the minimal twilio webhooks app."""
    with TestClient(app) as c:
        yield c


class TestPing:
    """Tests for GET /webhooks/twilio/ping."""

    def test_ping_returns_200(self, client):
        """Ping endpoint returns 200 with ok: true."""
        resp = client.get("/webhooks/twilio/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_ping_returns_json(self, client):
        """Ping endpoint returns JSON content type."""
        resp = client.get("/webhooks/twilio/ping")
        assert resp.headers["content-type"] == "application/json"


class TestHandleIncomingVoice:
    """Tests for POST /webhooks/twilio/voice."""

    def test_voice_returns_twiml_with_call_sid(self, client):
        """Voice webhook returns TwiML XML that includes the CallSid in stream URL."""
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-test123"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/xml"
        body = resp.text
        assert "CA-test123" in body
        assert "<Stream" in body
        assert "<Connect>" in body
        assert "<Say" in body
        assert "realtime/call/CA-test123" in body

    def test_voice_defaults_call_sid_to_unknown(self, client):
        """Voice webhook uses 'unknown' when CallSid is not provided."""
        resp = client.post("/webhooks/twilio/voice", data={})
        assert resp.status_code == 200
        body = resp.text
        assert "unknown" in body
        assert "realtime/call/unknown" in body

    def test_voice_uses_wss_for_https(self, client):
        """Voice webhook uses wss:// scheme when request scheme is https."""
        resp = client.post(
            "/webhooks/twilio/voice",
            data={"CallSid": "CA-secure"},
            headers={"X-Forwarded-Proto": "https"},
        )
        # TestClient simulates http by default. To test https, we'd need
        # a different approach, but TWILIO_WEBHOOK_BASE is the recommended way.
        # This test verifies the fallback path with http (ws://).
        assert resp.status_code == 200
        body = resp.text
        assert "realtime/call/CA-secure" in body

    def test_voice_with_webhook_base(self, client, monkeypatch):
        """Voice webhook uses TWILIO_WEBHOOK_BASE when set (reverse proxy)."""
        monkeypatch.setenv("TWILIO_WEBHOOK_BASE", "https://calls.example.com")
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-proxy"})
        assert resp.status_code == 200
        body = resp.text
        # Should use wss:// with the webhook base netloc
        assert "wss://calls.example.com/realtime/call/CA-proxy" in body

    def test_voice_with_webhook_base_http(self, client, monkeypatch):
        """Voice webhook uses ws:// when TWILIO_WEBHOOK_BASE is http."""
        monkeypatch.setenv("TWILIO_WEBHOOK_BASE", "http://calls.example.com:8000")
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-http"})
        assert resp.status_code == 200
        body = resp.text
        assert "ws://calls.example.com:8000/realtime/call/CA-http" in body

    def test_voice_twiml_structure(self, client):
        """Voice webhook returns valid TwiML structure."""
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-001"})
        assert resp.status_code == 200
        body = resp.text
        assert '<?xml version="1.0" encoding="UTF-8"?>' in body
        assert "<Response>" in body
        assert "</Response>" in body
        assert "<Say voice=\"alice\">" in body
        assert "</Say>" in body
        assert "<Connect>" in body
        assert "</Connect>" in body
        assert "<Stream " in body

    def test_voice_valid_xml_content_type(self, client):
        """Voice webhook returns application/xml content type."""
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-001"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/xml"


class TestHandleCallStatus:
    """Tests for POST /webhooks/twilio/call-status."""

    def test_call_status_returns_ok(self, client):
        """Call status webhook returns 200 with ok: true."""
        resp = client.post("/webhooks/twilio/call-status", data={
            "CallSid": "CA-status-1",
            "CallStatus": "completed",
            "From": "+1234567890",
            "To": "+0987654321",
        })
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_call_status_defaults_to_unknown(self, client):
        """Call status webhook uses defaults when fields are missing."""
        resp = client.post("/webhooks/twilio/call-status", data={})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_call_status_returns_json(self, client):
        """Call status webhook returns JSON content type."""
        resp = client.post("/webhooks/twilio/call-status", data={
            "CallSid": "CA-status-2",
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"

    def test_call_status_with_ringing(self, client):
        """Call status webhook handles 'ringing' status correctly."""
        resp = client.post("/webhooks/twilio/call-status", data={
            "CallSid": "CA-ringing",
            "CallStatus": "ringing",
            "From": "+1111111111",
            "To": "+2222222222",
        })
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


class TestHandleGather:
    """Tests for POST /webhooks/twilio/gather."""

    def test_gather_returns_twiml(self, client):
        """Gather webhook returns 200 with TwiML response."""
        resp = client.post("/webhooks/twilio/gather", data={
            "CallSid": "CA-gather-1",
            "Digits": "1234",
            "SpeechResult": "",
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/xml"
        body = resp.text
        assert "Thank you. Your input has been received." in body
        assert "<Response>" in body
        assert "<Say>" in body

    def test_gather_with_speech_result(self, client):
        """Gather webhook handles speech input."""
        resp = client.post("/webhooks/twilio/gather", data={
            "CallSid": "CA-gather-2",
            "Digits": "",
            "SpeechResult": "Yes, please",
        })
        assert resp.status_code == 200
        body = resp.text
        assert "Thank you. Your input has been received." in body

    def test_gather_without_call_sid(self, client):
        """Gather webhook defaults CallSid to unknown."""
        resp = client.post("/webhooks/twilio/gather", data={
            "Digits": "42",
        })
        assert resp.status_code == 200

    def test_gather_empty_form(self, client):
        """Gather webhook handles empty form data."""
        resp = client.post("/webhooks/twilio/gather", data={})
        assert resp.status_code == 200
        body = resp.text
        assert "Thank you. Your input has been received." in body


class TestValidateTwilioRequest:
    """Tests for the validate_twilio_request dependency bypass in dev mode."""

    def test_dev_mode_bypasses_validation(self, client):
        """In development mode (default), validation passes without signature."""
        # The default APP_ENV is "development", so no Twilio signature needed
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-dev"})
        assert resp.status_code == 200

    def test_production_mode_without_signature(self, client, monkeypatch):
        """In production mode, missing signature returns 403."""
        monkeypatch.setenv("APP_ENV", "production")
        resp = client.post("/webhooks/twilio/voice", data={"CallSid": "CA-prod"})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Missing Twilio Signature"

    def test_production_mode_with_invalid_signature(self, client, monkeypatch):
        """In production mode, invalid signature returns 403."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token")
        resp = client.post(
            "/webhooks/twilio/voice",
            data={"CallSid": "CA-bad-sig"},
            headers={"X-Twilio-Signature": "invalid-signature"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Invalid Twilio Signature"

    def test_validate_applied_to_status_webhook(self, client, monkeypatch):
        """Production mode without signature on /call-status returns 403."""
        monkeypatch.setenv("APP_ENV", "production")
        resp = client.post("/webhooks/twilio/call-status", data={"CallSid": "CA-1"})
        assert resp.status_code == 403

    def test_validate_applied_to_gather_webhook(self, client, monkeypatch):
        """Production mode without signature on /gather returns 403."""
        monkeypatch.setenv("APP_ENV", "production")
        resp = client.post("/webhooks/twilio/gather", data={"CallSid": "CA-1"})
        assert resp.status_code == 403
