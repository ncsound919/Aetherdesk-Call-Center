"""Tests for Langfuse LLM observability client."""

import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def reset_langfuse():
    """Reset singleton state before each test."""
    import api.services.langfuse_client as mod
    mod._langfuse = None
    mod._tried = False
    yield
    mod._langfuse = None
    mod._tried = False


class TestGetLangfuse:
    def test_returns_none_when_no_keys(self):
        from api.services.langfuse_client import get_langfuse
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            result = get_langfuse()
            assert result is None

    def test_returns_none_when_import_fails(self):
        from api.services.langfuse_client import get_langfuse
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
            "LANGFUSE_SECRET_KEY": "sk-lf-test",
        }):
            with patch.dict("sys.modules", {"langfuse": None}):
                result = get_langfuse()
                assert result is None

    def test_returns_none_on_init_error(self):
        from api.services.langfuse_client import get_langfuse
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
            "LANGFUSE_SECRET_KEY": "sk-lf-test",
        }):
            mock_langfuse_mod = MagicMock()
            mock_langfuse_mod.Langfuse.side_effect = Exception("conn refused")
            with patch.dict("sys.modules", {"langfuse": mock_langfuse_mod}):
                result = get_langfuse()
                assert result is None

    def test_caches_after_first_try(self):
        from api.services.langfuse_client import get_langfuse
        # First call sets _tried=True even on failure
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            result1 = get_langfuse()
            assert result1 is None

        # Second call should return immediately (cached)
        result2 = get_langfuse()
        assert result2 is None

    def test_returns_client_when_configured(self):
        from api.services.langfuse_client import get_langfuse
        mock_langfuse_cls = MagicMock()
        mock_instance = MagicMock()
        mock_langfuse_cls.return_value = mock_instance

        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
            "LANGFUSE_SECRET_KEY": "sk-lf-test",
            "LANGFUSE_HOST": "https://custom.langfuse.com",
        }):
            mock_langfuse_mod = MagicMock(Langfuse=mock_langfuse_cls)
            with patch.dict("sys.modules", {"langfuse": mock_langfuse_mod}):
                result = get_langfuse()
                assert result is mock_instance


class TestFlush:
    def test_flush_calls_langfuse_flush(self):
        from api.services.langfuse_client import flush
        mock_lf = MagicMock()
        with patch("api.services.langfuse_client.get_langfuse", return_value=mock_lf):
            flush()
            mock_lf.flush.assert_called_once()

    def test_flush_noop_when_no_client(self):
        from api.services.langfuse_client import flush
        with patch("api.services.langfuse_client.get_langfuse", return_value=None):
            flush()  # Should not raise


class TestScoreCall:
    def test_score_call_invokes_langfuse(self):
        from api.services.langfuse_client import score_call
        mock_lf = MagicMock()
        with patch("api.services.langfuse_client.get_langfuse", return_value=mock_lf):
            score_call("call-123", "satisfaction", 0.95, comment="great")
            mock_lf.score.assert_called_once_with(
                name="satisfaction",
                value=0.95,
                comment="great",
                metadata={"comment": "great"},
            )

    def test_score_call_noop_when_no_client(self):
        from api.services.langfuse_client import score_call
        with patch("api.services.langfuse_client.get_langfuse", return_value=None):
            score_call("call-123", "satisfaction", 0.95)  # Should not raise
