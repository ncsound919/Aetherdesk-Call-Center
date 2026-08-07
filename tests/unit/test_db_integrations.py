"""Unit tests for src/api/services/db_integrations.py.

Every public async helper is exercised against a fake SQLite connection
(patching ``_get_sqlite_conn``) and/or a fake asyncpg pool (patching
``get_pg_pool``), following the established pattern in test_db_platform_ops.py.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_integrations import (
    create_integration_config_db,
    create_ticket_sync_log_db,
    get_integration_config_db,
    list_integration_configs_db,
    list_ticket_sync_logs_db,
    update_integration_config_db,
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
        "api.services.db_integrations._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_integrations.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_integrations.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_integrations.USE_POSTGRES", False)


class TestIntegrationConfigs:
    @pytest.mark.asyncio
    async def test_create_sqlite_dict_config(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "provider": "twilio"})
        with _pg_false(), _patch_conn(conn):
            result = await create_integration_config_db(
                "t1", "twilio", "telephony", {"sid": "abc"}
            )
        assert result == {"tenant_id": "t1", "provider": "twilio"}
        assert "INSERT INTO integration_configs" in conn.executed_sqls[0]
        assert conn.executed_params[0][3] == '{"sid": "abc"}'
        assert conn.executed_params[0][4] == "active"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_str_config_and_custom_status(self):
        conn = FakeConn(fetchone={"tenant_id": "t1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_integration_config_db(
                "t1", "twilio", "telephony", "raw-json", status="inactive"
            )
        assert result == {"tenant_id": "t1"}
        assert conn.executed_params[0][3] == "raw-json"
        assert conn.executed_params[0][4] == "inactive"

    @pytest.mark.asyncio
    async def test_create_sqlite_no_row_returns_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert (
                await create_integration_config_db(
                    "t1", "twilio", "telephony", {"a": 1}
                )
                is None
            )

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool(fetchrow={"tenant_id": "t1", "provider": "twilio"})
        with _pg_true(), _patch_pg(pool):
            result = await create_integration_config_db(
                "t1", "twilio", "telephony", {"sid": "abc"}
            )
        assert result == {"tenant_id": "t1", "provider": "twilio"}
        sql, params = pool.executed[0]
        assert "INSERT INTO integration_configs" in sql
        assert params[3] == '{"sid": "abc"}'

    @pytest.mark.asyncio
    async def test_create_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_integration_config_db("t1", "twilio", "telephony", {})
                is None
            )

    @pytest.mark.asyncio
    async def test_list_sqlite_all(self):
        conn = FakeConn(fetchall=[{"tenant_id": "t1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_integration_configs_db("t1")
        assert result == [{"tenant_id": "t1"}]
        assert "integration_type" not in conn.last_sql
        assert conn.last_params == ("t1",)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_list_sqlite_filtered(self):
        conn = FakeConn(fetchall=[{"tenant_id": "t1"}])
        with _pg_false(), _patch_conn(conn):
            await list_integration_configs_db("t1", integration_type="telephony")
        assert "integration_type = ?" in conn.last_sql
        assert conn.last_params == ("t1", "telephony")

    @pytest.mark.asyncio
    async def test_list_pg_all(self):
        pool = FakePool(fetch=[{"tenant_id": "t1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_integration_configs_db("t1") == [{"tenant_id": "t1"}]

    @pytest.mark.asyncio
    async def test_list_pg_filtered(self):
        pool = FakePool(fetch=[{"tenant_id": "t1"}])
        with _pg_true(), _patch_pg(pool):
            await list_integration_configs_db("t1", integration_type="telephony")
        assert "integration_type = $2" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_integration_configs_db("t1") is None

    @pytest.mark.asyncio
    async def test_get_sqlite_found(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "provider": "twilio"})
        with _pg_false(), _patch_conn(conn):
            assert await get_integration_config_db("t1", "twilio") == {
                "tenant_id": "t1",
                "provider": "twilio",
            }
        assert conn.last_params == ("t1", "twilio")
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_get_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_integration_config_db("t1", "twilio") is None

    @pytest.mark.asyncio
    async def test_get_pg_found(self):
        pool = FakePool(fetchrow={"tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_integration_config_db("t1", "twilio") == {
                "tenant_id": "t1"
            }

    @pytest.mark.asyncio
    async def test_get_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_integration_config_db("t1", "twilio") is None

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_integration_config_db("t1", "twilio") is None


class TestUpdateIntegrationConfig:
    @pytest.mark.asyncio
    async def test_empty_updates_returns_none_no_conn(self):
        conn = MagicMock()
        with _pg_false(), _patch_conn(conn):
            assert await update_integration_config_db("t1", "twilio") is None
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_sqlite_all_fields(self):
        conn = FakeConn(fetchone={"tenant_id": "t1", "provider": "twilio"})
        with _pg_false(), _patch_conn(conn):
            result = await update_integration_config_db(
                "t1",
                "twilio",
                config_json={"a": 1},
                status="inactive",
                last_sync_at="2026-01-01T00:00:00",
                error_message="boom",
            )
        assert result == {"tenant_id": "t1", "provider": "twilio"}
        update_sql = conn.executed_sqls[0]
        assert update_sql.startswith("UPDATE integration_configs SET")
        assert "config_json = ?" in update_sql
        assert "status = ?" in update_sql
        assert "last_sync_at = ?" in update_sql
        assert "error_message = ?" in update_sql
        assert "updated_at = ?" in update_sql
        params = conn.executed_params[0]
        assert params[0] == '{"a": 1}'
        assert params[1] == "inactive"
        assert params[2] == "2026-01-01T00:00:00"
        assert params[3] == "boom"
        assert params[5] == "t1"
        assert params[6] == "twilio"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_status_only(self):
        conn = FakeConn(fetchone={"tenant_id": "t1"})
        with _pg_false(), _patch_conn(conn):
            result = await update_integration_config_db(
                "t1", "twilio", status="active"
            )
        assert result == {"tenant_id": "t1"}
        update_sql = conn.executed_sqls[0]
        assert "config_json" not in update_sql
        assert "last_sync_at" not in update_sql
        assert "error_message" not in update_sql

    @pytest.mark.asyncio
    async def test_pg_all_fields(self):
        pool = FakePool(fetchrow={"tenant_id": "t1", "provider": "twilio"})
        with _pg_true(), _patch_pg(pool):
            result = await update_integration_config_db(
                "t1",
                "twilio",
                config_json={"a": 1},
                status="inactive",
                last_sync_at="2026-01-01T00:00:00",
                error_message="boom",
            )
        assert result == {"tenant_id": "t1", "provider": "twilio"}
        update_sql, params = pool.executed[0]
        assert update_sql.startswith("UPDATE integration_configs SET")
        assert "config_json = $1::jsonb" in update_sql
        assert "status = $2" in update_sql
        assert "last_sync_at = $3" in update_sql
        assert "error_message = $4" in update_sql
        assert params == ('{"a": 1}', "inactive", "2026-01-01T00:00:00", "boom", "t1", "twilio")

    @pytest.mark.asyncio
    async def test_pg_status_only(self):
        pool = FakePool(fetchrow={"tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            result = await update_integration_config_db(
                "t1", "twilio", status="active"
            )
        assert result == {"tenant_id": "t1"}
        update_sql, params = pool.executed[0]
        assert "config_json" not in update_sql
        assert params == ("active", "t1", "twilio")

    @pytest.mark.asyncio
    async def test_pg_not_found_returns_none(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await update_integration_config_db(
                "t1", "twilio", status="active"
            ) is None

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await update_integration_config_db("t1", "twilio", status="active")
                is None
            )


class TestTicketSyncLogs:
    @pytest.mark.asyncio
    async def test_create_sqlite_dict_payloads(self):
        conn = FakeConn(fetchone={"id": "log1", "tenant_id": "t1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_ticket_sync_log_db(
                "t1",
                "tick1",
                call_id="c1",
                direction="inbound",
                status="failed",
                payload_json={"a": 1},
                response_json={"b": 2},
                error_message="err",
            )
        assert result == {"id": "log1", "tenant_id": "t1"}
        insert_sql = conn.executed_sqls[0]
        assert "INSERT INTO ticket_sync_log" in insert_sql
        params = conn.executed_params[0]
        assert params[6] == '{"a": 1}'
        assert params[7] == '{"b": 2}'
        assert params[8] == "err"
        assert params[4] == "inbound"
        assert params[5] == "failed"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_defaults_and_empty_payloads(self):
        conn = FakeConn(fetchone={"id": "log1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_ticket_sync_log_db("t1", "tick1")
        assert result == {"id": "log1"}
        params = conn.executed_params[0]
        assert params[3] is None  # call_id
        assert params[4] == "outbound"  # direction default
        assert params[5] == "success"  # status default
        assert params[6] == "{}"  # payload default
        assert params[7] == "{}"  # response default

    @pytest.mark.asyncio
    async def test_create_sqlite_str_payloads(self):
        conn = FakeConn(fetchone={"id": "log1"})
        with _pg_false(), _patch_conn(conn):
            await create_ticket_sync_log_db(
                "t1", "tick1", payload_json="raw", response_json="raw2"
            )
        params = conn.executed_params[0]
        assert params[6] == "raw"
        assert params[7] == "raw2"

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool(fetchrow={"id": "log1", "tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_ticket_sync_log_db(
                "t1", "tick1", payload_json={"a": 1}, response_json={"b": 2}
            )
        assert result == {"id": "log1", "tenant_id": "t1"}
        insert_sql, params = pool.executed[0]
        assert "INSERT INTO ticket_sync_log" in insert_sql
        assert params[6] == '{"a": 1}'
        assert params[7] == '{"b": 2}'

    @pytest.mark.asyncio
    async def test_create_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await create_ticket_sync_log_db("t1", "tick1") is None

    @pytest.mark.asyncio
    async def test_list_sqlite_all(self):
        conn = FakeConn(fetchall=[{"id": "log1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_ticket_sync_logs_db("t1", limit=10, offset=5)
        assert result == [{"id": "log1"}]
        assert "AND status" not in conn.last_sql
        assert conn.last_params == ("t1", 10, 5)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_list_sqlite_filtered(self):
        conn = FakeConn(fetchall=[{"id": "log1"}])
        with _pg_false(), _patch_conn(conn):
            await list_ticket_sync_logs_db("t1", limit=10, offset=0, status="failed")
        assert "AND status = ?" in conn.last_sql
        assert conn.last_params == ("t1", "failed", 10, 0)

    @pytest.mark.asyncio
    async def test_list_pg_all(self):
        pool = FakePool(fetch=[{"id": "log1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_ticket_sync_logs_db("t1") == [{"id": "log1"}]

    @pytest.mark.asyncio
    async def test_list_pg_filtered(self):
        pool = FakePool(fetch=[{"id": "log1"}])
        with _pg_true(), _patch_pg(pool):
            await list_ticket_sync_logs_db("t1", status="failed")
        assert "AND status = $2" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_ticket_sync_logs_db("t1") is None
