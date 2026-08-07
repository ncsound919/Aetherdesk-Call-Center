"""Unit tests for src/api/services/db_developer.py.

Every public async helper (API key management, webhook configs, webhook
delivery logs) is exercised against a fake SQLite connection (patching
``_get_sqlite_conn``) and/or a fake asyncpg pool (patching ``get_pg_pool``),
following the established pattern in test_db_platform_ops.py.

Branch semantics::

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            ...PG logic...
    else:
        ...SQLite logic...

For the fetch-returning helpers the PG "no pool" path returns None implicitly;
for the DELETE/UPDATE helpers that ``return "UPDATE" in result`` the trailing
``return False`` is exercised when the pool is unavailable.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_developer import (
    create_api_key_db,
    create_webhook_delivery_log_db,
    get_active_webhooks_for_event_db,
    get_api_key_by_id_db,
    get_api_key_by_prefix_db,
    get_webhook_by_id_db,
    get_webhook_delivery_log_by_id_db,
    get_webhook_delivery_logs_db,
    list_api_keys_db,
    list_webhooks_db,
    register_webhook_db,
    revoke_api_key_db,
    unregister_webhook_db,
    update_api_key_last_used_db,
    update_webhook_delivery_log_db,
)


class FakeCursor:
    """Cursor-like returned by FakeConn.execute / FakeConn.cursor."""

    def __init__(self, conn):
        self._conn = conn

    @property
    def lastrowid(self):
        return self._conn.lastrowid

    @property
    def rowcount(self):
        return self._conn.rowcount

    @property
    def last_sql(self):
        return self._conn.last_sql

    @property
    def last_params(self):
        return self._conn.last_params

    def execute(self, sql, params=None):
        self._conn.execute(sql, params)
        return self

    def fetchone(self):
        return self._conn.fetchone()

    def fetchall(self):
        return self._conn.fetchall()


class FakeConn:
    """Fake sqlite connection supporting execute/cursor/commit/close."""

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
    """Fake asyncpg pool."""

    def __init__(self, fetchrow=None, fetch=None, execute="OK"):
        self._row = fetchrow
        self._rows = fetch
        self._exec = execute
        self.executed = []  # (sql, params)

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
    return patch(
        "api.services.db_developer._get_sqlite_conn", MagicMock(return_value=conn)
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_developer.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_developer.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_developer.USE_POSTGRES", False)


class TestCreateApiKey:
    @pytest.mark.asyncio
    async def test_pg_returns_row(self):
        pool = FakePool(
            fetchrow={
                "id": "k1",
                "tenant_id": "t1",
                "name": "dev",
                "key_prefix": "ak_",
                "scopes_json": '["read"]',
                "expires_at": "2027-01-01",
            }
        )
        with _pg_true(), _patch_pg(pool):
            result = await create_api_key_db(
                "t1", "dev", "ak_", "hash", ["read", "write"], "2027-01-01"
            )
        assert result["id"] == "k1"
        sql, params = pool.executed[0]
        assert "INSERT INTO api_keys" in sql
        assert params[4] == '["read", "write"]'
        assert "RETURNING id" in sql

    @pytest.mark.asyncio
    async def test_pg_returns_none_when_insert_empty(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert (
                await create_api_key_db("t1", "dev", "ak_", "h", ["r"], None)
                is None
            )

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_api_key_db("t1", "dev", "ak_", "h", ["r"], None)
                is None
            )

    @pytest.mark.asyncio
    async def test_sqlite_returns_row(self):
        conn = FakeConn(fetchone={"id": "k1", "tenant_id": "t1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_api_key_db(
                "t1", "dev", "ak_", "hash", ["read"], "2027-01-01"
            )
        assert result == {"id": "k1", "tenant_id": "t1"}
        assert "INSERT INTO api_keys" in conn.executed_sqls[0]
        assert conn.executed_params[0][4] == '["read"]'
        assert conn.executed_sqls[1].startswith("SELECT * FROM api_keys")
        assert conn.executed_params[1] == (conn.lastrowid,)
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_returns_none_when_select_empty(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert (
                await create_api_key_db("t1", "dev", "ak_", "h", [], None) is None
            )


class TestGetApiKeyByPrefix:
    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "k1", "key_prefix": "ak_"})
        with _pg_true(), _patch_pg(pool):
            assert (await get_api_key_by_prefix_db("ak_"))["id"] == "k1"

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_api_key_by_prefix_db("ak_") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_api_key_by_prefix_db("ak_") is None

    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "k1"})
        with _pg_false(), _patch_conn(conn):
            assert (await get_api_key_by_prefix_db("ak_"))["id"] == "k1"
        assert "key_prefix = ?" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_api_key_by_prefix_db("ak_") is None


class TestRevokeApiKey:
    @pytest.mark.asyncio
    async def test_pg_revoked(self):
        pool = FakePool(execute="UPDATE 1")
        with _pg_true(), _patch_pg(pool):
            assert await revoke_api_key_db("t1", "k1") is True
        assert "SET is_active = FALSE" in pool.executed[0][0]
        assert pool.executed[0][1] == ("k1", "t1")

    @pytest.mark.asyncio
    async def test_pg_not_revoked(self):
        pool = FakePool(execute="DELETE 0")
        with _pg_true(), _patch_pg(pool):
            assert await revoke_api_key_db("t1", "k1") is False

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_false(self):
        with _pg_true(), _patch_pg(None):
            assert await revoke_api_key_db("t1", "k1") is False

    @pytest.mark.asyncio
    async def test_sqlite_revoked(self):
        conn = FakeConn(rowcount=1)
        with _pg_false(), _patch_conn(conn):
            assert await revoke_api_key_db("t1", "k1") is True
        assert "SET is_active = 0" in conn.last_sql
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_revoked(self):
        conn = FakeConn(rowcount=0)
        with _pg_false(), _patch_conn(conn):
            assert await revoke_api_key_db("t1", "k1") is False


class TestListApiKeys:
    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[{"id": "k1"}, {"id": "k2"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_api_keys_db("t1")
        assert result == [{"id": "k1"}, {"id": "k2"}]
        assert "ORDER BY created_at DESC" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_api_keys_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[{"id": "k1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_api_keys_db("t1") == [{"id": "k1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_api_keys_db("t1") == []


class TestUpdateApiKeyLastUsed:
    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            assert await update_api_key_last_used_db("k1") is None
        assert "last_used_at = NOW()" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_api_key_last_used_db("k1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            assert await update_api_key_last_used_db("k1") is None
        assert "CURRENT_TIMESTAMP" in conn.last_sql
        assert conn.committed is True
        assert conn.closed is True


class TestGetApiKeyById:
    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "k1", "tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_api_key_by_id_db("t1", "k1") == {
                "id": "k1",
                "tenant_id": "t1",
            }

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_api_key_by_id_db("t1", "k1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_api_key_by_id_db("t1", "k1") is None

    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "k1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_api_key_by_id_db("t1", "k1") == {"id": "k1"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_api_key_by_id_db("t1", "k1") is None


class TestRegisterWebhook:
    @pytest.mark.asyncio
    async def test_pg_returns_row(self):
        pool = FakePool(fetchrow={"id": "w1", "url": "https://x"})
        with _pg_true(), _patch_pg(pool):
            result = await register_webhook_db("t1", "https://x", ["call"], "sec")
        assert result["id"] == "w1"
        sql, params = pool.executed[0]
        assert "INSERT INTO webhook_configs" in sql
        assert params[2] == '["call"]'

    @pytest.mark.asyncio
    async def test_pg_returns_none_when_insert_empty(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await register_webhook_db("t1", "u", ["e"], "s") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await register_webhook_db("t1", "u", ["e"], "s") is None

    @pytest.mark.asyncio
    async def test_sqlite_returns_row(self):
        conn = FakeConn(fetchone={"id": "w1"})
        with _pg_false(), _patch_conn(conn):
            result = await register_webhook_db("t1", "https://x", ["call"], "sec")
        assert result == {"id": "w1"}
        assert conn.executed_params[0][2] == '["call"]'
        assert conn.committed is True
        assert conn.closed is True


class TestUnregisterWebhook:
    @pytest.mark.asyncio
    async def test_pg_deleted(self):
        pool = FakePool(execute="DELETE 1")
        with _pg_true(), _patch_pg(pool):
            assert await unregister_webhook_db("t1", "w1") is True

    @pytest.mark.asyncio
    async def test_pg_not_deleted(self):
        pool = FakePool(execute="UPDATE 0")
        with _pg_true(), _patch_pg(pool):
            assert await unregister_webhook_db("t1", "w1") is False

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_false(self):
        with _pg_true(), _patch_pg(None):
            assert await unregister_webhook_db("t1", "w1") is False

    @pytest.mark.asyncio
    async def test_sqlite_deleted(self):
        conn = FakeConn(rowcount=1)
        with _pg_false(), _patch_conn(conn):
            assert await unregister_webhook_db("t1", "w1") is True
        assert "DELETE FROM webhook_configs" in conn.last_sql
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_deleted(self):
        conn = FakeConn(rowcount=0)
        with _pg_false(), _patch_conn(conn):
            assert await unregister_webhook_db("t1", "w1") is False


class TestListWebhooks:
    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "w1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_webhooks_db("t1") == [{"id": "w1"}]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_webhooks_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "w1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_webhooks_db("t1") == [{"id": "w1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_webhooks_db("t1") == []


class TestGetWebhookById:
    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "w1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_webhook_by_id_db("t1", "w1") == {"id": "w1"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_webhook_by_id_db("t1", "w1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_webhook_by_id_db("t1", "w1") is None

    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "w1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_webhook_by_id_db("t1", "w1") == {"id": "w1"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_webhook_by_id_db("t1", "w1") is None


class TestGetActiveWebhooksForEvent:
    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "w1", "events_json": '["call.completed"]'}])
        with _pg_true(), _patch_pg(pool):
            result = await get_active_webhooks_for_event_db("t1", "call.completed")
        assert result == [{"id": "w1", "events_json": '["call.completed"]'}]
        assert "events_json::jsonb ? $2" in pool.executed[0][0]
        assert pool.executed[0][1] == ("t1", "call.completed")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_active_webhooks_for_event_db("t1", "e") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "w1"}])
        with _pg_false(), _patch_conn(conn):
            result = await get_active_webhooks_for_event_db("t1", "call.completed")
        assert result == [{"id": "w1"}]
        assert "events_json LIKE ?" in conn.last_sql
        assert conn.last_params[1] == '%"call.completed"%'
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await get_active_webhooks_for_event_db("t1", "e") == []


class TestCreateWebhookDeliveryLog:
    @pytest.mark.asyncio
    async def test_pg_returns_row(self):
        pool = FakePool(fetchrow={"id": "l1", "event_type": "call.completed"})
        with _pg_true(), _patch_pg(pool):
            result = await create_webhook_delivery_log_db(
                "t1", "w1", "call.completed", '{"a": 1}'
            )
        assert result["id"] == "l1"
        sql, params = pool.executed[0]
        assert "INSERT INTO webhook_delivery_logs" in sql
        assert params == ("t1", "w1", "call.completed", '{"a": 1}')

    @pytest.mark.asyncio
    async def test_pg_returns_none_when_insert_empty(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert (
                await create_webhook_delivery_log_db("t1", "w1", "e", None) is None
            )

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_webhook_delivery_log_db("t1", "w1", "e", None) is None

    @pytest.mark.asyncio
    async def test_sqlite_returns_row(self):
        conn = FakeConn(fetchone={"id": "l1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_webhook_delivery_log_db(
                "t1", "w1", "e", '{"a": 1}'
            )
        assert result == {"id": "l1"}
        assert conn.committed is True
        assert conn.closed is True


class TestUpdateWebhookDeliveryLog:
    @pytest.mark.asyncio
    async def test_pg_all_fields(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            result = await update_webhook_delivery_log_db(
                "l1",
                "delivered",
                response_status=200,
                response_body="ok",
                error_message="err",
                retry_count=3,
            )
        assert result is None
        sql, params = pool.executed[0]
        assert "SET status = $1" in sql
        assert "response_status = $2" in sql
        assert "response_body = $3" in sql
        assert "error_message = $4" in sql
        assert "retry_count = $5" in sql
        assert "WHERE id = $6" in sql
        assert params == ("delivered", 200, "ok", "err", 3, "l1")

    @pytest.mark.asyncio
    async def test_pg_status_only(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await update_webhook_delivery_log_db("l1", "pending")
        sql, params = pool.executed[0]
        assert "SET status = $1" in sql
        assert "response_status" not in sql
        assert "WHERE id = $2" in sql
        assert params == ("pending", "l1")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_webhook_delivery_log_db("l1", "pending") is None

    @pytest.mark.asyncio
    async def test_sqlite_all_fields(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await update_webhook_delivery_log_db(
                "l1",
                "delivered",
                response_status=200,
                error_message=None,
                retry_count=2,
            )
        assert "SET status = ?" in conn.last_sql
        assert "response_status = ?" in conn.last_sql
        assert "retry_count = ?" in conn.last_sql
        assert "error_message" not in conn.last_sql
        assert conn.last_params[-1] == "l1"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_status_only(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await update_webhook_delivery_log_db("l1", "failed")
        assert "SET status = ? WHERE id = ?" in conn.last_sql
        assert conn.last_params == ["failed", "l1"]


class TestGetWebhookDeliveryLogs:
    @pytest.mark.asyncio
    async def test_pg_with_limit(self):
        pool = FakePool(fetch=[{"id": "l1"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_webhook_delivery_logs_db("t1", "w1", limit=10)
        assert result == [{"id": "l1"}]
        sql, params = pool.executed[0]
        assert "LIMIT $3" in sql
        assert params == ("t1", "w1", 10)

    @pytest.mark.asyncio
    async def test_pg_default_limit(self):
        pool = FakePool(fetch=[{"id": "l1"}])
        with _pg_true(), _patch_pg(pool):
            await get_webhook_delivery_logs_db("t1", "w1")
        assert pool.executed[0][1] == ("t1", "w1", 50)

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_webhook_delivery_logs_db("t1", "w1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "l1"}])
        with _pg_false(), _patch_conn(conn):
            assert await get_webhook_delivery_logs_db("t1", "w1") == [{"id": "l1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await get_webhook_delivery_logs_db("t1", "w1") == []


class TestGetWebhookDeliveryLogById:
    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "l1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_webhook_delivery_log_by_id_db("l1") == {"id": "l1"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_webhook_delivery_log_by_id_db("l1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_webhook_delivery_log_by_id_db("l1") is None

    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "l1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_webhook_delivery_log_by_id_db("l1") == {"id": "l1"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_webhook_delivery_log_by_id_db("l1") is None
