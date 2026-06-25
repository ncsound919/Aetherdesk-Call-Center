"""Tests for PostHog product analytics client."""

import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def reset_posthog():
    """Reset singleton state before each test."""
    import api.services.analytics_client as mod
    mod._client = None
    mod._tried = False
    yield
    mod._client = None
    mod._tried = False


class TestIsPosthogEnabled:
    def test_returns_false_when_not_set(self):
        from api.services.analytics_client import is_posthog_enabled
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("POSTHOG_API_KEY", None)
            assert is_posthog_enabled() is False

    def test_returns_true_when_set(self):
        from api.services.analytics_client import is_posthog_enabled
        with patch.dict(os.environ, {"POSTHOG_API_KEY": "phc_test"}):
            assert is_posthog_enabled() is True


class TestGetPosthog:
    def test_returns_none_when_not_configured(self):
        from api.services.analytics_client import get_posthog
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("POSTHOG_API_KEY", None)
            result = get_posthog()
            assert result is None

    def test_caches_after_first_try(self):
        from api.services.analytics_client import get_posthog
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("POSTHOG_API_KEY", None)
            result1 = get_posthog()
            assert result1 is None
            # Second call should use cache
            result2 = get_posthog()
            assert result2 is None

    def test_returns_none_when_import_fails(self):
        from api.services.analytics_client import get_posthog
        with patch.dict(os.environ, {"POSTHOG_API_KEY": "phc_test"}):
            with patch.dict("sys.modules", {"posthog": None}):
                result = get_posthog()
                assert result is None

    def test_returns_none_on_init_error(self):
        from api.services.analytics_client import get_posthog
        with patch.dict(os.environ, {"POSTHOG_API_KEY": "phc_test"}):
            mock_mod = MagicMock()
            mock_mod.Posthog.side_effect = Exception("conn refused")
            with patch.dict("sys.modules", {"posthog": mock_mod}):
                result = get_posthog()
                assert result is None


class TestTrackEvent:
    def test_returns_false_when_not_configured(self):
        from api.services.analytics_client import track_event
        result = track_event("user-1", "page_view", {"page": "dashboard"})
        assert result is False

    def test_captures_when_configured(self):
        from api.services.analytics_client import track_event
        mock_ph = MagicMock()
        with patch("api.services.analytics_client.get_posthog", return_value=mock_ph):
            result = track_event("user-1", "page_view", {"page": "dashboard"})
            assert result is True
            mock_ph.capture.assert_called_once_with(
                distinct_id="user-1",
                event="page_view",
                properties={"page": "dashboard"},
                groups={},
            )

    def test_handles_error_gracefully(self):
        from api.services.analytics_client import track_event
        mock_ph = MagicMock()
        mock_ph.capture.side_effect = Exception("API error")
        with patch("api.services.analytics_client.get_posthog", return_value=mock_ph):
            result = track_event("user-1", "page_view")
            assert result is False


class TestIdentifyUser:
    def test_returns_false_when_not_configured(self):
        from api.services.analytics_client import identify_user
        result = identify_user("user-1", {"name": "Test"})
        assert result is False

    def test_identifies_when_configured(self):
        from api.services.analytics_client import identify_user
        mock_ph = MagicMock()
        with patch("api.services.analytics_client.get_posthog", return_value=mock_ph):
            result = identify_user("user-1", {"name": "Test"})
            assert result is True
            mock_ph.identify.assert_called_once_with(
                distinct_id="user-1",
                properties={"name": "Test"},
            )


class TestIsFeatureEnabled:
    def test_returns_default_when_not_configured(self):
        from api.services.analytics_client import is_feature_enabled
        assert is_feature_enabled("new-ui", "user-1") is True
        assert is_feature_enabled("new-ui", "user-1", default=False) is False

    def test_defers_to_posthog_when_configured(self):
        from api.services.analytics_client import is_feature_enabled
        mock_ph = MagicMock()
        mock_ph.feature_enabled.return_value = True
        with patch("api.services.analytics_client.get_posthog", return_value=mock_ph):
            result = is_feature_enabled("new-ui", "user-1")
            assert result is True
            mock_ph.feature_enabled.assert_called_once_with(key="new-ui", distinct_id="user-1")


class TestGetFeatureFlag:
    def test_returns_default_when_not_configured(self):
        from api.services.analytics_client import get_feature_flag
        assert get_feature_flag("new-ui", "user-1") is None
        assert get_feature_flag("new-ui", "user-1", default="control") == "control"


class TestShutdown:
    def test_shutdown_calls_client(self):
        from api.services.analytics_client import shutdown
        mock_ph = MagicMock()
        import api.services.analytics_client as mod
        mod._client = mock_ph
        mod._tried = True

        shutdown()
        mock_ph.shutdown.assert_called_once()
        assert mod._client is None
        assert mod._tried is False  # Reset so re-initialization is possible

    def test_shutdown_noop_when_no_client(self):
        from api.services.analytics_client import shutdown
        shutdown()  # Should not raise
