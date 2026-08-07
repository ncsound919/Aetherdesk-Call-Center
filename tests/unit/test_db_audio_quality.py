"""Unit tests for src/api/services/db_audio_quality.py.

Exercises every public async helper (quality metric creation/listing,
quality summary with p95 aggregation, quality trends bucketing, per-call
quality lookup) against a fake SQLite connection and a fake asyncpg pool,
following the established pattern in test_db_platform_ops.py.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_audio_quality import (
    create_quality_metric_db,
    get_call_quality_db,
    get_quality_summary_db,
    get_quality_trends_db,
    list_quality_metrics_db,
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
        "api.services.db_audio_quality._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_audio_quality.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_audio_quality.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_audio_quality.USE_POSTGRES", False)


class TestCreateQualityMetric:
    @pytest.mark.asyncio
    async def test_pg_with_rtt_list(self):
        pool = FakePool(fetchrow={"id": "m1", "mos": 4.2})
        with _pg_true(), _patch_pg(pool):
            result = await create_quality_metric_db(
                "t1", "c1", "a1", 4.2, 12, 0.1, 80, [1, 2, 3], "opus", "good"
            )
        assert result["id"] == "m1"
        sql, params = pool.executed[0]
        assert "INSERT INTO voice_quality_metrics" in sql
        assert params[8] == "[1, 2, 3]"

    @pytest.mark.asyncio
    async def test_pg_with_non_list_rtt(self):
        pool = FakePool(fetchrow={"id": "m1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_quality_metric_db(
                "t1", "c1", "a1", 3.1, 20, 0.5, 90, None, "opus", "fair"
            )
        assert result == {"id": "m1"}
        assert pool.executed[0][1][8] == "[]"

    @pytest.mark.asyncio
    async def test_pg_returns_none_when_select_empty(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert (
                await create_quality_metric_db(
                    "t1", "c1", "a1", 1.0, 1, 1, 1, None, "c", "bad"
                )
                is None
            )

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_quality_metric_db(
                    "t1", "c1", "a1", 1.0, 1, 1, 1, [], "c", "bad"
                )
                is None
            )

    @pytest.mark.asyncio
    async def test_sqlite_with_rtt_list(self):
        conn = FakeConn(fetchone={"id": "m1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_quality_metric_db(
                "t1", "c1", "a1", 4.2, 12, 0.1, 80, [5, 6], "opus", "good"
            )
        assert result == {"id": "m1"}
        assert conn.executed_params[0][8] == "[5, 6]"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_non_list_rtt(self):
        conn = FakeConn(fetchone={"id": "m1"})
        with _pg_false(), _patch_conn(conn):
            await create_quality_metric_db(
                "t1", "c1", "a1", 3.0, 20, 0.2, 70, "n/a", "opus", "good"
            )
        assert conn.executed_params[0][8] == "[]"


class TestListQualityMetrics:
    @pytest.mark.asyncio
    async def test_pg_no_filters(self):
        pool = FakePool(fetch=[{"id": "m1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_quality_metrics_db("t1")
        assert result == [{"id": "m1"}]
        sql, params = pool.executed[0]
        assert "mos >=" not in sql
        assert "LIMIT 50 OFFSET 0" in sql
        assert params == ("t1",)

    @pytest.mark.asyncio
    async def test_pg_min_mos_only(self):
        pool = FakePool(fetch=[{"id": "m1"}])
        with _pg_true(), _patch_pg(pool):
            await list_quality_metrics_db("t1", min_mos=4.0)
        sql, params = pool.executed[0]
        assert "AND mos >= $2" in sql
        assert params == ("t1", 4.0)

    @pytest.mark.asyncio
    async def test_pg_start_only(self):
        pool = FakePool(fetch=[{"id": "m1"}])
        with _pg_true(), _patch_pg(pool):
            await list_quality_metrics_db("t1", start_date="2026-01-01")
        sql, params = pool.executed[0]
        assert "AND created_at >= $2" in sql
        assert "created_at <=" not in sql
        assert params == ("t1", "2026-01-01")

    @pytest.mark.asyncio
    async def test_pg_end_only(self):
        pool = FakePool(fetch=[{"id": "m1"}])
        with _pg_true(), _patch_pg(pool):
            await list_quality_metrics_db("t1", end_date="2026-02-01")
        sql, params = pool.executed[0]
        assert "AND created_at <= $2" in sql
        assert params == ("t1", "2026-02-01")

    @pytest.mark.asyncio
    async def test_pg_all_filters(self):
        pool = FakePool(fetch=[{"id": "m1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_quality_metrics_db(
                "t1",
                limit=10,
                offset=5,
                min_mos=3.0,
                start_date="2026-01-01",
                end_date="2026-02-01",
            )
        assert result == [{"id": "m1"}]
        sql, params = pool.executed[0]
        assert "mos >= $2" in sql
        assert "created_at >= $3" in sql
        assert "created_at <= $4" in sql
        assert "LIMIT 10 OFFSET 5" in sql
        assert params == ("t1", 3.0, "2026-01-01", "2026-02-01")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_quality_metrics_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite_all_filters(self):
        conn = FakeConn(fetchall=[{"id": "m1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_quality_metrics_db(
                "t1", limit=10, offset=5, min_mos=3.0, start_date="a", end_date="b"
            )
        assert result == [{"id": "m1"}]
        assert "mos >= ?" in conn.last_sql
        assert "created_at >= ?" in conn.last_sql
        assert "created_at <= ?" in conn.last_sql
        assert "LIMIT 10 OFFSET 5" in conn.last_sql
        assert conn.last_params == ["t1", 3.0, "a", "b"]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_filters(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_quality_metrics_db("t1") == []
        assert "mos >=" not in conn.last_sql


class TestGetQualitySummary:
    ROWS = [
        {"mos": 4.5, "jitter_ms": 10, "packet_loss_pct": 0.1, "quality_rating": "excellent"},
        {"mos": 4.0, "jitter_ms": 20, "packet_loss_pct": 0.2, "quality_rating": "good"},
        {"mos": 3.5, "jitter_ms": 30, "packet_loss_pct": 0.3, "quality_rating": "good"},
        {"mos": 2.0, "jitter_ms": 40, "packet_loss_pct": 0.4, "quality_rating": "poor"},
        {"mos": 1.5, "jitter_ms": 5, "packet_loss_pct": 0.05, "quality_rating": "unknown"},
    ]

    def _assert_defaults(self, result):
        assert result["total_calls"] == 0
        assert result["avg_mos"] == 0.0
        assert result["p95_jitter_ms"] == 0.0
        assert result["p95_packet_loss_pct"] == 0.0
        assert result["quality_distribution"] == {
            "excellent": 0,
            "good": 0,
            "fair": 0,
            "poor": 0,
            "bad": 0,
        }

    @pytest.mark.asyncio
    async def test_pg_with_data(self):
        pool = FakePool(fetchrow={"total": 5, "avg_mos": 3.1}, fetch=self.ROWS)
        with _pg_true(), _patch_pg(pool):
            result = await get_quality_summary_db("t1")
        assert result["total_calls"] == 5
        assert result["avg_mos"] == 3.1
        assert result["p95_jitter_ms"] == 40
        assert result["p95_packet_loss_pct"] == 0.4
        assert result["quality_distribution"] == {
            "excellent": 1,
            "good": 2,
            "fair": 0,
            "poor": 1,
            "bad": 0,
        }

    @pytest.mark.asyncio
    async def test_pg_with_filters(self):
        pool = FakePool(fetchrow={"total": 1, "avg_mos": 4.0}, fetch=self.ROWS[:1])
        with _pg_true(), _patch_pg(pool):
            result = await get_quality_summary_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result["total_calls"] == 1
        sql, params = pool.executed[0]
        assert "created_at >= $2" in sql
        assert "created_at <= $3" in sql
        assert params == ("t1", "2026-01-01", "2026-02-01")

    @pytest.mark.asyncio
    async def test_pg_no_agg_no_rows(self):
        pool = FakePool(fetchrow=None, fetch=[])
        with _pg_true(), _patch_pg(pool):
            result = await get_quality_summary_db("t1")
        self._assert_defaults(result)

    @pytest.mark.asyncio
    async def test_pg_agg_present_rows_empty(self):
        pool = FakePool(fetchrow={"total": 0, "avg_mos": 0}, fetch=[])
        with _pg_true(), _patch_pg(pool):
            result = await get_quality_summary_db("t1")
        assert result["total_calls"] == 0
        assert result["p95_jitter_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            result = await get_quality_summary_db("t1")
        self._assert_defaults(result)

    @pytest.mark.asyncio
    async def test_sqlite_with_data(self):
        conn = FakeConn(fetchone={"total": 5, "avg_mos": 3.1}, fetchall=self.ROWS)
        with _pg_false(), _patch_conn(conn):
            result = await get_quality_summary_db("t1")
        assert result["total_calls"] == 5
        assert result["avg_mos"] == 3.1
        assert result["p95_jitter_ms"] == 40
        assert result["quality_distribution"]["good"] == 2
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_filters(self):
        conn = FakeConn(fetchone={"total": 1, "avg_mos": 4.0}, fetchall=self.ROWS[:1])
        with _pg_false(), _patch_conn(conn):
            result = await get_quality_summary_db(
                "t1", start_date="a", end_date="b"
            )
        assert result["total_calls"] == 1
        assert "created_at >= ?" in conn.executed_sqls[0]
        assert "created_at <= ?" in conn.executed_sqls[0]
        assert conn.executed_params[0] == ["t1", "a", "b"]

    @pytest.mark.asyncio
    async def test_sqlite_no_agg_no_rows(self):
        conn = FakeConn(fetchone=None, fetchall=[])
        with _pg_false(), _patch_conn(conn):
            result = await get_quality_summary_db("t1")
        self._assert_defaults(result)

    @pytest.mark.asyncio
    async def test_sqlite_agg_present_rows_empty(self):
        conn = FakeConn(fetchone={"total": 0, "avg_mos": 0}, fetchall=[])
        with _pg_false(), _patch_conn(conn):
            result = await get_quality_summary_db("t1")
        assert result["total_calls"] == 0
        assert result["p95_jitter_ms"] == 0.0


class TestGetQualityTrends:
    @pytest.mark.asyncio
    async def test_pg_hour(self):
        pool = FakePool(fetch=[{"bucket": "2026-01-01T10:00:00", "call_count": 2}])
        with _pg_true(), _patch_pg(pool):
            result = await get_quality_trends_db("t1", granularity="hour")
        assert result == [{"bucket": "2026-01-01T10:00:00", "call_count": 2}]
        assert "date_trunc('hour'" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_day(self):
        pool = FakePool(fetch=[{"bucket": "2026-01-01", "call_count": 2}])
        with _pg_true(), _patch_pg(pool):
            await get_quality_trends_db("t1", granularity="day")
        assert "date_trunc('day'" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_other_granularity_defaults_to_hour(self):
        pool = FakePool(fetch=[])
        with _pg_true(), _patch_pg(pool):
            await get_quality_trends_db("t1", granularity="week")
        assert "date_trunc('hour'" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_with_filters(self):
        pool = FakePool(fetch=[{"bucket": "b", "call_count": 1}])
        with _pg_true(), _patch_pg(pool):
            await get_quality_trends_db("t1", start_date="a", end_date="b")
        sql, params = pool.executed[0]
        assert "created_at >= $2" in sql
        assert "created_at <= $3" in sql
        assert params == ("t1", "a", "b")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_quality_trends_db("t1") is None

    @pytest.mark.asyncio
    async def test_sqlite_hour(self):
        conn = FakeConn(fetchall=[{"bucket": "2026-01-01T10:00:00"}])
        with _pg_false(), _patch_conn(conn):
            result = await get_quality_trends_db("t1", granularity="hour")
        assert result == [{"bucket": "2026-01-01T10:00:00"}]
        assert "strftime('%Y-%m-%dT%H:00:00', created_at)" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_day(self):
        conn = FakeConn(fetchall=[{"bucket": "2026-01-01"}])
        with _pg_false(), _patch_conn(conn):
            await get_quality_trends_db("t1", granularity="day")
        assert "strftime('%Y-%m-%d', created_at)" in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_other_granularity_defaults_to_hour(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            await get_quality_trends_db("t1", granularity="week")
        assert "strftime('%Y-%m-%dT%H:00:00', created_at)" in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_with_filters(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            await get_quality_trends_db("t1", start_date="a", end_date="b")
        assert "created_at >= ?" in conn.last_sql
        assert "created_at <= ?" in conn.last_sql
        assert conn.last_params == ["t1", "a", "b"]


class TestGetCallQuality:
    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "m1", "call_id": "c1"})
        with _pg_true(), _patch_pg(pool):
            result = await get_call_quality_db("t1", "c1")
        assert result == {"id": "m1", "call_id": "c1"}
        assert "ORDER BY created_at DESC LIMIT 1" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_call_quality_db("t1", "c1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_call_quality_db("t1", "c1") is None

    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "m1"})
        with _pg_false(), _patch_conn(conn):
            assert await get_call_quality_db("t1", "c1") == {"id": "m1"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_call_quality_db("t1", "c1") is None
