"""Unit tests for api.routers.security (MFA endpoints)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import security as security_module
from api.services.auth import get_current_user


@pytest.fixture
def app():
    from api.routers.security import router

    application = FastAPI()
    application.include_router(router)

    async def _override_get_current_user():
        return {"sub": "user-1", "email": "user@example.com"}

    application.dependency_overrides[get_current_user] = _override_get_current_user
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _token(overrides=None):
    token = {"sub": "user-1", "email": "user@example.com"}
    if overrides:
        token.update(overrides)
    return token


class TestSetupMFA:
    def test_success(self, client):
        with patch.object(
            security_module.mfa_service,
            "setup_mfa",
            new=AsyncMock(
                return_value={
                    "secret": "SECRET",
                    "otpauth_url": "otpauth://totp/AetherDesk:user@example.com?secret=SECRET&issuer=AetherDesk",
                    "backup_codes": ["11111111", "22222222"],
                }
            ),
        ) as mock_setup:
            resp = client.post("/auth/mfa/setup")

        assert resp.status_code == 200
        body = resp.json()
        assert body["secret"] == "SECRET"
        assert body["backup_codes"] == ["11111111", "22222222"]
        mock_setup.assert_called_once_with("user-1", "user@example.com")

    def test_missing_user_info(self, app, client):
        async def _override():
            return {"sub": None, "email": None}

        app.dependency_overrides[get_current_user] = _override
        resp = client.post("/auth/mfa/setup")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing user info in token"


class TestVerifyMFASetup:
    def test_success(self, client):
        with (
            patch.object(
                security_module.mfa_service, "verify_totp", new=AsyncMock(return_value=True)
            ),
            patch.object(
                security_module.mfa_service,
                "enable_mfa",
                new=AsyncMock(return_value={"success": True}),
            ),
        ):
            resp = client.post("/auth/mfa/verify", json={"code": "123456"})

        assert resp.status_code == 200
        assert resp.json() == {"message": "MFA enabled successfully"}

    def test_invalid_totp(self, client):
        with patch.object(
            security_module.mfa_service, "verify_totp", new=AsyncMock(return_value=False)
        ):
            resp = client.post("/auth/mfa/verify", json={"code": "000000"})

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid TOTP code"

    def test_enable_failure(self, client):
        with (
            patch.object(
                security_module.mfa_service, "verify_totp", new=AsyncMock(return_value=True)
            ),
            patch.object(
                security_module.mfa_service,
                "enable_mfa",
                new=AsyncMock(return_value={"success": False, "error": "No MFA setup found"}),
            ),
        ):
            resp = client.post("/auth/mfa/verify", json={"code": "123456"})

        assert resp.status_code == 400
        assert resp.json()["detail"] == "No MFA setup found"

    def test_missing_user_id(self, app, client):
        async def _override():
            return _token(overrides={"sub": None})

        app.dependency_overrides[get_current_user] = _override
        resp = client.post("/auth/mfa/verify", json={"code": "123456"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing user info in token"


class TestDisableMFA:
    def test_success(self, client):
        with patch.object(
            security_module.mfa_service,
            "disable_mfa",
            new=AsyncMock(return_value={"success": True}),
        ) as mock_disable:
            resp = client.post("/auth/mfa/disable")

        assert resp.status_code == 200
        assert resp.json() == {"message": "MFA disabled successfully"}
        mock_disable.assert_called_once_with("user-1")

    def test_disable_failure(self, client):
        with patch.object(
            security_module.mfa_service,
            "disable_mfa",
            new=AsyncMock(return_value={"success": False, "error": "No MFA setup found"}),
        ):
            resp = client.post("/auth/mfa/disable")

        assert resp.status_code == 400
        assert resp.json()["detail"] == "No MFA setup found"

    def test_missing_user_id(self, app, client):
        async def _override():
            return _token(overrides={"sub": None})

        app.dependency_overrides[get_current_user] = _override
        resp = client.post("/auth/mfa/disable")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing user info in token"


class TestMFALogin:
    def test_invalid_session_token(self, client):
        with patch(
            "api.services.jwt_utils.verify_access_token", return_value=None
        ) as mock_verify:
            resp = client.post(
                "/auth/mfa/login", json={"session_token": "bad-token", "code": "123456"}
            )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid or expired session token"
        mock_verify.assert_called_once_with("bad-token")

    def test_not_mfa_pending(self, client):
        with patch(
            "api.services.jwt_utils.verify_access_token",
            return_value={"sub": "user-1", "mfa_pending": False},
        ):
            resp = client.post(
                "/auth/mfa/login", json={"session_token": "tok", "code": "123456"}
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Token is not an MFA pending session"

    def test_totp_success(self, client):
        with (
            patch(
                "api.services.jwt_utils.verify_access_token",
                return_value={
                    "sub": "user-1",
                    "mfa_pending": True,
                    "tenant_id": "tenant-1",
                    "email": "user@example.com",
                    "role": "admin",
                },
            ),
            patch.object(
                security_module.mfa_service, "verify_totp", new=AsyncMock(return_value=True)
            ),
            patch.object(
                security_module.mfa_service, "verify_backup_code", new=AsyncMock(return_value=False)
            ),
            patch(
                "api.services.auth.create_full_token", new=AsyncMock(return_value="full-token")
            ) as mock_token,
        ):
            resp = client.post(
                "/auth/mfa/login", json={"session_token": "tok", "code": "123456"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["token"] == "full-token"
        assert body["access_token"] == "full-token"
        assert body["token_type"] == "bearer"
        assert body["tenantId"] == "tenant-1"
        assert body["userId"] == "user-1"
        assert body["role"] == "admin"
        assert body["email"] == "user@example.com"
        mock_token.assert_called_once_with(
            user_id="user-1",
            tenant_id="tenant-1",
            email="user@example.com",
            role="admin",
        )

    def test_backup_code_fallback_success(self, client):
        with (
            patch(
                "api.services.jwt_utils.verify_access_token",
                return_value={
                    "sub": "user-1",
                    "mfa_pending": True,
                    "tenant_id": "",
                    "email": "",
                    "role": "",
                },
            ),
            patch.object(
                security_module.mfa_service, "verify_totp", new=AsyncMock(return_value=False)
            ),
            patch.object(
                security_module.mfa_service, "verify_backup_code", new=AsyncMock(return_value=True)
            ),
            patch(
                "api.services.auth.create_full_token", new=AsyncMock(return_value="full-token")
            ),
        ):
            resp = client.post(
                "/auth/mfa/login", json={"session_token": "tok", "code": "87654321"}
            )

        assert resp.status_code == 200
        assert resp.json()["token"] == "full-token"

    def test_invalid_mfa_code(self, client):
        with (
            patch(
                "api.services.jwt_utils.verify_access_token",
                return_value={"sub": "user-1", "mfa_pending": True},
            ),
            patch.object(
                security_module.mfa_service, "verify_totp", new=AsyncMock(return_value=False)
            ),
            patch.object(
                security_module.mfa_service, "verify_backup_code", new=AsyncMock(return_value=False)
            ),
        ):
            resp = client.post(
                "/auth/mfa/login", json={"session_token": "tok", "code": "000000"}
            )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid MFA code"


class TestMFABackupCode:
    def test_success(self, client):
        with patch.object(
            security_module.mfa_service, "verify_backup_code", new=AsyncMock(return_value=True)
        ) as mock_verify:
            resp = client.post("/auth/mfa/backup-code", json={"code": "87654321"})

        assert resp.status_code == 200
        assert resp.json() == {"message": "Backup code verified successfully"}
        mock_verify.assert_called_once_with("user-1", "87654321")

    def test_invalid_backup_code(self, client):
        with patch.object(
            security_module.mfa_service, "verify_backup_code", new=AsyncMock(return_value=False)
        ):
            resp = client.post("/auth/mfa/backup-code", json={"code": "00000000"})

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid backup code"

    def test_missing_user_id(self, app, client):
        async def _override():
            return _token(overrides={"sub": None})

        app.dependency_overrides[get_current_user] = _override
        resp = client.post("/auth/mfa/backup-code", json={"code": "87654321"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing user info in token"


class TestMFAStatus:
    def test_success(self, client):
        with patch.object(
            security_module.mfa_service,
            "get_mfa_status",
            new=AsyncMock(return_value={"enabled": True, "enrolled": True}),
        ) as mock_status:
            resp = client.get("/auth/mfa/status")

        assert resp.status_code == 200
        assert resp.json() == {"enabled": True, "enrolled": True}
        mock_status.assert_called_once_with("user-1")

    def test_missing_user_id(self, app, client):
        async def _override():
            return _token(overrides={"sub": None})

        app.dependency_overrides[get_current_user] = _override
        resp = client.get("/auth/mfa/status")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing user info in token"
