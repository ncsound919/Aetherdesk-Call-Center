"""Unit tests for src/api/services/db_ai_evaluation.py.

Uses the established fake-sqlite / fake-asyncpg pattern from
test_db_platform_ops.py: FakeConn for the SQLite branch, FakePool for the
Postgres branch, and patch() of the module-level USE_POSTGRES / _get_sqlite_conn
/ get_pg_pool globals.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.services.db_ai_evaluation as module
from api.services.db_ai_evaluation import (
    create_evaluation_db,
    create_experiment_db,
    get_accuracy_metrics_db,
    get_confidence_distribution_db,
    get_experiment_db,
    list_evaluations_db,
    list_experiments_db,
    update_experiment_db,
)

ROW = {"id": "r1", "tenant_id": "t1", "name": "x"}


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

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed_sqls.append(sql)
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
    def __init__(self, fetchrow=None, fetch=None):
        self._row = fetchrow
        self._rows = fetch or []
        self.executed = []
        self.fetched = []

    async def fetchrow(self, sql, *params):
        self.fetched.append((sql, params))
        return self._row

    async def fetch(self, sql, *params):
        self.fetched.append((sql, params))
        return self._rows

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return "OK"


def _patch_conn(conn):
    return patch(
        "api.services.db_ai_evaluation._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_ai_evaluation.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_ai_evaluation.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_ai_evaluation.USE_POSTGRES", False)


def _eval_row(**overrides):
    row = {
        "predicted_intent": "billing",
        "actual_intent": "billing",
        "confidence": 0.9,
        "is_correct": True,
    }
    row.update(overrides)
    return row


class TestCreateEvaluation:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_evaluation_db(
                "t1", "exp-1", "call-1", "billing", "billing", 0.9, True
            )
        assert result == ROW
        assert "INSERT INTO ai_evaluation_results" in conn.executed_sqls[0]
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert (
                await create_evaluation_db(
                    "t1", "exp-1", "call-1", "billing", "billing", 0.9, True
                )
                is None
            )

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            result = await create_evaluation_db(
                "t1", "exp-1", "call-1", "billing", "billing", 0.9, True,
                model_used="m1", latency_ms=12.5,
            )
        assert result == ROW
        assert "INSERT INTO ai_evaluation_results" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert (
                await create_evaluation_db(
                    "t1", "exp-1", "call-1", "billing", "billing", 0.9, True
                )
                is None
            )

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert (
                await create_evaluation_db(
                    "t1", "exp-1", "call-1", "billing", "billing", 0.9, True
                )
                is None
            )


class TestListEvaluations:
    @pytest.mark.asyncio
    async def test_sqlite_no_filters(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_evaluations_db("t1")
        assert result == [ROW]
        assert "experiment_id" not in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_with_filters(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_evaluations_db(
                "t1", experiment_id="e1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result == [ROW]
        assert "AND experiment_id = ?" in conn.last_sql
        assert "AND created_at >= ?" in conn.last_sql
        assert "AND created_at <= ?" in conn.last_sql
        assert "LIMIT 100 OFFSET 0" in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_evaluations_db("t1") == []

    @pytest.mark.asyncio
    async def test_pg_with_filters(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            result = await list_evaluations_db(
                "t1", limit=50, offset=5, experiment_id="e1",
                start_date="2026-01-01", end_date="2026-02-01",
            )
        assert result == [ROW]
        sql, params = pool.fetched[0]
        assert "AND experiment_id = $2" in sql
        assert "AND created_at >= $3" in sql
        assert "AND created_at <= $4" in sql
        assert params == ("t1", "e1", "2026-01-01", "2026-02-01")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_evaluations_db("t1") is None


class TestGetAccuracyMetrics:
    @pytest.mark.asyncio
    async def test_pg_with_rows_full_calculation(self):
        rows = [
            _eval_row(),
            _eval_row(predicted_intent="billing", actual_intent="support",
                      is_correct=False, confidence=0.5),
            _eval_row(predicted_intent="support", actual_intent="support",
                      is_correct=True, confidence=1.0),
            _eval_row(predicted_intent="novel", actual_intent=None,
                      is_correct=False, confidence=0.1),
            _eval_row(predicted_intent="ghost", actual_intent="ghost",
                      is_correct=False, confidence=0.2),
        ]
        pool = FakePool(fetch=rows)
        with _pg_true(), _patch_pg(pool):
            result = await get_accuracy_metrics_db("t1")
        assert result["total_evaluations"] == 5
        assert result["accuracy"] == 0.4
        assert result["avg_confidence"] == 0.54
        assert result["intents"]["billing"]["f1"] == round(2 * 0.5 * 1.0 / 1.5, 4)
        assert result["intents"]["support"]["recall"] == 0.5
        assert result["intents"]["novel"]["precision"] == 0.0
        assert result["intents"]["novel"]["f1"] == 0.0
        assert result["confusion_matrix"]["billing->billing"] == 1
        assert result["confusion_matrix"]["unlabeled->novel"] == 1

    @pytest.mark.asyncio
    async def test_pg_empty(self):
        pool = FakePool(fetch=[])
        with _pg_true(), _patch_pg(pool):
            result = await get_accuracy_metrics_db("t1")
        assert result["total_evaluations"] == 0
        assert result["accuracy"] == 0.0
        assert result["intents"] == {}
        assert result["confusion_matrix"] == {}

    @pytest.mark.asyncio
    async def test_pg_with_date_filters(self):
        rows = [_eval_row()]
        pool = FakePool(fetch=rows)
        with _pg_true(), _patch_pg(pool):
            result = await get_accuracy_metrics_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result["total_evaluations"] == 1
        sql, params = pool.fetched[0]
        assert "AND created_at >= $2" in sql
        assert "AND created_at <= $3" in sql
        assert params == ("t1", "2026-01-01", "2026-02-01")

    @pytest.mark.asyncio
    async def test_sqlite_with_filters_and_rows(self):
        rows = [
            _eval_row(predicted_intent="only", actual_intent="only",
                      is_correct=True, confidence=0.7),
            _eval_row(predicted_intent="only", actual_intent="other",
                      is_correct=False, confidence=0.3),
        ]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            result = await get_accuracy_metrics_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result["total_evaluations"] == 2
        assert result["accuracy"] == 0.5
        assert result["avg_confidence"] == 0.5
        assert result["intents"]["only"]["precision"] == 0.5
        assert result["intents"]["other"]["f1"] == 0.0
        assert "AND created_at >= ?" in conn.last_sql
        assert "AND created_at <= ?" in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_empty_returns_defaults(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            result = await get_accuracy_metrics_db("t1")
        assert result == {
            "total_evaluations": 0,
            "accuracy": 0.0,
            "intents": {},
            "confusion_matrix": {},
            "avg_confidence": 0.0,
        }

    @pytest.mark.asyncio
    async def test_pg_no_pool_raises_unbound_local(self):
        """USE_POSTGRES on with no pool leaves `results` unbound."""
        with _pg_true(), _patch_pg(None):
            with pytest.raises(UnboundLocalError):
                await get_accuracy_metrics_db("t1")


class TestCreateExperiment:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_experiment_db(
                "t1", "exp", "desc", "model-a", "model-b", 0.5
            )
        assert result == ROW
        assert "INSERT INTO ai_experiments" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert (
                await create_experiment_db("t1", "exp", "desc", "a", "b", 0.5) is None
            )

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert (
                await create_experiment_db("t1", "exp", "desc", "a", "b", 0.5) == ROW
            )

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await create_experiment_db("t1", "exp", "desc", "a", "b", 0.5) is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_experiment_db("t1", "exp", "desc", "a", "b", 0.5) is None


class TestListExperiments:
    @pytest.mark.asyncio
    async def test_sqlite_no_status(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_experiments_db("t1")
        assert result == [ROW]
        assert "AND status" not in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_with_status(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_experiments_db("t1", status="active")
        assert result == [ROW]
        assert "AND status = ?" in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_experiments_db("t1") == []

    @pytest.mark.asyncio
    async def test_pg_with_status(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            result = await list_experiments_db("t1", status="active")
        assert result == [ROW]
        sql, params = pool.fetched[0]
        assert "AND status = $2" in sql
        assert params == ("t1", "active")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_experiments_db("t1") is None


class TestGetExperiment:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            assert await get_experiment_db("t1", "e1") == ROW

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_experiment_db("t1", "e1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await get_experiment_db("t1", "e1") == ROW

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_experiment_db("t1", "e1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_experiment_db("t1", "e1") is None


class TestUpdateExperiment:
    @pytest.mark.asyncio
    async def test_sqlite_all_fields(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await update_experiment_db(
                "t1", "e1", winner="a", status="completed", stopped_at="2026-01-01"
            )
        assert result == ROW
        assert "winner = ?" in conn.executed_sqls[0]
        assert "status = ?" in conn.executed_sqls[0]
        assert "stopped_at = ?" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_fields_returns_none(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            assert await update_experiment_db("t1", "e1") is None
        assert conn.executed_sqls == []

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await update_experiment_db("t1", "e1", winner="a") is None

    @pytest.mark.asyncio
    async def test_pg_all_fields(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            result = await update_experiment_db(
                "t1", "e1", winner="a", status="completed", stopped_at="2026-01-01"
            )
        assert result == ROW
        sql, params = pool.executed[0]
        assert "UPDATE ai_experiments SET" in sql
        assert params == ("a", "completed", "2026-01-01", "e1", "t1")

    @pytest.mark.asyncio
    async def test_pg_no_fields_returns_none(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await update_experiment_db("t1", "e1") is None
        assert pool.executed == []

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_experiment_db("t1", "e1", winner="a") is None


class TestConfidenceDistribution:
    @pytest.mark.asyncio
    async def test_pg_with_rows(self):
        pool = FakePool(
            fetch=[{"confidence": 0.0}, {"confidence": 0.5}, {"confidence": 1.0}]
        )
        with _pg_true(), _patch_pg(pool):
            result = await get_confidence_distribution_db("t1")
        assert result["total"] == 3
        counts = [b["count"] for b in result["buckets"]]
        assert counts == [1, 0, 1, 0, 1]
        assert result["avg_confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_pg_with_date_filters(self):
        pool = FakePool(fetch=[{"confidence": 0.7}, {"confidence": 0.9}])
        with _pg_true(), _patch_pg(pool):
            result = await get_confidence_distribution_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result["total"] == 2
        sql, params = pool.fetched[0]
        assert "AND created_at >= $2" in sql
        assert "AND created_at <= $3" in sql
        assert params == ("t1", "2026-01-01", "2026-02-01")

    @pytest.mark.asyncio
    async def test_sqlite_with_edge_values(self):
        rows = [
            {"confidence": c}
            for c in [0.0, 0.15, 0.4, 0.99, 1.0, 1.5, -0.1]
        ]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            result = await get_confidence_distribution_db(
                "t1", start_date="2026-01-01", end_date="2026-02-01"
            )
        assert result["total"] == 7
        counts = [b["count"] for b in result["buckets"]]
        # 0.0, 0.15 -> [0,0.2]; 0.4 -> [0.4,0.6); 0.99, 1.0 -> [0.8,1.0]
        assert counts == [2, 0, 1, 0, 2]
        assert "AND created_at >= ?" in conn.last_sql
        assert "AND created_at <= ?" in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            result = await get_confidence_distribution_db("t1")
        assert result["total"] == 0
        assert all(b["count"] == 0 for b in result["buckets"])
        assert result["avg_confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_pg_no_pool_raises_unbound_local(self):
        """USE_POSTGRES on with no pool leaves `confidences` unbound."""
        with _pg_true(), _patch_pg(None):
            with pytest.raises(UnboundLocalError):
                await get_confidence_distribution_db("t1")
