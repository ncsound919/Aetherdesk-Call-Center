"""Unit tests for src/api/services/db_reliability.py.

Every public async helper is exercised against a fake SQLite connection
(patching ``_get_sqlite_conn``) and/or a fake asyncpg pool (patching
``get_pg_pool``), following the established pattern in test_db_platform_ops.py.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_reliability import (
    create_dr_test_db,
    get_dr_test_db,
    get_rate_limit_config_db,
    list_circuit_breaker_events_db,
    list_dr_tests_db,
    list_rate_limit_configs_db,
    log_circuit_breaker_event_db,
    set_rate_limit_config_db,
)


class FakeConn:
    """Fake sqlite connection.

    ``fetchone`` may be a single row or a LIST of rows consumed in order
    (used by set_rate_limit_config_db which fetches twice).
    """

    def __init__(self, fetchone=None, fetchall=None, rowcount=1):
        self._one = fetchone
        self._all = fetchall
        self._one_idx = 0
        self.rowcount = rowcount
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
        if isinstance(self._one, list):
            if self._one_idx < len(self._one):
                val = self._one[self._one_idx]
                self._one_idx += 1
                return val
            return None
        return self._one

    def fetchall(self):
        return self._all if self._all is not None else []

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
        self.executed.append((sql, params))
        return self._row

    async def fetch(self, sql, *params):
        self.executed.append((sql, params))
        return self._rows

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return "OK"


def _patch_conn(conn):
    return patch(
        "api.services.db_reliability._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_reliability.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_reliability.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_reliability.USE_POSTGRES", False)


class TestDRTests:
    @pytest.mark.asyncio
    async def test_create_sqlite(self):
        conn = FakeConn(fetchone={"id": "dr1", "tenant_id": "t1", "status": "passed"})
        with _pg_false(), _patch_conn(conn):
            result = await create_dr_test_db(
                "t1", "restore", "passed", {"steps": 3}, 12.5
            )
        assert result == {"id": "dr1", "tenant_id": "t1", "status": "passed"}
        assert "INSERT INTO dr_tests" in conn.executed_sqls[0]
        assert conn.executed_params[0][4] == '{"steps": 3}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_non_dict_result(self):
        conn = FakeConn(fetchone={"id": "dr1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_dr_test_db("t1", "restore", "failed", "raw", 1)
        assert result == {"id": "dr1"}
        assert conn.executed_params[0][4] == "{}"

    @pytest.mark.asyncio
    async def test_create_sqlite_no_row_returns_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_dr_test_db("t1", "restore", "passed", {}, 1) is None

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool(fetchrow={"id": "dr1", "tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_dr_test_db("t1", "restore", "passed", {"a": 1}, 5)
        assert result == {"id": "dr1", "tenant_id": "t1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO dr_tests" in sql
        assert params[4] == '{"a": 1}'

    @pytest.mark.asyncio
    async def test_create_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await create_dr_test_db("t1", "restore", "passed", {}, 1) is None

    @pytest.mark.asyncio
    async def test_list_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "dr1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_dr_tests_db("t1") == [{"id": "dr1"}]
        assert "ORDER BY tested_at DESC" in conn.last_sql
        assert conn.last_params == ("t1",)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_list_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_dr_tests_db("t1") == []

    @pytest.mark.asyncio
    async def test_list_pg(self):
        pool = FakePool(fetch=[{"id": "dr1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_dr_tests_db("t1") == [{"id": "dr1"}]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_dr_tests_db("t1") is None

    @pytest.mark.asyncio
    async def test_get_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "dr1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_dr_test_db("dr1") == {"id": "dr1"}
        assert conn.last_params == ("dr1",)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_get_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_dr_test_db("dr1") is None

    @pytest.mark.asyncio
    async def test_get_pg_found(self):
        pool = FakePool(fetchrow={"id": "dr1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_dr_test_db("dr1") == {"id": "dr1"}

    @pytest.mark.asyncio
    async def test_get_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_dr_test_db("dr1") is None

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_dr_test_db("dr1") is None


class TestRateLimitConfigs:
    @pytest.mark.asyncio
    async def test_get_sqlite_found(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "route_key": "api", "max_requests": 10})
        with _pg_false(), _patch_conn(conn):
            result = await get_rate_limit_config_db("t1", "api")
        assert result["max_requests"] == 10
        assert conn.last_params == ("t1", "api")
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_get_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_rate_limit_config_db("t1", "api") is None

    @pytest.mark.asyncio
    async def test_get_pg_found(self):
        pool = FakePool(fetchrow={"tenant_id": "t1", "route_key": "api"})
        with _pg_true(), _patch_pg(pool):
            assert await get_rate_limit_config_db("t1", "api") == {
                "tenant_id": "t1",
                "route_key": "api",
            }

    @pytest.mark.asyncio
    async def test_get_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_rate_limit_config_db("t1", "api") is None

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_rate_limit_config_db("t1", "api") is None

    @pytest.mark.asyncio
    async def test_set_sqlite_existing_updates(self):
        conn = FakeConn(
            fetchone=[{"id": "cfg1"}, {"id": "cfg1", "tenant_id": "t1", "max_requests": 20}]
        )
        with _pg_false(), _patch_conn(conn):
            result = await set_rate_limit_config_db("t1", "api", 20, 60)
        assert result == {"id": "cfg1", "tenant_id": "t1", "max_requests": 20}
        assert conn.executed_sqls[1].startswith("UPDATE rate_limit_configs")
        assert conn.executed_params[1] == (20, 60, conn.executed_params[1][2], "cfg1")
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_set_sqlite_insert_when_missing(self):
        conn = FakeConn(fetchone=[None, {"id": "cfg-uuid", "tenant_id": "t1"}])
        with _pg_false(), _patch_conn(conn):
            result = await set_rate_limit_config_db("t1", "api", 10, 60)
        assert result == {"id": "cfg-uuid", "tenant_id": "t1"}
        assert conn.executed_sqls[1].startswith("INSERT INTO rate_limit_configs")
        assert conn.executed_params[1][1] == "t1"
        assert conn.executed_params[1][2] == "api"
        assert conn.executed_params[1][3] == 10
        assert conn.executed_params[1][4] == 60

    @pytest.mark.asyncio
    async def test_set_pg(self):
        pool = FakePool(fetchrow={"id": "cfg1", "tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            result = await set_rate_limit_config_db("t1", "api", 10, 60)
        assert result == {"id": "cfg1", "tenant_id": "t1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO rate_limit_configs" in sql
        assert "ON CONFLICT (tenant_id, route_key)" in sql
        assert params[1] == "t1"
        assert params[2] == "api"

    @pytest.mark.asyncio
    async def test_set_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await set_rate_limit_config_db("t1", "api", 10, 60) is None

    @pytest.mark.asyncio
    async def test_list_sqlite_all(self):
        conn = FakeConn(fetchall=[{"id": "cfg1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_rate_limit_configs_db()
        assert result == [{"id": "cfg1"}]
        assert "WHERE tenant_id" not in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_list_sqlite_by_tenant(self):
        conn = FakeConn(fetchall=[{"id": "cfg1"}])
        with _pg_false(), _patch_conn(conn):
            await list_rate_limit_configs_db(tenant_id="t1")
        assert "WHERE tenant_id = ?" in conn.last_sql
        assert conn.last_params == ("t1",)

    @pytest.mark.asyncio
    async def test_list_pg_all(self):
        pool = FakePool(fetch=[{"id": "cfg1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_rate_limit_configs_db() == [{"id": "cfg1"}]

    @pytest.mark.asyncio
    async def test_list_pg_by_tenant(self):
        pool = FakePool(fetch=[{"id": "cfg1"}])
        with _pg_true(), _patch_pg(pool):
            await list_rate_limit_configs_db(tenant_id="t1")
        assert "WHERE tenant_id = $1" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_rate_limit_configs_db() is None


class TestCircuitBreakerEvents:
    @pytest.mark.asyncio
    async def test_log_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await log_circuit_breaker_event_db("llm", "closed", "open", 5)
        assert "INSERT INTO circuit_breaker_events" in conn.last_sql
        assert conn.last_params[1] == "llm"
        assert conn.last_params[2] == "closed"
        assert conn.last_params[3] == "open"
        assert conn.last_params[4] == 5
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_log_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await log_circuit_breaker_event_db("llm", "closed", "open", 5)
        sql, params = pool.executed[0]
        assert "INSERT INTO circuit_breaker_events" in sql
        assert params[1] == "llm"

    @pytest.mark.asyncio
    async def test_log_pg_no_pool_noop(self):
        with _pg_true(), _patch_pg(None):
            await log_circuit_breaker_event_db("llm", "closed", "open", 5)

    @pytest.mark.asyncio
    async def test_list_sqlite_all(self):
        conn = FakeConn(fetchall=[{"id": "e1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_circuit_breaker_events_db(limit=50)
        assert result == [{"id": "e1"}]
        assert "WHERE breaker_name" not in conn.last_sql
        assert conn.last_params == (50,)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_list_sqlite_by_breaker(self):
        conn = FakeConn(fetchall=[{"id": "e1"}])
        with _pg_false(), _patch_conn(conn):
            await list_circuit_breaker_events_db(breaker_name="llm", limit=10)
        assert "WHERE breaker_name = ?" in conn.last_sql
        assert conn.last_params == ("llm", 10)

    @pytest.mark.asyncio
    async def test_list_pg_all(self):
        pool = FakePool(fetch=[{"id": "e1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_circuit_breaker_events_db() == [{"id": "e1"}]

    @pytest.mark.asyncio
    async def test_list_pg_by_breaker(self):
        pool = FakePool(fetch=[{"id": "e1"}])
        with _pg_true(), _patch_pg(pool):
            await list_circuit_breaker_events_db(breaker_name="llm")
        assert "WHERE breaker_name = $1" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_circuit_breaker_events_db() is None
