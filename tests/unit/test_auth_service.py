"""Unit tests for api.services.auth.

The auth module uses late imports (inside function bodies) to avoid circular
dependencies.  In particular ``verify_access_token`` does::

    from api.main import redis_client

when the decoded payload contains a ``jti`` claim.  The real ``api.main``
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

# ── Mock api.main to avoid importing the real module (broken deps) ──────

_mock_main = ModuleType("api.main")
_mock_main.redis_client = None  # Will be patched per-test when needed
sys.modules["api.main"] = _mock_main


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
        from api.services.auth import verify_access_token

        # jti present → triggers late import of mock api.main.redis_client.
        # Our mock has redis_client = None (not in sys.modules yet → falls to
        # fallback blocklist check, which is empty → token OK).
        with patch("api.services.jwt_utils.verify_access_token") as mock_verify:
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
        from api.services.auth import verify_access_token

        with patch("api.services.jwt_utils.verify_access_token") as mock_verify:
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
        from api.services.auth import verify_access_token

        with patch("api.services.jwt_utils.verify_access_token") as mock_verify:
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
        from api.services.auth import verify_access_token

        with patch("api.services.jwt_utils.verify_access_token") as mock_verify, \
             patch("api.services.auth._fallback_blocklist", {"blocked-jti"}):
            mock_verify.return_value = {"tenant_id": "T-1", "jti": "blocked-jti"}

            result = await verify_access_token("blocked.token")
            assert result is None

    # ------------------------------------------------------------------
    # Token without jti — skips blocklist check
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_token_without_jti_skips_blocklist_check(self):
        """A valid token that has no jti claim skips the blocklist check entirely."""
        from api.services.auth import verify_access_token

        with patch("api.services.jwt_utils.verify_access_token") as mock_verify:
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
        from api.services.auth import verify_api_key

        result = await verify_api_key("dev-api-key")
        assert result == "TENANT-001"

    # ------------------------------------------------------------------
    # None API key in dev mode
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_none_api_key_in_dev_raises_401(self):
        """None API key in dev mode should raise 401 (no dev bypass)."""
        from api.services.auth import verify_api_key

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(None)
        assert exc_info.value.status_code == 401

    # ------------------------------------------------------------------
    # Valid tenant-specific API key (DB lookup)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_valid_tenant_api_key_returns_tenant_id(self):
        """A valid tenant API key (from DB) should return its tenant ID."""
        from api.services.auth import verify_api_key

        with patch(
            "api.services.database.get_tenant_by_api_key",
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
        from api.services.auth import verify_api_key

        with patch(
            "api.services.database.get_tenant_by_api_key",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key("completely-bogus-key")
            assert exc_info.value.status_code == 403
            assert "Invalid API Key" in str(exc_info.value.detail)

    # ------------------------------------------------------------------
    # Production mode with missing key
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_api_key_production_missing(self):
        """Production env without API key should raise HTTP 401."""
        from api.services.auth import verify_api_key

        with patch("os.getenv", return_value="production"):
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(None)
            assert exc_info.value.status_code == 401
            assert "API key required" in str(exc_info.value.detail)


class TestVerifyPassword:
    """Tests for auth.verify_password."""

    def test_verify_password_correct(self):
        from api.services.auth import verify_password, get_password_hash
        hashed = get_password_hash("correct-password")
        assert verify_password("correct-password", hashed) is True

    def test_verify_password_incorrect(self):
        from api.services.auth import verify_password, get_password_hash
        hashed = get_password_hash("correct-password")
        assert verify_password("wrong-password", hashed) is False


class TestGetPasswordHash:
    """Tests for auth.get_password_hash."""

    def test_hash_differs_from_plaintext(self):
        from api.services.auth import get_password_hash
        hashed = get_password_hash("my-password")
        assert hashed != "my-password"
        assert hashed.startswith("$argon2")


class TestTokenStore:
    """Tests for TokenStore methods with fallback storage (no Redis)."""

    @pytest.mark.asyncio
    async def test_create_token_no_redis(self):
        from api.services.auth import TokenStore
        store = TokenStore()
        token = await store.create_token("user-1")
        assert isinstance(token, str)
        assert len(token) > 20
        assert hasattr(store, "_fallback_tokens")
        assert token in store._fallback_tokens

    @pytest.mark.asyncio
    async def test_validate_token_fallback(self):
        from api.services.auth import TokenStore
        import time
        store = TokenStore()
        store._fallback_tokens = {
            "valid-token": {"user_id": "user-1", "created_at": time.time(), "metadata": {}}
        }
        result = await store.validate_token("valid-token")
        assert result is not None
        assert result["user_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_validate_token_expired(self):
        from api.services.auth import TokenStore, TOKEN_EXPIRY_SECONDS
        import time
        store = TokenStore()
        store._fallback_tokens = {
            "expired-token": {
                "user_id": "user-1",
                "created_at": time.time() - TOKEN_EXPIRY_SECONDS - 10,
                "metadata": {},
            }
        }
        result = await store.validate_token("expired-token")
        assert result is None
        assert "expired-token" not in store._fallback_tokens

    @pytest.mark.asyncio
    async def test_revoke_token_fallback(self):
        from api.services.auth import TokenStore
        import time
        store = TokenStore()
        store._fallback_tokens = {
            "revoke-me": {"user_id": "user-1", "created_at": time.time(), "metadata": {}}
        }
        await store.revoke_token("revoke-me")
        assert "revoke-me" not in store._fallback_tokens

    def test_cleanup_expired(self):
        from api.services.auth import TokenStore, TOKEN_EXPIRY_SECONDS
        import time
        store = TokenStore()
        now = time.time()
        store._fallback_tokens = {
            "expired-1": {
                "user_id": "u1",
                "created_at": now - TOKEN_EXPIRY_SECONDS - 100,
                "metadata": {},
            },
            "expired-2": {
                "user_id": "u2",
                "created_at": now - TOKEN_EXPIRY_SECONDS - 200,
                "metadata": {},
            },
            "fresh": {"user_id": "u3", "created_at": now, "metadata": {}},
        }
        store.cleanup_expired()
        assert "fresh" in store._fallback_tokens
        assert "expired-1" not in store._fallback_tokens
        assert "expired-2" not in store._fallback_tokens


class TestGenerateAccessToken:
    """Tests for auth.generate_access_token."""

    def test_generate_access_token(self):
        from api.services.auth import generate_access_token

        with patch("api.services.jwt_utils.create_access_token") as mock_create:
            mock_create.return_value = "signed.jwt.token"
            result = generate_access_token({"sub": "user-1"})
            assert result == "signed.jwt.token"
            mock_create.assert_called_once()
            args, _ = mock_create.call_args
            assert args[0] == {"sub": "user-1"}
            assert args[1].seconds == 3600


class TestGetCurrentUser:
    """Tests for auth.get_current_user."""

    @pytest.mark.asyncio
    async def test_get_current_user_valid(self):
        from api.services.auth import get_current_user

        mock_creds = type("Creds", (), {"credentials": "valid.jwt.token"})()
        with patch("api.services.jwt_utils.verify_access_token") as mock_verify:
            mock_verify.return_value = {"sub": "user-1", "tenant_id": "T-1"}
            result = await get_current_user(mock_creds)
            assert result == {"sub": "user-1", "tenant_id": "T-1"}

    @pytest.mark.asyncio
    async def test_get_current_user_invalid(self):
        from api.services.auth import get_current_user

        mock_creds = type("Creds", (), {"credentials": "invalid.jwt.token"})()
        with patch("api.services.jwt_utils.verify_access_token") as mock_verify:
            mock_verify.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_creds)
            assert exc_info.value.status_code == 401
            assert "Invalid or expired token" in str(exc_info.value.detail)


class TestWebSocketAuthMiddleware:
    """Tests for WebSocketAuthMiddleware."""

    @pytest.mark.asyncio
    async def test_non_websocket_scope(self):
        from api.services.auth import WebSocketAuthMiddleware

        mock_app = AsyncMock()
        scope = {"type": "http", "path": "/some-path"}
        receive = AsyncMock()
        send = AsyncMock()
        middleware = WebSocketAuthMiddleware(mock_app)
        await middleware(scope, receive, send)
        mock_app.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_excluded_path(self):
        from api.services.auth import WebSocketAuthMiddleware

        mock_app = AsyncMock()
        middleware = WebSocketAuthMiddleware(mock_app)
        for path in ["/api/v1/voice/incoming/call", "/health", "/"]:
            mock_app.reset_mock()
            scope = {"type": "websocket", "path": path, "headers": []}
            await middleware(scope, AsyncMock(), AsyncMock())
            mock_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_token_rejected(self):
        from api.services.auth import WebSocketAuthMiddleware

        mock_app = AsyncMock()
        send = AsyncMock()
        scope = {
            "type": "websocket",
            "path": "/ws/custom",
            "headers": [],
            "query_string": b"",
        }
        middleware = WebSocketAuthMiddleware(mock_app)
        await middleware(scope, AsyncMock(), send)
        mock_app.assert_not_called()
        send.assert_awaited()

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self):
        from api.services.auth import WebSocketAuthMiddleware

        mock_app = AsyncMock()
        send = AsyncMock()
        headers = [(b"authorization", b"Bearer bad-token")]
        scope = {
            "type": "websocket",
            "path": "/ws/custom",
            "headers": headers,
            "query_string": b"",
        }
        with patch(
            "api.services.auth.verify_websocket_token",
            new_callable=AsyncMock,
        ) as mock_verify:
            mock_verify.return_value = None
            middleware = WebSocketAuthMiddleware(mock_app)
            await middleware(scope, AsyncMock(), send)
            mock_app.assert_not_called()
            send.assert_awaited()


class TestVerifyTenantAccess:
    """Tests for auth.verify_tenant_access."""

    @pytest.mark.asyncio
    async def test_dev_bypass(self):
        from api.services.auth import verify_tenant_access

        result = await verify_tenant_access("T-42", x_api_key="dev-api-key")
        assert result == "T-42"

    @pytest.mark.asyncio
    async def test_production_valid(self):
        from api.services.auth import verify_tenant_access

        with patch("os.getenv", return_value="production"), \
             patch("api.services.auth.INTERNAL_API_KEY", "prod-internal-key"), \
             patch(
                 "api.services.database.verify_tenant_api_key",
                 new_callable=AsyncMock,
             ) as mock_verify:
            mock_verify.return_value = True
            result = await verify_tenant_access("T-42", x_api_key="valid-tenant-key")
            assert result == "T-42"
            mock_verify.assert_called_once_with("T-42", "valid-tenant-key")

    @pytest.mark.asyncio
    async def test_production_invalid(self):
        from api.services.auth import verify_tenant_access

        with patch("os.getenv", return_value="production"), \
             patch("api.services.auth.INTERNAL_API_KEY", "prod-internal-key"), \
             patch(
                 "api.services.database.verify_tenant_api_key",
                 new_callable=AsyncMock,
             ) as mock_verify:
            mock_verify.return_value = False
            with pytest.raises(HTTPException) as exc_info:
                await verify_tenant_access("T-42", x_api_key="invalid-key")
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_db_failure(self):
        from api.services.auth import verify_tenant_access

        with patch("os.getenv", return_value="production"), \
             patch("api.services.auth.INTERNAL_API_KEY", "prod-internal-key"), \
             patch(
                 "api.services.database.verify_tenant_api_key",
                 new_callable=AsyncMock,
             ) as mock_verify:
            mock_verify.side_effect = Exception("DB connection failed")
            with pytest.raises(HTTPException) as exc_info:
                await verify_tenant_access("T-42", x_api_key="any-key")
            assert exc_info.value.status_code == 403
