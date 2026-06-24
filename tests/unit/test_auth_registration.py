import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestRegistration:
    @pytest.mark.asyncio
    async def test_register_creates_user_and_tenant(self):
        from apps.api.routers.auth import register, RegisterRequest

        with patch("apps.api.services.db_tenants.get_user_by_email_db", new_callable=AsyncMock) as mock_get, \
             patch("apps.api.services.db_tenants.create_tenant", new_callable=AsyncMock) as mock_create_tenant, \
             patch("apps.api.services.db_tenants.create_user_db", new_callable=AsyncMock) as mock_create_user, \
             patch("apps.api.services.auth.get_password_hash", return_value="hashed_password"):

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
        from apps.api.routers.auth import register, RegisterRequest
        from fastapi import HTTPException

        with patch("apps.api.services.db_tenants.get_user_by_email_db", new_callable=AsyncMock) as mock_get:
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
        from apps.api.routers.auth import register, RegisterRequest
        from fastapi import HTTPException

        with patch("apps.api.services.db_tenants.get_user_by_email_db", new_callable=AsyncMock) as mock_get:
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
        from apps.api.routers.auth import verify_email, VerifyEmailRequest

        with patch("apps.api.services.db_tenants.verify_user_email_db", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = "user-123"
            result = await verify_email(VerifyEmailRequest(token="valid_token"))
            assert result["message"] == "Email verified successfully"

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self):
        from apps.api.routers.auth import verify_email, VerifyEmailRequest
        from fastapi import HTTPException

        with patch("apps.api.services.db_tenants.verify_user_email_db", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = None
            with pytest.raises(HTTPException) as exc:
                await verify_email(VerifyEmailRequest(token="invalid"))
            assert exc.value.status_code == 400


class TestPasswordReset:
    @pytest.mark.asyncio
    async def test_forgot_password_returns_token(self):
        from apps.api.routers.auth import forgot_password, ForgotPasswordRequest

        with patch("apps.api.services.db_tenants.set_password_reset_token_db", new_callable=AsyncMock) as mock_reset:
            mock_reset.return_value = ("user-123", "reset_token_abc")
            result = await forgot_password(ForgotPasswordRequest(email="test@example.com"))
            assert "dev_token" in result

    @pytest.mark.asyncio
    async def test_reset_password_success(self):
        from apps.api.routers.auth import reset_password, ResetPasswordRequest

        with patch("apps.api.services.db_tenants.reset_password_db", new_callable=AsyncMock) as mock_reset, \
             patch("apps.api.services.auth.get_password_hash", return_value="new_hash"):
            mock_reset.return_value = "user-123"
            result = await reset_password(ResetPasswordRequest(token="valid", new_password="newpass123"))
            assert result["message"] == "Password reset successfully"

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self):
        from apps.api.routers.auth import reset_password, ResetPasswordRequest
        from fastapi import HTTPException

        with patch("apps.api.services.db_tenants.reset_password_db", new_callable=AsyncMock) as mock_reset, \
             patch("apps.api.services.auth.get_password_hash", return_value="new_hash"):
            mock_reset.return_value = None
            with pytest.raises(HTTPException) as exc:
                await reset_password(ResetPasswordRequest(token="invalid", new_password="newpass123"))
            assert exc.value.status_code == 400


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_dev_user_success(self):
        from apps.api.routers.auth import login, LoginRequest

        with patch("apps.api.routers.auth.os.getenv", return_value="true"), \
             patch("apps.api.routers.auth.generate_access_token", return_value="dev_token"):
            req = LoginRequest(email="admin@aetherdesk.com", password="admin123")
            result = await login(req)
            assert result.access_token == "dev_token"
            assert result.userId == "USER-ADMIN-001"
            assert result.role == "admin"
            assert result.tenantId == "TENANT-001"
            assert result.name == "Admin User"

    @pytest.mark.asyncio
    async def test_login_dev_agent_success(self):
        from apps.api.routers.auth import login, LoginRequest

        with patch("apps.api.routers.auth.os.getenv", return_value="true"), \
             patch("apps.api.routers.auth.generate_access_token", return_value="agent_token"):
            req = LoginRequest(email="agent@aetherdesk.com", password="agent123")
            result = await login(req)
            assert result.role == "agent"
            assert result.name == "Test Agent"

    @pytest.mark.asyncio
    async def test_login_dev_user_wrong_password(self):
        from apps.api.routers.auth import login, LoginRequest
        from fastapi import HTTPException

        with patch("apps.api.routers.auth.os.getenv", return_value="true"):
            req = LoginRequest(email="admin@aetherdesk.com", password="wrongpass")
            with pytest.raises(HTTPException) as exc:
                await login(req)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_dev_user_not_found(self):
        from apps.api.routers.auth import login, LoginRequest
        from fastapi import HTTPException

        with patch("apps.api.routers.auth.os.getenv", return_value="true"):
            req = LoginRequest(email="unknown@test.com", password="anypass")
            with pytest.raises(HTTPException) as exc:
                await login(req)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_production_success(self):
        from apps.api.routers.auth import login, LoginRequest

        with patch("apps.api.routers.auth.os.getenv", return_value="false"), \
             patch("apps.api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db, \
             patch("apps.api.services.auth.verify_password", return_value=True), \
             patch("apps.api.routers.auth.generate_access_token", return_value="prod_token"):
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
        from apps.api.routers.auth import login, LoginRequest

        with patch("apps.api.routers.auth.os.getenv", return_value="false"), \
             patch("apps.api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db, \
             patch("apps.api.services.auth.verify_password", return_value=True), \
             patch("apps.api.routers.auth.generate_access_token", return_value="tok"):
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
        from apps.api.routers.auth import login, LoginRequest
        from fastapi import HTTPException

        with patch("apps.api.routers.auth.os.getenv", return_value="false"), \
             patch("apps.api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db, \
             patch("apps.api.services.auth.verify_password", return_value=False):
            mock_db.return_value = {"id": "u1", "password_hash": "hash"}
            req = LoginRequest(email="user@co.com", password="wrong")
            with pytest.raises(HTTPException) as exc:
                await login(req)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_production_user_not_found(self):
        from apps.api.routers.auth import login, LoginRequest
        from fastapi import HTTPException

        with patch("apps.api.routers.auth.os.getenv", return_value="false"), \
             patch("apps.api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = None
            req = LoginRequest(email="nobody@co.com", password="pass")
            with pytest.raises(HTTPException) as exc:
                await login(req)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_production_db_unavailable(self):
        from apps.api.routers.auth import login, LoginRequest
        from fastapi import HTTPException

        with patch("apps.api.routers.auth.os.getenv", return_value="false"), \
             patch("apps.api.routers.auth.get_user_by_email_db", new_callable=AsyncMock) as mock_db:
            mock_db.side_effect = Exception("DB connection refused")
            req = LoginRequest(email="user@co.com", password="pass")
            with pytest.raises(HTTPException) as exc:
                await login(req)
            assert exc.value.status_code == 503


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_with_redis(self):
        import sys
        from apps.api.routers.auth import logout
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        mock_redis = AsyncMock()
        mock_main = MagicMock()
        mock_main.redis_client = mock_redis

        mock_creds = MagicMock()
        mock_creds.credentials = "valid_tok"
        with patch.dict("sys.modules", {"apps.api.main": mock_main}), \
             patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = {"jti": "jti-1", "exp": 9999999999}
            result = await logout(credentials=mock_creds)
            assert result["message"] == "Logged out successfully"
            mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_logout_fallback_blocklist(self):
        import sys
        from apps.api.routers.auth import logout
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        mock_main = MagicMock()
        mock_main.redis_client = None

        mock_creds = MagicMock()
        mock_creds.credentials = "valid_tok"
        mock_blocklist = set()
        with patch.dict("sys.modules", {"apps.api.main": mock_main}), \
             patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v, \
             patch("apps.api.services.auth._fallback_blocklist", mock_blocklist):
            mock_v.return_value = {"jti": "jti-2", "exp": 9999999999}
            result = await logout(credentials=mock_creds)
            assert result["message"] == "Logged out successfully"
            assert "jti-2" in mock_blocklist

    @pytest.mark.asyncio
    async def test_logout_no_credentials(self):
        from apps.api.routers.auth import logout

        result = await logout(credentials=None)
        assert result["message"] == "Logged out successfully"

    @pytest.mark.asyncio
    async def test_logout_invalid_token(self):
        from apps.api.routers.auth import logout
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        mock_creds = MagicMock()
        mock_creds.credentials = "bad_tok"
        with patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = None
            result = await logout(credentials=mock_creds)
            assert result["message"] == "Logged out successfully"


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_get_current_user_success(self):
        from apps.api.routers.auth import get_current_user
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        mock_creds = MagicMock()
        mock_creds.credentials = "valid_tok"
        with patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = {"sub": "user-1", "tenant_id": "t-1", "email": "a@b.com", "role": "admin"}
            result = await get_current_user(credentials=mock_creds)
            assert result["userId"] == "user-1"
            assert result["tenantId"] == "t-1"
            assert result["role"] == "admin"

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self):
        from apps.api.routers.auth import get_current_user
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=None)
        assert exc.value.status_code == 401
        assert "No token" in exc.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        from apps.api.routers.auth import get_current_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials as Creds

        mock_creds = MagicMock()
        mock_creds.credentials = "bad_tok"
        with patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_v:
            mock_v.return_value = None
            with pytest.raises(HTTPException) as exc:
                await get_current_user(credentials=mock_creds)
            assert exc.value.status_code == 401
            assert "Invalid or expired" in exc.value.detail


class TestRegistrationExtended:
    @pytest.mark.asyncio
    async def test_register_without_company_name(self):
        from apps.api.routers.auth import register, RegisterRequest

        with patch("apps.api.services.db_tenants.get_user_by_email_db", new_callable=AsyncMock) as mock_get, \
             patch("apps.api.services.db_tenants.create_tenant", new_callable=AsyncMock) as mock_create_tenant, \
             patch("apps.api.services.db_tenants.create_user_db", new_callable=AsyncMock) as mock_create_user, \
             patch("apps.api.services.auth.get_password_hash", return_value="hash"):
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
        from apps.api.routers.auth import register, RegisterRequest

        with patch("apps.api.services.db_tenants.get_user_by_email_db", new_callable=AsyncMock) as mock_get, \
             patch("apps.api.services.db_tenants.create_tenant", new_callable=AsyncMock) as mock_create_tenant, \
             patch("apps.api.services.db_tenants.create_user_db", new_callable=AsyncMock) as mock_create_user, \
             patch("apps.api.services.auth.get_password_hash", return_value="hash"):
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
        from apps.api.routers.auth import forgot_password, ForgotPasswordRequest

        with patch("apps.api.services.db_tenants.set_password_reset_token_db", new_callable=AsyncMock) as mock_reset:
            mock_reset.return_value = (None, None)
            result = await forgot_password(ForgotPasswordRequest(email="unknown@test.com"))
            assert "message" in result
            assert "dev_token" not in result
