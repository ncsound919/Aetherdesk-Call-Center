"""Unit tests for src/api/services/db_bc.py (business continuity).

Exercises every public async helper (failover tests, chaos experiments,
vendor contracts, backup channels) against a fake SQLite connection and a
fake asyncpg pool, following the established pattern in test_db_platform_ops.py.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_bc import (
    create_backup_channel_db,
    create_chaos_experiment_db,
    create_contract_db,
    create_failover_test_db,
    get_contract_alerts_db,
    list_backup_channels_db,
    list_chaos_experiments_db,
    list_contracts_db,
    list_failover_tests_db,
    update_backup_channel_test_db,
    update_chaos_experiment_db,
)


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    @property
    def lastrowid(self):
        return self._conn.lastrowid

    @property
    def rowcount(self):
        return self._conn.rowcount

    def execute(self, sql, params=None):
        self._conn.execute(sql, params)
        return self

    def fetchone(self):
        return self._conn.fetchone()

    def fetchall(self):
        return self._conn.fetchall()


class FakeConn:
    def __init__(self, fetchone=None, fetchall=None, rowcount=1, lastrowid=1):
        self._one = fetchone
        self._all = fetchall
        self.rowcount = rowcount
        self.lastrowid = lastrowid
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
        return FakeCursor(self)

    def cursor(self):
        return FakeCursor(self)

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all if self._all is not None else []

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class FakePool:
    def __init__(self, fetchrow=None, fetch=None, execute="OK"):
        self._row = fetchrow
        self._rows = fetch
        self._exec = execute
        self.executed = []

    async def fetchrow(self, sql, *params):
        self.executed.append((sql, params))
        return self._row

    async def fetch(self, sql, *params):
        self.executed.append((sql, params))
        return self._rows if self._rows is not None else []

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return self._exec


def _patch_conn(conn):
    return patch("api.services.db_bc._get_sqlite_conn", MagicMock(return_value=conn))


def _patch_pg(pool):
    return patch(
        "api.services.db_bc.get_pg_pool", new_callable=AsyncMock, return_value=pool
    )


def _pg_true():
    return patch("api.services.db_bc.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_bc.USE_POSTGRES", False)


class TestCreateFailoverTest:
    @pytest.mark.asyncio
    async def test_pg_with_dict_result(self):
        pool = FakePool(fetchrow={"id": "f1", "status": "passed"})
        with _pg_true(), _patch_pg(pool):
            result = await create_failover_test_db(
                "t1", "voice", {"status": "passed", "detail": "ok"}, 12.5, "ops"
            )
        assert result == {"id": "f1", "status": "passed"}
        sql, params = pool.executed[0]
        assert "INSERT INTO failover_tests" in sql
        assert params[3] == "passed"
        assert params[4] == '{"status": "passed", "detail": "ok"}'
        assert params[5] == 12.5

    @pytest.mark.asyncio
    async def test_pg_result_without_status_defaults_unknown(self):
        pool = FakePool(fetchrow={"id": "f1"})
        with _pg_true(), _patch_pg(pool):
            await create_failover_test_db("t1", "voice", {"a": 1}, 1.0, "ops")
        assert pool.executed[0][1][3] == "unknown"

    @pytest.mark.asyncio
    async def test_pg_returns_none_when_select_empty(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert (
                await create_failover_test_db(
                    "t1", "voice", {"status": "x"}, 1.0, "ops"
                )
                is None
            )

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_failover_test_db(
                    "t1", "voice", {"status": "x"}, 1.0, "ops"
                )
                is None
            )

    @pytest.mark.asyncio
    async def test_sqlite_with_dict_result(self):
        conn = FakeConn(fetchone={"id": "f1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_failover_test_db(
                "t1", "voice", {"status": "failed"}, 2.0, "ops"
            )
        assert result == {"id": "f1"}
        assert conn.executed_params[0][3] == "failed"
        assert conn.executed_params[0][4] == '{"status": "failed"}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_result_without_status_defaults_unknown(self):
        conn = FakeConn(fetchone={"id": "f1"})
        with _pg_false(), _patch_conn(conn):
            await create_failover_test_db("t1", "voice", {"a": 1}, 1.0, "ops")
        assert conn.executed_params[0][3] == "unknown"


class TestListFailoverTests:
    @pytest.mark.asyncio
    async def test_pg_with_limit(self):
        pool = FakePool(fetch=[{"id": "f1"}, {"id": "f2"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_failover_tests_db("t1", limit=5)
        assert result == [{"id": "f1"}, {"id": "f2"}]
        sql, params = pool.executed[0]
        assert "LIMIT $2" in sql
        assert params == ("t1", 5)

    @pytest.mark.asyncio
    async def test_pg_default_limit(self):
        pool = FakePool(fetch=[])
        with _pg_true(), _patch_pg(pool):
            await list_failover_tests_db("t1")
        assert pool.executed[0][1] == ("t1", 50)

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_failover_tests_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "f1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_failover_tests_db("t1") == [{"id": "f1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_failover_tests_db("t1") == []


class TestCreateChaosExperiment:
    @pytest.mark.asyncio
    async def test_pg_returns_row(self):
        pool = FakePool(fetchrow={"id": "e1", "status": "running"})
        with _pg_true(), _patch_pg(pool):
            result = await create_chaos_experiment_db("t1", "pg-primary", "kill", 30)
        assert result == {"id": "e1", "status": "running"}
        sql, params = pool.executed[0]
        assert "INSERT INTO chaos_experiments" in sql
        assert params[1:] == ("t1", "pg-primary", "kill", 30)

    @pytest.mark.asyncio
    async def test_pg_returns_none_when_select_empty(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await create_chaos_experiment_db("t1", "t", "f", 1) is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_chaos_experiment_db("t1", "t", "f", 1) is None

    @pytest.mark.asyncio
    async def test_sqlite_returns_row(self):
        conn = FakeConn(fetchone={"id": "e1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_chaos_experiment_db("t1", "t", "f", 10)
        assert result == {"id": "e1"}
        assert "'running'" in conn.executed_sqls[0]
        assert conn.committed is True
        assert conn.closed is True


class TestUpdateChaosExperiment:
    @pytest.mark.asyncio
    async def test_pg_with_dict_result(self):
        pool = FakePool(fetchrow={"id": "e1", "result_json": "{}"})
        with _pg_true(), _patch_pg(pool):
            result = await update_chaos_experiment_db(
                "e1", "completed", {"observations": ["x"]}
            )
        assert result == {"id": "e1", "result_json": "{}"}
        sql, params = pool.executed[0]
        assert "UPDATE chaos_experiments SET status = $1, result_json = $2::jsonb" in sql
        assert params == ("completed", '{"observations": ["x"]}', "e1")

    @pytest.mark.asyncio
    async def test_pg_with_string_result(self):
        pool = FakePool(fetchrow={"id": "e1"})
        with _pg_true(), _patch_pg(pool):
            await update_chaos_experiment_db("e1", "failed", "boom")
        assert pool.executed[0][1][1] == "boom"

    @pytest.mark.asyncio
    async def test_pg_returns_none_when_select_empty(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await update_chaos_experiment_db("e1", "x", {}) is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_chaos_experiment_db("e1", "x", {}) is None

    @pytest.mark.asyncio
    async def test_sqlite_with_dict_result(self):
        conn = FakeConn(fetchone={"id": "e1"})
        with _pg_false(), _patch_conn(conn):
            result = await update_chaos_experiment_db(
                "e1", "completed", {"notes": "ok"}
            )
        assert result == {"id": "e1"}
        assert conn.executed_params[0] == (
            "completed",
            '{"notes": "ok"}',
            "e1",
        )
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_string_result(self):
        conn = FakeConn(fetchone={"id": "e1"})
        with _pg_false(), _patch_conn(conn):
            await update_chaos_experiment_db("e1", "failed", "boom")
        assert conn.executed_params[0][1] == "boom"


class TestListChaosExperiments:
    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "e1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_chaos_experiments_db("t1") == [{"id": "e1"}]
        assert "LIMIT $2" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_chaos_experiments_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "e1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_chaos_experiments_db("t1") == [{"id": "e1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_chaos_experiments_db("t1") == []


class TestCreateContract:
    @pytest.mark.asyncio
    async def test_pg_with_cost(self):
        pool = FakePool(fetchrow={"id": "c1", "status": "active"})
        with _pg_true(), _patch_pg(pool):
            result = await create_contract_db(
                "t1", "Twilio", "terms...", "2027-01-01", cost=100.0
            )
        assert result == {"id": "c1", "status": "active"}
        sql, params = pool.executed[0]
        assert "INSERT INTO vendor_contracts" in sql
        assert params[1:] == ("t1", "Twilio", "terms...", "2027-01-01", 100.0)

    @pytest.mark.asyncio
    async def test_pg_without_cost(self):
        pool = FakePool(fetchrow={"id": "c1"})
        with _pg_true(), _patch_pg(pool):
            await create_contract_db("t1", "Twilio", "terms", "2027-01-01")
        assert pool.executed[0][1][5] is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_contract_db("t1", "V", "T", "2027-01-01") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchone={"id": "c1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_contract_db("t1", "V", "T", "2027-01-01")
        assert result == {"id": "c1"}
        assert conn.executed_params[0][5] is None  # cost
        assert conn.committed is True
        assert conn.closed is True


class TestListContracts:
    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "c1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_contracts_db("t1") == [{"id": "c1"}]
        assert "ORDER BY renewal_date ASC" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_contracts_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "c1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_contracts_db("t1") == [{"id": "c1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_contracts_db("t1") == []


class TestGetContractAlerts:
    @pytest.mark.asyncio
    async def test_pg_default_days(self):
        pool = FakePool(fetch=[{"id": "c1"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_contract_alerts_db("t1")
        assert result == [{"id": "c1"}]
        sql, params = pool.executed[0]
        assert "status = 'active'" in sql
        assert "INTERVAL '30 days'" in sql
        assert params == ("t1",)

    @pytest.mark.asyncio
    async def test_pg_custom_days(self):
        pool = FakePool(fetch=[{"id": "c1"}])
        with _pg_true(), _patch_pg(pool):
            await get_contract_alerts_db("t1", days_ahead=7)
        assert "INTERVAL '7 days'" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_contract_alerts_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "c1"}])
        with _pg_false(), _patch_conn(conn):
            result = await get_contract_alerts_db("t1", days_ahead=14)
        assert result == [{"id": "c1"}]
        assert "+14 days" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await get_contract_alerts_db("t1") == []


class TestCreateBackupChannel:
    @pytest.mark.asyncio
    async def test_pg_with_dict_config(self):
        pool = FakePool(fetchrow={"id": "b1", "status": "active"})
        with _pg_true(), _patch_pg(pool):
            result = await create_backup_channel_db(
                "t1", "s3", {"bucket": "x", "region": "us"}
            )
        assert result == {"id": "b1", "status": "active"}
        sql, params = pool.executed[0]
        assert "INSERT INTO backup_channels" in sql
        assert params[1:] == (
            "t1",
            "s3",
            '{"bucket": "x", "region": "us"}',
        )

    @pytest.mark.asyncio
    async def test_pg_with_string_config(self):
        pool = FakePool(fetchrow={"id": "b1"})
        with _pg_true(), _patch_pg(pool):
            await create_backup_channel_db("t1", "s3", "raw-config")
        assert pool.executed[0][1][3] == "raw-config"

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_backup_channel_db("t1", "s3", {}) is None

    @pytest.mark.asyncio
    async def test_sqlite_with_dict_config(self):
        conn = FakeConn(fetchone={"id": "b1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_backup_channel_db("t1", "s3", {"bucket": "x"})
        assert result == {"id": "b1"}
        assert conn.executed_params[0][3] == '{"bucket": "x"}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_string_config(self):
        conn = FakeConn(fetchone={"id": "b1"})
        with _pg_false(), _patch_conn(conn):
            await create_backup_channel_db("t1", "s3", "raw-config")
        assert conn.executed_params[0][3] == "raw-config"


class TestListBackupChannels:
    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "b1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_backup_channels_db("t1") == [{"id": "b1"}]
        assert "ORDER BY created_at DESC" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_backup_channels_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "b1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_backup_channels_db("t1") == [{"id": "b1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_backup_channels_db("t1") == []


class TestUpdateBackupChannelTest:
    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            assert await update_backup_channel_test_db("b1", "passed") is None
        sql, params = pool.executed[0]
        assert "last_test_at = NOW()" in sql
        assert params == ("passed", "b1")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_backup_channel_test_db("b1", "passed") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            assert await update_backup_channel_test_db("b1", "passed") is None
        assert conn.last_params[0]  # timestamp
        assert conn.last_params[1] == "passed"
        assert conn.committed is True
        assert conn.closed is True
