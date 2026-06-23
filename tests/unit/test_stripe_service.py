import pytest
from unittest.mock import patch, MagicMock


class TestStripeService:
    def test_get_price_id_returns_env_value(self):
        from apps.api.services.stripe_service import get_price_id

        with patch("apps.api.services.stripe_service.os.getenv", return_value="price_pro"):
            result = get_price_id("pro")
            assert result == "price_pro"

    def test_get_price_id_missing_returns_none(self):
        from apps.api.services.stripe_service import get_price_id

        with patch("apps.api.services.stripe_service.os.getenv", return_value=None):
            result = get_price_id("bogus")
            assert result is None

    def test_is_stripe_enabled_false_without_key(self):
        from apps.api.services.stripe_service import is_stripe_enabled

        with patch("apps.api.services.stripe_service._STRIPE_ENABLED", False), \
             patch("apps.api.services.stripe_service._stripe", None):
            assert is_stripe_enabled() is False

    def test_create_checkout_session_mock(self):
        from apps.api.services.stripe_service import create_checkout_session

        with patch("apps.api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = create_checkout_session("cus_test", "price_pro", "https://success.url", "https://cancel.url")
            assert result["mock"] is True
            assert "url" in result
            assert "https://success.url" in result["url"]

    def test_create_portal_session_mock(self):
        from apps.api.services.stripe_service import create_portal_session

        with patch("apps.api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = create_portal_session("cus_test", "https://portal.url")
            assert result["mock"] is True
            assert "url" in result

    def test_verify_webhook_mock_valid_json(self):
        from apps.api.services.stripe_service import verify_webhook_signature

        with patch("apps.api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = verify_webhook_signature(b'{"type":"checkout.session.completed"}', "sig", "secret")
            assert result is not None
            assert result["type"] == "checkout.session.completed"

    def test_verify_webhook_mock_invalid_json(self):
        from apps.api.services.stripe_service import verify_webhook_signature

        with patch("apps.api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = verify_webhook_signature(b"not json", "sig", "secret")
            assert result is None

    def test_create_customer_mock(self):
        from apps.api.services.stripe_service import create_customer

        with patch("apps.api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = create_customer("test@example.com", name="Test User")
            assert result["mock"] is True
            assert result["email"] == "test@example.com"

    def test_report_usage_mock(self):
        from apps.api.services.stripe_service import report_usage

        with patch("apps.api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = report_usage("si_test", 42)
            assert result["mock"] is True
            assert result["quantity"] == 42
