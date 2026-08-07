"""Unit tests for src/api/services/db_security.py.

Covers pen-test scans, WAF events, data classification, and RBAC audit
results under both SQLite (fake conn via ``_get_sqlite_conn``) and PostgreSQL
(fake asyncpg pool via ``get_pg_pool``), following the established pattern.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_security import (
    create_pen_test_scan_db,
    create_rbac_audit_result_db,
    create_waf_event_db,
    get_data_classification_db,
    get_pen_test_scan_db,
    list_pen_test_scans_db,
    list_rbac_audit_results_db,
    list_waf_events_db,
    set_data_classification_db,
    update_pen_test_scan_db,
)


class FakeConn:
    """Minimal sqlite3-like connection.

    ``fetchone`` may be a single row or a LIST of rows consumed in order (for
    multi-query functions). ``fetchall`` takes a list of rows (or a list of
    lists for sequential fetchall results).
    """

    def __init__(self, fetchone=None, fetchall=None, rowcount=1):
        if isinstance(fetchone, list):
            self._one = list(fetchone)
        else:
            self._one = [fetchone]
        if isinstance(fetchall, list) and fetchall and isinstance(fetchall[0], list):
            self._all = list(fetchall)
        else:
            self._all = [fetchall]
        self.rowcount = rowcount
        self.closed = False
        self.committed = False
        self.last_sql = None
        self.last_params = None
        self.executed_sqls = []
        self.executed_calls = []

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed_sqls.append(sql)
        self.executed_calls.append((sql, params))
        return self

    def fetchone(self):
        if self._one:
            return self._one.pop(0)
        return None

    def fetchall(self):
        if self._all:
            return self._all.pop(0)
        return None

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class FakePool:
    """Minimal asyncpg-like pool."""

    def __init__(self, fetchrow=None, fetch=None, fetchval=None):
        if isinstance(fetchrow, list):
            self._row = list(fetchrow)
        else:
            self._row = [fetchrow]
        if isinstance(fetch, list) and fetch and isinstance(fetch[0], list):
            self._rows = list(fetch)
        else:
            self._rows = [fetch]
        if isinstance(fetchval, list):
            self._vals = [fetchval]
        else:
            self._vals = [fetchval]
        self.executed = []
        self.last_fetch_sql = None

    async def fetchrow(self, sql, *params):
        if self._row:
            return self._row.pop(0)
        return None

    async def fetchval(self, sql, *params):
        if self._vals:
            return self._vals.pop(0)
        return None

    async def fetch(self, sql, *params):
        self.last_fetch_sql = sql
        if self._rows:
            return self._rows.pop(0)
        return []

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return "OK"


def _patch_conn(conn):
    return patch(
        "api.services.db_security._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_security.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_security.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_security.USE_POSTGRES", False)


class TestCreatePenTestScan:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        row = {"id": "s1", "status": "running"}
        conn = FakeConn(fetchone=row)
        with _pg_false(), _patch_conn(conn):
            result = await create_pen_test_scan_db("t1", "https://x.com", "high")
        assert result == row
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO pen_test_scans" in insert_sql
        assert insert_params[1] == "t1"
        assert insert_params[2] == "https://x.com"
        assert insert_params[4] == "high"
        assert insert_params[3] == "[]"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_pen_test_scan_db("t1", "https://x.com") is None

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "s1", "status": "running"})
        with _pg_true(), _patch_pg(pool):
            result = await create_pen_test_scan_db("t1", "https://x.com", "low")
        assert result == {"id": "s1", "status": "running"}
        sql, params = pool.executed[0]
        assert "INSERT INTO pen_test_scans" in sql
        assert params[1] == "t1"
        assert params[2] == "https://x.com"
        assert params[4] == "low"

    @pytest.mark.asyncio
    async def test_pg_row_none(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await create_pen_test_scan_db("t1", "https://x.com") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_pen_test_scan_db("t1", "https://x.com") is None


class TestUpdatePenTestScan:
    @pytest.mark.asyncio
    async def test_sqlite_with_completed_at(self):
        row = {"id": "s1", "status": "complete"}
        conn = FakeConn(fetchone=row)
        with _pg_false(), _patch_conn(conn):
            result = await update_pen_test_scan_db(
                "s1", "complete", [{"severity": "high"}], "2026-01-01"
            )
        assert result == row
        update_sql, update_params = conn.executed_calls[0]
        assert "completed_at = ?" in update_sql
        assert update_params[1] == '[{"severity": "high"}]'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_without_completed_at_str_findings(self):
        conn = FakeConn(fetchone={"id": "s1"})
        with _pg_false(), _patch_conn(conn):
            result = await update_pen_test_scan_db("s1", "failed", "already-json")
        assert result == {"id": "s1"}
        update_sql, update_params = conn.executed_calls[0]
        assert "completed_at = ?" not in update_sql
        assert update_params[1] == "already-json"

    @pytest.mark.asyncio
    async def test_pg_with_completed_at(self):
        pool = FakePool(fetchrow={"id": "s1"})
        with _pg_true(), _patch_pg(pool):
            result = await update_pen_test_scan_db(
                "s1", "complete", ["finding"], "2026-01-01"
            )
        assert result == {"id": "s1"}
        sql, params = pool.executed[0]
        assert "completed_at = $3" in sql
        assert params[1] == '["finding"]'
        assert params[2] == "2026-01-01"

    @pytest.mark.asyncio
    async def test_pg_without_completed_at(self):
        pool = FakePool(fetchrow={"id": "s1"})
        with _pg_true(), _patch_pg(pool):
            result = await update_pen_test_scan_db("s1", "running", ["finding"])
        assert result == {"id": "s1"}
        sql, params = pool.executed[0]
        assert "completed_at = $3" not in sql
        assert params[1] == '["finding"]'

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_pen_test_scan_db("s1", "running", []) is None


class TestListPenTestScans:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        rows = [{"id": "s1"}, {"id": "s2"}]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            result = await list_pen_test_scans_db("t1")
        assert result == rows
        assert conn.last_params == ("t1",)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "s1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_pen_test_scans_db("t1")
        assert result == [{"id": "s1"}]
        assert "ORDER BY started_at DESC" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_pen_test_scans_db("t1") is None


class TestGetPenTestScan:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "s1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_pen_test_scan_db("s1") == {"id": "s1"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_pen_test_scan_db("s1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "s1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_pen_test_scan_db("s1") == {"id": "s1"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_pen_test_scan_db("s1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_pen_test_scan_db("s1") is None


class TestCreateWafEvent:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        row = {"id": "e1", "rule_id": "r1"}
        conn = FakeConn(fetchone=row)
        with _pg_false(), _patch_conn(conn):
            result = await create_waf_event_db(
                "t1", "r1", "block", "1.2.3.4", "/login"
            )
        assert result == row
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO waf_events" in insert_sql
        assert insert_params[1] == "t1"
        assert insert_params[4] == "1.2.3.4"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "e1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_waf_event_db(
                "t1", "r1", "block", "1.2.3.4", "/login"
            )
        assert result == {"id": "e1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO waf_events" in sql
        assert params[1] == "t1"
        assert params[4] == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_waf_event_db("t1", "r1", "block", "ip", "/")
                is None
            )


class TestListWafEvents:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "e1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_waf_events_db("t1", limit=50)
        assert result == [{"id": "e1"}]
        assert conn.last_params == ("t1", 50)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "e1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_waf_events_db("t1")
        assert result == [{"id": "e1"}]
        assert "LIMIT $2" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_waf_events_db("t1") is None


class TestSetDataClassification:
    @pytest.mark.asyncio
    async def test_sqlite_existing_updates(self):
        row = {"id": "c1", "sensitivity": "PII"}
        conn = FakeConn(fetchone=[{"id": "c1"}, row])
        with _pg_false(), _patch_conn(conn):
            result = await set_data_classification_db(
                "t1", "public", "users", "email", "PII", "desc"
            )
        assert result == row
        assert any(s.startswith("UPDATE data_classification") for s in conn.executed_sqls)
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_missing_inserts(self):
        row = {"id": "c1", "sensitivity": "PII"}
        conn = FakeConn(fetchone=[None, row])
        with _pg_false(), _patch_conn(conn):
            result = await set_data_classification_db(
                "t1", "public", "users", "email", "PII"
            )
        assert result == row
        assert any(s.startswith("INSERT INTO data_classification") for s in conn.executed_sqls)
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "c1"})
        with _pg_true(), _patch_pg(pool):
            result = await set_data_classification_db(
                "t1", "public", "users", "email", "PII", "desc"
            )
        assert result == {"id": "c1"}
        sql, params = pool.executed[0]
        assert "ON CONFLICT" in sql
        assert params[5] == "PII"
        assert params[6] == "desc"

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await set_data_classification_db("t1", "s", "t", "c", "PII")
                is None
            )


class TestGetDataClassification:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        rows = [{"id": "c1"}, {"id": "c2"}]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            result = await get_data_classification_db("t1")
        assert result == rows
        assert conn.last_params == ("t1",)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "c1"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_data_classification_db("t1")
        assert result == [{"id": "c1"}]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_data_classification_db("t1") is None


class TestCreateRbacAuditResult:
    @pytest.mark.asyncio
    async def test_sqlite_passed(self):
        row = {"id": "a1", "passed": 1}
        conn = FakeConn(fetchone=row)
        with _pg_false(), _patch_conn(conn):
            result = await create_rbac_audit_result_db(
                "t1", "admin", "calls", "read", "allow", "allow", True
            )
        assert result == row
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO rbac_audit_results" in insert_sql
        assert insert_params[7] == 1
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_passed(self):
        conn = FakeConn(fetchone={"id": "a1", "passed": 0})
        with _pg_false(), _patch_conn(conn):
            result = await create_rbac_audit_result_db(
                "t1", "admin", "calls", "read", "allow", "deny", False
            )
        assert result["passed"] == 0
        assert conn.executed_calls[0][1][7] == 0

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "a1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_rbac_audit_result_db(
                "t1", "admin", "calls", "read", "allow", "deny", False
            )
        assert result == {"id": "a1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO rbac_audit_results" in sql
        assert params[7] is False

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_rbac_audit_result_db(
                    "t1", "admin", "calls", "read", "allow", "deny", True
                )
                is None
            )


class TestListRbacAuditResults:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn(fetchall=[{"id": "a1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_rbac_audit_results_db("t1")
        assert result == [{"id": "a1"}]
        assert conn.last_params == ("t1",)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "a1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_rbac_audit_results_db("t1")
        assert result == [{"id": "a1"}]
        assert "ORDER BY tested_at DESC" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_rbac_audit_results_db("t1") is None
