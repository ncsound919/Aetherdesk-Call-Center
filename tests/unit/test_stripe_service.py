import pytest
from unittest.mock import patch, MagicMock


class TestStripeService:
    def test_get_price_id_returns_env_value(self):
        from api.services.stripe_service import get_price_id

        with patch("api.services.stripe_service.os.getenv", return_value="price_pro"):
            result = get_price_id("pro")
            assert result == "price_pro"

    def test_get_price_id_missing_returns_none(self):
        from api.services.stripe_service import get_price_id

        with patch("api.services.stripe_service.os.getenv", return_value=None):
            result = get_price_id("bogus")
            assert result is None

    def test_is_stripe_enabled_false_without_key(self):
        from api.services.stripe_service import is_stripe_enabled

        with patch("api.services.stripe_service._STRIPE_ENABLED", False), \
             patch("api.services.stripe_service._stripe", None):
            assert is_stripe_enabled() is False

    def test_create_checkout_session_mock(self):
        from api.services.stripe_service import create_checkout_session

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = create_checkout_session("cus_test", "price_pro", "https://success.url", "https://cancel.url")
            assert result["mock"] is True
            assert "url" in result
            assert "https://success.url" in result["url"]

    def test_create_portal_session_mock(self):
        from api.services.stripe_service import create_portal_session

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = create_portal_session("cus_test", "https://portal.url")
            assert result["mock"] is True
            assert "url" in result

    def test_verify_webhook_mock_valid_json(self):
        from api.services.stripe_service import verify_webhook_signature

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = verify_webhook_signature(b'{"type":"checkout.session.completed"}', "sig", "secret")
            assert result is not None
            assert result["type"] == "checkout.session.completed"

    def test_verify_webhook_mock_invalid_json(self):
        from api.services.stripe_service import verify_webhook_signature

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = verify_webhook_signature(b"not json", "sig", "secret")
            assert result is None

    def test_create_customer_mock(self):
        from api.services.stripe_service import create_customer

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = create_customer("test@example.com", name="Test User")
            assert result["mock"] is True
            assert result["email"] == "test@example.com"

    def test_report_usage_mock(self):
        from api.services.stripe_service import report_usage

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=False):
            result = report_usage("si_test", 42)
            assert result["mock"] is True
            assert result["quantity"] == 42

    def test_create_customer_with_real_stripe_enabled(self):
        from api.services.stripe_service import create_customer

        mock_customer = MagicMock()
        mock_customer.to_dict.return_value = {"id": "cus_real", "email": "test@example.com", "mock": False}

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=True), \
             patch("api.services.stripe_service._stripe") as mock_stripe:
            mock_stripe.Customer.create.return_value = mock_customer
            result = create_customer("test@example.com", name="Test User")
            mock_stripe.Customer.create.assert_called_once_with(email="test@example.com", name="Test User", metadata={})
            assert result == {"id": "cus_real", "email": "test@example.com", "mock": False}

    def test_create_customer_missing_email(self):
        from api.services.stripe_service import create_customer

        mock_customer = MagicMock()
        mock_customer.to_dict.return_value = {"id": "cus_noemail", "mock": False}

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=True), \
             patch("api.services.stripe_service._stripe") as mock_stripe:
            mock_stripe.Customer.create.return_value = mock_customer
            result = create_customer("")
            mock_stripe.Customer.create.assert_called_once_with(email="", name=None, metadata={})
            assert result == {"id": "cus_noemail", "mock": False}

    def test_report_usage_with_real_stripe(self):
        from api.services.stripe_service import report_usage

        mock_usage = MagicMock()
        mock_usage.to_dict.return_value = {"id": "mbur_real", "quantity": 10, "mock": False}

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=True), \
             patch("api.services.stripe_service._stripe") as mock_stripe:
            mock_stripe.SubscriptionItem.create_usage_record.return_value = mock_usage
            result = report_usage("si_test", 10, timestamp=1234567890)
            mock_stripe.SubscriptionItem.create_usage_record.assert_called_once_with(
                "si_test", quantity=10, timestamp=1234567890
            )
            assert result == {"id": "mbur_real", "quantity": 10, "mock": False}

    def test_report_usage_no_subscription_item(self):
        from api.services.stripe_service import report_usage

        mock_usage = MagicMock()
        mock_usage.to_dict.return_value = {"id": "mbur_empty", "quantity": 0, "mock": False}

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=True), \
             patch("api.services.stripe_service._stripe") as mock_stripe:
            mock_stripe.SubscriptionItem.create_usage_record.return_value = mock_usage
            result = report_usage("", 0)
            mock_stripe.SubscriptionItem.create_usage_record.assert_called_once_with(
                "", quantity=0, timestamp=None
            )
            assert result == {"id": "mbur_empty", "quantity": 0, "mock": False}

    def test_verify_webhook_with_real_stripe(self):
        from api.services.stripe_service import verify_webhook_signature

        mock_event = MagicMock()
        payload = b'{"type": "checkout.session.completed"}'

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=True), \
             patch("api.services.stripe_service._stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = mock_event
            result = verify_webhook_signature(payload, "sig_header", "secret")
            mock_stripe.Webhook.construct_event.assert_called_once_with(payload, "sig_header", "secret")
            assert result == mock_event

    def test_verify_webhook_signature_error(self):
        from api.services.stripe_service import verify_webhook_signature

        class _SignatureVerificationError(Exception):
            pass

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=True), \
             patch("api.services.stripe_service._stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.side_effect = _SignatureVerificationError("sig mismatch")
            result = verify_webhook_signature(b"payload", "sig", "secret")
            assert result is None

    def test_verify_webhook_generic_error(self):
        from api.services.stripe_service import verify_webhook_signature

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=True), \
             patch("api.services.stripe_service._stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.side_effect = Exception("something went wrong")
            result = verify_webhook_signature(b"payload", "sig", "secret")
            assert result is None

    def test_create_checkout_session_real(self):
        from api.services.stripe_service import create_checkout_session

        mock_session = MagicMock()
        mock_session.id = "cs_real"
        mock_session.url = "https://checkout.stripe.com/test"

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=True), \
             patch("api.services.stripe_service._stripe") as mock_stripe:
            mock_stripe.checkout.Session.create.return_value = mock_session
            result = create_checkout_session(
                "cus_test", "price_pro", "https://success.url", "https://cancel.url",
                metadata={"order": "123"},
            )
            mock_stripe.checkout.Session.create.assert_called_once_with(
                customer="cus_test",
                mode="subscription",
                line_items=[{"price": "price_pro", "quantity": 1}],
                success_url="https://success.url",
                cancel_url="https://cancel.url",
                metadata={"order": "123"},
            )
            assert result == {"id": "cs_real", "url": "https://checkout.stripe.com/test", "mock": False}

    def test_create_portal_session_real(self):
        from api.services.stripe_service import create_portal_session

        mock_portal = MagicMock()
        mock_portal.id = "ps_real"
        mock_portal.url = "https://billing.stripe.com/test"

        with patch("api.services.stripe_service.is_stripe_enabled", return_value=True), \
             patch("api.services.stripe_service._stripe") as mock_stripe:
            mock_stripe.billing_portal.Session.create.return_value = mock_portal
            result = create_portal_session("cus_test", "https://return.url")
            mock_stripe.billing_portal.Session.create.assert_called_once_with(
                customer="cus_test", return_url="https://return.url"
            )
            assert result == {"id": "ps_real", "url": "https://billing.stripe.com/test", "mock": False}
