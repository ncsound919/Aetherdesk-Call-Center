"""Unit tests for src/api/services/db_calls.py.

Every public async helper is exercised against a fake SQLite connection
(patching ``_get_sqlite_conn``) and/or a fake asyncpg pool (patching
``get_pg_pool``), following the established pattern in test_db_platform_ops.py.

Branch semantics (identical across all ``db_*`` helpers here)::

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            ...PG logic...
    else:
        ...SQLite logic...
    ...trailing default (None / [] / False) ...

So the SQLite path runs when USE_POSTGRES is False; the PG path runs when
USE_POSTGRES is True AND a pool is available; when USE_POSTGRES is True but
the pool is unavailable the function returns its trailing default and never
touches SQLite.
"""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_calls import (
    create_call_session,
    dequeue_call,
    enqueue_call,
    get_billing_summary,
    get_call_session,
    get_order_status_db,
    get_pending_approvals_db,
    get_saas_dashboard_db,
    get_session_recordings_db,
    get_usage_stats,
    get_webhook_url_db,
    list_calls,
    log_audit_event,
    lookup_invoice_db,
    process_approval_db,
    rent_agent_db,
    update_call_status,
)


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
    return patch("api.services.db_calls._get_sqlite_conn", MagicMock(return_value=conn))


def _patch_pg(pool):
    return patch(
        "api.services.db_calls.get_pg_pool", new_callable=AsyncMock, return_value=pool
    )


def _pg_true():
    return patch("api.services.db_calls.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_calls.USE_POSTGRES", False)


CALL_ROW = {
    "id": "c1",
    "tenant_id": "t1",
    "agent_id": "a1",
    "call_status": "active",
}


class TestCreateCallSession:
    @pytest.mark.asyncio
    async def test_sqlite_ringing_when_agent(self):
        conn = FakeConn(fetchone=CALL_ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_call_session(
                "t1", "a1", "+1555000", caller_name="Bob", called_number="+1555111"
            )
        assert result == CALL_ROW
        assert "INSERT INTO call_sessions" in conn.executed_sqls[0]
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_initiated_without_agent(self):
        conn = FakeConn(fetchone=CALL_ROW)
        with _pg_false(), _patch_conn(conn):
            await create_call_session("t1", None, "+1555000")
        assert conn.executed_params[0][7] == "initiated"

    @pytest.mark.asyncio
    async def test_sqlite_called_number_falls_back_to_caller(self):
        conn = FakeConn(fetchone=CALL_ROW)
        with _pg_false(), _patch_conn(conn):
            await create_call_session("t1", "a1", "+1555000")
        assert conn.executed_params[0][5] == "+1555000"

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow=CALL_ROW)
        with _pg_true(), _patch_pg(pool):
            result = await create_call_session(
                "t1", "a1", "+1555000", caller_name="Bob", called_number="+1555111"
            )
        assert result == CALL_ROW
        assert "INSERT INTO call_sessions" in pool.executed[0][0]
        assert pool.executed[1][0].startswith("SELECT * FROM call_sessions")

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await create_call_session("t1", "a1", "+1555000") is None


class TestGetCallSession:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=CALL_ROW)
        with _pg_false(), _patch_conn(conn):
            assert await get_call_session("c1") == CALL_ROW
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_call_session("c1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=CALL_ROW)
        with _pg_true(), _patch_pg(pool):
            assert await get_call_session("c1") == CALL_ROW

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_call_session("c1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_call_session("c1") is None


class TestUpdateCallStatus:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchone=CALL_ROW)
        with _pg_false(), _patch_conn(conn):
            result = await update_call_status("c1", "completed")
        assert result == CALL_ROW
        assert "UPDATE call_sessions SET call_status = ?" in conn.executed_sqls[0]
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow=CALL_ROW)
        with _pg_true(), _patch_pg(pool):
            result = await update_call_status("c1", "completed")
        assert result == CALL_ROW
        assert pool.executed[0][0].startswith("UPDATE call_sessions SET call_status = $1")
        assert pool.executed[1][0].startswith("SELECT * FROM call_sessions")

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await update_call_status("c1", "completed") is None


