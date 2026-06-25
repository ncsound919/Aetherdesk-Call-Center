"""Tests for Lago billing engine."""

import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def reset_lago():
    """Reset singleton state before each test."""
    import api.services.billing_engine as mod
    mod._client = None
    mod._enabled = False
    yield
    mod._client = None
    mod._enabled = False


class TestGetClient:
    def test_returns_none_when_no_api_key(self):
        from api.services.billing_engine import _get_client
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LAGO_API_KEY", None)
            result = _get_client()
            assert result is None

    def test_returns_none_when_import_fails(self):
        from api.services.billing_engine import _get_client
        with patch.dict(os.environ, {"LAGO_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"lago_python_client": None}):
                result = _get_client()
                assert result is None

    def test_returns_none_on_init_error(self):
        from api.services.billing_engine import _get_client
        with patch.dict(os.environ, {"LAGO_API_KEY": "test-key"}):
            mock_mod = MagicMock()
            mock_mod.LagoClient.side_effect = Exception("conn refused")
            with patch.dict("sys.modules", {"lago_python_client": mock_mod}):
                result = _get_client()
                assert result is None

    def test_returns_client_when_configured(self):
        from api.services.billing_engine import _get_client
        mock_client = MagicMock()
        mock_lago_cls = MagicMock(return_value=mock_client)

        with patch.dict(os.environ, {"LAGO_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"lago_python_client": MagicMock(LagoClient=mock_lago_cls)}):
                result = _get_client()
                assert result is mock_client


class TestIsLagoEnabled:
    def test_returns_false_when_not_configured(self):
        from api.services.billing_engine import is_lago_enabled
        assert is_lago_enabled() is False


class TestTrackCallUsage:
    def test_mock_mode_when_not_enabled(self):
        from api.services.billing_engine import track_call_usage
        result = track_call_usage("tenant-1", "call-123", 60, "inbound")
        assert result["mock"] is True
        assert result["tenant_id"] == "tenant-1"

    def test_records_when_enabled(self):
        from api.services.billing_engine import track_call_usage
        mock_client = MagicMock()
        import api.services.billing_engine as mod
        mod._client = mock_client
        mod._enabled = True

        result = track_call_usage("tenant-1", "call-123", 60, "inbound")
        assert result["recorded"] is True
        mock_client.events().create.assert_called_once()

    def test_handles_error_gracefully(self):
        from api.services.billing_engine import track_call_usage
        mock_client = MagicMock()
        mock_client.events().create.side_effect = Exception("API error")
        import api.services.billing_engine as mod
        mod._client = mock_client
        mod._enabled = True

        result = track_call_usage("tenant-1", "call-123", 60, "inbound")
        assert result["recorded"] is False
        assert "error" in result


class TestTrackAiUsage:
    def test_mock_mode_when_not_enabled(self):
        from api.services.billing_engine import track_ai_usage
        result = track_ai_usage("tenant-1", "session-1", 500, "gpt-4")
        assert result["mock"] is True

    def test_records_when_enabled(self):
        from api.services.billing_engine import track_ai_usage
        mock_client = MagicMock()
        import api.services.billing_engine as mod
        mod._client = mock_client
        mod._enabled = True

        result = track_ai_usage("tenant-1", "session-1", 500, "gpt-4")
        assert result["recorded"] is True


class TestGetCustomerUsage:
    def test_mock_mode(self):
        from api.services.billing_engine import get_customer_usage
        result = get_customer_usage("tenant-1", "2024-01-01", "2024-01-31")
        assert result["mock"] is True
        assert result["customer_id"] == "tenant-1"


class TestCreateCustomer:
    def test_mock_mode(self):
        from api.services.billing_engine import create_customer
        result = create_customer("tenant-1", "test@example.com", "Test Co")
        assert result["mock"] is True
        assert result["email"] == "test@example.com"


class TestGetInvoices:
    def test_mock_mode_returns_empty(self):
        from api.services.billing_engine import getinvoices
        result = getinvoices("tenant-1")
        assert result == []

    def test_returns_invoices_when_enabled(self):
        from api.services.billing_engine import getinvoices
        mock_client = MagicMock()
        mock_inv = MagicMock()
        mock_inv.id = "inv-1"
        mock_inv.status = "paid"
        mock_inv.amount_cents = 1000
        mock_inv.created_at = "2024-01-01"
        mock_client.invoices().find_all.return_value = [mock_inv]

        import api.services.billing_engine as mod
        mod._client = mock_client
        mod._enabled = True

        result = getinvoices("tenant-1")
        assert len(result) == 1
        assert result[0]["id"] == "inv-1"
