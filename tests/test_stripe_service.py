"""Tests for src/api/services/stripe_service.py — Stripe SDK wrapper with mock mode."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import api.services.stripe_service as ss  # noqa: E402


class TestMockMode:
    def test_is_stripe_enabled_false_without_key(self):
        assert ss.is_stripe_enabled() is False

    def test_get_price_id(self, monkeypatch):
        monkeypatch.setenv("STRIPE_PRICE_BASIC", "price_123")
        assert ss.get_price_id("basic") == "price_123"
        assert ss.get_price_id("nonexistent") is None

    def test_create_checkout_session_mock(self):
        out = ss.create_checkout_session("cus_1", "price_1", "https://ok", "https://cancel")
        assert out["mock"] is True
        assert out["id"] == "cs_mock_price_1"
        assert "mock=true" in out["url"]

    def test_create_portal_session_mock(self):
        out = ss.create_portal_session("cus_1", "https://ok")
        assert out["mock"] is True
        assert out["id"] == "portal_mock_cus_1"

    def test_get_customer_mock(self):
        out = ss.get_customer("cus_1")
        assert out["mock"] is True
        assert out["email"] == "mock@example.com"

    def test_create_customer_mock(self):
        out = ss.create_customer("a@b.com", name="A")
        assert out["mock"] is True
        assert out["id"] == "cus_mock_a_b_com"

    def test_report_usage_mock(self):
        out = ss.report_usage("si_1", 5)
        assert out["mock"] is True
        assert out["quantity"] == 5

    def test_verify_webhook_signature_valid_json(self):
        payload = json.dumps({"event": "checkout.session.completed"}).encode()
        out = ss.verify_webhook_signature(payload, "sig", "secret")
        assert out == {"event": "checkout.session.completed"}

    def test_verify_webhook_signature_invalid_json(self):
        out = ss.verify_webhook_signature(b"not-json", "sig", "secret")
        assert out is None


class TestEnabledMode:
    @pytest.fixture(autouse=True)
    def _enable(self, monkeypatch):
        fake = MagicMock()
        fake.checkout.Session.create.return_value = MagicMock(id="cs_1", url="https://pay")
        fake.billing_portal.Session.create.return_value = MagicMock(id="ps_1", url="https://portal")
        fake.Customer.retrieve.return_value = MagicMock(
            to_dict=lambda: {"id": "cus_1", "email": "x@x.com"}
        )
        fake.Customer.create.return_value = MagicMock(
            to_dict=lambda: {"id": "cus_2", "email": "y@y.com"}
        )
        fake.SubscriptionItem.create_usage_record.return_value = MagicMock(
            to_dict=lambda: {"id": "mbur_1", "quantity": 3}
        )
        fake.Webhook.construct_event.return_value = {"event": "invoice.paid"}
        monkeypatch.setattr(ss, "_stripe", fake)
        monkeypatch.setattr(ss, "_STRIPE_ENABLED", True)

    def test_is_stripe_enabled(self):
        assert ss.is_stripe_enabled() is True

    def test_create_checkout_session_real(self):
        out = ss.create_checkout_session("cus_1", "price_1", "https://ok", "https://cancel", metadata={"k": 1})
        assert out == {"id": "cs_1", "url": "https://pay", "mock": False}

    def test_create_portal_session_real(self):
        out = ss.create_portal_session("cus_1", "https://ok")
        assert out == {"id": "ps_1", "url": "https://portal", "mock": False}

    def test_get_customer_real(self):
        out = ss.get_customer("cus_1")
        assert out["id"] == "cus_1"

    def test_create_customer_real(self):
        out = ss.create_customer("y@y.com")
        assert out["id"] == "cus_2"

    def test_report_usage_real(self):
        out = ss.report_usage("si_1", 3)
        assert out["quantity"] == 3

    def test_verify_webhook_signature_real(self):
        out = ss.verify_webhook_signature(b"{}", "sig", "secret")
        assert out == {"event": "invoice.paid"}

    def test_verify_webhook_signature_raises(self, monkeypatch):
        def _boom(*a, **k):
            raise Exception("bad signature")

        monkeypatch.setattr(ss._stripe.Webhook, "construct_event", _boom)
        out = ss.verify_webhook_signature(b"{}", "sig", "secret")
        assert out is None
