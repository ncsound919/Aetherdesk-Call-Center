"""Tests for Casbin RBAC authorization service."""

import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


@pytest.fixture(autouse=True)
def reset_casbin():
    """Reset enforcer singleton before each test."""
    import api.services.authorization as mod
    mod._enforcer = None
    yield
    mod._enforcer = None


class TestCheckPermission:
    def test_permissive_mode_when_no_enforcer_non_production(self):
        from api.services.authorization import check_permission
        with patch.dict(os.environ, {"APP_ENV": "development"}), \
             patch("api.services.authorization._get_enforcer", return_value=None):
            assert check_permission("agent", "calls", "read") is True
            assert check_permission("admin", "billing", "delete") is True

    def test_fails_closed_when_no_enforcer_in_production(self):
        from api.services.authorization import check_permission
        with patch.dict(os.environ, {"APP_ENV": "production"}), \
             patch("api.services.authorization._get_enforcer", return_value=None):
            assert check_permission("agent", "calls", "read") is False
            assert check_permission("admin", "billing", "delete") is False

    def test_fails_closed_when_enforcer_init_raises_in_production(self):
        from api.services.authorization import check_permission
        with patch.dict(os.environ, {"APP_ENV": "production"}), \
             patch("api.services.authorization._get_enforcer", side_effect=RuntimeError("boom")):
            assert check_permission("admin", "billing", "delete") is False

    def test_allows_admin_everything(self):
        from api.services.authorization import check_permission
        mock_enforcer = MagicMock()
        mock_enforcer.enforce.return_value = True
        with patch("api.services.authorization._get_enforcer", return_value=mock_enforcer):
            assert check_permission("admin", "billing", "delete") is True
            mock_enforcer.enforce.assert_called_with("admin", "billing", "delete")

    def test_denies_agent_write(self):
        from api.services.authorization import check_permission
        mock_enforcer = MagicMock()
        mock_enforcer.enforce.return_value = False
        with patch("api.services.authorization._get_enforcer", return_value=mock_enforcer):
            assert check_permission("agent", "billing", "write") is False

    def test_handles_enforcer_error(self):
        from api.services.authorization import check_permission
        mock_enforcer = MagicMock()
        mock_enforcer.enforce.side_effect = Exception("enforcer crash")
        with patch("api.services.authorization._get_enforcer", return_value=mock_enforcer):
            # Fail closed on error
            assert check_permission("admin", "calls", "read") is False


class TestAddRoleForUser:
    def test_returns_true_when_no_enforcer(self):
        from api.services.authorization import add_role_for_user
        with patch("api.services.authorization._get_enforcer", return_value=None):
            assert add_role_for_user("user-1", "admin") is True

    def test_calls_enforcer(self):
        from api.services.authorization import add_role_for_user
        mock_enforcer = MagicMock()
        with patch("api.services.authorization._get_enforcer", return_value=mock_enforcer):
            result = add_role_for_user("user-1", "admin")
            assert result is True
            mock_enforcer.add_role_for_user.assert_called_once_with("user-1", "admin")


class TestRemoveRoleForUser:
    def test_returns_true_when_no_enforcer(self):
        from api.services.authorization import remove_role_for_user
        with patch("api.services.authorization._get_enforcer", return_value=None):
            assert remove_role_for_user("user-1", "admin") is True


class TestGetRolesForUser:
    def test_returns_empty_when_no_enforcer(self):
        from api.services.authorization import get_roles_for_user
        with patch("api.services.authorization._get_enforcer", return_value=None):
            assert get_roles_for_user("user-1") == []

    def test_returns_roles(self):
        from api.services.authorization import get_roles_for_user
        mock_enforcer = MagicMock()
        mock_enforcer.get_roles_for_user.return_value = ["admin", "supervisor"]
        with patch("api.services.authorization._get_enforcer", return_value=mock_enforcer):
            result = get_roles_for_user("user-1")
            assert result == ["admin", "supervisor"]


class TestGetPermissions:
    def test_returns_empty_when_no_enforcer(self):
        from api.services.authorization import get_permissions
        with patch("api.services.authorization._get_enforcer", return_value=None):
            assert get_permissions("admin") == []

    def test_returns_permissions(self):
        from api.services.authorization import get_permissions
        mock_enforcer = MagicMock()
        mock_enforcer.get_permissions_for_user.return_value = [
            ["admin", "*", "*"],
            ["admin", "billing", "read"],
        ]
        with patch("api.services.authorization._get_enforcer", return_value=mock_enforcer):
            result = get_permissions("admin")
            assert len(result) == 2


class TestGetEnforcer:
    def test_returns_none_when_files_missing(self):
        from api.services.authorization import _get_enforcer
        with patch("os.path.exists", return_value=False):
            result = _get_enforcer()
            assert result is None

    def test_returns_none_when_import_fails(self):
        from api.services.authorization import _get_enforcer
        with patch("os.path.exists", return_value=True):
            with patch.dict("sys.modules", {"casbin": None}):
                result = _get_enforcer()
                assert result is None
