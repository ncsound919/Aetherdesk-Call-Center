"""Unit tests for src/api/services/db_data_lineage.py.

Covers lineage entry creation, record/column lineage lookups, the lineage
graph query, and the data health score under both SQLite (fake conn) and
PostgreSQL (fake asyncpg pool) paths.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_data_lineage import (
    create_lineage_entry_db,
    get_column_lineage_db,
    get_data_health_score_db,
    get_lineage_graph_db,
    get_record_lineage_db,
)


class FakeConn:
    """Minimal sqlite3-like connection (single-value or sequential fetchone)."""

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
        self.fetchrow_calls = []
        self.last_fetch_sql = None
        self.last_fetch_params = None

    async def fetchrow(self, sql, *params):
        self.fetchrow_calls.append((sql, params))
        if self._row:
            return self._row.pop(0)
        return None

    async def fetchval(self, sql, *params):
        if self._vals:
            return self._vals.pop(0)
        return None

    async def fetch(self, sql, *params):
        self.last_fetch_sql = sql
        self.last_fetch_params = params
        if self._rows:
            return self._rows.pop(0)
        return []

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return "OK"


def _patch_conn(conn):
    return patch(
        "api.services.db_data_lineage._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_data_lineage.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_data_lineage.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_data_lineage.USE_POSTGRES", False)


class TestCreateLineageEntry:
    @pytest.mark.asyncio
    async def test_sqlite_dict_metadata(self):
        row = {"id": "e1", "operation": "insert"}
        conn = FakeConn(fetchone=row)
        with _pg_false(), _patch_conn(conn):
            result = await create_lineage_entry_db(
                "t1", "calls", "call1", "leads", "lead1", "insert", {"src": "api"}
            )
        assert result == row
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO data_lineage" in insert_sql
        assert insert_params[1] == "t1"
        assert insert_params[7] == '{"src": "api"}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_metadata_none(self):
        conn = FakeConn(fetchone={"id": "e1"})
        with _pg_false(), _patch_conn(conn):
            await create_lineage_entry_db("t1", "a", "1", "b", "2", "copy")
        assert conn.executed_calls[0][1][7] == "{}"

    @pytest.mark.asyncio
    async def test_sqlite_metadata_str_passthrough(self):
        conn = FakeConn(fetchone={"id": "e1"})
        with _pg_false(), _patch_conn(conn):
            await create_lineage_entry_db(
                "t1", "a", "1", "b", "2", "copy", '{"raw": 1}'
            )
        assert conn.executed_calls[0][1][7] == '{"raw": 1}'

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_lineage_entry_db("t1", "a", "1", "b", "2", "copy") is None

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"id": "e1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_lineage_entry_db(
                "t1", "a", "1", "b", "2", "copy", {"x": 1}
            )
        assert result == {"id": "e1"}
        sql, params = pool.fetchrow_calls[0]
        assert "INSERT INTO data_lineage" in sql
        assert "RETURNING *" in sql
        assert params[1] == "t1"
        assert params[7] == '{"x": 1}'

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_lineage_entry_db("t1", "a", "1", "b", "2", "copy")
                is None
            )


class TestGetRecordLineage:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        rows = [{"id": "e1", "source_table": "calls"}]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            result = await get_record_lineage_db("t1", "calls", "call1")
        assert result == rows
        assert conn.last_params == ("t1", "calls", "call1", "calls", "call1")
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "e1"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_record_lineage_db("t1", "calls", "call1")
        assert result == [{"id": "e1"}]
        assert "source_table = $2" in pool.last_fetch_sql
        assert pool.last_fetch_params == ("t1", "calls", "call1")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_record_lineage_db("t1", "calls", "call1") is None


class TestGetLineageGraph:
    @pytest.mark.asyncio
    async def test_sqlite_no_dates(self):
        conn = FakeConn(fetchall=[{"id": "e1"}])
        with _pg_false(), _patch_conn(conn):
            result = await get_lineage_graph_db("t1")
        assert result == [{"id": "e1"}]
        assert conn.last_params == ["t1"]
        assert "LIMIT 500" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_dates_and_limit(self):
        conn = FakeConn(fetchall=[{"id": "e1"}])
        with _pg_false(), _patch_conn(conn):
            result = await get_lineage_graph_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01", limit=10
            )
        assert result == [{"id": "e1"}]
        assert conn.last_params == ["t1", "2026-01-01", "2026-02-01"]
        assert "LIMIT 10" in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_start_only(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            await get_lineage_graph_db("t1", start_date="2026-01-01")
        assert conn.last_params == ["t1", "2026-01-01"]
        assert "created_at <= ?" not in conn.last_sql

    @pytest.mark.asyncio
    async def test_pg_no_dates(self):
        pool = FakePool(fetch=[{"id": "e1"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_lineage_graph_db("t1")
        assert result == [{"id": "e1"}]
        assert pool.last_fetch_params == ("t1",)
        assert "LIMIT 500" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_with_dates(self):
        pool = FakePool(fetch=[{"id": "e1"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_lineage_graph_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result == [{"id": "e1"}]
        assert "created_at >= $2" in pool.last_fetch_sql
        assert "created_at <= $3" in pool.last_fetch_sql
        assert pool.last_fetch_params == ("t1", "2026-01-01", "2026-02-01")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_lineage_graph_db("t1") is None


class TestGetColumnLineage:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        rows = [{"id": "e1", "column_name": "email"}]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            result = await get_column_lineage_db("t1", "users", "email")
        assert result == rows
        assert conn.last_params == ("t1", "email", "users")
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetch=[{"id": "e1"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_column_lineage_db("t1", "users", "email")
        assert result == [{"id": "e1"}]
        assert "column_name = $2" in pool.last_fetch_sql
        assert pool.last_fetch_params == ("t1", "email", "users")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_column_lineage_db("t1", "users", "email") is None


class TestGetDataHealthScore:
    @pytest.mark.asyncio
    async def test_sqlite_no_records_returns_zeros(self):
        conn = FakeConn(fetchone={"total": 0})
        with _pg_false(), _patch_conn(conn):
            result = await get_data_health_score_db("t1")
        assert result == {"completeness": 0, "consistency": 0, "freshness": 0, "overall": 0}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_records(self):
        now = datetime.now(UTC)
        recent = (now - timedelta(hours=1)).isoformat()
        conn = FakeConn(
            fetchone=[
                {"total": 2},
                {"cnt": 1},
                {"cnt": 2},
                {"created_at": recent},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_data_health_score_db("t1")
        assert result["completeness"] == 50.0
        assert result["consistency"] == 100.0
        assert result["freshness"] == 75.0
        assert result["overall"] == round((50.0 + 100.0 + 75.0) / 3, 1)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_freshness_100(self):
        now = datetime.now(UTC)
        recent = (now - timedelta(minutes=10)).isoformat()
        conn = FakeConn(
            fetchone=[
                {"total": 1},
                {"cnt": 1},
                {"cnt": 1},
                {"created_at": recent},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_data_health_score_db("t1")
        assert result["freshness"] == 100.0

    @pytest.mark.asyncio
    async def test_sqlite_freshness_50(self):
        now = datetime.now(UTC)
        stale = (now - timedelta(days=2)).isoformat()
        conn = FakeConn(
            fetchone=[
                {"total": 1},
                {"cnt": 1},
                {"cnt": 1},
                {"created_at": stale},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_data_health_score_db("t1")
        assert result["freshness"] == 50.0

    @pytest.mark.asyncio
    async def test_sqlite_freshness_25(self):
        now = datetime.now(UTC)
        very_stale = (now - timedelta(days=10)).isoformat()
        conn = FakeConn(
            fetchone=[
                {"total": 1},
                {"cnt": 1},
                {"cnt": 1},
                {"created_at": very_stale},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_data_health_score_db("t1")
        assert result["freshness"] == 25.0

    @pytest.mark.asyncio
    async def test_sqlite_bad_date_and_missing_rows(self):
        conn = FakeConn(
            fetchone=[
                {"total": 1},
                {"cnt": 0},
                {"cnt": 3},
                {"created_at": "not-a-date"},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_data_health_score_db("t1")
        assert result["completeness"] == 0.0
        assert result["consistency"] == 100.0
        assert result["freshness"] == 100.0  # unparseable date → default

    @pytest.mark.asyncio
    async def test_sqlite_no_last_row(self):
        conn = FakeConn(
            fetchone=[
                {"total": 1},
                {"cnt": 1},
                {"cnt": 1},
                None,
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_data_health_score_db("t1")
        assert result["freshness"] == 100.0
        assert result["overall"] == 100.0

    @pytest.mark.asyncio
    async def test_pg_row_none_returns_defaults(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            result = await get_data_health_score_db("t1")
        assert result == {"completeness": 100.0, "consistency": 100.0, "freshness": 100.0, "overall": 100.0}

    @pytest.mark.asyncio
    async def test_pg_with_data_fresh(self):
        pool = FakePool(
            fetchrow={
                "total": 2,
                "completeness": 80.5,
                "consistency": 90.0,
                "seconds_since_last": 10,
            }
        )
        with _pg_true(), _patch_pg(pool):
            result = await get_data_health_score_db("t1")
        assert result["completeness"] == 80.5
        assert result["consistency"] == 90.0
        assert result["freshness"] == 100.0
        assert result["overall"] == round((80.5 + 90.0 + 100.0) / 3, 1)

    @pytest.mark.asyncio
    async def test_pg_freshness_buckets(self):
        for secs, expected in [(7200, 75.0), (172800, 50.0), (700000, 25.0)]:
            pool = FakePool(
                fetchrow={
                    "total": 1,
                    "completeness": 100.0,
                    "consistency": 100.0,
                    "seconds_since_last": secs,
                }
            )
            with _pg_true(), _patch_pg(pool):
                result = await get_data_health_score_db("t1")
            assert result["freshness"] == expected

    @pytest.mark.asyncio
    async def test_pg_row_zero_total_returns_defaults(self):
        pool = FakePool(
            fetchrow={
                "total": 0,
                "completeness": 0.0,
                "consistency": 0.0,
                "seconds_since_last": 0,
            }
        )
        with _pg_true(), _patch_pg(pool):
            result = await get_data_health_score_db("t1")
        assert result["overall"] == 100.0

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_defaults(self):
        with _pg_true(), _patch_pg(None):
            result = await get_data_health_score_db("t1")
        assert result["overall"] == 100.0
