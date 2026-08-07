"""Unit tests for src/api/services/db_enterprise.py.

Every public async helper is exercised against a fake SQLite connection
(patching ``_get_sqlite_conn``) and/or a fake asyncpg pool (patching
``get_pg_pool``), following the established pattern in test_db_platform_ops.py.

Branch semantics::

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            ...PG logic...
    else:
        ...SQLite logic...

so the SQLite path runs when USE_POSTGRES is False, the PG path runs when
USE_POSTGRES is True AND a pool is available, and when USE_POSTGRES is True
but the pool is unavailable the function returns its trailing default
(``None`` for creates/gets, ``[]`` for list-with-pool-guard, ``False`` for
update).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_enterprise import (
    create_api_version_db,
    create_conversation_quality_score_db,
    create_customer_portal_session_db,
    create_failover_test_db,
    get_api_versions_db,
    get_customer_portal_session_db,
    list_conversation_quality_scores_db,
    list_failover_tests_db,
    update_api_version_status_db,
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
        "api.services.db_enterprise._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_enterprise.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_enterprise.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_enterprise.USE_POSTGRES", False)


class TestFailoverTests:
    @pytest.mark.asyncio
    async def test_create_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            test_id = await create_failover_test_db(
                "t1", "telephony", "twilio", "telnyx", True, 123, True
            )
        assert isinstance(test_id, str) and test_id
        assert "INSERT INTO failover_tests" in conn.last_sql
        assert conn.last_params[1] == "t1"
        assert conn.last_params[5] is True
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            test_id = await create_failover_test_db(
                "t1", "telephony", "twilio", "telnyx", True, 123, True
            )
        assert isinstance(test_id, str) and test_id
        assert "INSERT INTO failover_tests" in pool.executed[0][0]
        assert pool.executed[0][1][1] == "t1"

    @pytest.mark.asyncio
    async def test_create_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_failover_test_db("t1", "x", "a", "b", True, 1, True)
                is None
            )

    @pytest.mark.asyncio
    async def test_list_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "f1", "tenant_id": "t1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_failover_tests_db("t1", limit=10)
        assert result == [{"id": "f1", "tenant_id": "t1"}]
        assert conn.last_params == ("t1", 10)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_list_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_failover_tests_db("t1") == []

    @pytest.mark.asyncio
    async def test_list_pg(self):
        pool = FakePool(fetch=[{"id": "f1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_failover_tests_db("t1") == [{"id": "f1"}]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_failover_tests_db("t1") is None


class TestConversationQualityScores:
    @pytest.mark.asyncio
    async def test_create_sqlite_with_dict_criteria(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            score_id = await create_conversation_quality_score_db(
                "t1", "a1", "c1", "h1", "rubric", 95, {"clarity": 90}
            )
        assert isinstance(score_id, str) and score_id
        assert "INSERT INTO conversation_quality_scores" in conn.last_sql
        assert conn.last_params[7] == '{"clarity": 90}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_non_dict_criteria(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            score_id = await create_conversation_quality_score_db(
                "t1", "a1", "c1", "h1", "rubric", 95, "raw"
            )
        assert isinstance(score_id, str)
        assert conn.last_params[7] == "{}"

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            score_id = await create_conversation_quality_score_db(
                "t1", "a1", "c1", "h1", "rubric", 95, {"clarity": 90}
            )
        assert isinstance(score_id, str) and score_id
        sql, params = pool.executed[0]
        assert "INSERT INTO conversation_quality_scores" in sql
        assert params[0] == score_id
        assert params[7] == '{"clarity": 90}'

    @pytest.mark.asyncio
    async def test_create_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_conversation_quality_score_db(
                    "t1", "a1", "c1", "h1", "r", 5, {}
                )
                is None
            )

    @pytest.mark.asyncio
    async def test_list_sqlite_all(self):
        conn = FakeConn(fetchall=[{"id": "s1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_conversation_quality_scores_db("t1")
        assert result == [{"id": "s1"}]
        assert "AND agent_id" not in conn.last_sql
        assert conn.last_params == ("t1", 100)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_list_sqlite_by_agent(self):
        conn = FakeConn(fetchall=[{"id": "s1"}])
        with _pg_false(), _patch_conn(conn):
            await list_conversation_quality_scores_db("t1", agent_id="a1", limit=5)
        assert "AND agent_id = ?" in conn.last_sql
        assert conn.last_params == ("t1", "a1", 5)

    @pytest.mark.asyncio
    async def test_list_pg_all(self):
        pool = FakePool(fetch=[{"id": "s1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_conversation_quality_scores_db("t1") == [{"id": "s1"}]

    @pytest.mark.asyncio
    async def test_list_pg_by_agent(self):
        pool = FakePool(fetch=[{"id": "s1"}])
        with _pg_true(), _patch_pg(pool):
            await list_conversation_quality_scores_db("t1", agent_id="a1")
        assert "AND agent_id = $2" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_conversation_quality_scores_db("t1") is None


class TestAPIVersions:
    @pytest.mark.asyncio
    async def test_create_sqlite_defaults(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            version_id = await create_api_version_db("v2", "beta", "2026-01-01")
        assert isinstance(version_id, str) and version_id
        assert "INSERT INTO api_versions" in conn.last_sql
        assert conn.last_params[4] is None  # sunset_date default
        assert conn.last_params[6] is None  # migration_notes default
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_all_fields(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await create_api_version_db(
                "v2", "beta", "2026-01-01", "2027-01-01", "chg", "mig"
            )
        assert conn.last_params == (
            conn.last_params[0], "v2", "beta", "2026-01-01", "2027-01-01", "chg", "mig"
        )

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            version_id = await create_api_version_db("v2", "beta", "2026-01-01")
        assert isinstance(version_id, str)
        assert "INSERT INTO api_versions" in pool.executed[0][0]
        assert pool.executed[0][1][1] == "v2"

    @pytest.mark.asyncio
    async def test_create_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await create_api_version_db("v2", "beta", "2026-01-01") is None

    @pytest.mark.asyncio
    async def test_get_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "v1"}])
        with _pg_false(), _patch_conn(conn):
            assert await get_api_versions_db() == [{"id": "v1"}]
        assert "ORDER BY release_date DESC" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_get_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await get_api_versions_db() == []

    @pytest.mark.asyncio
    async def test_get_pg(self):
        pool = FakePool(fetch=[{"id": "v1"}])
        with _pg_true(), _patch_pg(pool):
            assert await get_api_versions_db() == [{"id": "v1"}]

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_api_versions_db() is None

    @pytest.mark.asyncio
    async def test_update_sqlite_without_sunset(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            assert await update_api_version_status_db("v2", "deprecated") is True
        assert conn.last_params == ("deprecated", "v2")
        assert "sunset_date" not in conn.last_sql
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_update_sqlite_with_sunset(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            assert await update_api_version_status_db("v2", "deprecated", "2027-01-01") is True
        assert conn.last_params == ("deprecated", "2027-01-01", "v2")

    @pytest.mark.asyncio
    async def test_update_pg_without_sunset(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            assert await update_api_version_status_db("v2", "deprecated") is True
        sql, params = pool.executed[0]
        assert "sunset_date" not in sql
        assert params == ("deprecated", "v2")

    @pytest.mark.asyncio
    async def test_update_pg_with_sunset(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            assert (
                await update_api_version_status_db("v2", "deprecated", "2027-01-01")
                is True
            )
        sql, params = pool.executed[0]
        assert "sunset_date = $2" in sql
        assert params == ("deprecated", "2027-01-01", "v2")

    @pytest.mark.asyncio
    async def test_update_pg_no_pool_returns_false(self):
        with _pg_true(), _patch_pg(None):
            assert await update_api_version_status_db("v2", "deprecated") is False


class TestCustomerPortalSessions:
    @pytest.mark.asyncio
    async def test_create_sqlite_dict_data(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            session_id = await create_customer_portal_session_db(
                "t1", "c1", {"theme": "dark"}
            )
        assert isinstance(session_id, str) and session_id
        assert "INSERT INTO customer_portal_sessions" in conn.last_sql
        assert conn.last_params[3] == '{"theme": "dark"}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_non_dict_data(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            session_id = await create_customer_portal_session_db("t1", "c1", "raw")
        assert isinstance(session_id, str)
        assert conn.last_params[3] == "{}"

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            session_id = await create_customer_portal_session_db(
                "t1", "c1", {"theme": "dark"}
            )
        assert isinstance(session_id, str)
        sql, params = pool.executed[0]
        assert "INSERT INTO customer_portal_sessions" in sql
        assert params[3] == '{"theme": "dark"}'

    @pytest.mark.asyncio
    async def test_create_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_customer_portal_session_db("t1", "c1", {}) is None
            )

    @pytest.mark.asyncio
    async def test_get_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "s1", "tenant_id": "t1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_customer_portal_session_db("s1") == {
                "id": "s1",
                "tenant_id": "t1",
            }
        assert conn.last_params == ("s1",)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_get_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_customer_portal_session_db("s1") is None

    @pytest.mark.asyncio
    async def test_get_pg_found(self):
        pool = FakePool(fetchrow={"id": "s1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_customer_portal_session_db("s1") == {"id": "s1"}

    @pytest.mark.asyncio
    async def test_get_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_customer_portal_session_db("s1") is None

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_customer_portal_session_db("s1") is None
