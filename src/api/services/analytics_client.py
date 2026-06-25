"""
PostHog product analytics — event tracking, feature flags, A/B testing.

Tracks how tenants use the UI, A/B tests call routing algorithms,
and feature-flags new capabilities for gradual rollout.

Graceful degradation: if POSTHOG_API_KEY is not set, all operations
are no-ops.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_client = None
_tried = False


def is_posthog_enabled() -> bool:
    """Check if PostHog is configured."""
    return bool(os.getenv("POSTHOG_API_KEY"))


def get_posthog():
    """Get or create PostHog client singleton."""
    global _client, _tried
    if _tried:
        return _client
    if not is_posthog_enabled():
        _tried = True
        return None
    try:
        from posthog import Posthog
        api_key = os.getenv("POSTHOG_API_KEY", "")
        host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
        _client = Posthog(api_key=api_key, host=host)
        _tried = True
        logger.info(f"PostHog initialized: {host}")
        return _client
    except ImportError:
        _tried = True
        logger.warning("posthog not installed — pip install posthog")
        return None
    except Exception as exc:
        _tried = True
        logger.warning(f"PostHog init failed: {exc}")
        return None


def track_event(
    distinct_id: str,
    event: str,
    properties: dict | None = None,
    groups: dict | None = None,
):
    """Track a product analytics event."""
    ph = get_posthog()
    if not ph:
        return False
    try:
        ph.capture(
            distinct_id=distinct_id,
            event=event,
            properties=properties or {},
            groups=groups or {},
        )
        return True
    except Exception as exc:
        logger.warning(f"PostHog track_event failed: {exc}")
        return False


def identify_user(
    distinct_id: str,
    properties: dict | None = None,
):
    """Identify a user with properties."""
    ph = get_posthog()
    if not ph:
        return False
    try:
        ph.identify(
            distinct_id=distinct_id,
            properties=properties or {},
        )
        return True
    except Exception as exc:
        logger.warning(f"PostHog identify failed: {exc}")
        return False


def is_feature_enabled(
    flag_key: str,
    distinct_id: str,
    default: bool = True,
) -> bool:
    """Check if a feature flag is enabled for a user."""
    ph = get_posthog()
    if not ph:
        return default
    try:
        return ph.feature_enabled(key=flag_key, distinct_id=distinct_id)
    except Exception as exc:
        logger.warning(f"PostHog feature flag check failed: {exc}")
        return default


def get_feature_flag(
    flag_key: str,
    distinct_id: str,
    default: Any = None,
) -> Any:
    """Get the variant/value of a feature flag."""
    ph = get_posthog()
    if not ph:
        return default
    try:
        return ph.get_feature_flag(key=flag_key, distinct_id=distinct_id)
    except Exception as exc:
        logger.warning(f"PostHog get_feature_flag failed: {exc}")
        return default


def shutdown():
    """Flush and shut down PostHog client."""
    global _client, _tried
    if _client is not None:
        try:
            _client.shutdown()
        except Exception:
            pass
        _client = None
        _tried = False