class TestListCalls:
    @pytest.mark.asyncio
    async def test_sqlite_with_status(self):
        conn = FakeConn(fetchall=[CALL_ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_calls("t1", status="active")
        assert result == [CALL_ROW]
        assert "AND call_status = ?" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_without_status(self):
        conn = FakeConn(fetchall=[CALL_ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_calls("t1")
        assert result == [CALL_ROW]
        assert "AND call_status" not in conn.last_sql

    @pytest.mark.asyncio
    async def test_pg_with_status(self):
        pool = FakePool(fetch=[CALL_ROW])
        with _pg_true(), _patch_pg(pool):
            result = await list_calls("t1", status="active")
        assert result == [CALL_ROW]
        assert "call_status = $2" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_without_status(self):
        pool = FakePool(fetch=[CALL_ROW])
        with _pg_true(), _patch_pg(pool):
            result = await list_calls("t1")
        assert result == [CALL_ROW]
        assert "call_status" not in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await list_calls("t1") is None


class TestEnqueueCall:
    @pytest.mark.asyncio
    async def test_sqlite_default_position_when_no_row(self):
        conn = FakeConn(fetchone=[None, {"id": "q1"}])
        with _pg_false(), _patch_conn(conn):
            result = await enqueue_call("t1", "+1555000", intent="support")
        assert result == {"id": "q1"}
        assert conn.executed_params[1][3] == 1

    @pytest.mark.asyncio
    async def test_sqlite_position_from_max(self):
        conn = FakeConn(fetchone=[{"max_pos": 7}, {"id": "q1"}])
        with _pg_false(), _patch_conn(conn):
            result = await enqueue_call(
                "t1", "+1555000", intent="support", skills_required=["billing"]
            )
        assert result == {"id": "q1"}
        assert conn.executed_params[1][3] == 7
        assert conn.executed_params[1][5] == '["billing"]'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_position_when_max_null(self):
        conn = FakeConn(fetchone=[{"max_pos": None}, {"id": "q1"}])
        with _pg_false(), _patch_conn(conn):
            await enqueue_call("t1", "+1555000")
        assert conn.executed_params[1][3] == 1

    @pytest.mark.asyncio
    async def test_sqlite_skills_default_to_empty(self):
        conn = FakeConn(fetchone=[{"max_pos": 3}, {"id": "q1"}])
        with _pg_false(), _patch_conn(conn):
            await enqueue_call("t1", "+1555000")
        assert conn.executed_params[1][5] == "[]"

    @pytest.mark.asyncio
    async def test_pg_with_max_pos(self):
        pool = FakePool(fetchval=5, fetchrow={"id": "q1"})
        with _pg_true(), _patch_pg(pool):
            result = await enqueue_call("t1", "+1555000", intent="sales")
        assert result == {"id": "q1"}
        assert pool.executed[0][0].startswith("SELECT COALESCE(MAX(position)")
        assert "INSERT INTO call_queue" in pool.executed[1][0]

    @pytest.mark.asyncio
    async def test_pg_max_pos_none(self):
        pool = FakePool(fetchval=None, fetchrow={"id": "q1"})
        with _pg_true(), _patch_pg(pool):
            await enqueue_call("t1", "+1555000")
        assert pool.executed[1][1][3] == 1

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await enqueue_call("t1", "+1555000") is None


class TestDequeueCall:
    @pytest.mark.asyncio
    async def test_sqlite_assigns_row(self):
        conn = FakeConn(fetchone={"id": "q1", "tenant_id": "t1"})
        with _pg_false(), _patch_conn(conn):
            result = await dequeue_call("t1", "a1")
        assert result == {"id": "q1", "tenant_id": "t1"}
        assert any(
            s.startswith("UPDATE call_queue SET status = 'assigned'")
            for s in conn.executed_sqls
        )
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_row(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await dequeue_call("t1", "a1") is None
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg_assigns_row(self):
        pool = FakePool(fetchrow={"id": "q1", "tenant_id": "t1"})
        with _pg_true(), _patch_pg(pool):
            result = await dequeue_call("t1", "a1")
        assert result == {"id": "q1", "tenant_id": "t1"}
        assert pool.executed[1][0].startswith("UPDATE call_queue")

    @pytest.mark.asyncio
    async def test_pg_no_row(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await dequeue_call("t1", "a1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await dequeue_call("t1", "a1") is None


class TestGetUsageStats:
    @pytest.mark.asyncio
    async def test_sqlite_values(self):
        conn = FakeConn(
            fetchone=[
                {"cnt": 4},
                {"cnt": 2},
                {"cnt": 10},
                {"cnt": 3},
                {"val": 5.5},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_usage_stats("t1")
        assert result == {
            "total_agents": 4,
            "active_agents": 2,
            "total_calls": 10,
            "active_calls": 3,
            "total_minutes": 5.5,
            "queue_depth": 0,
        }
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_missing_rows_coerces_zero(self):
        conn = FakeConn(fetchone=[None, None, None, None, None])
        with _pg_false(), _patch_conn(conn):
            result = await get_usage_stats("t1")
        assert result["total_agents"] == 0
        assert result["active_agents"] == 0
        assert result["total_minutes"] == 0.0

    @pytest.mark.asyncio
    async def test_pg_values(self):
        pool = FakePool(fetchval=[4, 2, 10, 3, 5.5])
        with _pg_true(), _patch_pg(pool):
            result = await get_usage_stats("t1")
        assert result["total_agents"] == 4
        assert result["active_agents"] == 2
        assert result["total_minutes"] == 5.5

    @pytest.mark.asyncio
    async def test_pg_none_values(self):
        pool = FakePool(fetchval=[None, None, None, None, None])
        with _pg_true(), _patch_pg(pool):
            result = await get_usage_stats("t1")
        assert result["total_minutes"] == 0.0
        assert result["active_agents"] == 0

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_usage_stats("t1") is None


class TestGetBillingSummary:
    @pytest.mark.asyncio
    async def test_sqlite_values(self):
        conn = FakeConn(fetchone=[{"cnt": 5}, {"mins": 10.0}])
        with _pg_false(), _patch_conn(conn), patch.dict(
            os.environ, {"CALL_COST_PER_MINUTE": "0.02"}, clear=False
        ):
            result = await get_billing_summary("t1", "2026-01-01", "2026-01-31")
        assert result["total_calls"] == 5
        assert result["total_minutes"] == 10.0
        assert result["total_cost"] == pytest.approx(0.2)
        assert result["currency"] == "USD"
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_missing_rows_coerces_zero(self):
        conn = FakeConn(fetchone=[None, None])
        with _pg_false(), _patch_conn(conn):
            result = await get_billing_summary("t1", "a", "b")
        assert result["total_calls"] == 0
        assert result["total_cost"] == 0.0

    @pytest.mark.asyncio
    async def test_pg_values(self):
        pool = FakePool(fetchval=[5, 10.0])
        with _pg_true(), _patch_pg(pool), patch.dict(
            os.environ, {"CALL_COST_PER_MINUTE": "0.01"}, clear=False
        ):
            result = await get_billing_summary("t1", "a", "b")
        assert result["total_calls"] == 5
        assert result["total_cost"] == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_billing_summary("t1", "a", "b") is None


class TestLogAuditEvent:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await log_audit_event(
                "t1", "u1", "update", "lead", "l1", {"old": 1}, {"new": 2}
            )
        assert "INSERT INTO audit_log" in conn.last_sql
        assert conn.last_params[5] == '{"old": 1}'
        assert conn.last_params[6] == '{"new": 2}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_none_values_default_empty(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await log_audit_event("t1", "u1", "read", "lead", "l1")
        assert conn.last_params[5] == "{}"
        assert conn.last_params[6] == "{}"

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await log_audit_event("t1", "u1", "delete", "lead", "l1")
        assert "INSERT INTO audit_log" in pool.executed[0][0]
        assert pool.executed[0][1][5] == "{}"

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            await log_audit_event("t1", "u1", "x", "lead", "l1")


class TestGetSaasDashboard:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall_seq=[[{"id": "r1"}], [{"id": "p1"}]])
        with _pg_false(), _patch_conn(conn):
            result = await get_saas_dashboard_db("t1")
        assert result == {"rentals": [{"id": "r1"}], "profiles": [{"id": "p1"}]}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch_seq=[[{"id": "r1"}], [{"id": "p1"}]])
        with _pg_true(), _patch_pg(pool):
            result = await get_saas_dashboard_db("t1")
        assert result == {"rentals": [{"id": "r1"}], "profiles": [{"id": "p1"}]}

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_empty(self):
        with _pg_true(), _patch_pg(None):
            assert await get_saas_dashboard_db("t1") == {"rentals": [], "profiles": []}


class TestRentAgent:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        end = datetime(2026, 1, 1, 12, 30, 0)
        with _pg_false(), _patch_conn(conn):
            await rent_agent_db("r1", "t1", "p1", "monthly", end)
        assert "INSERT INTO rentals" in conn.last_sql
        assert conn.last_params[4] == "2026-01-01 12:30:00"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await rent_agent_db("r1", "t1", "p1", "monthly", datetime.now(UTC))
        assert "INSERT INTO rentals" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            await rent_agent_db("r1", "t1", "p1", "monthly", datetime.now(UTC))


class TestGetSessionRecordings:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "rec1"}])
        with _pg_false(), _patch_conn(conn):
            result = await get_session_recordings_db("t1")
        assert result == [{"id": "rec1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "rec1"}])
        with _pg_true(), _patch_pg(pool):
            assert await get_session_recordings_db("t1") == [{"id": "rec1"}]

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_empty(self):
        with _pg_true(), _patch_pg(None):
            assert await get_session_recordings_db("t1") == []


class TestGetPendingApprovals:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "ap1"}])
        with _pg_false(), _patch_conn(conn):
            result = await get_pending_approvals_db("t1")
        assert result == [{"id": "ap1"}]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "ap1"}])
        with _pg_true(), _patch_pg(pool):
            assert await get_pending_approvals_db("t1") == [{"id": "ap1"}]

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_empty(self):
        with _pg_true(), _patch_pg(None):
            assert await get_pending_approvals_db("t1") == []


