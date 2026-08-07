"""Unit tests for src/api/services/db_tenants.py.

Every public async helper (plus the sync ``_parse_skills`` helper) is
exercised against a fake SQLite connection (patching ``_get_sqlite_conn``)
and/or a fake asyncpg pool (patching ``get_pg_pool``), following the
established pattern in test_db_platform_ops.py.

Branch semantics for the "guarded" helpers::

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            ...PG logic...
    else:
        ...SQLite logic...

so the SQLite path runs when USE_POSTGRES is False, the PG path runs when
USE_POSTGRES is True AND a pool is available, and when USE_POSTGRES is True
but the pool is unavailable the function returns its trailing default.

The newer "unguarded" helpers (users / billing / leads / scripts / templates)
call ``pool.acquire()`` directly inside ``if USE_POSTGRES:`` without an
``if pool:`` guard, so no "no-pool" variant exists for them.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_tenants import (
    _parse_skills,
    bulk_delete_leads_db,
    bulk_update_leads_db,
    count_active_agents_db,
    count_active_calls_db,
    create_agent,
    create_agent_profile_db,
    create_lead_db,
    create_script_db,
    create_script_template_db,
    create_tenant,
    create_user_db,
    delete_agent_db,
    delete_lead_db,
    delete_script_db,
    delete_script_template_db,
    get_agent_db,
    get_available_agents,
    get_lead_db,
    get_script_db,
    get_script_template_db,
    get_tenant_by_api_key,
    get_tenant_by_stripe_customer_db,
    get_tenant_db,
    get_tenant_plan_db,
    get_tenant_settings_db,
    get_user_by_email_db,
    get_user_by_id_db,
    list_agents,
    list_leads_db,
    list_script_templates_db,
    list_scripts_db,
    list_tenants_db,
    record_usage_db,
    reset_password_db,
    set_password_reset_token_db,
    update_agent_db,
    update_agent_status,
    update_lead_db,
    update_script_db,
    update_tenant_settings_db,
    update_tenant_subscription_db,
    update_user_onboarding_db,
    verify_tenant_api_key,
    verify_user_email_db,
)


class RowLike:
    """dict-like but NOT a dict (simulates sqlite3.Row)."""

    def __init__(self, mapping):
        self._mapping = mapping

    def keys(self):
        return self._mapping.keys()

    def __getitem__(self, key):
        return self._mapping[key]

    def get(self, key, default=None):
        return self._mapping.get(key, default)


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self.executed_sqls = []

    @property
    def last_sql(self):
        return self._conn.last_sql

    @property
    def last_params(self):
        return self._conn.last_params

    @property
    def rowcount(self):
        return self._conn.rowcount

    def execute(self, sql, params=None):
        self._conn.execute(sql, params)
        self.executed_sqls.append(sql)
        return self

    def fetchone(self):
        return self._conn.fetchone()

    def fetchall(self):
        return self._conn.fetchall()


class FakeConn:
    """Fake sqlite connection.

    ``fetchone`` may be a single row or a LIST of rows consumed in order.
    ``fetchall`` is returned as-is; ``fetchall_seq`` is a list of results
    consumed in order (for functions that fetch multiple result sets).
    """

    def __init__(
        self,
        fetchone=None,
        fetchall=None,
        rowcount=1,
        total_changes=1,
        fetchall_seq=None,
    ):
        self._one = fetchone
        self._all = fetchall
        self._all_seq = fetchall_seq
        self._one_idx = 0
        self._all_idx = 0
        self.rowcount = rowcount
        self.total_changes = total_changes
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

    def cursor(self):
        return FakeCursor(self)

    def fetchone(self):
        if isinstance(self._one, list):
            if self._one_idx < len(self._one):
                val = self._one[self._one_idx]
                self._one_idx += 1
                return val
            return None
        return self._one

    def fetchall(self):
        if self._all_seq is not None:
            if self._all_idx < len(self._all_seq):
                val = self._all_seq[self._all_idx]
                self._all_idx += 1
                return val
            return []
        return self._all if self._all is not None else []

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class _FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Acquire:
    def __init__(self, pool):
        self._pool = pool

    async def __aenter__(self):
        return self._pool

    async def __aexit__(self, *exc):
        return False


class FakePool:
    """Fake asyncpg pool.

    ``fetch`` takes a list of rows (returned directly); ``fetch_seq`` takes a
    list of such lists consumed in order. ``fetchrow`` / ``fetchval`` take a
    single value or a LIST consumed in order. ``execute`` returns the
    configured result string. ``acquire()`` and ``transaction()`` yield the
    pool itself.
    """

    def __init__(
        self, fetchrow=None, fetch=None, fetchval=None, execute="OK", fetch_seq=None
    ):
        self._row = fetchrow
        self._rows = fetch
        self._val = fetchval
        self._exec = execute
        self._rows_seq = fetch_seq
        self._row_idx = 0
        self._val_idx = 0
        self._rows_seq_idx = 0
        self.executed = []  # (sql, params)

    async def fetchrow(self, sql, *params):
        self.executed.append((sql, params))
        if isinstance(self._row, list):
            if self._row_idx < len(self._row):
                val = self._row[self._row_idx]
                self._row_idx += 1
                return val
            return None
        return self._row

    async def fetch(self, sql, *params):
        self.executed.append((sql, params))
        if self._rows_seq is not None:
            if self._rows_seq_idx < len(self._rows_seq):
                val = self._rows_seq[self._rows_seq_idx]
                self._rows_seq_idx += 1
                return val
            return []
        return self._rows if self._rows is not None else []

    async def fetchval(self, sql, *params):
        self.executed.append((sql, params))
        if isinstance(self._val, list):
            if self._val_idx < len(self._val):
                val = self._val[self._val_idx]
                self._val_idx += 1
                return val
            return None
        return self._val

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return self._exec

    def acquire(self):
        return _Acquire(self)

    def transaction(self):
        return _FakeTx()


def _patch_conn(conn):
    return patch(
        "api.services.db_tenants._get_sqlite_conn", MagicMock(return_value=conn)
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_tenants.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_tenants.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_tenants.USE_POSTGRES", False)


class TestCreateTenant:
    @pytest.mark.asyncio
    async def test_sqlite_without_gdpr(self):
        conn = FakeConn(fetchone={"id": "t1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_tenant("Acme", "a@b.com", "acme", plan_id="p1")
        assert result == {"id": "t1"}
        assert "INSERT INTO tenants" in conn.executed_sqls[0]
        assert conn.executed_params[0][8] is None  # gdpr_consented_at
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_gdpr(self):
        conn = FakeConn(fetchone={"id": "t1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_tenant(
                "Acme", "a@b.com", "acme", settings={"k": "v"}, gdpr_consent=True
            )
        assert result == {"id": "t1"}
        assert conn.executed_params[0][6] == '{"k": "v"}'
        assert conn.executed_params[0][8] is not None  # timestamp recorded
        assert conn.executed_params[0][9]  # api key

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "t1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_tenant("Acme", "a@b.com", "acme")
        assert result == {"id": "t1"}
        assert "INSERT INTO tenants" in pool.executed[0][0]
        assert pool.executed[0][1][9]  # api key present
        assert pool.executed[1][0].startswith("SELECT * FROM tenants")

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await create_tenant("Acme", "a@b.com", "acme") is None


class TestGetTenant:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "t1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_db("t1") == {"id": "t1"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "t1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_tenant_db("t1") == {"id": "t1"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_tenant_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_tenant_db("t1") is None


class TestListTenants:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "t1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_tenants_db() == [{"id": "t1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "t1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_tenants_db() == [{"id": "t1"}]

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await list_tenants_db() is None


class TestGetTenantByApiKey:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "t1", "name": "Acme"})
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_by_api_key("k") == {"id": "t1", "name": "Acme"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_by_api_key("k") is None

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "t1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_tenant_by_api_key("k") == {"id": "t1"}

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_tenant_by_api_key("k") is None


class TestVerifyTenantApiKey:
    @pytest.mark.asyncio
    async def test_sqlite_valid(self):
        conn = FakeConn(fetchone={"1": 1})
        with _pg_false(), _patch_conn(conn):
            assert await verify_tenant_api_key("t1", "k") is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_invalid(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await verify_tenant_api_key("t1", "k") is False

    @pytest.mark.asyncio
    async def test_pg_valid(self):
        pool = FakePool(fetchrow={"1": 1})
        with _pg_true(), _patch_pg(pool):
            assert await verify_tenant_api_key("t1", "k") is True

    @pytest.mark.asyncio
    async def test_pg_invalid(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await verify_tenant_api_key("t1", "k") is False

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_false(self):
        with _pg_true(), _patch_pg(None):
            assert await verify_tenant_api_key("t1", "k") is False


class TestCreateAgent:
    @pytest.mark.asyncio
    async def test_sqlite_display_name_defaults_to_name(self):
        conn = FakeConn(fetchone={"id": "a1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_agent("t1", "Alice", None, skills=["billing"])
        assert result == {"id": "a1"}
        assert "INSERT INTO agents" in conn.executed_sqls[0]
        assert conn.executed_params[0][3] == "Alice"
        assert conn.executed_params[0][5] == '["billing"]'
        assert conn.executed_params[0][6] == "{}"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_display_name(self):
        conn = FakeConn(fetchone={"id": "a1"})
        with _pg_false(), _patch_conn(conn):
            await create_agent("t1", "Alice", "Alicia", agent_type="human")
        assert conn.executed_params[0][3] == "Alicia"
        assert conn.executed_params[0][4] == "human"

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "a1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_agent("t1", "Alice", None)
        assert result == {"id": "a1"}
        assert "INSERT INTO agents" in pool.executed[0][0]
        assert pool.executed[0][1][3] == "Alice"

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await create_agent("t1", "Alice", None) is None


class TestGetAgent:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "a1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_agent_db("a1") == {"id": "a1"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_agent_db("a1") is None

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "a1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_agent_db("a1") == {"id": "a1"}

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_agent_db("a1") is None


class TestListAgents:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "a1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_agents("t1") == [{"id": "a1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "a1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_agents("t1") == [{"id": "a1"}]

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await list_agents("t1") is None


class TestUpdateAgentStatus:
    @pytest.mark.asyncio
    async def test_sqlite_logs_activity(self):
        conn = FakeConn(fetchone=[{"tenant_id": "t1", "status": "offline"}])
        with _pg_false(), _patch_conn(conn):
            result = await update_agent_status("a1", "available", session_ref="s1")
        assert result == {"success": True, "agent_id": "a1", "new_status": "available"}
        assert any(
            "INSERT INTO agent_activity" in s for s in conn.executed_sqls
        )
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_agent_row_skips_activity(self):
        conn = FakeConn(fetchone=[None])
        with _pg_false(), _patch_conn(conn):
            result = await update_agent_status("a1", "busy")
        assert result["success"] is True
        assert not any("INSERT INTO agent_activity" in s for s in conn.executed_sqls)

    @pytest.mark.asyncio
    async def test_pg_returns_json(self):
        pool = FakePool(fetchval='{"success": true, "agent_id": "a1"}')
        with _pg_true(), _patch_pg(pool):
            result = await update_agent_status("a1", "available", "s1")
        assert result == {"success": True, "agent_id": "a1"}

    @pytest.mark.asyncio
    async def test_pg_null_result(self):
        pool = FakePool(fetchval=None)
        with _pg_true(), _patch_pg(pool):
            result = await update_agent_status("a1", "available")
        assert result == {"success": False, "error": "function returned null"}

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await update_agent_status("a1", "available") is None


class TestUpdateAgent:
    @pytest.mark.asyncio
    async def test_sqlite_all_fields(self):
        conn = FakeConn(fetchone={"id": "a1"})
        with _pg_false(), _patch_conn(conn):
            result = await update_agent_db(
                "a1",
                "t1",
                name="New",
                display_name="D",
                agent_type="human",
                skills=["s1"],
                config={"k": 1},
            )
        assert result == {"id": "a1"}
        assert conn.executed_sqls[0].startswith("UPDATE agents SET")
        assert "name = ?" in conn.executed_sqls[0]
        assert "config = ?" in conn.executed_sqls[0]
        assert conn.executed_params[0][3] == '["s1"]'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_fields_skips_update(self):
        conn = FakeConn(fetchone={"id": "a1"})
        with _pg_false(), _patch_conn(conn):
            result = await update_agent_db("a1", "t1")
        assert result == {"id": "a1"}
        assert not any(s.startswith("UPDATE agents") for s in conn.executed_sqls)
        assert conn.committed is False

    @pytest.mark.asyncio
    async def test_pg_all_fields(self):
        pool = FakePool(fetchrow={"id": "a1"})
        with _pg_true(), _patch_pg(pool):
            result = await update_agent_db(
                "a1",
                "t1",
                name="New",
                display_name="D",
                agent_type="human",
                skills=["s1"],
                config={"k": 1},
            )
        assert result == {"id": "a1"}
        update_sql, params = pool.executed[0]
        assert update_sql.startswith("UPDATE agents SET")
        assert "name = $1" in update_sql
        assert "skills = $4" in update_sql
        assert params[3] == '["s1"]'

    @pytest.mark.asyncio
    async def test_pg_no_fields_skips_update(self):
        pool = FakePool(fetchrow={"id": "a1"})
        with _pg_true(), _patch_pg(pool):
            result = await update_agent_db("a1", "t1")
        assert result == {"id": "a1"}
        assert len(pool.executed) == 1  # only the SELECT-back fetchrow

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await update_agent_db("a1", "t1") is None


class TestDeleteAgent:
    @pytest.mark.asyncio
    async def test_sqlite_deleted(self):
        conn = FakeConn(total_changes=1)
        with _pg_false(), _patch_conn(conn):
            assert await delete_agent_db("a1", "t1") is True
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_deleted(self):
        conn = FakeConn(total_changes=0)
        with _pg_false(), _patch_conn(conn):
            assert await delete_agent_db("a1", "t1") is False

    @pytest.mark.asyncio
    async def test_pg_deleted(self):
        pool = FakePool(execute="DELETE 1")
        with _pg_true(), _patch_pg(pool):
            assert await delete_agent_db("a1", "t1") is True

    @pytest.mark.asyncio
    async def test_pg_not_deleted(self):
        pool = FakePool(execute="DELETE 0")
        with _pg_true(), _patch_pg(pool):
            assert await delete_agent_db("a1", "t1") is False

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await delete_agent_db("a1", "t1") is None


class TestParseSkills:
    def test_none(self):
        assert _parse_skills(None) == []

    def test_list(self):
        assert _parse_skills(["a", "b"]) == ["a", "b"]

    def test_valid_json_list(self):
        assert _parse_skills('["a", "b"]') == ["a", "b"]

    def test_invalid_json(self):
        assert _parse_skills("not-json") == []

    def test_json_non_list(self):
        assert _parse_skills('{"a": 1}') == []

    def test_other_type(self):
        assert _parse_skills(42) == []


class TestGetAvailableAgents:
    @pytest.mark.asyncio
    async def test_sqlite_no_skills_returns_all(self):
        conn = FakeConn(fetchall=[{"id": "a1"}, {"id": "a2"}])
        with _pg_false(), _patch_conn(conn):
            result = await get_available_agents("t1")
        assert result == [{"id": "a1"}, {"id": "a2"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_filters_by_skill(self):
        conn = FakeConn(
            fetchall=[
                {"id": "a1", "skills": '["billing", "sales"]'},
                {"id": "a2", "skills": '["support"]'},
                {"id": "a3", "skills": None},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_available_agents("t1", skills=["billing"])
        assert [r["id"] for r in result] == ["a1"]

    @pytest.mark.asyncio
    async def test_sqlite_skill_list_in_row(self):
        conn = FakeConn(fetchall=[{"id": "a1", "skills": ["billing"]}])
        with _pg_false(), _patch_conn(conn):
            result = await get_available_agents("t1", skills=["billing"])
        assert [r["id"] for r in result] == ["a1"]

    @pytest.mark.asyncio
    async def test_pg_with_skills(self):
        pool = FakePool(fetch=[{"id": "a1"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_available_agents("t1", skills=["billing"])
        assert result == [{"id": "a1"}]
        assert "skills @> $2" in pool.executed[0][0]
        assert pool.executed[0][1][1] == '["billing"]'

    @pytest.mark.asyncio
    async def test_pg_without_skills(self):
        pool = FakePool(fetch=[{"id": "a1"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_available_agents("t1")
        assert result == [{"id": "a1"}]
        assert "skills @>" not in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_available_agents("t1") is None


class TestCreateAgentProfile:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await create_agent_profile_db("p1", "t1", "Agent", "prompt", {"a": 1})
        assert "INSERT INTO agent_profiles" in conn.last_sql
        assert conn.last_params[4] == '{"a": 1}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await create_agent_profile_db("p1", "t1", "Agent", "prompt", {"a": 1})
        assert "INSERT INTO agent_profiles" in pool.executed[0][0]
        assert pool.executed[0][1][4] == '{"a": 1}'

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            await create_agent_profile_db("p1", "t1", "Agent", "prompt", {"a": 1})


class TestGetTenantSettings:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"tenant_id": "t1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_settings_db("t1") == {"tenant_id": "t1"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_settings_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_tenant_settings_db("t1") == {"tenant_id": "t1"}

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_tenant_settings_db("t1") is None


class TestUpdateTenantSettings:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        settings = {
            "api_feeds": ["feed1"],
            "auto_mode_enabled": 1,
            "redact_pii": 0,
            "require_consent": 0,
            "sync_dnc": 1,
            "mcp_servers": {"srv": {}},
        }
        with _pg_false(), _patch_conn(conn):
            await update_tenant_settings_db("t1", settings)
        assert "ON CONFLICT(tenant_id)" in conn.last_sql
        assert conn.last_params[0] == "t1"
        assert conn.last_params[1] == '["feed1"]'
        assert conn.last_params[4] == 0
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_defaults(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await update_tenant_settings_db("t1", {})
        assert conn.last_params[2] == 0  # auto_mode_enabled default
        assert conn.last_params[3] == 1  # redact_pii default
        assert conn.last_params[6] == '"{}"'  # mcp_servers default

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        settings = {
            "api_feeds": ["feed1"],
            "auto_mode_enabled": 1,
            "redact_pii": 0,
            "require_consent": 1,
            "sync_dnc": 0,
            "mcp_servers": {"srv": {}},
        }
        with _pg_true(), _patch_pg(pool):
            await update_tenant_settings_db("t1", settings)
        assert "ON CONFLICT(tenant_id)" in pool.executed[0][0]
        assert pool.executed[0][1][0] == "t1"

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            await update_tenant_settings_db("t1", {})


class TestGetUserByEmail:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "u1", "email": "a@b.com"})
        with _pg_false(), _patch_conn(conn):
            assert await get_user_by_email_db("a@b.com") == {
                "id": "u1",
                "email": "a@b.com",
            }
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_user_by_email_db("a@b.com") is None

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "u1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_user_by_email_db("a@b.com") == {"id": "u1"}

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_user_by_email_db("a@b.com") is None


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            result = await create_user_db("a@b.com", "hash", "Alice", "t1", "agent")
        assert result["email"] == "a@b.com"
        assert result["verification_token"]
        assert "INSERT INTO users" in conn.last_sql
        assert conn.last_params[4] == "t1"
        assert conn.last_params[5] == "agent"
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            result = await create_user_db("a@b.com", "hash", "Alice")
        assert result["email"] == "a@b.com"
        assert "INSERT INTO users" in pool.executed[0][0]
        assert pool.executed[0][1][4] is None  # default tenant_id
        assert pool.executed[0][1][5] == "owner"


class TestGetUserById:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "u1", "email": "a@b.com"})
        with _pg_false(), _patch_conn(conn):
            result = await get_user_by_id_db("u1")
        assert result == {"id": "u1", "email": "a@b.com"}

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_user_by_id_db("u1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "u1", "email": "a@b.com"})
        with _pg_true(), _patch_pg(pool):
            assert await get_user_by_id_db("u1") == {"id": "u1", "email": "a@b.com"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_user_by_id_db("u1") is None


class TestVerifyUserEmail:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "u1"})
        with _pg_false(), _patch_conn(conn):
            assert await verify_user_email_db("tok") == "u1"
        assert "UPDATE users SET email_verified = 1" in conn.last_sql
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await verify_user_email_db("tok") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "u1"})
        with _pg_true(), _patch_pg(pool):
            assert await verify_user_email_db("tok") == "u1"
        assert "UPDATE users SET email_verified = TRUE" in pool.executed[1][0]

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await verify_user_email_db("tok") is None


class TestSetPasswordResetToken:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "u1"})
        with _pg_false(), _patch_conn(conn):
            user_id, token = await set_password_reset_token_db("a@b.com")
        assert user_id == "u1"
        assert token
        assert "UPDATE users SET reset_token" in conn.last_sql
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await set_password_reset_token_db("a@b.com") == (None, None)

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "u1"})
        with _pg_true(), _patch_pg(pool):
            user_id, token = await set_password_reset_token_db("a@b.com")
        assert user_id == "u1"
        assert token
        assert "UPDATE users SET reset_token = $1" in pool.executed[1][0]

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await set_password_reset_token_db("a@b.com") == (None, None)


class TestResetPassword:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "u1"})
        with _pg_false(), _patch_conn(conn):
            assert await reset_password_db("tok", "newhash") == "u1"
        assert "UPDATE users SET password_hash" in conn.last_sql
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await reset_password_db("tok", "newhash") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "u1"})
        with _pg_true(), _patch_pg(pool):
            assert await reset_password_db("tok", "newhash") == "u1"
        assert "UPDATE users SET password_hash = $1" in pool.executed[1][0]

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await reset_password_db("tok", "newhash") is None


class TestUpdateUserOnboarding:
    @pytest.mark.asyncio
    async def test_sqlite_completed(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await update_user_onboarding_db("u1", 3, completed=True)
        assert conn.last_params[1] == 1
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_completed(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await update_user_onboarding_db("u1", 2)
        assert conn.last_params[1] == 0

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await update_user_onboarding_db("u1", 3, completed=True)
        assert "UPDATE users SET onboarding_step" in pool.executed[0][0]


class TestUpdateTenantSubscription:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await update_tenant_subscription_db(
                "t1", stripe_customer_id="c1", plan_id="p1"
            )
        assert "COALESCE" in conn.last_sql
        assert conn.last_params[0] == "c1"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_all_none(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await update_tenant_subscription_db("t1")
        assert conn.last_params[4] == "t1"

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await update_tenant_subscription_db("t1", plan_ends_at="2026-01-01")
        assert "COALESCE" in pool.executed[0][0]


class TestGetTenantByStripeCustomer:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "t1", "plan_id": "p1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_by_stripe_customer_db("c1") == {
                "id": "t1",
                "plan_id": "p1",
            }
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_tenant_by_stripe_customer_db("c1") is None

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "t1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_tenant_by_stripe_customer_db("c1") == {"id": "t1"}


class TestRecordUsage:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await record_usage_db("t1", "agent_minutes", 5.0, "a", "b")
        assert "INSERT INTO billing_records" in conn.last_sql
        assert conn.last_params[4] == 5.0
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await record_usage_db("t1", "agent_minutes", 5.0, "a", "b")
        assert "INSERT INTO billing_records" in pool.executed[0][0]
        assert pool.executed[0][1][4] == 5.0


class TestGetTenantPlan:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchone={"plan_name": "pro", "max_concurrent_calls": 10})
        with _pg_false(), _patch_conn(conn):
            result = await get_tenant_plan_db("t1")
        assert result["plan_name"] == "pro"
        assert "LEFT JOIN plans" in conn.last_sql

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"plan_name": "pro"})
        with _pg_true(), _patch_pg(pool):
            assert await get_tenant_plan_db("t1") == {"plan_name": "pro"}


class TestCountActiveAgents:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchone={"COUNT(*)": 3})
        with _pg_false(), _patch_conn(conn):
            assert await count_active_agents_db("t1") == 3

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchval=3)
        with _pg_true(), _patch_pg(pool):
            assert await count_active_agents_db("t1") == 3


class TestCountActiveCalls:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchone={"COUNT(*)": 5})
        with _pg_false(), _patch_conn(conn):
            assert await count_active_calls_db("t1") == 5

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchval=5)
        with _pg_true(), _patch_pg(pool):
            assert await count_active_calls_db("t1") == 5


class TestCreateLead:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            result = await create_lead_db(
                "t1", "+1555000", company_name="Acme", custom_fields={"a": 1}
            )
        assert result["id"]
        assert "INSERT INTO leads" in conn.last_sql
        assert conn.last_params[15] == '{"a": 1}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            result = await create_lead_db("t1", "+1555000")
        assert result["id"]
        assert "INSERT INTO leads" in pool.executed[0][0]
        assert pool.executed[0][1][14] == "{}"


class TestGetLead:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "l1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_lead_db("l1", "t1") == {"id": "l1"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_lead_db("l1", "t1") is None

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "l1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_lead_db("l1", "t1") == {"id": "l1"}


class TestListLeads:
    @pytest.mark.asyncio
    async def test_sqlite_no_filters(self):
        conn = FakeConn(fetchall=[{"id": "l1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_leads_db("t1")
        assert result == [{"id": "l1"}]
        assert "AND status" not in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_status_only(self):
        conn = FakeConn(fetchall=[{"id": "l1"}])
        with _pg_false(), _patch_conn(conn):
            await list_leads_db("t1", status="new")
        assert " AND status = ?" in conn.last_sql
        assert " AND industry LIKE ?" not in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_industry_only(self):
        conn = FakeConn(fetchall=[{"id": "l1"}])
        with _pg_false(), _patch_conn(conn):
            await list_leads_db("t1", industry="tech")
        assert " AND industry LIKE ?" in conn.last_sql
        assert conn.last_params[1] == "%tech%"

    @pytest.mark.asyncio
    async def test_sqlite_both_filters(self):
        conn = FakeConn(fetchall=[{"id": "l1"}])
        with _pg_false(), _patch_conn(conn):
            await list_leads_db("t1", status="new", industry="tech")
        assert " AND status = ?" in conn.last_sql
        assert " AND industry LIKE ?" in conn.last_sql

    @pytest.mark.asyncio
    async def test_pg_no_filters(self):
        pool = FakePool(fetch=[{"id": "l1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_leads_db("t1")
        assert result == [{"id": "l1"}]
        assert "status = $2" not in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_both_filters(self):
        pool = FakePool(fetch=[{"id": "l1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_leads_db("t1", status="new", industry="tech", limit=50)
        assert result == [{"id": "l1"}]
        assert "status = $2" in pool.executed[0][0]
        assert "industry ILIKE $3" in pool.executed[0][0]
        assert pool.executed[0][1][1] == "new"
        assert pool.executed[0][1][2] == "%tech%"


class TestUpdateLead:
    @pytest.mark.asyncio
    async def test_no_updates_delegates_to_get(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_tenants.get_lead_db",
            new_callable=AsyncMock,
            return_value={"id": "l1"},
        ):
            result = await update_lead_db("l1", "t1", {})
        assert result == {"id": "l1"}

    @pytest.mark.asyncio
    async def test_sqlite_plain_update(self):
        conn = FakeConn(fetchone=[{"id": "l1", "status": "new"}])
        with _pg_false(), _patch_conn(conn):
            result = await update_lead_db("l1", "t1", {"status": "qualified"})
        assert result == {"id": "l1", "status": "new"}
        assert conn.executed_sqls[0].startswith("UPDATE leads SET")
        assert "status = ?" in conn.executed_sqls[0]
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_custom_fields_merge_existing(self):
        conn = FakeConn(fetchone=[('{"a": 1}',), {"id": "l1"}])
        with _pg_false(), _patch_conn(conn):
            result = await update_lead_db(
                "l1", "t1", {"custom_fields": {"b": 2}}
            )
        assert result == {"id": "l1"}
        assert any("custom_fields = ?" in s for s in conn.executed_sqls)
        assert conn.executed_params[1][0] == '{"a": 1, "b": 2}'

    @pytest.mark.asyncio
    async def test_sqlite_custom_fields_no_existing(self):
        conn = FakeConn(fetchone=[None, {"id": "l1"}])
        with _pg_false(), _patch_conn(conn):
            result = await update_lead_db("l1", "t1", {"custom_fields": {"b": 2}})
        assert result == {"id": "l1"}
        assert conn.executed_params[1][0] == '{"b": 2}'

    @pytest.mark.asyncio
    async def test_sqlite_custom_fields_existing_null(self):
        conn = FakeConn(fetchone=[(None,), {"id": "l1"}])
        with _pg_false(), _patch_conn(conn):
            result = await update_lead_db("l1", "t1", {"custom_fields": {"b": 2}})
        assert result == {"id": "l1"}
        assert conn.executed_params[1][0] == '{"b": 2}'

    @pytest.mark.asyncio
    async def test_pg_with_custom_fields(self):
        pool = FakePool(fetchrow={"id": "l1"})
        with _pg_true(), _patch_pg(pool), patch(
            "api.services.db_tenants.get_lead_db",
            new_callable=AsyncMock,
            return_value={"id": "l1"},
        ):
            result = await update_lead_db(
                "l1", "t1", {"status": "qualified", "custom_fields": {"a": 1}}
            )
        assert result == {"id": "l1"}
        update_sql, params = pool.executed[0]
        assert "custom_fields = $2" in update_sql
        assert params[1] == '{"a": 1}'

    @pytest.mark.asyncio
    async def test_pg_plain_update(self):
        pool = FakePool(fetchrow={"id": "l1"})
        with _pg_true(), _patch_pg(pool), patch(
            "api.services.db_tenants.get_lead_db",
            new_callable=AsyncMock,
            return_value={"id": "l1"},
        ):
            await update_lead_db("l1", "t1", {"status": "qualified"})
        update_sql, params = pool.executed[0]
        assert "status = $1" in update_sql
        assert params[0] == "qualified"


class TestDeleteLead:
    @pytest.mark.asyncio
    async def test_sqlite_deleted(self):
        conn = FakeConn(rowcount=1)
        with _pg_false(), _patch_conn(conn):
            assert await delete_lead_db("l1", "t1") is True
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_deleted(self):
        conn = FakeConn(rowcount=0)
        with _pg_false(), _patch_conn(conn):
            assert await delete_lead_db("l1", "t1") is False

    @pytest.mark.asyncio
    async def test_pg_deleted(self):
        pool = FakePool(execute="DELETE 1")
        with _pg_true(), _patch_pg(pool):
            assert await delete_lead_db("l1", "t1") is True

    @pytest.mark.asyncio
    async def test_pg_not_deleted(self):
        pool = FakePool(execute="DELETE 0")
        with _pg_true(), _patch_pg(pool):
            assert await delete_lead_db("l1", "t1") is False


class TestBulkUpdateLeads:
    @pytest.mark.asyncio
    async def test_empty_ids(self):
        with _pg_false():
            assert await bulk_update_leads_db("t1", [], {"status": "x"}) == 0

    @pytest.mark.asyncio
    async def test_empty_updates(self):
        with _pg_false():
            assert await bulk_update_leads_db("t1", ["l1"], {}) == 0

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchone=[('{"a": 1}',), (None,)])
        with _pg_false(), _patch_conn(conn):
            result = await bulk_update_leads_db(
                "t1", ["l1", "l2"], {"custom_fields": {"b": 2}}
            )
        assert result == 2
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_plain_fields(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            result = await bulk_update_leads_db("t1", ["l1", "l2"], {"status": "x"})
        assert result == 2

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(execute="UPDATE 3")
        with _pg_true(), _patch_pg(pool):
            result = await bulk_update_leads_db(
                "t1", ["l1"], {"status": "qualified"}
            )
        assert result == 3
        assert "id = ANY($" in pool.executed[0][0]


class TestBulkDeleteLeads:
    @pytest.mark.asyncio
    async def test_empty_ids(self):
        with _pg_false():
            assert await bulk_delete_leads_db("t1", []) == 0

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(rowcount=2)
        with _pg_false(), _patch_conn(conn):
            result = await bulk_delete_leads_db("t1", ["l1", "l2"])
        assert result == 2
        assert "DELETE FROM leads WHERE id IN (?, ?)" in conn.last_sql
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(execute="DELETE 2")
        with _pg_true(), _patch_pg(pool):
            result = await bulk_delete_leads_db("t1", ["l1", "l2"])
        assert result == 2
        assert "id = ANY($1)" in pool.executed[0][0]


class TestCreateScript:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            result = await create_script_db(
                "t1", "Script", {"intro": "Hi"}, [{"name": "var1"}]
            )
        assert result["id"]
        assert "INSERT INTO scripts" in conn.last_sql
        assert conn.last_params[3] == '{"intro": "Hi"}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            result = await create_script_db("t1", "Script", {"intro": "Hi"})
        assert result["id"]
        assert "INSERT INTO scripts" in pool.executed[0][0]
        assert pool.executed[0][1][4] == "[]"


class TestGetScript:
    @pytest.mark.asyncio
    async def test_sqlite_parses_json_fields(self):
        conn = FakeConn(
            fetchone={
                "id": "s1",
                "content": '{"intro": "Hi"}',
                "variables": '["v1"]',
            }
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_script_db("s1", "t1")
        assert result["content"] == {"intro": "Hi"}
        assert result["variables"] == ["v1"]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_already_parsed(self):
        conn = FakeConn(
            fetchone={"id": "s1", "content": {"intro": "Hi"}, "variables": ["v1"]}
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_script_db("s1", "t1")
        assert result["content"] == {"intro": "Hi"}

    @pytest.mark.asyncio
    async def test_sqlite_rowlike(self):
        conn = FakeConn(
            fetchone=RowLike(
                {
                    "id": "s1",
                    "content": '{"intro": "Hi"}',
                    "variables": '["v1"]',
                }
            )
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_script_db("s1", "t1")
        assert result["content"] == {"intro": "Hi"}
        assert result["variables"] == ["v1"]

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_script_db("s1", "t1") is None

    @pytest.mark.asyncio
    async def test_sqlite_tuple_row_passthrough(self):
        conn = FakeConn(fetchone=("s1", "content"))
        with _pg_false(), _patch_conn(conn):
            assert await get_script_db("s1", "t1") == ("s1", "content")

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "s1", "content": "{}", "variables": "[]"})
        with _pg_true(), _patch_pg(pool):
            result = await get_script_db("s1", "t1")
        assert result["id"] == "s1"
        assert result["content"] == {}


class TestListScripts:
    @pytest.mark.asyncio
    async def test_sqlite_no_is_active(self):
        conn = FakeConn(fetchall=[{"id": "s1", "content": "{}", "variables": "[]"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_scripts_db("t1")
        assert result == [{"id": "s1", "content": {}, "variables": []}]
        assert "is_active" not in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_is_active_true(self):
        conn = FakeConn(fetchall=[{"id": "s1", "content": "{}", "variables": "[]"}])
        with _pg_false(), _patch_conn(conn):
            await list_scripts_db("t1", is_active=True)
        assert "AND is_active = ?" in conn.last_sql
        assert conn.last_params[1] == 1

    @pytest.mark.asyncio
    async def test_sqlite_is_active_false(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            await list_scripts_db("t1", is_active=False)
        assert conn.last_params[1] == 0

    @pytest.mark.asyncio
    async def test_sqlite_parses_rows(self):
        conn = FakeConn(
            fetchall=[
                {"id": "s1", "content": '{"a":1}', "variables": "[]"},
                RowLike({"id": "s2", "content": '{"b":1}', "variables": '["x"]'}),
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await list_scripts_db("t1")
        assert result[0]["content"] == {"a": 1}
        assert result[1]["content"] == {"b": 1}
        assert result[1]["variables"] == ["x"]

    @pytest.mark.asyncio
    async def test_pg_with_is_active(self):
        pool = FakePool(fetch=[{"id": "s1", "content": "{}", "variables": "[]"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_scripts_db("t1", is_active=True)
        assert result == [{"id": "s1", "content": {}, "variables": []}]
        assert "is_active = $2" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_is_active(self):
        pool = FakePool(fetch=[{"id": "s1", "content": "{}", "variables": "[]"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_scripts_db("t1")
        assert result == [{"id": "s1", "content": {}, "variables": []}]
        assert "is_active" not in pool.executed[0][0]


class TestUpdateScript:
    @pytest.mark.asyncio
    async def test_no_updates_delegates_to_get(self):
        with _pg_false(), patch(
            "api.services.db_tenants.get_script_db",
            new_callable=AsyncMock,
            return_value={"id": "s1"},
        ):
            assert await update_script_db("s1", "t1", {}) == {"id": "s1"}

    @pytest.mark.asyncio
    async def test_sqlite_missing_script_returns_none(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_tenants.get_script_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await update_script_db("s1", "t1", {"name": "New"}) is None
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_updates_and_merges_content(self):
        conn = FakeConn()
        existing = {"id": "s1", "content": {"a": 1}, "variables": ["v1"], "name": "Old"}
        final = {"id": "s1", "content": {"a": 1, "b": 2}, "name": "New"}
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_tenants.get_script_db",
            new_callable=AsyncMock,
            side_effect=[existing, final],
        ):
            result = await update_script_db(
                "s1", "t1", {"name": "New", "content": {"b": 2}}
            )
        assert result == final
        assert conn.executed_sqls[0].startswith("UPDATE scripts SET")
        assert "version = version + 1" in conn.executed_sqls[0]
        assert '{"a": 1, "b": 2}' in conn.executed_params[0]
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_content_as_string(self):
        conn = FakeConn()
        existing = {"id": "s1", "content": '{"a": 1}', "variables": []}
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_tenants.get_script_db",
            new_callable=AsyncMock,
            side_effect=[existing, existing],
        ):
            await update_script_db("s1", "t1", {"content": {"b": 2}})
        assert '{"a": 1, "b": 2}' in conn.executed_params[0]

    @pytest.mark.asyncio
    async def test_sqlite_all_fields(self):
        conn = FakeConn()
        existing = {"id": "s1", "content": {}, "variables": [], "name": "Old", "is_active": True}
        with _pg_false(), _patch_conn(conn), patch(
            "api.services.db_tenants.get_script_db",
            new_callable=AsyncMock,
            side_effect=[existing, existing],
        ):
            await update_script_db(
                "s1",
                "t1",
                {
                    "content": {"x": 1},
                    "variables": ["v"],
                    "name": "New",
                    "is_active": False,
                },
            )
        update_params = conn.executed_params[0]
        assert '{"x": 1}' in update_params
        assert '["v"]' in update_params
        assert "New" in update_params
        assert 0 in update_params

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "s1"})
        with _pg_true(), _patch_pg(pool), patch(
            "api.services.db_tenants.get_script_db",
            new_callable=AsyncMock,
            return_value={"id": "s1"},
        ):
            result = await update_script_db(
                "s1", "t1", {"name": "New", "is_active": True}
            )
        assert result == {"id": "s1"}
        update_sql, params = pool.executed[0]
        assert "name = $1" in update_sql
        assert "is_active = $2" in update_sql
        assert params[0] == "New"
        assert params[1] is True

    @pytest.mark.asyncio
    async def test_pg_content_only(self):
        pool = FakePool(fetchrow={"id": "s1"})
        with _pg_true(), _patch_pg(pool), patch(
            "api.services.db_tenants.get_script_db",
            new_callable=AsyncMock,
            return_value={"id": "s1"},
        ):
            result = await update_script_db("s1", "t1", {"content": {"x": 1}})
        assert result == {"id": "s1"}
        update_sql, params = pool.executed[0]
        assert "content = $1" in update_sql
        assert params[0] == '{"x": 1}'


class TestDeleteScript:
    @pytest.mark.asyncio
    async def test_sqlite_deleted(self):
        conn = FakeConn(rowcount=1)
        with _pg_false(), _patch_conn(conn):
            assert await delete_script_db("s1", "t1") is True
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_deleted(self):
        conn = FakeConn(rowcount=0)
        with _pg_false(), _patch_conn(conn):
            assert await delete_script_db("s1", "t1") is False

    @pytest.mark.asyncio
    async def test_pg_deleted(self):
        pool = FakePool(execute="DELETE 1")
        with _pg_true(), _patch_pg(pool):
            assert await delete_script_db("s1", "t1") is True

    @pytest.mark.asyncio
    async def test_pg_not_deleted(self):
        pool = FakePool(execute="DELETE 0")
        with _pg_true(), _patch_pg(pool):
            assert await delete_script_db("s1", "t1") is False


class TestGetScriptTemplate:
    @pytest.mark.asyncio
    async def test_sqlite_parses_json(self):
        conn = FakeConn(
            fetchone={
                "id": "st1",
                "content": '{"intro": "Hi"}',
                "variables": '["v1"]',
            }
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_script_template_db("st1")
        assert result["content"] == {"intro": "Hi"}
        assert result["variables"] == ["v1"]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_rowlike(self):
        conn = FakeConn(
            fetchone=RowLike(
                {"id": "st1", "content": '{"a":1}', "variables": '["v1"]'}
            )
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_script_template_db("st1")
        assert result["content"] == {"a": 1}

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_script_template_db("st1") is None

    @pytest.mark.asyncio
    async def test_sqlite_tuple_passthrough(self):
        conn = FakeConn(fetchone=("st1", "content"))
        with _pg_false(), _patch_conn(conn):
            assert await get_script_template_db("st1") == ("st1", "content")

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "st1", "content": "{}", "variables": "[]"})
        with _pg_true(), _patch_pg(pool):
            result = await get_script_template_db("st1")
        assert result["content"] == {}


class TestListScriptTemplates:
    @pytest.mark.asyncio
    async def test_sqlite_no_industry(self):
        conn = FakeConn(fetchall=[{"id": "st1", "content": "{}", "variables": "[]"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_script_templates_db()
        assert result == [{"id": "st1", "content": {}, "variables": []}]
        assert "industry" not in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_industry(self):
        conn = FakeConn(
            fetchall=[
                {"id": "st1", "content": '{"a":1}', "variables": "[]"},
                RowLike({"id": "st2", "content": '{"b":1}', "variables": '["v"]'}),
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await list_script_templates_db(industry="tech")
        assert "AND industry LIKE ?" in conn.last_sql
        assert conn.last_params[0] == "%tech%"
        assert result[0]["content"] == {"a": 1}
        assert result[1]["content"] == {"b": 1}

    @pytest.mark.asyncio
    async def test_pg_no_industry(self):
        pool = FakePool(fetch=[{"id": "st1", "content": "{}", "variables": "[]"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_script_templates_db()
        assert result == [{"id": "st1", "content": {}, "variables": []}]
        assert "industry" not in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_with_industry(self):
        pool = FakePool(fetch=[{"id": "st1", "content": "{}", "variables": "[]"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_script_templates_db(industry="tech")
        assert result == [{"id": "st1", "content": {}, "variables": []}]
        assert "industry ILIKE $1" in pool.executed[0][0]
        assert pool.executed[0][1][0] == "%tech%"


class TestCreateScriptTemplate:
    @pytest.mark.asyncio
    async def test_sqlite_public(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            result = await create_script_template_db(
                "T", "desc", "tech", {"a": 1}, [{"v": 1}], is_public=True
            )
        assert result["id"]
        assert "INSERT INTO script_templates" in conn.last_sql
        assert conn.last_params[6] == 1
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_private(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await create_script_template_db(
                "T", "desc", "tech", {"a": 1}, [], is_public=False
            )
        assert conn.last_params[6] == 0

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            result = await create_script_template_db(
                "T", "desc", "tech", {"a": 1}, [], is_public=False
            )
        assert result["id"]
        assert "INSERT INTO script_templates" in pool.executed[0][0]
        assert pool.executed[0][1][6] is False


class TestDeleteScriptTemplate:
    @pytest.mark.asyncio
    async def test_sqlite_deleted(self):
        conn = FakeConn(rowcount=1)
        with _pg_false(), _patch_conn(conn):
            assert await delete_script_template_db("st1") is True
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_deleted(self):
        conn = FakeConn(rowcount=0)
        with _pg_false(), _patch_conn(conn):
            assert await delete_script_template_db("st1") is False

    @pytest.mark.asyncio
    async def test_pg_deleted(self):
        pool = FakePool(execute="DELETE 1")
        with _pg_true(), _patch_pg(pool):
            assert await delete_script_template_db("st1") is True

    @pytest.mark.asyncio
    async def test_pg_not_deleted(self):
        pool = FakePool(execute="DELETE 0")
        with _pg_true(), _patch_pg(pool):
            assert await delete_script_template_db("st1") is False
