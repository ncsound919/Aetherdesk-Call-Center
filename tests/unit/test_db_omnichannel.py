"""Unit tests for src/api/services/db_omnichannel.py.

Exercises every public async helper (SMS templates/logs, chat sessions and
messages) against a fake SQLite connection and a fake asyncpg pool, following
the established pattern in test_db_platform_ops.py.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_omnichannel import (
    add_chat_message_db,
    create_chat_session_db,
    create_sms_template_db,
    get_chat_messages_db,
    get_chat_session_db,
    list_sms_log_db,
    list_sms_templates_db,
    list_waiting_sessions_db,
    log_sms_db,
    update_chat_session_db,
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
    return patch(
        "api.services.db_omnichannel._get_sqlite_conn", MagicMock(return_value=conn)
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_omnichannel.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_omnichannel.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_omnichannel.USE_POSTGRES", False)


class TestCreateSmsTemplate:
    @pytest.mark.asyncio
    async def test_pg_returns_row(self):
        pool = FakePool(fetchrow={"id": "s1", "name": "welcome"})
        with _pg_true(), _patch_pg(pool):
            result = await create_sms_template_db("t1", "welcome", "Hi there")
        assert result == {"id": "s1", "name": "welcome"}
        sql, params = pool.executed[0]
        assert "INSERT INTO sms_templates" in sql
        assert params[1:] == ("t1", "welcome", "Hi there")

    @pytest.mark.asyncio
    async def test_pg_returns_none_when_select_empty(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await create_sms_template_db("t1", "w", "b") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_sms_template_db("t1", "w", "b") is None

    @pytest.mark.asyncio
    async def test_sqlite_returns_row(self):
        conn = FakeConn(fetchone={"id": "s1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_sms_template_db("t1", "welcome", "Hi")
        assert result == {"id": "s1"}
        assert conn.executed_params[0][4]  # created_at timestamp
        assert conn.committed is True
        assert conn.closed is True


class TestListSmsTemplates:
    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "s1"}, {"id": "s2"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_sms_templates_db("t1") == [
                {"id": "s1"},
                {"id": "s2"},
            ]
        assert "ORDER BY created_at DESC" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_sms_templates_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "s1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_sms_templates_db("t1") == [{"id": "s1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_sms_templates_db("t1") == []


class TestLogSms:
    @pytest.mark.asyncio
    async def test_pg_defaults(self):
        pool = FakePool(fetchrow={"id": "l1", "direction": "outbound"})
        with _pg_true(), _patch_pg(pool):
            result = await log_sms_db("t1", "+1555", "hello")
        assert result["id"] == "l1"
        sql, params = pool.executed[0]
        assert "INSERT INTO sms_log" in sql
        assert params[1] == "t1"
        assert params[2] == "+1555"
        assert params[3] is None  # from_number default
        assert params[5] == "sent"  # status default
        assert params[6] == "outbound"  # direction default

    @pytest.mark.asyncio
    async def test_pg_all_args(self):
        pool = FakePool(fetchrow={"id": "l1"})
        with _pg_true(), _patch_pg(pool):
            result = await log_sms_db(
                "t1",
                "+1555",
                "hello",
                from_number="+1000",
                status="failed",
                direction="inbound",
                sid="SM1",
            )
        assert result == {"id": "l1"}
        assert pool.executed[0][1][7] == "SM1"

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await log_sms_db("t1", "+1555", "hi") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchone={"id": "l1"})
        with _pg_false(), _patch_conn(conn):
            result = await log_sms_db("t1", "+1555", "hello", sid="SM1")
        assert result == {"id": "l1"}
        assert conn.executed_params[0][7] == "SM1"
        assert conn.committed is True
        assert conn.closed is True


class TestListSmsLog:
    @pytest.mark.asyncio
    async def test_pg_with_pagination(self):
        pool = FakePool(fetch=[{"id": "l1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_sms_log_db("t1", limit=25, offset=10)
        assert result == [{"id": "l1"}]
        sql, params = pool.executed[0]
        assert "LIMIT $2 OFFSET $3" in sql
        assert params == ("t1", 25, 10)

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_sms_log_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "l1"}])
        with _pg_false(), _patch_conn(conn):
            assert await list_sms_log_db("t1") == [{"id": "l1"}]
        assert conn.last_params == ("t1", 100, 0)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_sms_log_db("t1") == []


class TestCreateChatSession:
    @pytest.mark.asyncio
    async def test_pg_returns_row(self):
        pool = FakePool(fetchrow={"id": "s1", "status": "waiting"})
        with _pg_true(), _patch_pg(pool):
            result = await create_chat_session_db(
                "t1", "v1", visitor_name="Bob", visitor_email="b@x.com"
            )
        assert result == {"id": "s1", "status": "waiting"}
        sql, params = pool.executed[0]
        assert "INSERT INTO chat_sessions" in sql
        assert params[2] == "v1"
        assert params[3] == "Bob"
        assert params[4] == "b@x.com"

    @pytest.mark.asyncio
    async def test_pg_returns_none_when_select_empty(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await create_chat_session_db("t1", "v1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_chat_session_db("t1", "v1") is None

    @pytest.mark.asyncio
    async def test_sqlite_returns_row(self):
        conn = FakeConn(fetchone={"id": "s1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_chat_session_db("t1", "v1")
        assert result == {"id": "s1"}
        assert "'waiting'" in conn.executed_sqls[0]
        assert conn.committed is True
        assert conn.closed is True


class TestGetChatSession:
    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "s1", "tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_chat_session_db("s1") == {"id": "s1", "tenant_id": "t1"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_chat_session_db("s1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_chat_session_db("s1") is None

    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "s1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_chat_session_db("s1") == {"id": "s1"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_chat_session_db("s1") is None


class TestListWaitingSessions:
    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(
            fetch=[{"id": "s1", "message_count": 3}, {"id": "s2", "message_count": 0}]
        )
        with _pg_true(), _patch_pg(pool):
            result = await list_waiting_sessions_db("t1")
        assert result == [
            {"id": "s1", "message_count": 3},
            {"id": "s2", "message_count": 0},
        ]
        assert "LEFT JOIN chat_messages" in pool.executed[0][0]
        assert "status = 'waiting'" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_waiting_sessions_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "s1", "message_count": 1}])
        with _pg_false(), _patch_conn(conn):
            assert await list_waiting_sessions_db("t1") == [
                {"id": "s1", "message_count": 1}
            ]
        assert "COUNT(cm.id)" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_waiting_sessions_db("t1") == []


class TestAddChatMessage:
    @pytest.mark.asyncio
    async def test_pg_returns_row(self):
        pool = FakePool(fetchrow={"id": "m1", "content": "hi"})
        with _pg_true(), _patch_pg(pool):
            result = await add_chat_message_db("s1", "visitor", "hi", sender_name="Bob")
        assert result == {"id": "m1", "content": "hi"}
        sql, params = pool.executed[0]
        assert "INSERT INTO chat_messages" in sql
        assert params[2] == "visitor"
        assert params[3] == "Bob"

    @pytest.mark.asyncio
    async def test_pg_returns_none_when_select_empty(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await add_chat_message_db("s1", "agent", "hi") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await add_chat_message_db("s1", "agent", "hi") is None

    @pytest.mark.asyncio
    async def test_sqlite_returns_row(self):
        conn = FakeConn(fetchone={"id": "m1"})
        with _pg_false(), _patch_conn(conn):
            result = await add_chat_message_db("s1", "agent", "hi")
        assert result == {"id": "m1"}
        assert conn.executed_params[0][3] is None  # sender_name default
        assert conn.committed is True
        assert conn.closed is True


class TestGetChatMessages:
    @pytest.mark.asyncio
    async def test_pg_after_id(self):
        pool = FakePool(fetch=[{"id": "m2"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_chat_messages_db("s1", after_id="m1")
        assert result == [{"id": "m2"}]
        assert "id > $2" in pool.executed[0][0]
        assert pool.executed[0][1] == ("s1", "m1")

    @pytest.mark.asyncio
    async def test_pg_no_after_id(self):
        pool = FakePool(fetch=[{"id": "m1"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_chat_messages_db("s1")
        assert result == [{"id": "m1"}]
        assert "id >" not in pool.executed[0][0]
        assert pool.executed[0][1] == ("s1",)

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_chat_messages_db("s1") is None

    @pytest.mark.asyncio
    async def test_sqlite_after_id(self):
        conn = FakeConn(fetchall=[{"id": "m2"}])
        with _pg_false(), _patch_conn(conn):
            result = await get_chat_messages_db("s1", after_id="m1")
        assert result == [{"id": "m2"}]
        assert "id > ?" in conn.last_sql
        assert conn.last_params == ("s1", "m1")
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_after_id(self):
        conn = FakeConn(fetchall=[{"id": "m1"}])
        with _pg_false(), _patch_conn(conn):
            result = await get_chat_messages_db("s1")
        assert result == [{"id": "m1"}]
        assert "id >" not in conn.last_sql


class TestUpdateChatSession:
    @pytest.mark.asyncio
    async def test_no_updates_returns_none(self):
        with _pg_false():
            assert await update_chat_session_db("s1") is None

    @pytest.mark.asyncio
    async def test_only_disallowed_kwargs_returns_none(self):
        with _pg_false(), _patch_conn(FakeConn()) as mc:
            result = await update_chat_session_db("s1", visitor_id="x", name="Bob")
        assert result is None
        mc.assert_not_called()

    @pytest.mark.asyncio
    async def test_pg_with_updates(self):
        pool = FakePool(fetchrow={"id": "s1", "status": "active"})
        with _pg_true(), _patch_pg(pool):
            result = await update_chat_session_db(
                "s1", status="active", agent_id="a1", visitor_name="ignored"
            )
        assert result == {"id": "s1", "status": "active"}
        sql, params = pool.executed[0]
        assert "SET status = $1, agent_id = $2" in sql
        assert "visitor_name" not in sql
        assert "WHERE id = $3" in sql
        assert params == ("active", "a1", "s1")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_chat_session_db("s1", status="active") is None

    @pytest.mark.asyncio
    async def test_sqlite_with_updates(self):
        conn = FakeConn(fetchone={"id": "s1", "status": "closed"})
        with _pg_false(), _patch_conn(conn):
            result = await update_chat_session_db(
                "s1", status="closed", assigned_at="now", closed_at="later"
            )
        assert result == {"id": "s1", "status": "closed"}
        assert "SET status = ?, assigned_at = ?, closed_at = ?" in conn.executed_sqls[0]
        assert conn.executed_params[0] == ["closed", "now", "later", "s1"]
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_none_value_filtered(self):
        conn = FakeConn(fetchone={"id": "s1"})
        with _pg_false(), _patch_conn(conn):
            result = await update_chat_session_db("s1", status="x", assigned_at=None)
        assert result == {"id": "s1"}
        assert "assigned_at" not in conn.last_sql