class TestProcessApproval:
    @pytest.mark.asyncio
    async def test_sqlite_updated(self):
        conn = FakeConn(rowcount=1)
        with _pg_false(), _patch_conn(conn):
            assert await process_approval_db("ap1", "approved", "t1") is True
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_rows(self):
        conn = FakeConn(rowcount=0)
        with _pg_false(), _patch_conn(conn):
            assert await process_approval_db("ap1", "approved", "t1") is False

    @pytest.mark.asyncio
    async def test_pg_updated(self):
        pool = FakePool(execute="UPDATE 1")
        with _pg_true(), _patch_pg(pool):
            assert await process_approval_db("ap1", "approved", "t1") is True

    @pytest.mark.asyncio
    async def test_pg_no_rows(self):
        pool = FakePool(execute="UPDATE 0")
        with _pg_true(), _patch_pg(pool):
            assert await process_approval_db("ap1", "approved", "t1") is False

    @pytest.mark.asyncio
    async def test_pg_result_not_parseable(self):
        pool = FakePool(execute="SOMETHING")
        with _pg_true(), _patch_pg(pool):
            assert await process_approval_db("ap1", "approved", "t1") is False

    @pytest.mark.asyncio
    async def test_pg_result_none(self):
        pool = FakePool(execute=None)
        with _pg_true(), _patch_pg(pool):
            assert await process_approval_db("ap1", "approved", "t1") is False

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_false(self):
        with _pg_true(), _patch_pg(None):
            assert await process_approval_db("ap1", "approved", "t1") is False


