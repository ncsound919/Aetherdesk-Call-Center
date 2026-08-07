"""Unit tests for src/api/services/db_platform_ops.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.services.db_platform_ops as module
from api.services.db_platform_ops import (
    complete_onboarding_step_db,
    create_onboarding_progress_db,
    get_custom_domain_db,
    get_onboarding_progress_db,
    get_tenant_branding_db,
    get_tenant_config_value_db,
    list_white_label_tenants_db,
    set_custom_domain_db,
    set_tenant_branding_db,
    set_tenant_config_value_db,
    verify_domain_db,
)


class FakeConn:
    def __init__(self, fetchone=None, fetchall=None, rowcount=1):
        self._one = fetchone
        self._all = fetchall
        self.rowcount = rowcount
        self.closed = False
        self.committed = False
        self.last_sql = None
        self.last_params = None
        self.executed_sqls = []

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed_sqls.append(sql)
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
        "api.services.db_platform_ops._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_platform_ops.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_platform_ops.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_platform_ops.USE_POSTGRES", False)


class TestGetTenantBranding:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "company_name": "Acme"})
        with _pg_false(), _patch_conn(conn):
            result = await get_tenant_branding_db("t1")
        assert result["tenant_id"] == "t1"
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_branding_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            result = await get_tenant_branding_db("t1")
        assert result == {"tenant_id": "t1"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_tenant_branding_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_tenant_branding_db("t1") is None


class TestSetTenantBranding:
    @pytest.mark.asyncio
    async def test_sqlite_insert_when_missing(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "company_name": "Acme"})
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_platform_ops.get_tenant_branding_db",
            new_callable=AsyncMock,
            side_effect=[None, {"tenant_id": "t1", "company_name": "Acme"}],
        ):
            result = await set_tenant_branding_db(
                "t1", {"company_name": "Acme", "logo_url": "l.png"}
            )
        assert result["company_name"] == "Acme"
        assert "INSERT INTO tenant_branding" in conn.last_sql
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_update_when_exists(self):
        conn = FakeConn(fetchone={"tenant_id": "t1"})
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_platform_ops.get_tenant_branding_db",
            new_callable=AsyncMock,
            side_effect=[{"tenant_id": "t1"}, {"tenant_id": "t1"}],
        ):
            result = await set_tenant_branding_db(
                "t1", {"company_name": "New", "primary_color": None}
            )
        assert result == {"tenant_id": "t1"}
        assert "UPDATE tenant_branding SET" in conn.last_sql
        assert "company_name = ?" in conn.last_sql
        assert "primary_color" not in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_update_with_empty_config(self):
        conn = FakeConn(fetchone={"tenant_id": "t1"})
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_platform_ops.get_tenant_branding_db",
            new_callable=AsyncMock,
            side_effect=[{"tenant_id": "t1"}, {"tenant_id": "t1"}],
        ):
            await set_tenant_branding_db("t1", {})
        assert "updated_at = ?" in conn.last_sql
        assert "SET updated_at = ?" in conn.last_sql  # nothing else in SET

    @pytest.mark.asyncio
    async def test_pg_update_when_exists(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool), patch(
            "api.services.db_platform_ops.get_tenant_branding_db",
            new_callable=AsyncMock,
            side_effect=[{"tenant_id": "t1"}, {"tenant_id": "t1"}],
        ):
            await set_tenant_branding_db(
                "t1", {"company_name": "New", "logo_url": None}
            )
        sql, params = pool.executed[0]
        assert "UPDATE tenant_branding SET company_name = $1" in sql
        assert params == ("New", "t1")

    @pytest.mark.asyncio
    async def test_pg_insert_when_missing(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool), patch(
            "api.services.db_platform_ops.get_tenant_branding_db",
            new_callable=AsyncMock,
            side_effect=[None, {"tenant_id": "t1"}],
        ):
            result = await set_tenant_branding_db(
                "t1", {"company_name": "Acme"}
            )
        assert result == {"tenant_id": "t1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO tenant_branding" in sql
        assert params[1] == "t1"
        assert params[2] == "Acme"

    @pytest.mark.asyncio
    async def test_pg_no_pool_insert(self):
        with _pg_true(), _patch_pg(None), patch(
            "api.services.db_platform_ops.get_tenant_branding_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await set_tenant_branding_db("t1", {"company_name": "Acme"}) is None


class TestListWhiteLabelTenants:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(
            fetchall=[{"tenant_id": "t1", "tenant_name": "Acme"}]
        )
        with _pg_false(), _patch_conn(conn):
            result = await list_white_label_tenants_db()
        assert result == [{"tenant_id": "t1", "tenant_name": "Acme"}]

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_white_label_tenants_db() == []

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[{"tenant_id": "t1", "tenant_name": "Acme"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_white_label_tenants_db()
        assert result == [{"tenant_id": "t1", "tenant_name": "Acme"}]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_white_label_tenants_db() == []


class TestCustomDomain:
    @pytest.mark.asyncio
    async def test_get_sqlite_found(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "domain": "a.com"})
        with _pg_false(), _patch_conn(conn):
            result = await get_custom_domain_db("t1")
        assert result["domain"] == "a.com"

    @pytest.mark.asyncio
    async def test_get_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_custom_domain_db("t1") is None

    @pytest.mark.asyncio
    async def test_get_pg_found(self):
        pool = FakePool(fetchrow={"tenant_id": "t1", "domain": "a.com"})
        with _pg_true(), _patch_pg(pool):
            assert (await get_custom_domain_db("t1"))["domain"] == "a.com"

    @pytest.mark.asyncio
    async def test_get_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_custom_domain_db("t1") is None

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_custom_domain_db("t1") is None

    @pytest.mark.asyncio
    async def test_set_sqlite(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "domain": "a.com"})
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_platform_ops.get_custom_domain_db",
            new_callable=AsyncMock,
            return_value={"tenant_id": "t1", "domain": "a.com"},
        ):
            result = await set_custom_domain_db("t1", "a.com", "pending")
        assert result["domain"] == "a.com"
        assert "INSERT INTO custom_domains" in conn.last_sql
        assert conn.last_params[3] == "pending"

    @pytest.mark.asyncio
    async def test_set_pg(self):
        pool = FakePool(fetchrow={"tenant_id": "t1", "domain": "a.com"})
        with _pg_true(), _patch_pg(pool), patch(
            "api.services.db_platform_ops.get_custom_domain_db",
            new_callable=AsyncMock,
            return_value={"tenant_id": "t1", "domain": "a.com"},
        ):
            result = await set_custom_domain_db("t1", "a.com")
        assert result["domain"] == "a.com"

    @pytest.mark.asyncio
    async def test_set_pg_no_pool(self):
        with _pg_true(), _patch_pg(None), patch(
            "api.services.db_platform_ops.get_custom_domain_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await set_custom_domain_db("t1", "a.com") is None

    @pytest.mark.asyncio
    async def test_verify_sqlite(self):
        conn = FakeConn(fetchone={"id": "d1", "verified": 1})
        with _pg_false(), _patch_conn(conn):
            result = await verify_domain_db("d1")
        assert result["id"] == "d1"
        assert any(sql.startswith("UPDATE custom_domains") for sql in conn.executed_sqls)

    @pytest.mark.asyncio
    async def test_verify_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await verify_domain_db("d1") is None

    @pytest.mark.asyncio
    async def test_verify_pg(self):
        pool = FakePool(fetchrow={"id": "d1", "verified": True})
        with _pg_true(), _patch_pg(pool):
            result = await verify_domain_db("d1")
        assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_verify_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await verify_domain_db("d1") is None

    @pytest.mark.asyncio
    async def test_verify_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await verify_domain_db("d1") is None


class TestOnboardingProgress:
    @pytest.mark.asyncio
    async def test_get_sqlite_found(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "current_step": "welcome"})
        with _pg_false(), _patch_conn(conn):
            assert (await get_onboarding_progress_db("t1"))["current_step"] == "welcome"

    @pytest.mark.asyncio
    async def test_get_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_onboarding_progress_db("t1") is None

    @pytest.mark.asyncio
    async def test_get_pg_found(self):
        pool = FakePool(fetchrow={"tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            assert (await get_onboarding_progress_db("t1"))["tenant_id"] == "t1"

    @pytest.mark.asyncio
    async def test_get_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_onboarding_progress_db("t1") is None

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_onboarding_progress_db("t1") is None

    @pytest.mark.asyncio
    async def test_create_sqlite(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "current_step": "welcome"})
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_platform_ops.get_onboarding_progress_db",
            new_callable=AsyncMock,
            return_value={"tenant_id": "t1", "current_step": "welcome"},
        ):
            result = await create_onboarding_progress_db("t1")
        assert result["current_step"] == "welcome"
        assert "INSERT INTO onboarding_progress" in conn.last_sql

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool(fetchrow={"tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool), patch(
            "api.services.db_platform_ops.get_onboarding_progress_db",
            new_callable=AsyncMock,
            return_value={"tenant_id": "t1"},
        ):
            result = await create_onboarding_progress_db("t1")
        assert result["tenant_id"] == "t1"

    @pytest.mark.asyncio
    async def test_create_pg_no_pool(self):
        with _pg_true(), _patch_pg(None), patch(
            "api.services.db_platform_ops.get_onboarding_progress_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await create_onboarding_progress_db("t1") is None

    @pytest.mark.asyncio
    async def test_complete_step_creates_when_missing(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "steps_completed_json": "[]"})
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_platform_ops.get_onboarding_progress_db",
            new_callable=AsyncMock,
            side_effect=[
                None,  # first get → missing
                {"tenant_id": "t1", "steps_completed_json": '["welcome"]'},
            ],
        ), patch(
            "api.services.db_platform_ops.create_onboarding_progress_db",
            new_callable=AsyncMock,
            return_value={"tenant_id": "t1", "steps_completed_json": "[]"},
        ):
            result = await complete_onboarding_step_db("t1", "welcome")
        assert "welcome" in result["steps_completed_json"]

    @pytest.mark.asyncio
    async def test_complete_step_appends_new(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "steps_completed_json": "[]"})
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_platform_ops.get_onboarding_progress_db",
            new_callable=AsyncMock,
            side_effect=[
                {"tenant_id": "t1", "steps_completed_json": '["welcome"]'},
                {"tenant_id": "t1", "steps_completed_json": '["welcome", "phone_number"]'},
            ],
        ):
            result = await complete_onboarding_step_db("t1", "phone_number")
        assert '"phone_number"' in result["steps_completed_json"]
        assert "current_step" in conn.last_sql

    @pytest.mark.asyncio
    async def test_complete_step_duplicate_ignored(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "steps_completed_json": "[]"})
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_platform_ops.get_onboarding_progress_db",
            new_callable=AsyncMock,
            side_effect=[
                {"tenant_id": "t1", "steps_completed_json": '["welcome"]'},
                {"tenant_id": "t1", "steps_completed_json": '["welcome"]'},
            ],
        ):
            result = await complete_onboarding_step_db("t1", "welcome")
        assert result["steps_completed_json"].count("welcome") == 1

    @pytest.mark.asyncio
    async def test_complete_step_reaches_done(self):
        import json as _json

        conn = FakeConn(fetchone={"tenant_id": "t1", "steps_completed_json": "[]"})
        all_steps = ["welcome", "phone_number", "quickstart", "health_check"]
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_platform_ops.get_onboarding_progress_db",
            new_callable=AsyncMock,
            side_effect=[
                {"tenant_id": "t1", "steps_completed_json": _json.dumps(all_steps)},
                {
                    "tenant_id": "t1",
                    "steps_completed_json": _json.dumps(all_steps + ["welcome"]),
                },
            ],
        ):
            result = await complete_onboarding_step_db("t1", "welcome")
        assert result["steps_completed_json"] == _json.dumps(all_steps + ["welcome"])

    @pytest.mark.asyncio
    async def test_complete_step_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool), patch(
            "api.services.db_platform_ops.get_onboarding_progress_db",
            new_callable=AsyncMock,
            side_effect=[
                {"tenant_id": "t1", "steps_completed_json": "[]"},
                {"tenant_id": "t1", "steps_completed_json": '["welcome"]'},
            ],
        ):
            result = await complete_onboarding_step_db("t1", "welcome")
        assert "welcome" in result["steps_completed_json"]


class TestTenantConfig:
    @pytest.mark.asyncio
    async def test_get_sqlite_value(self):
        conn = FakeConn(fetchone={"value": "v1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_config_value_db("t1", "k") == "v1"

    @pytest.mark.asyncio
    async def test_get_sqlite_missing(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_config_value_db("t1", "k") is None

    @pytest.mark.asyncio
    async def test_get_pg_value(self):
        pool = FakePool(fetchrow={"value": "v1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_tenant_config_value_db("t1", "k") == "v1"

    @pytest.mark.asyncio
    async def test_get_pg_missing(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_tenant_config_value_db("t1", "k") is None

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_tenant_config_value_db("t1", "k") is None

    @pytest.mark.asyncio
    async def test_set_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await set_tenant_config_value_db("t1", "k", "v")
        assert "INSERT OR REPLACE INTO tenant_config" in conn.last_sql
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_set_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await set_tenant_config_value_db("t1", "k", "v")
        sql, params = pool.executed[0]
        assert "ON CONFLICT" in sql
        assert params == ("t1", "k", "v")

    @pytest.mark.asyncio
    async def test_set_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            await set_tenant_config_value_db("t1", "k", "v")  # no-op
