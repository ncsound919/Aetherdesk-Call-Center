"""Unit tests for src/api/services/default_creds.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.default_creds import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    WEAK_PASSWORDS,
    audit_credential_strength,
    check_default_credentials,
    force_password_reset,
    generate_secure_password,
)


class FakeConn:
    def __init__(self, fetchone=None, fetchall=None):
        self._one = fetchone
        self._all = fetchall
        self.closed = False
        self.committed = False
        self.last_sql = None
        self.last_params = None
        self.executed_sqls = []
        self.executed_params = []

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed_sqls.append(sql)
        self.executed_params.append(params)
        return self

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class FakePool:
    def __init__(self, fetchrow=None, fetch=None):
        self._row = fetchrow
        self._rows = fetch or []
        self.executed = []

    async def fetchrow(self, sql, *params):
        return self._row

    async def fetch(self, sql):
        return self._rows

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return "OK"


def _patch_conn(conn):
    return patch(
        "api.services.default_creds._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.default_creds.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.default_creds.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.default_creds.USE_POSTGRES", False)


class TestConstants:
    def test_default_password_is_weak(self):
        assert DEFAULT_ADMIN_PASSWORD in WEAK_PASSWORDS

    def test_default_admin_email(self):
        assert DEFAULT_ADMIN_EMAIL == "admin@aetherdesk.com"


class TestCheckDefaultCredentials:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(
            fetchone={"id": 1, "email": DEFAULT_ADMIN_EMAIL}
        )
        with _pg_false(), _patch_conn(conn):
            result = await check_default_credentials()
        assert result == {"user_id": 1, "email": DEFAULT_ADMIN_EMAIL}
        assert DEFAULT_ADMIN_EMAIL in conn.last_params
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await check_default_credentials() is None
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": 1, "email": DEFAULT_ADMIN_EMAIL})
        with _pg_true(), _patch_pg(pool):
            result = await check_default_credentials()
        assert result == {"user_id": "1", "email": DEFAULT_ADMIN_EMAIL}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await check_default_credentials() is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await check_default_credentials() is None


class TestForcePasswordReset:
    @pytest.mark.asyncio
    async def test_sqlite_updates_user(self):
        conn = FakeConn(fetchone={"id": "u1", "email": "a@b.com"})
        with _pg_false(), _patch_conn(conn):
            result = await force_password_reset("u1")
        assert result == {"id": "u1", "email": "a@b.com"}
        assert conn.committed is True
        assert conn.closed is True
        assert any(
            sql.startswith("UPDATE users SET reset_token") for sql in conn.executed_sqls
        )
        update_sql = conn.executed_sqls[0]
        assert "password_hash = ''" in update_sql
        assert conn.executed_params[0][0]  # reset_token non-empty
        assert conn.executed_params[0][1]  # expires_at present
        assert conn.executed_params[0][2] == "u1"

    @pytest.mark.asyncio
    async def test_sqlite_user_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await force_password_reset("missing") is None
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_pg_updates_user(self):
        pool = FakePool(fetchrow={"id": "u1", "email": "a@b.com"})
        with _pg_true(), _patch_pg(pool):
            result = await force_password_reset("u1")
        assert result == {"id": "u1", "email": "a@b.com"}
        sql, params = pool.executed[0]
        assert "UPDATE users SET reset_token" in sql
        assert params[1] == "u1"

    @pytest.mark.asyncio
    async def test_pg_user_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await force_password_reset("u1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await force_password_reset("u1") is None


class TestGenerateSecurePassword:
    def test_default_length_and_complexity(self):
        password = generate_secure_password()
        assert len(password) == 24
        assert any(c.islower() for c in password)
        assert any(c.isupper() for c in password)
        assert any(c.isdigit() for c in password)
        assert any(c in "!@#$%^&*" for c in password)

    def test_custom_length(self):
        password = generate_secure_password(32)
        assert len(password) == 32
        assert any(c.islower() for c in password)
        assert any(c.isupper() for c in password)
        assert any(c.isdigit() for c in password)
        assert any(c in "!@#$%^&*" for c in password)

    def test_produces_varied_passwords(self):
        seen = {generate_secure_password() for _ in range(20)}
        assert len(seen) > 1

    def test_retries_until_complexity_met(self):
        length = 4
        # First attempt: all lowercase (fails) -> retry with a valid mix.
        first = ["a"] * length
        valid = ["A", "a", "1", "!"]
        with patch(
            "api.services.default_creds.secrets.choice",
            side_effect=first + valid,
        ):
            password = generate_secure_password(length)
        assert password == "Aa1!"


class TestAuditCredentialStrength:
    @pytest.mark.asyncio
    async def test_sqlite_mixed_rows(self):
        conn = FakeConn(
            fetchall=[
                {"id": 1, "email": DEFAULT_ADMIN_EMAIL},
                {"id": 2, "email": "user@corp.com"},
                {"id": 3, "email": "other@corp.com"},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await audit_credential_strength()
        assert result["total_users"] == 3
        assert result["critical"] == 1
        assert result["ok"] == 2
        assert result["warning"] == 0
        assert result["users"][0]["has_default_credential"] is True
        assert result["users"][0]["status"] == "critical"
        assert result["users"][1]["status"] == "ok"
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            result = await audit_credential_strength()
        assert result["total_users"] == 0
        assert result["critical"] == 0
        assert result["ok"] == 0

    @pytest.mark.asyncio
    async def test_pg_mixed_rows(self):
        pool = FakePool(
            fetch=[
                {"id": 1, "email": DEFAULT_ADMIN_EMAIL},
                {"id": 2, "email": "user@corp.com"},
            ]
        )
        with _pg_true(), _patch_pg(pool):
            result = await audit_credential_strength()
        assert result["total_users"] == 2
        assert result["critical"] == 1
        assert result["ok"] == 1
        assert result["users"][0]["user_id"] == "1"

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            result = await audit_credential_strength()
        assert result == {
            "total_users": 0,
            "critical": 0,
            "warning": 0,
            "ok": 0,
            "users": [],
        }