class TestGetWebhookUrl:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"webhook_url": "https://hooks.example.com"})
        with _pg_false(), _patch_conn(conn):
            result = await get_webhook_url_db("t1")
        assert result == "https://hooks.example.com"
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_webhook_url_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg_from_tenants_settings(self):
        pool = FakePool(fetchrow=[{"webhook_url": "https://hooks.example.com"}, {}])
        with _pg_true(), _patch_pg(pool):
            assert await get_webhook_url_db("t1") == "https://hooks.example.com"

    @pytest.mark.asyncio
    async def test_pg_falls_back_to_tenant_settings(self):
        pool = FakePool(
            fetchrow=[{"webhook_url": None}, {"webhook_url": "https://fallback.example.com"}]
        )
        with _pg_true(), _patch_pg(pool):
            assert await get_webhook_url_db("t1") == "https://fallback.example.com"

    @pytest.mark.asyncio
    async def test_pg_no_webhook_anywhere(self):
        pool = FakePool(fetchrow=[{}, None])
        with _pg_true(), _patch_pg(pool):
            assert await get_webhook_url_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_webhook_url_db("t1") is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        with _pg_false(), patch(
            "api.services.db_calls._get_sqlite_conn",
            MagicMock(side_effect=Exception("boom")),
        ):
            assert await get_webhook_url_db("t1") is None


class TestLookupInvoice:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"amount": 10.0, "status": "paid"})
        with _pg_false(), _patch_conn(conn):
            result = await lookup_invoice_db("inv1")
        assert result == {"amount": 10.0, "status": "paid"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await lookup_invoice_db("inv1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"amount": 10.0})
        with _pg_true(), _patch_pg(pool):
            assert await lookup_invoice_db("inv1") == {"amount": 10.0}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await lookup_invoice_db("inv1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await lookup_invoice_db("inv1") is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        with _pg_false(), patch(
            "api.services.db_calls._get_sqlite_conn",
            MagicMock(side_effect=Exception("boom")),
        ):
            assert await lookup_invoice_db("inv1") is None


class TestGetOrderStatus:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"status": "shipped", "expected_delivery": "2026-01-05"})
        with _pg_false(), _patch_conn(conn):
            result = await get_order_status_db("o1")
        assert result == {"status": "shipped", "expected_delivery": "2026-01-05"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_order_status_db("o1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"status": "shipped"})
        with _pg_true(), _patch_pg(pool):
            assert await get_order_status_db("o1") == {"status": "shipped"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_order_status_db("o1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_none(self):
        with _pg_true(), _patch_pg(None):
            assert await get_order_status_db("o1") is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        with _pg_false(), patch(
            "api.services.db_calls._get_sqlite_conn",
            MagicMock(side_effect=Exception("boom")),
        ):
            assert await get_order_status_db("o1") is None
