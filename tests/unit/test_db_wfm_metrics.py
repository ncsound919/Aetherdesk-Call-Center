"""Unit tests for src/api/services/db_wfm_metrics.py (AHT/FCR/CSAT/NPS data access)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_wfm_metrics import (
    create_aht_db,
    create_csat_db,
    create_fcr_db,
    create_nps_db,
    get_aht_stats_db,
    get_csat_trend_db,
    get_fcr_stats_db,
    get_nps_stats_db,
    list_aht_db,
    list_csat_db,
    list_fcr_db,
)


class FakeConn:
    def __init__(self, fetchone=None, fetchall=None):
        self._one = fetchone
        self._all = fetchall
        self.closed = False
        self.committed = False
        self.last_sql = None
        self.last_params = None
        self.executed_sqls = []
        self.executed = []

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed_sqls.append(sql)
        self.executed.append((sql, params))
        return self

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class FakePool:
    def __init__(self, fetchrow=None, fetch=None, fetchval=None):
        self._row = fetchrow
        self._rows = fetch if fetch is not None else []
        self._val = fetchval
        self.executed = []
        self.fetchrow_sqls = []
        self.fetch_calls = []
        self.fetchval_sqls = []

    async def fetchrow(self, sql, *params):
        self.fetchrow_sqls.append(sql)
        if isinstance(self._row, list):
            return self._row.pop(0) if self._row else None
        return self._row

    async def fetch(self, sql, *params):
        self.fetch_calls.append((sql, params))
        return self._rows

    async def fetchval(self, sql, *params):
        self.fetchval_sqls.append(sql)
        return self._val

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return "OK"


def _patch_conn(conn):
    return patch(
        "api.services.db_wfm_metrics._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _find_sql(conn, fragment):
    for sql, params in conn.executed:
        if fragment in sql:
            return sql, params
    return None, None


def _patch_pg(pool):
    return patch(
        "api.services.db_wfm_metrics.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_wfm_metrics.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_wfm_metrics.USE_POSTGRES", False)


class TestCreateAht:
    @pytest.mark.asyncio
    async def test_sqlite_inserts_and_returns(self):
        conn = FakeConn(fetchone={"id": "a1", "duration_seconds": 120})
        with _pg_false(), _patch_conn(conn):
            result = await create_aht_db("t1", "agent1", "call1", 120)
        assert result == {"id": "a1", "duration_seconds": 120}
        sql, params = _find_sql(conn, "INSERT INTO wfm_aht")
        assert sql is not None
        assert params[1] == "t1"
        assert params[2] == "agent1"
        assert conn.committed is True
        assert conn.closed is True
        assert "SELECT * FROM wfm_aht WHERE id = ?" in conn.last_sql
        assert len(conn.last_params) == 1

    @pytest.mark.asyncio
    async def test_sqlite_missing_returns_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_aht_db("t1", "agent1", "call1", 120) is None

    @pytest.mark.asyncio
    async def test_pg_inserts_and_returns(self):
        pool = FakePool(fetchrow={"id": "a1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_aht_db("t1", "agent1", "call1", 120)
        assert result == {"id": "a1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO wfm_aht" in sql
        assert params[1] == "t1"
        assert params[2] == "agent1"

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_aht_db("t1", "agent1", "call1", 120) is None


class TestCreateFcr:
    @pytest.mark.asyncio
    async def test_sqlite_resolved_true(self):
        conn = FakeConn(fetchone={"id": "f1", "resolved": 1})
        with _pg_false(), _patch_conn(conn):
            result = await create_fcr_db("t1", "cu1", "call1", True, "follow1")
        assert result == {"id": "f1", "resolved": 1}
        sql, params = _find_sql(conn, "INSERT INTO wfm_fcr")
        assert sql is not None
        assert params[4] == 1
        assert params[5] == "follow1"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_resolved_false(self):
        conn = FakeConn(fetchone={"id": "f1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_fcr_db("t1", "cu1", "call1", False)
        assert result == {"id": "f1"}
        _, params = _find_sql(conn, "INSERT INTO wfm_fcr")
        assert params[4] == 0
        assert params[5] is None

    @pytest.mark.asyncio
    async def test_pg_resolved_false(self):
        pool = FakePool(fetchrow=[{"id": "f1"}])
        with _pg_true(), _patch_pg(pool):
            result = await create_fcr_db("t1", "cu1", "call1", False)
        assert result == {"id": "f1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO wfm_fcr" in sql
        assert params[4] == 0

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_fcr_db("t1", "cu1", "call1", True) is None


class TestCreateCsat:
    @pytest.mark.asyncio
    async def test_sqlite_inserts_and_returns(self):
        conn = FakeConn(fetchone={"id": "c1", "rating": 5})
        with _pg_false(), _patch_conn(conn):
            result = await create_csat_db("t1", "cu1", "call1", 5)
        assert result == {"id": "c1", "rating": 5}
        sql, params = _find_sql(conn, "INSERT INTO wfm_csat")
        assert sql is not None
        assert params[4] == 5
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_missing_returns_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_csat_db("t1", "cu1", "call1", 5) is None

    @pytest.mark.asyncio
    async def test_pg_inserts_and_returns(self):
        pool = FakePool(fetchrow={"id": "c1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_csat_db("t1", "cu1", "call1", 4)
        assert result == {"id": "c1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO wfm_csat" in sql
        assert params[4] == 4

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_csat_db("t1", "cu1", "call1", 4) is None


class TestCreateNps:
    @pytest.mark.asyncio
    async def test_sqlite_inserts_and_returns(self):
        conn = FakeConn(fetchone={"id": "n1", "score": 9})
        with _pg_false(), _patch_conn(conn):
            result = await create_nps_db("t1", "cu1", "call1", 9)
        assert result == {"id": "n1", "score": 9}
        sql, params = _find_sql(conn, "INSERT INTO wfm_nps")
        assert sql is not None
        assert params[4] == 9
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_missing_returns_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_nps_db("t1", "cu1", "call1", 9) is None

    @pytest.mark.asyncio
    async def test_pg_inserts_and_returns(self):
        pool = FakePool(fetchrow={"id": "n1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_nps_db("t1", "cu1", "call1", 9)
        assert result == {"id": "n1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO wfm_nps" in sql
        assert params[4] == 9

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_nps_db("t1", "cu1", "call1", 9) is None


class TestGetAhtStats:
    @pytest.mark.asyncio
    async def test_sqlite_empty_returns_zeros(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            result = await get_aht_stats_db("t1")
        assert result == {"avg": 0, "p50": 0, "p90": 0, "p99": 0, "count": 0}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_single_value(self):
        conn = FakeConn(fetchall=[{"duration_seconds": 100}])
        with _pg_false(), _patch_conn(conn):
            result = await get_aht_stats_db("t1", "24h")
        assert result["avg"] == 100.0
        assert result["p50"] == 100.0
        assert result["p90"] == 100.0
        assert result["p99"] == 100.0
        assert result["count"] == 1
        assert conn.last_params == ("t1", "-1 days")

    @pytest.mark.asyncio
    async def test_sqlite_multiple_values_interpolates(self):
        conn = FakeConn(fetchall=[{"duration_seconds": d} for d in (100, 200, 300)])
        with _pg_false(), _patch_conn(conn):
            result = await get_aht_stats_db("t1", "30d")
        assert result["avg"] == 200.0
        assert result["p50"] == 200.0
        assert result["p90"] == 280.0
        assert result["p99"] == 298.0
        assert result["count"] == 3

    @pytest.mark.asyncio
    async def test_sqlite_unknown_period_default(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            result = await get_aht_stats_db("t1", "bogus")
        assert result["count"] == 0
        assert conn.last_params == ("t1", "-7 days")

    @pytest.mark.asyncio
    async def test_pg_computes_stats(self):
        pool = FakePool(fetch=[{"duration_seconds": d} for d in (100, 200, 300)])
        with _pg_true(), _patch_pg(pool):
            result = await get_aht_stats_db("t1", "90d")
        assert result["avg"] == 200.0
        assert result["count"] == 3
        assert "INTERVAL '90 days'" in pool.fetch_calls[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool_raises_name_error(self):
        with _pg_true(), _patch_pg(None):
            with pytest.raises(NameError):
                await get_aht_stats_db("t1")


class TestGetFcrStats:
    @pytest.mark.asyncio
    async def test_sqlite_empty_returns_zeros(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            result = await get_fcr_stats_db("t1")
        assert result == {"fcr_rate": 0.0, "resolved": 0, "total": 0}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_mixed_resolutions(self):
        conn = FakeConn(fetchall=[{"resolved": 1}, {"resolved": 0}, {"resolved": 1}])
        with _pg_false(), _patch_conn(conn):
            result = await get_fcr_stats_db("t1", "7d")
        assert result["fcr_rate"] == round(2 / 3 * 100, 2)
        assert result["resolved"] == 2
        assert result["total"] == 3

    @pytest.mark.asyncio
    async def test_sqlite_all_resolved(self):
        conn = FakeConn(fetchall=[{"resolved": 1}, {"resolved": 1}])
        with _pg_false(), _patch_conn(conn):
            result = await get_fcr_stats_db("t1", "bogus")
        assert result["fcr_rate"] == 100.0
        assert conn.last_params == ("t1", "-7 days")

    @pytest.mark.asyncio
    async def test_pg_computes_stats(self):
        pool = FakePool(fetch=[{"resolved": 1}, {"resolved": 1}, {"resolved": 0}])
        with _pg_true(), _patch_pg(pool):
            result = await get_fcr_stats_db("t1", "24h")
        assert result["resolved"] == 2
        assert result["total"] == 3
        assert "INTERVAL '24 hours'" in pool.fetch_calls[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool_raises_name_error(self):
        with _pg_true(), _patch_pg(None):
            with pytest.raises(NameError):
                await get_fcr_stats_db("t1")


class TestGetCsatTrend:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(
            fetchall=[
                {"date": "2024-01-01", "avg_rating": 4.567, "count": 10},
                {"date": "2024-01-02", "avg_rating": 5.0, "count": 2},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_csat_trend_db("t1", "30d")
        assert result == [
            {"date": "2024-01-01", "avg_rating": 4.57, "count": 10},
            {"date": "2024-01-02", "avg_rating": 5.0, "count": 2},
        ]
        assert conn.last_params == ("t1", "-30 days")
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await get_csat_trend_db("t1") == []

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[{"date": "2024-01-01", "avg_rating": 4.567, "count": 10}])
        with _pg_true(), _patch_pg(pool):
            result = await get_csat_trend_db("t1", "90d")
        assert result == [{"date": "2024-01-01", "avg_rating": 4.57, "count": 10}]
        assert "INTERVAL '90 days'" in pool.fetch_calls[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_empty(self):
        with _pg_true(), _patch_pg(None):
            assert await get_csat_trend_db("t1") == []


class TestGetNpsStats:
    @pytest.mark.asyncio
    async def test_sqlite_empty_returns_zeros(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            result = await get_nps_stats_db("t1")
        assert result == {
            "nps_score": 0,
            "promoters": 0,
            "passives": 0,
            "detractors": 0,
            "total": 0,
        }
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_mixed_scores(self):
        conn = FakeConn(
            fetchall=[
                {"score": 9},
                {"score": 9},
                {"score": 8},
                {"score": 7},
                {"score": 5},
                {"score": 3},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_nps_stats_db("t1", "30d")
        assert result["promoters"] == 2
        assert result["passives"] == 2
        assert result["detractors"] == 2
        assert result["total"] == 6
        assert result["nps_score"] == 0.0

    @pytest.mark.asyncio
    async def test_sqlite_all_promoters(self):
        conn = FakeConn(fetchall=[{"score": 10}, {"score": 9}])
        with _pg_false(), _patch_conn(conn):
            result = await get_nps_stats_db("t1", "bogus")
        assert result["nps_score"] == 100.0
        assert result["promoters"] == 2
        assert conn.last_params == ("t1", "-7 days")

    @pytest.mark.asyncio
    async def test_pg_computes_stats(self):
        pool = FakePool(fetch=[{"score": 10}, {"score": 7}, {"score": 4}])
        with _pg_true(), _patch_pg(pool):
            result = await get_nps_stats_db("t1", "24h")
        assert result["promoters"] == 1
        assert result["passives"] == 1
        assert result["detractors"] == 1
        assert result["total"] == 3
        assert "INTERVAL '24 hours'" in pool.fetch_calls[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool_raises_name_error(self):
        with _pg_true(), _patch_pg(None):
            with pytest.raises(NameError):
                await get_nps_stats_db("t1")


class TestListAht:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[{"id": "a1", "duration_seconds": 120}])
        with _pg_false(), _patch_conn(conn):
            result = await list_aht_db("t1", limit=10)
        assert result == [{"id": "a1", "duration_seconds": 120}]
        assert conn.last_params == ("t1", 10)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[{"id": "a1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_aht_db("t1", limit=5)
        assert result == [{"id": "a1"}]
        sql, params = pool.fetch_calls[0]
        assert "LIMIT $2" in sql
        assert params == ("t1", 5)

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_aht_db("t1") is None


class TestListFcr:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[{"id": "f1", "resolved": 1}])
        with _pg_false(), _patch_conn(conn):
            result = await list_fcr_db("t1")
        assert result == [{"id": "f1", "resolved": 1}]
        assert "LIMIT ?" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[{"id": "f1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_fcr_db("t1", limit=3)
        assert result == [{"id": "f1"}]
        sql, params = pool.fetch_calls[0]
        assert "LIMIT $2" in sql
        assert params == ("t1", 3)

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_fcr_db("t1") is None


class TestListCsat:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[{"id": "c1", "rating": 5}])
        with _pg_false(), _patch_conn(conn):
            result = await list_csat_db("t1", limit=2)
        assert result == [{"id": "c1", "rating": 5}]
        assert conn.last_params == ("t1", 2)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[{"id": "c1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_csat_db("t1")
        assert result == [{"id": "c1"}]
        sql, params = pool.fetch_calls[0]
        assert "LIMIT $2" in sql
        assert params == ("t1", 50)

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_csat_db("t1") is None
