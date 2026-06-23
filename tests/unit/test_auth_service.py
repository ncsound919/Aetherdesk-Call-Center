"""Unit tests for apps.api.services.auth.

The auth module uses late imports (inside function bodies) to avoid circular
dependencies.  In particular ``verify_access_token`` does::

    from apps.api.main import redis_client

when the decoded payload contains a ``jti`` claim.  The real ``apps.api.main``
cannot be imported in a unit-test environment because it triggers a cascade of
router imports that include ``webhooks_fonster.py`` with a broken import
(``db_update_call_status`` missing from ``database.py``).

We work around this by registering a lightweight mock module in
``sys.modules`` *before* the function under test is called.
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

# ── Mock apps.api.main to avoid importing the real module (broken deps) ──────

_mock_main = ModuleType("apps.api.main")
_mock_main.redis_client = None  # Will be patched per-test when needed
sys.modules.setdefault("apps.api.main", _mock_main)


class TestVerifyAccessToken:
    """Tests for auth.verify_access_token(token: str) -> dict | None.

    The function delegates to ``jwt_utils.verify_access_token`` for RS256
    verification, then checks a blocklist.  When Redis is unavailable (normal
    for unit tests) it falls back to an in-memory ``_fallback_blocklist`` set.
    """

    # ------------------------------------------------------------------
    # Valid token
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_valid_token_returns_payload(self):
        """A valid JWT token should return the decoded payload."""
        from apps.api.services.auth import verify_access_token

        # jti present → triggers late import of mock apps.api.main.redis_client.
        # Our mock has redis_client = None (not in sys.modules yet → falls to
        # fallback blocklist check, which is empty → token OK).
        with patch("apps.api.services.jwt_utils.verify_access_token") as mock_verify:
            mock_verify.return_value = {
                "tenant_id": "T-1",
                "email": "test@test.com",
                "jti": "jti-abc",
            }

            result = await verify_access_token("valid.jwt.token")
            assert result == {
                "tenant_id": "T-1",
                "email": "test@test.com",
                "jti": "jti-abc",
            }
            mock_verify.assert_called_once_with("valid.jwt.token")

    # ------------------------------------------------------------------
    # Invalid / expired token
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        """An invalid / expired JWT token should return None."""
        from apps.api.services.auth import verify_access_token

        with patch("apps.api.services.jwt_utils.verify_access_token") as mock_verify:
            mock_verify.return_value = None

            result = await verify_access_token("expired.jwt.token")
            assert result is None
            mock_verify.assert_called_once_with("expired.jwt.token")

    # ------------------------------------------------------------------
    # None token
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_none_token_returns_none(self):
        """Passing None as the token should return None."""
        from apps.api.services.auth import verify_access_token

        with patch("apps.api.services.jwt_utils.verify_access_token") as mock_verify:
            mock_verify.return_value = None

            result = await verify_access_token(None)
            assert result is None
            mock_verify.assert_called_once_with(None)

    # ------------------------------------------------------------------
    # Blocklisted token (via in-memory fallback)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_blocklisted_token_returns_none(self):
        """A token whose jti appears in the fallback blocklist should return None."""
        from apps.api.services.auth import verify_access_token

        with patch("apps.api.services.jwt_utils.verify_access_token") as mock_verify, \
             patch("apps.api.services.auth._fallback_blocklist", {"blocked-jti"}):
            mock_verify.return_value = {"tenant_id": "T-1", "jti": "blocked-jti"}

            result = await verify_access_token("blocked.token")
            assert result is None

    # ------------------------------------------------------------------
    # Token without jti — skips blocklist check
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_token_without_jti_skips_blocklist_check(self):
        """A valid token that has no jti claim skips the blocklist check entirely."""
        from apps.api.services.auth import verify_access_token

        with patch("apps.api.services.jwt_utils.verify_access_token") as mock_verify:
            mock_verify.return_value = {"tenant_id": "T-1", "email": "test@test.com"}

            result = await verify_access_token("token.no.jti")
            assert result == {"tenant_id": "T-1", "email": "test@test.com"}


class TestVerifyApiKey:
    """Tests for auth.verify_api_key(x_api_key: str) -> str.

    The function is also used as a FastAPI ``Header()`` dependency, but can be
    called directly with a string argument.  In development mode a ``None``
    value is automatically replaced by the hard-coded dev API key.
    """

    # ------------------------------------------------------------------
    # Dev / internal API key
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_internal_dev_api_key_returns_default_tenant(self):
        """The dev / internal API key should return TENANT-001."""
        from apps.api.services.auth import verify_api_key

        result = await verify_api_key("dev-api-key")
        assert result == "TENANT-001"

    # ------------------------------------------------------------------
    # None API key in dev mode
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_none_api_key_in_dev_uses_dev_fallback(self):
        """None API key in dev mode should use the dev-api-key fallback."""
        from apps.api.services.auth import verify_api_key

        result = await verify_api_key(None)
        assert result == "TENANT-001"

    # ------------------------------------------------------------------
    # Valid tenant-specific API key (DB lookup)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_valid_tenant_api_key_returns_tenant_id(self):
        """A valid tenant API key (from DB) should return its tenant ID."""
        from apps.api.services.auth import verify_api_key

        with patch(
            "apps.api.services.database.get_tenant_by_api_key",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {"id": "T-42"}

            result = await verify_api_key("tenant-specific-key")
            assert result == "T-42"
            mock_get.assert_called_once_with("tenant-specific-key")

    # ------------------------------------------------------------------
    # Invalid API key
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_invalid_api_key_raises_403(self):
        """An API key not found in the tenant DB should raise HTTP 403."""
        from apps.api.services.auth import verify_api_key

        with patch(
            "apps.api.services.database.get_tenant_by_api_key",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key("completely-bogus-key")
            assert exc_info.value.status_code == 403
            assert "Invalid API Key" in str(exc_info.value.detail)
