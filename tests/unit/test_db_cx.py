"""Unit tests for src/api/services/db_cx.py.

Covers the CX `*_db` functions (surveys, CSAT, NPS, sentiment trends,
customer 360) under both the SQLite and PostgreSQL (mocked pool) paths.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_cx import (
    create_survey_db,
    get_csat_score_db,
    get_customer_360_db,
    get_nps_score_db,
    get_response_rate_db,
    get_sentiment_trends_db,
    list_surveys_db,
)


class FakeConn:
    """Minimal sqlite3-like connection.

    - fetchone/fetchall may be a single value OR a list of values to return
      in sequence (for multi-query functions).
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
    """Minimal asyncpg-like pool.

    - fetchrow/fetchval may be a single value OR a list of values to return
      in sequence.
    - fetch expects lists of rows; a single list is a single result, and a
      list-of-lists is a sequence of results.
    """

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
        self.last_fetch_sql = sql
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
        "api.services.db_cx._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_cx.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_cx.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_cx.USE_POSTGRES", False)


class TestCreateSurvey:
    @pytest.mark.asyncio
    async def test_sqlite_returns_row(self):
        conn = FakeConn(fetchone={"id": "s1", "tenant_id": "t1", "rating": 5})
        with _pg_false(), _patch_conn(conn):
            result = await create_survey_db(
                "t1",
                call_id="c1",
                customer_id="cust1",
                rating=4,
                feedback="great",
                channel="voice",
            )
        assert result == {"id": "s1", "tenant_id": "t1", "rating": 5}
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO csat_surveys" in insert_sql
        assert insert_params[1:8] == ("t1", "c1", "cust1", 4, "great", "voice", 1)
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_survey_db("t1") is None
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg_returns_row(self):
        pool = FakePool(fetchrow={"id": "s1", "rating": 5})
        with _pg_true(), _patch_pg(pool):
            result = await create_survey_db(
                "t1", rating=3, feedback="ok", responded=0
            )
        assert result == {"id": "s1", "rating": 5}
        sql, params = pool.executed[0]
        assert "INSERT INTO csat_surveys" in sql
        assert params[1:] == ("t1", None, None, 3, "ok", "voice", 0)

    @pytest.mark.asyncio
    async def test_pg_row_none(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await create_survey_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_survey_db("t1") is None


class TestListSurveys:
    @pytest.mark.asyncio
    async def test_sqlite_all_filters(self):
        conn = FakeConn(fetchall=[{"id": "s1", "rating": 4}])
        with _pg_false(), _patch_conn(conn):
            result = await list_surveys_db(
                "t1",
                limit=10,
                offset=5,
                min_rating=3,
                channel="voice",
                start_date="2026-01-01",
                end_date="2026-02-01",
            )
        assert result == [{"id": "s1", "rating": 4}]
        assert "rating >= ?" in conn.last_sql
        assert "channel = ?" in conn.last_sql
        assert "created_at >= ?" in conn.last_sql
        assert "created_at <= ?" in conn.last_sql
        assert conn.last_params[-2:] == [10, 5]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_filters(self):
        conn = FakeConn(fetchall=[{"id": "s1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_surveys_db("t1")
        assert result == [{"id": "s1"}]
        assert "rating >= ?" not in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_surveys_db("t1") == []

    @pytest.mark.asyncio
    async def test_pg_all_filters(self):
        pool = FakePool(fetch=[[{"id": "s1", "rating": 4}]])
        with _pg_true(), _patch_pg(pool):
            result = await list_surveys_db(
                "t1",
                min_rating=3,
                channel="sms",
                start_date="2026-01-01",
                end_date="2026-02-01",
            )
        assert result == [{"id": "s1", "rating": 4}]
        assert "rating >= $2" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_surveys_db("t1") is None


class TestCsatScore:
    @pytest.mark.asyncio
    async def test_sqlite_with_filters(self):
        conn = FakeConn(fetchone={"avg_rating": 4.5, "total": 10})
        with _pg_false(), _patch_conn(conn):
            result = await get_csat_score_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result == {"avg_rating": 4.5, "total_surveys": 10}
        assert "created_at >= ?" in conn.last_sql
        assert "created_at <= ?" in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_no_filters(self):
        conn = FakeConn(fetchone={"avg_rating": 3.0, "total": 2})
        with _pg_false(), _patch_conn(conn):
            assert await get_csat_score_db("t1") == {
                "avg_rating": 3.0,
                "total_surveys": 2,
            }

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_csat_score_db("t1") == {
                "avg_rating": 0,
                "total_surveys": 0,
            }

    @pytest.mark.asyncio
    async def test_pg_with_filters(self):
        pool = FakePool(fetchrow={"avg_rating": 4, "total": 5})
        with _pg_true(), _patch_pg(pool):
            result = await get_csat_score_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result == {"avg_rating": 4.0, "total_surveys": 5}

    @pytest.mark.asyncio
    async def test_pg_row_none(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_csat_score_db("t1") == {
                "avg_rating": 0,
                "total_surveys": 0,
            }

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_csat_score_db("t1") is None


class TestResponseRate:
    @pytest.mark.asyncio
    async def test_sqlite_with_data(self):
        conn = FakeConn(fetchone={"total": 10, "responded": 7})
        with _pg_false(), _patch_conn(conn):
            result = await get_response_rate_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result == {
            "response_rate": 70.0,
            "total_sent": 10,
            "total_responded": 7,
        }

    @pytest.mark.asyncio
    async def test_sqlite_zero_total(self):
        conn = FakeConn(fetchone={"total": 0, "responded": 0})
        with _pg_false(), _patch_conn(conn):
            assert await get_response_rate_db("t1") == {
                "response_rate": 0,
                "total_sent": 0,
                "total_responded": 0,
            }

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_response_rate_db("t1") == {
                "response_rate": 0,
                "total_sent": 0,
                "total_responded": 0,
            }

    @pytest.mark.asyncio
    async def test_pg_with_data(self):
        pool = FakePool(fetchrow={"total": 4, "responded": 1})
        with _pg_true(), _patch_pg(pool):
            result = await get_response_rate_db("t1")
        assert result == {
            "response_rate": 25.0,
            "total_sent": 4,
            "total_responded": 1,
        }

    @pytest.mark.asyncio
    async def test_pg_with_filters(self):
        pool = FakePool(fetchrow={"total": 10, "responded": 5})
        with _pg_true(), _patch_pg(pool):
            result = await get_response_rate_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result == {
            "response_rate": 50.0,
            "total_sent": 10,
            "total_responded": 5,
        }
        assert "created_at >= $2" in pool.last_fetch_sql
        assert "created_at <= $3" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_zero_total(self):
        pool = FakePool(fetchrow={"total": 0, "responded": 0})
        with _pg_true(), _patch_pg(pool):
            assert await get_response_rate_db("t1") == {
                "response_rate": 0,
                "total_sent": 0,
                "total_responded": 0,
            }

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_response_rate_db("t1") is None


class TestNpsScore:
    @pytest.mark.asyncio
    async def test_sqlite_with_data(self):
        conn = FakeConn(
            fetchone={
                "total": 10,
                "promoters": 5,
                "passives": 2,
                "detractors": 3,
            }
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_nps_score_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result == {
            "nps": 20.0,
            "promoters": 5,
            "passives": 2,
            "detractors": 3,
            "total": 10,
        }

    @pytest.mark.asyncio
    async def test_sqlite_zero_total(self):
        conn = FakeConn(
            fetchone={
                "total": 0,
                "promoters": 0,
                "passives": 0,
                "detractors": 0,
            }
        )
        with _pg_false(), _patch_conn(conn):
            assert await get_nps_score_db("t1") == {
                "nps": 0,
                "promoters": 0,
                "passives": 0,
                "detractors": 0,
                "total": 0,
            }

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_nps_score_db("t1") == {
                "nps": 0,
                "promoters": 0,
                "passives": 0,
                "detractors": 0,
                "total": 0,
            }

    @pytest.mark.asyncio
    async def test_pg_with_data(self):
        pool = FakePool(
            fetchrow={
                "total": 4,
                "promoters": 2,
                "passives": 1,
                "detractors": 1,
            }
        )
        with _pg_true(), _patch_pg(pool):
            result = await get_nps_score_db("t1")
        assert result == {
            "nps": 25.0,
            "promoters": 2,
            "passives": 1,
            "detractors": 1,
            "total": 4,
        }

    @pytest.mark.asyncio
    async def test_pg_with_filters(self):
        pool = FakePool(
            fetchrow={
                "total": 10,
                "promoters": 5,
                "passives": 2,
                "detractors": 3,
            }
        )
        with _pg_true(), _patch_pg(pool):
            result = await get_nps_score_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result == {
            "nps": 20.0,
            "promoters": 5,
            "passives": 2,
            "detractors": 3,
            "total": 10,
        }
        assert "created_at >= $2" in pool.last_fetch_sql
        assert "created_at <= $3" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_zero_total(self):
        pool = FakePool(
            fetchrow={
                "total": 0,
                "promoters": 0,
                "passives": 0,
                "detractors": 0,
            }
        )
        with _pg_true(), _patch_pg(pool):
            assert await get_nps_score_db("t1") == {
                "nps": 0,
                "promoters": 0,
                "passives": 0,
                "detractors": 0,
                "total": 0,
            }

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_nps_score_db("t1") is None


class TestSentimentTrends:
    @pytest.mark.asyncio
    async def test_sqlite_day_with_filters(self):
        conn = FakeConn(fetchall=[[{"period": "2026-01-01", "sentiment": "positive", "count": 3}]])
        with _pg_false(), _patch_conn(conn):
            result = await get_sentiment_trends_db(
                "t1", start_date="2026-01-01", end_date="2026-01-31"
            )
        assert result == [{"period": "2026-01-01", "sentiment": "positive", "count": 3}]
        assert "date(created_at)" in conn.last_sql
        assert "created_at >= ?" in conn.last_sql
        assert "created_at <= ?" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_hour_no_filters(self):
        conn = FakeConn(fetchall=[[{"period": "2026-01-01 10:00:00", "sentiment": "neutral", "count": 1}]])
        with _pg_false(), _patch_conn(conn):
            result = await get_sentiment_trends_db("t1", granularity="hour")
        assert result == [{"period": "2026-01-01 10:00:00", "sentiment": "neutral", "count": 1}]
        assert "strftime('%Y-%m-%d %H:00:00'" in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await get_sentiment_trends_db("t1") == []

    @pytest.mark.asyncio
    async def test_pg_day_with_filters(self):
        pool = FakePool(fetch=[[{"period": "2026-01-01", "sentiment": "positive", "count": 2}]])
        with _pg_true(), _patch_pg(pool):
            result = await get_sentiment_trends_db(
                "t1", start_date="2026-01-01", end_date="2026-01-31"
            )
        assert result == [{"period": "2026-01-01", "sentiment": "positive", "count": 2}]
        assert "date_trunc('day', created_at)" in pool.last_fetch_sql
        assert "created_at >= $2" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_hour_no_filters(self):
        pool = FakePool(fetch=[[{"period": "2026-01-01 10:00:00", "sentiment": "negative", "count": 1}]])
        with _pg_true(), _patch_pg(pool):
            result = await get_sentiment_trends_db("t1", granularity="hour")
        assert result == [{"period": "2026-01-01 10:00:00", "sentiment": "negative", "count": 1}]
        assert "date_trunc('hour', created_at)" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_sentiment_trends_db("t1") is None


class TestCustomer360:
    @pytest.mark.asyncio
    async def test_sqlite_all(self):
        conn = FakeConn(
            fetchall=[
                [{"id": "i1", "interaction_type": "call"}],
                [{"id": "s1", "rating": 5}],
            ],
            fetchone=[
                {
                    "interaction_types": 2,
                    "total_interactions": 3,
                    "sentiment_avg": 0.75,
                },
                {"avg_csat": 4.5, "survey_count": 2},
            ],
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_customer_360_db("t1", "cust1")
        assert result["customer_id"] == "cust1"
        assert result["interactions"] == [{"id": "i1", "interaction_type": "call"}]
        assert result["surveys"] == [{"id": "s1", "rating": 5}]
        assert result["summary"]["interaction_types"] == 2
        assert result["summary"]["avg_csat"] == 4.5
        assert result["summary"]["survey_count"] == 2
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_summaries(self):
        conn = FakeConn(fetchall=[[], []], fetchone=[None, None])
        with _pg_false(), _patch_conn(conn):
            result = await get_customer_360_db("t1", "cust1")
        assert result == {
            "customer_id": "cust1",
            "interactions": [],
            "surveys": [],
            "summary": {},
        }

    @pytest.mark.asyncio
    async def test_pg_all(self):
        pool = FakePool(
            fetch=[
                [{"id": "i1"}],
                [{"id": "s1"}],
            ],
            fetchrow=[
                {
                    "interaction_types": 1,
                    "total_interactions": 1,
                    "sentiment_avg": 1.0,
                },
                {"avg_csat": 5, "survey_count": 1},
            ],
        )
        with _pg_true(), _patch_pg(pool):
            result = await get_customer_360_db("t1", "cust1")
        assert result["interactions"] == [{"id": "i1"}]
        assert result["surveys"] == [{"id": "s1"}]
        assert result["summary"]["avg_csat"] == 5.0
        assert result["summary"]["survey_count"] == 1

    @pytest.mark.asyncio
    async def test_pg_summary_none(self):
        pool = FakePool(
            fetch=[[], []],
            fetchrow=[None, {"avg_csat": 3, "survey_count": 4}],
        )
        with _pg_true(), _patch_pg(pool):
            result = await get_customer_360_db("t1", "cust1")
        assert result["summary"] == {"avg_csat": 3.0, "survey_count": 4}

    @pytest.mark.asyncio
    async def test_pg_csat_none(self):
        pool = FakePool(
            fetch=[[], []],
            fetchrow=[
                {"interaction_types": 1, "total_interactions": 1, "sentiment_avg": 0.5},
                None,
            ],
        )
        with _pg_true(), _patch_pg(pool):
            result = await get_customer_360_db("t1", "cust1")
        assert result["summary"] == {
            "interaction_types": 1,
            "total_interactions": 1,
            "sentiment_avg": 0.5,
        }
        assert "avg_csat" not in result["summary"]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            result = await get_customer_360_db("t1", "cust1")
        assert result == {
            "customer_id": "cust1",
            "interactions": [],
            "surveys": [],
            "summary": {},
        }
