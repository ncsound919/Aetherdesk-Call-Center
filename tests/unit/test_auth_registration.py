import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestRegistration:
    @pytest.mark.asyncio
    async def test_register_creates_user_and_tenant(self):
        from api.routers.auth import register, RegisterRequest

        with patch("api.services.db_tenants.get_user_by_email_db", new_callable=AsyncMock) as mock_get, \
             patch("api.services.db_tenants.create_tenant", new_callable=AsyncMock) as mock_create_tenant, \
             patch("api.services.db_tenants.create_user_db", new_callable=AsyncMock) as mock_create_user, \
             patch("api.services.auth.get_password_hash", return_value="hashed_password"):

            mock_get.return_value = None  # No existing user
            mock_create_tenant.return_value = {"id": "tenant-123"}
            mock_create_user.return_value = {"id": "user-123", "verification_token": "tok_abc"}

            req = RegisterRequest(
                email="test@example.com",
                password="securepass123",
                full_name="Test User",
                company_name="Test Corp"
            )
            result = await register(req)

            assert result.user_id == "user-123"
            assert result.verification_token == "tok_abc"
            mock_create_tenant.assert_called_once()
            mock_create_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_rejects_duplicate_email(self):
        from api.routers.auth import register, RegisterRequest
        from fastapi import HTTPException

        with patch("api.services.db_tenants.get_user_by_email_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "existing-user"}

            req = RegisterRequest(
                email="existing@example.com",
                password="securepass123",
                full_name="Test User"
            )
            with pytest.raises(HTTPException) as exc:
                await register(req)
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_register_rejects_short_password(self):
        from api.routers.auth import register, RegisterRequest
        from fastapi import HTTPException

        with patch("api.services.db_tenants.get_user_by_email_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            req = RegisterRequest(
                email="test@example.com",
                password="short",
                full_name="Test User"
            )
            with pytest.raises(HTTPException) as exc:
                await register(req)
            assert exc.value.status_code == 400


class TestEmailVerification:
    @pytest.mark.asyncio
    async def test_verify_email_success(self):
        from api.routers.auth import verify_email, VerifyEmailRequest

        with patch("api.services.db_tenants.verify_user_email_db", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = "user-123"
            result = await verify_email(VerifyEmailRequest(token="valid_token"))
            assert result["message"] == "Email verified successfully"

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self):
        from api.routers.auth import verify_email, VerifyEmailRequest
        from fastapi import HTTPException

        with patch("api.services.db_tenants.verify_user_email_db", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = None
            with pytest.raises(HTTPException) as exc:
                await verify_email(VerifyEmailRequest(token="invalid"))
            assert exc.value.status_code == 400


class TestPasswordReset:
    @pytest.mark.asyncio
    async def test_forgot_password_returns_token(self):
        from api.routers.auth import forgot_password, ForgotPasswordRequest

        with patch("api.services.db_tenants.set_password_reset_token_db", new_callable=AsyncMock) as mock_reset:
            mock_reset.return_value = ("user-123", "reset_token_abc")
            result = await forgot_password(ForgotPasswordRequest(email="test@example.com"))
            assert "dev_token" in result

    @pytest.mark.asyncio
    async def test_reset_password_success(self):
        from api.routers.auth import reset_password, ResetPasswordRequest

        with patch("api.services.db_tenants.reset_password_db", new_callable=AsyncMock) as mock_reset, \
             patch("api.services.auth.get_password_hash", return_value="new_hash"):
            mock_reset.return_value = "user-123"
            result = await reset_password(ResetPasswordRequest(token="valid", new_password="newpass123"))
            assert result["message"] == "Password reset successfully"

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self):
        from api.routers.auth import reset_password, ResetPasswordRequest
        from fastapi import HTTPException

        with patch("api.services.db_tenants.reset_password_db", new_callable=AsyncMock) as mock_reset, \
             patch("api.services.auth.get_password_hash", return_value="new_hash"):
            mock_reset.return_value = None
            with pytest.raises(HTTPException) as exc:
                await reset_password(ResetPasswordRequest(token="invalid", new_password="newpass123"))
            assert exc.value.status_code == 400


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_dev_user_success(self):
        from api.routers.auth import login, LoginRequest

        dev_users = {
            "admin@aetherdesk.com": {
                "password": "admin123",
                "tenant_id": "TENANT-001",
                "user_id": "USER-ADMIN-001",
                "role": "admin",
                "name": "Admin User",
            }
        }
        with patch("api.routers.auth._dev_users_enabled", return_value=True), \
             patch("api.routers.auth.DEV_USERS", dev_users), \
             patch("api.routers.auth.generate_access_token", return_value="dev_token"):
            req = LoginRequest(email="admin@aetherdesk.com", password="admin123")
            result = await login(req)
            assert result.access_token == "dev_token"
            assert result.userId == "USER-ADMIN-001"
            assert result.role == "admin"
            assert result.tenantId == "TENANT-001"
            assert result.name == "Admin User"

    @pytest.mark.asyncio
    async def test_login_dev_agent_success(self):
        from api.routers.auth import login, LoginRequest

        dev_users = {
            "agent@aetherdesk.com": {
                "password": "agent123",
                "tenant_id": "TENANT-001",
                "user_id": "USER-AGENT-001",
                "role": "agent",
                "name": "Test Agent",
            }
        }
        with patch("api.routers.auth._dev_users_enabled", return_value=True), \
             patch("api.routers.auth.DEV_USERS", dev_users), \
             patch("api.routers.auth.generate_access_token", return_value="agent_token"):
            req = LoginRequest(email="agent@aetherdesk.com", password="agent123")
            result = await login(req)
            assert result.role == "agent"
            assert result.name == "Test Agent"

    @pytest.mark.asyncio
    async def test_login_dev_user_wrong_password(self):
        from api.routers.auth import login, LoginRequest
        from fastapi import HTTPException

        dev_users = {
            "admin@aetherdesk.com": {
                "password": "admin123",
                "tenant_id": "TENANT-001",
                "user_id": "USER-ADMIN-001",
                "role": "admin",
                "name": "Admin User",
            }
        }
        with patch("api.routers.auth._dev_users_enabled", return_value=True), \
             patch("api.routers.auth.DEV_USERS", dev_users):
            req = LoginRequest(email="admin@aetherdesk.com", password="wrongpass")
            with pytest.raises(HTTPException) as exc:
                await login(req)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_dev_user_not_found(self):
        from api.routers.auth import login, LoginRequest
        from fastapi import HTTPException

        with patch("api.routers.auth._dev_users_enabled", return_value=True), \
             patch("api.routers.auth.DEV_USERS", {}):
            req = LoginRequest(email="unknown@test.com", password="anypass")
            with pytest.raises(HTTPException) as exc:
                await login(req)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_dev_users_disabled_in_production_even_if_flag_set(self):
        """Dev users must be forcibly disabled when APP_ENV=production,
        regardless of ENABLE_DEV_USERS."""
        from api.routers.auth import _dev_users_enabled

        with patch.dict(
            "os.environ",
            {"APP_ENV": "production", "ENABLE_DEV_USERS": "true"},
        ):
            assert _dev_users_enabled() is False

    @pytest.mark.asyncio
    async def test_login_production_success(self):
        from api.routers.auth import login, LoginRequest

        with patch("api.routers.auth.os.getenv", return_value="false"), \
             patch("api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db, \
             patch("api.services.auth.verify_password", return_value=True), \
             patch("api.routers.auth.generate_access_token", return_value="prod_token"):
            mock_db.return_value = {
                "id": "user-123", "tenant_id": "tenant-001",
                "email": "user@co.com", "password_hash": "hash",
                "role": "agent", "display_name": "Alice"
            }
            req = LoginRequest(email="user@co.com", password="pass")
            result = await login(req)
            assert result.access_token == "prod_token"
            assert result.userId == "user-123"
            assert result.name == "Alice"

    @pytest.mark.asyncio
    async def test_login_production_fallback_display_name(self):
        from api.routers.auth import login, LoginRequest

        with patch("api.routers.auth.os.getenv", return_value="false"), \
             patch("api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db, \
             patch("api.services.auth.verify_password", return_value=True), \
             patch("api.routers.auth.generate_access_token", return_value="tok"):
            mock_db.return_value = {
                "id": "u1", "tenant_id": "t1",
                "email": "user@co.com", "password_hash": "h",
                "role": "agent", "display_name": None
            }
            req = LoginRequest(email="user@co.com", password="pass")
            result = await login(req)
            assert result.name == "user@co.com"

    @pytest.mark.asyncio
    async def test_login_production_wrong_password(self):
        from api.routers.auth import login, LoginRequest
        from fastapi import HTTPException

        with patch("api.routers.auth.os.getenv", return_value="false"), \
             patch("api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db, \
             patch("api.services.auth.verify_password", return_value=False):
            mock_db.return_value = {"id": "u1", "password_hash": "hash"}
            req = LoginRequest(email="user@co.com", password="wrong")
            with pytest.raises(HTTPException) as exc:
                await login(req)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_production_user_not_found(self):
        from api.routers.auth import login, LoginRequest
        from fastapi import HTTPException

        with patch("api.routers.auth.os.getenv", return_value="false"), \
             patch("api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = None
            req = LoginRequest(email="nobody@co.com", password="pass")
            with pytest.raises(HTTPException) as exc:
                await login(req)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_production_db_unavailable(self):
        from api.routers.auth import login, LoginRequest
        from fastapi import HTTPException

        with patch("api.routers.auth.os.getenv", return_value="false"), \
             patch("api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db:
            mock_db.side_effect = Exception("DB connection refused")
            req = LoginRequest(email="user@co.com", password="pass")
            with pytest.raises(HTTPException) as exc:
                await login(req)
            assert exc.value.status_code == 503


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_with_redis(self):
        import sys
        from api.routers.auth import logout
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        mock_redis = AsyncMock()
        mock_main = MagicMock()
        mock_main.redis_client = mock_redis

        mock_creds = MagicMock()
        mock_creds.credentials = "valid_tok"
        with patch.dict("sys.modules", {"api.main": mock_main}), \
             patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = {"jti": "jti-1", "exp": 9999999999}
            result = await logout(credentials=mock_creds)
            assert result["message"] == "Logged out successfully"
            mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_logout_fallback_blocklist(self):
        import sys
        from api.routers.auth import logout
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        mock_main = MagicMock()
        mock_main.redis_client = None

        mock_creds = MagicMock()
        mock_creds.credentials = "valid_tok"
        mock_blocklist = set()
        with patch.dict("sys.modules", {"api.main": mock_main}), \
             patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v, \
             patch("api.services.auth._fallback_blocklist", mock_blocklist):
            mock_v.return_value = {"jti": "jti-2", "exp": 9999999999}
            result = await logout(credentials=mock_creds)
            assert result["message"] == "Logged out successfully"
            assert "jti-2" in mock_blocklist

    @pytest.mark.asyncio
    async def test_logout_no_credentials(self):
        from api.routers.auth import logout

        result = await logout(credentials=None)
        assert result["message"] == "Logged out successfully"

    @pytest.mark.asyncio
    async def test_logout_invalid_token(self):
        from api.routers.auth import logout
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        mock_creds = MagicMock()
        mock_creds.credentials = "bad_tok"
        with patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = None
            result = await logout(credentials=mock_creds)
            assert result["message"] == "Logged out successfully"


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_get_current_user_success(self):
        from api.routers.auth import get_current_user
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        mock_creds = MagicMock()
        mock_creds.credentials = "valid_tok"
        with patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = {"sub": "user-1", "tenant_id": "t-1", "email": "a@b.com", "role": "admin"}
            result = await get_current_user(credentials=mock_creds)
            assert result["userId"] == "user-1"
            assert result["tenantId"] == "t-1"
            assert result["role"] == "admin"

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self):
        from api.routers.auth import get_current_user
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=None)
        assert exc.value.status_code == 401
        assert "No token" in exc.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        from api.routers.auth import get_current_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        mock_creds = MagicMock()
        mock_creds.credentials = "bad_tok"
        with patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = None
            with pytest.raises(HTTPException) as exc:
                await get_current_user(credentials=mock_creds)
            assert exc.value.status_code == 401
            assert "Invalid or expired" in exc.value.detail


class TestRegistrationExtended:
    @pytest.mark.asyncio
    async def test_register_without_company_name(self):
        from api.routers.auth import register, RegisterRequest

        with patch("api.services.db_tenants.get_user_by_email_db", new_callable=AsyncMock) as mock_get, \
             patch("api.services.db_tenants.create_tenant", new_callable=AsyncMock) as mock_create_tenant, \
             patch("api.services.db_tenants.create_user_db", new_callable=AsyncMock) as mock_create_user, \
             patch("api.services.auth.get_password_hash", return_value="hash"):
            mock_get.return_value = None
            mock_create_user.return_value = {"id": "user-456", "verification_token": "tok_def"}
            req = RegisterRequest(
                email="no@company.com", password="password123", full_name="No Company"
            )
            result = await register(req)
            assert result.user_id == "user-456"
            mock_create_tenant.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_company_slug_sanitization(self):
        from api.routers.auth import register, RegisterRequest

        with patch("api.services.db_tenants.get_user_by_email_db", new_callable=AsyncMock) as mock_get, \
             patch("api.services.db_tenants.create_tenant", new_callable=AsyncMock) as mock_create_tenant, \
             patch("api.services.db_tenants.create_user_db", new_callable=AsyncMock) as mock_create_user, \
             patch("api.services.auth.get_password_hash", return_value="hash"):
            mock_get.return_value = None
            mock_create_tenant.return_value = {"id": "tenant-abc"}
            mock_create_user.return_value = {"id": "user-789", "verification_token": "tok_ghi"}
            req = RegisterRequest(
                email="co@test.com", password="password123",
                full_name="Test", company_name="O'Brien Tech"
            )
            result = await register(req)
            assert result.user_id == "user-789"
            mock_create_tenant.assert_called_once()
            slug_arg = mock_create_tenant.call_args.kwargs["slug"]
            assert "'" not in slug_arg


class TestForgotPasswordExtended:
    @pytest.mark.asyncio
    async def test_forgot_password_user_not_found(self):
        from api.routers.auth import forgot_password, ForgotPasswordRequest

        with patch("api.services.db_tenants.set_password_reset_token_db", new_callable=AsyncMock) as mock_reset:
            mock_reset.return_value = (None, None)
            result = await forgot_password(ForgotPasswordRequest(email="unknown@test.com"))
            assert "message" in result
            assert "dev_token" not in result


class TestLoginMFA:
    @pytest.mark.asyncio
    async def test_login_mfa_required_returns_temp_token(self):
        from api.routers.auth import login, LoginRequest

        with patch("api.routers.auth.os.getenv", return_value="false"), \
             patch("api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db, \
             patch("api.services.auth.verify_password", return_value=True), \
             patch("api.routers.auth.is_mfa_required", new_callable=AsyncMock) as mock_mfa, \
             patch("api.routers.auth.create_mfa_session_token", new_callable=AsyncMock) as mock_temp:
            mock_db.return_value = {
                "id": "u1", "tenant_id": "t1", "email": "u@c.com",
                "password_hash": "hash", "role": "agent",
            }
            mock_mfa.return_value = True
            mock_temp.return_value = "temp-token-xyz"

            result = await login(LoginRequest(email="u@c.com", password="pass"))

            assert result["mfa_required"] is True
            assert result["temp_token"] == "temp-token-xyz"
            mock_mfa.assert_called_once_with("u1")
            mock_temp.assert_called_once_with("u1", "t1", "u@c.com", "agent")

    @pytest.mark.asyncio
    async def test_login_mfa_not_required_proceeds(self):
        from api.routers.auth import login, LoginRequest

        with patch("api.routers.auth.os.getenv", return_value="false"), \
             patch("api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db, \
             patch("api.services.auth.verify_password", return_value=True), \
             patch("api.routers.auth.is_mfa_required", new_callable=AsyncMock) as mock_mfa, \
             patch("api.routers.auth.generate_access_token", return_value="full-token"):
            mock_db.return_value = {
                "id": "u1", "tenant_id": "t1", "email": "u@c.com",
                "password_hash": "hash", "role": "agent", "display_name": "Alice",
            }
            mock_mfa.return_value = False

            result = await login(LoginRequest(email="u@c.com", password="pass"))

            assert result.access_token == "full-token"
            assert result.userId == "u1"


class TestLogoutExtended:
    @pytest.mark.asyncio
    async def test_logout_expired_token_skips_blocklist(self):
        import sys
        import time
        from api.routers.auth import logout

        mock_main = MagicMock()
        mock_redis = AsyncMock()
        mock_main.redis_client = mock_redis
        mock_creds = MagicMock()
        mock_creds.credentials = "expired_tok"

        with patch.dict("sys.modules", {"api.main": mock_main}), \
             patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = {"jti": "jti-expired", "exp": time.time() - 100}
            result = await logout(credentials=mock_creds)
            assert result["message"] == "Logged out successfully"
            mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_logout_payload_without_jti(self):
        import sys
        from api.routers.auth import logout

        mock_main = MagicMock()
        mock_main.redis_client = AsyncMock()
        mock_creds = MagicMock()
        mock_creds.credentials = "no-jti-tok"

        with patch.dict("sys.modules", {"api.main": mock_main}), \
             patch("api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = {"sub": "u1"}
            result = await logout(credentials=mock_creds)
            assert result["message"] == "Logged out successfully"


class TestOverlayTokenUtils:
    """Direct unit tests for the Overlay 365 token helpers."""

    def test_base64url_encode(self):
        import base64
        from api.routers.auth import base64url_encode

        assert base64url_encode("hello world") == base64.urlsafe_b64encode(b"hello world").rstrip(b"=").decode()

    def test_sign_and_verify_overlay_token(self):
        import time
        from api.routers.auth import _sign_overlay_token, _verify_overlay_token

        payload = {
            "sub": "u1", "email": "a@b.com", "tier": "worker",
            "exp": time.time() + 3600, "iss": "overlay365",
        }
        token = _sign_overlay_token(payload, "master-secret")
        assert len(token.split(".")) == 3
        assert _verify_overlay_token(token, "master-secret") == payload
        assert _verify_overlay_token(token, "wrong-secret") is None

    def test_verify_overlay_token_malformed(self):
        from api.routers.auth import _verify_overlay_token

        assert _verify_overlay_token("one-part", "s") is None
        assert _verify_overlay_token("a.b.c.d", "s") is None
        assert _verify_overlay_token("a.b.c", "s") is None  # bad signature

    def test_verify_overlay_token_expired(self):
        import time
        from api.routers.auth import _sign_overlay_token, _verify_overlay_token

        payload = {"sub": "u1", "exp": time.time() - 100}
        token = _sign_overlay_token(payload, "s")
        assert _verify_overlay_token(token, "s") is None

    def test_verify_overlay_token_bad_payload_json(self):
        import base64
        import hashlib
        import hmac
        from api.routers.auth import _verify_overlay_token

        header_b64 = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"OVERLAY"}').rstrip(b"=").decode()
        payload_b64 = base64.urlsafe_b64encode(b"not-json").rstrip(b"=").decode()
        body = header_b64 + "." + payload_b64
        sig = hmac.new(b"s", body.encode(), hashlib.sha256).hexdigest()
        token = body + "." + sig

        assert _verify_overlay_token(token, "s") is None

    def test_verify_overlay_token_unexpected_error(self):
        from api.routers.auth import _verify_overlay_token

        # Non-string token -> AttributeError (not in the handled exception tuple)
        assert _verify_overlay_token(None, "s") is None
        assert _verify_overlay_token(12345, "s") is None


class TestOverlayEndpoints:
    """TestClient tests for /auth/v1/auth/token and /auth/v1/auth/validate."""

    @staticmethod
    def _app():
        from fastapi import FastAPI
        from api.routers.auth import router

        application = FastAPI()
        application.include_router(router)
        return application

    def test_generate_overlay_token_success(self):
        with patch("api.routers.auth.OVERLAY_MASTER_KEY", "master-secret"):
            app = self._app()
            with TestClient(app) as client:
                resp = client.post(
                    "/auth/v1/auth/token",
                    json={"user_id": "u1", "email": "a@b.com", "tier": "worker"},
                    headers={"Authorization": "Bearer master-secret"},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["token_type"] == "overlay"
            assert data["tier"] == "worker"
            assert data["user_id"] == "u1"
            assert data["access_token"].count(".") == 2

    def test_generate_overlay_token_no_master_key(self):
        with patch("api.routers.auth.OVERLAY_MASTER_KEY", ""):
            app = self._app()
            with TestClient(app) as client:
                resp = client.post(
                    "/auth/v1/auth/token",
                    json={"user_id": "u1", "email": "a@b.com", "tier": "worker"},
                    headers={"Authorization": "Bearer whatever"},
                )
            assert resp.status_code == 503

    def test_generate_overlay_token_wrong_key(self):
        with patch("api.routers.auth.OVERLAY_MASTER_KEY", "real-key"):
            app = self._app()
            with TestClient(app) as client:
                resp = client.post(
                    "/auth/v1/auth/token",
                    json={"user_id": "u1", "email": "a@b.com", "tier": "worker"},
                    headers={"Authorization": "Bearer wrong-key"},
                )
            assert resp.status_code == 401

    def test_generate_overlay_token_invalid_tier(self):
        with patch("api.routers.auth.OVERLAY_MASTER_KEY", "real-key"):
            app = self._app()
            with TestClient(app) as client:
                resp = client.post(
                    "/auth/v1/auth/token",
                    json={"user_id": "u1", "email": "a@b.com", "tier": "superadmin"},
                    headers={"Authorization": "Bearer real-key"},
                )
            assert resp.status_code == 400

    def test_validate_overlay_token_success(self):
        with patch("api.routers.auth.OVERLAY_MASTER_KEY", "master-secret"):
            app = self._app()
            with TestClient(app) as client:
                gen = client.post(
                    "/auth/v1/auth/token",
                    json={"user_id": "u1", "email": "a@b.com", "tier": "business"},
                    headers={"Authorization": "Bearer master-secret"},
                )
                token = gen.json()["access_token"]
                resp = client.post(
                    "/auth/v1/auth/validate",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["valid"] is True
            assert data["user_id"] == "u1"
            assert data["tier"] == "business"

    def test_validate_overlay_token_no_master_key(self):
        with patch("api.routers.auth.OVERLAY_MASTER_KEY", ""):
            app = self._app()
            with TestClient(app) as client:
                resp = client.post(
                    "/auth/v1/auth/validate",
                    headers={"Authorization": "Bearer abc.def.ghi"},
                )
            assert resp.status_code == 503

    def test_validate_overlay_token_invalid(self):
        with patch("api.routers.auth.OVERLAY_MASTER_KEY", "master-secret"):
            app = self._app()
            with TestClient(app) as client:
                resp = client.post(
                    "/auth/v1/auth/validate",
                    headers={"Authorization": "Bearer not.a.real.token"},
                )
            assert resp.status_code == 401


class TestDevUsersModuleState:
    """Covers the import-time DEV_USERS construction and startup warnings.

    These branches only execute when the module is (re)imported with the
    relevant env vars set. Each reload is restored to the default env
    afterwards so the module state is unchanged for the rest of the suite.
    """

    def test_dev_users_populated_from_env(self):
        import importlib
        import os
        import api.routers.auth as auth_mod

        os.environ["DEV_ADMIN_PASSWORD"] = "admin-pw-123"
        os.environ["DEV_AGENT_PASSWORD"] = "agent-pw-456"
        try:
            reloaded = importlib.reload(auth_mod)
            assert reloaded.DEV_USERS["admin@aetherdesk.com"]["role"] == "admin"
            assert reloaded.DEV_USERS["admin@aetherdesk.com"]["password"] == "admin-pw-123"
            assert reloaded.DEV_USERS["agent@aetherdesk.com"]["role"] == "agent"
            assert reloaded.DEV_USERS["agent@aetherdesk.com"]["password"] == "agent-pw-456"
        finally:
            os.environ.pop("DEV_ADMIN_PASSWORD", None)
            os.environ.pop("DEV_AGENT_PASSWORD", None)
            importlib.reload(auth_mod)

    def test_dev_users_enabled_no_passwords_warns(self):
        import importlib
        import os
        import api.routers.auth as auth_mod

        os.environ["ENABLE_DEV_USERS"] = "true"
        try:
            reloaded = importlib.reload(auth_mod)
            assert reloaded._dev_users_enabled() is True
            assert reloaded.DEV_USERS == {}
        finally:
            os.environ.pop("ENABLE_DEV_USERS", None)
            importlib.reload(auth_mod)

    def test_dev_users_enabled_with_passwords(self):
        import importlib
        import os
        import api.routers.auth as auth_mod

        os.environ["ENABLE_DEV_USERS"] = "true"
        os.environ["DEV_ADMIN_PASSWORD"] = "pw"
        try:
            reloaded = importlib.reload(auth_mod)
            assert reloaded._dev_users_enabled() is True
            assert "admin@aetherdesk.com" in reloaded.DEV_USERS
        finally:
            os.environ.pop("ENABLE_DEV_USERS", None)
            os.environ.pop("DEV_ADMIN_PASSWORD", None)
            importlib.reload(auth_mod)

    def test_dev_users_forced_off_in_production(self):
        import importlib
        import os
        import api.routers.auth as auth_mod

        os.environ["ENABLE_DEV_USERS"] = "true"
        os.environ["APP_ENV"] = "production"
        try:
            reloaded = importlib.reload(auth_mod)
            assert reloaded._dev_users_enabled() is False
            assert reloaded.DEV_USERS == {}
        finally:
            os.environ["APP_ENV"] = "development"
            os.environ.pop("ENABLE_DEV_USERS", None)
            importlib.reload(auth_mod)
