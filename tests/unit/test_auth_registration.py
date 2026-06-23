import pytest
from unittest.mock import AsyncMock, patch


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
