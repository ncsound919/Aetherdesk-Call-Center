"""Unit tests for src/api/services/db_ai_platform.py.

Uses the established fake-sqlite / fake-asyncpg pattern from
test_db_platform_ops.py: FakeConn for the SQLite branch, FakePool for the
Postgres branch, and patch() of the module-level USE_POSTGRES / _get_sqlite_conn
/ get_pg_pool globals.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.services.db_ai_platform as module
from api.services.db_ai_platform import (
    create_dataset_db,
    create_eval_metrics_db,
    create_emotion_log_db,
    create_external_job_db,
    create_label_db,
    create_model_audit_log_db,
    create_model_db,
    create_training_job_db,
    create_turn_db,
    create_voice_profile_db,
    get_active_model_db,
    get_dataset_db,
    get_eval_metrics_db,
    get_emotion_trends_db,
    get_model_audit_log_db,
    get_model_db,
    get_model_version_db,
    get_training_job_db,
    list_datasets_db,
    list_external_jobs_db,
    list_labels_db,
    list_models_db,
    list_training_jobs_db,
    list_turns_db,
    list_voice_profiles_db,
    promote_model_db,
    rollback_model_db,
    update_dataset_db,
    update_training_job_db,
)

ROW = {"id": "r1", "tenant_id": "t1", "name": "x"}


class FakeConn:
    """Minimal synchronous sqlite connection double.

    ``fetchone`` returns a static value, or pops from a list of values when a
    list is supplied (used where a function performs multiple fetchone calls,
    e.g. promote_model_db).
    """

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
        if isinstance(self._one, list):
            if self._one:
                return self._one.pop(0)
            return None
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
        "api.services.db_ai_platform._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_ai_platform.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_ai_platform.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_ai_platform.USE_POSTGRES", False)


class TestCreateModel:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_model_db("t1", "m", "1.0")
        assert result == ROW
        assert "INSERT INTO ai_models" in conn.executed_sqls[0]
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_model_db("t1", "m", "1.0") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            result = await create_model_db("t1", "m", "1.0")
        assert result == ROW
        assert "INSERT INTO ai_models" in pool.executed[0][0]

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await create_model_db("t1", "m", "1.0") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_model_db("t1", "m", "1.0") is None


class TestListModels:
    @pytest.mark.asyncio
    async def test_sqlite_plain(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_models_db("t1")
        assert result == [ROW]
        assert "AND model_type" not in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_filtered(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_models_db("t1", model_type="intent")
        assert result == [ROW]
        assert "AND model_type = ?" in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_models_db("t1") == []

    @pytest.mark.asyncio
    async def test_pg_plain(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            assert await list_models_db("t1") == [ROW]

    @pytest.mark.asyncio
    async def test_pg_filtered(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            result = await list_models_db("t1", model_type="intent")
        assert result == [ROW]
        assert "AND model_type = $2" in pool.fetched[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_models_db("t1") == []


class TestGetModel:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            assert await get_model_db("t1", "m1") == ROW

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_model_db("t1", "m1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await get_model_db("t1", "m1") == ROW

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_model_db("t1", "m1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_model_db("t1", "m1") is None


class TestGetModelVersion:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            assert await get_model_version_db("t1", "m1", "1.0") == ROW

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_model_version_db("t1", "m1", "1.0") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await get_model_version_db("t1", "m1", "1.0") == ROW

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_model_version_db("t1", "m1", "1.0") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_model_version_db("t1", "m1", "1.0") is None


class TestPromoteModel:
    @pytest.mark.asyncio
    async def test_sqlite_with_type_row(self):
        conn = FakeConn(fetchone=[{"model_type": "intent"}, ROW])
        with _pg_false(), _patch_conn(conn):
            result = await promote_model_db("t1", "m1", "1.0", "production")
        assert result == ROW
        assert any("SET status = 'staging'" in s for s in conn.executed_sqls)
        assert any("SET status = ?" in s for s in conn.executed_sqls)
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_without_type_row(self):
        conn = FakeConn(fetchone=[None, ROW])
        with _pg_false(), _patch_conn(conn):
            result = await promote_model_db("t1", "m1", "1.0")
        assert result == ROW
        assert not any("'staging'" in s for s in conn.executed_sqls)

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=[{"model_type": "intent"}, None])
        with _pg_false(), _patch_conn(conn):
            assert await promote_model_db("t1", "m1", "1.0") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            result = await promote_model_db("t1", "m1", "1.0", "production")
        assert result == ROW
        assert len(pool.executed) == 2

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await promote_model_db("t1", "m1", "1.0") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await promote_model_db("t1", "m1", "1.0") is None


class TestRollbackModel:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await rollback_model_db("t1", "m1", "1.0")
        assert result == ROW
        assert len(conn.executed_sqls) == 3
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await rollback_model_db("t1", "m1", "1.0") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await rollback_model_db("t1", "m1", "1.0") == ROW

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await rollback_model_db("t1", "m1", "1.0") is None


class TestGetActiveModel:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            assert await get_active_model_db("t1") == ROW

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_active_model_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await get_active_model_db("t1", "sentiment") == ROW

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_active_model_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_active_model_db("t1") is None


class TestCreateTrainingJob:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_training_job_db("t1", "job", "gpt")
        assert result == ROW
        assert "INSERT INTO training_jobs" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_training_job_db("t1", "job", "gpt") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await create_training_job_db("t1", "job", "gpt") == ROW

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_training_job_db("t1", "job", "gpt") is None


class TestGetTrainingJob:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            assert await get_training_job_db("j1") == ROW

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_training_job_db("j1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await get_training_job_db("j1") == ROW

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_training_job_db("j1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_training_job_db("j1") is None


class TestListTrainingJobs:
    @pytest.mark.asyncio
    async def test_sqlite_rows(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            assert await list_training_jobs_db("t1") == [ROW]

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_training_jobs_db("t1") == []

    @pytest.mark.asyncio
    async def test_pg_rows(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            assert await list_training_jobs_db("t1") == [ROW]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_training_jobs_db("t1") == []


class TestUpdateTrainingJob:
    @pytest.mark.asyncio
    async def test_sqlite_all_fields_completed(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await update_training_job_db(
                "j1",
                status="completed",
                progress=0.5,
                example_count=10,
                result_json="{}",
                error_message="err",
            )
        assert result == ROW
        assert "status = ?" in conn.executed_sqls[0]
        assert "progress = ?" in conn.executed_sqls[0]
        assert "example_count = ?" in conn.executed_sqls[0]
        assert "result_json = ?" in conn.executed_sqls[0]
        assert "error_message = ?" in conn.executed_sqls[0]
        assert "completed_at = ?" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_fields(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await update_training_job_db("j1")
        assert result == ROW
        assert all(s.startswith("SELECT") for s in conn.executed_sqls)

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await update_training_job_db("j1", status="done") is None

    @pytest.mark.asyncio
    async def test_pg_all_fields_completed(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            result = await update_training_job_db(
                "j1",
                status="completed",
                progress=0.5,
                example_count=10,
                result_json="{}",
                error_message="err",
            )
        assert result == ROW
        sql, params = pool.executed[0]
        assert "UPDATE training_jobs SET" in sql
        assert "completed_at = NOW()" in sql
        assert params[-1] == "j1"

    @pytest.mark.asyncio
    async def test_pg_no_fields(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            result = await update_training_job_db("j1")
        assert result == ROW
        assert pool.executed == []

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_training_job_db("j1", status="done") is None


class TestVoiceProfiles:
    @pytest.mark.asyncio
    async def test_create_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_voice_profile_db("t1", "Alice")
        assert result == ROW
        assert "INSERT INTO voice_profiles" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_voice_profile_db("t1", "Alice") is None

    @pytest.mark.asyncio
    async def test_create_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await create_voice_profile_db("t1", "Alice") == ROW

    @pytest.mark.asyncio
    async def test_create_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_voice_profile_db("t1", "Alice") is None

    @pytest.mark.asyncio
    async def test_list_sqlite_rows(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            assert await list_voice_profiles_db("t1") == [ROW]

    @pytest.mark.asyncio
    async def test_list_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_voice_profiles_db("t1") == []

    @pytest.mark.asyncio
    async def test_list_pg_rows(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            assert await list_voice_profiles_db("t1") == [ROW]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_voice_profiles_db("t1") == []


class TestEmotionLogs:
    @pytest.mark.asyncio
    async def test_create_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_emotion_log_db("t1", "call-1", "agent", "happy", 0.9, 100)
        assert result == ROW
        assert "INSERT INTO emotion_logs" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_emotion_log_db("t1", "call-1") is None

    @pytest.mark.asyncio
    async def test_create_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await create_emotion_log_db("t1", "call-1") == ROW

    @pytest.mark.asyncio
    async def test_create_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_emotion_log_db("t1", "call-1") is None

    @pytest.mark.asyncio
    async def test_trends_sqlite_rows(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            assert await get_emotion_trends_db("t1", "call-1") == [ROW]

    @pytest.mark.asyncio
    async def test_trends_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await get_emotion_trends_db("t1", "call-1") == []

    @pytest.mark.asyncio
    async def test_trends_pg_rows(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            assert await get_emotion_trends_db("t1", "call-1") == [ROW]

    @pytest.mark.asyncio
    async def test_trends_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_emotion_trends_db("t1", "call-1") == []


class TestDatasets:
    @pytest.mark.asyncio
    async def test_create_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_dataset_db("t1", "ds")
        assert result == ROW
        assert "INSERT INTO datasets" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_dataset_db("t1", "ds") is None

    @pytest.mark.asyncio
    async def test_create_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await create_dataset_db("t1", "ds") == ROW

    @pytest.mark.asyncio
    async def test_create_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_dataset_db("t1", "ds") is None

    @pytest.mark.asyncio
    async def test_list_sqlite_plain(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            assert await list_datasets_db("t1") == [ROW]

    @pytest.mark.asyncio
    async def test_list_sqlite_filtered(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_datasets_db("t1", recipe_type="qa", limit=10)
        assert result == [ROW]
        assert "AND recipe_type = ?" in conn.last_sql
        assert "LIMIT ?" in conn.last_sql

    @pytest.mark.asyncio
    async def test_list_pg_filtered(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            result = await list_datasets_db("t1", recipe_type="qa", limit=10)
        assert result == [ROW]
        sql, params = pool.fetched[0]
        assert "AND recipe_type = $2" in sql
        assert params == ("t1", "qa", 10)

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_datasets_db("t1") == []

    @pytest.mark.asyncio
    async def test_get_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            assert await get_dataset_db("ds1") == ROW

    @pytest.mark.asyncio
    async def test_get_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_dataset_db("ds1") is None

    @pytest.mark.asyncio
    async def test_get_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await get_dataset_db("ds1") == ROW

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_dataset_db("ds1") is None


class TestUpdateDataset:
    @pytest.mark.asyncio
    async def test_sqlite_all_fields(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await update_dataset_db(
                "ds1",
                total_examples=5,
                total_turns=2,
                quality_score=0.8,
                stats_json="{}",
                status="ready",
            )
        assert result == ROW
        for col in (
            "total_examples = ?",
            "total_turns = ?",
            "quality_score = ?",
            "stats_json = ?",
            "status = ?",
        ):
            assert col in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_fields(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await update_dataset_db("ds1")
        assert result == ROW
        assert all(s.startswith("SELECT") for s in conn.executed_sqls)

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await update_dataset_db("ds1", status="ready") is None

    @pytest.mark.asyncio
    async def test_pg_all_fields(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            result = await update_dataset_db(
                "ds1",
                total_examples=5,
                total_turns=2,
                quality_score=0.8,
                stats_json="{}",
                status="ready",
            )
        assert result == ROW
        sql, params = pool.executed[0]
        assert "UPDATE datasets SET" in sql
        assert "stats_json = $4::jsonb" in sql
        assert params == (5, 2, 0.8, "{}", "ready", "ds1")

    @pytest.mark.asyncio
    async def test_pg_no_fields(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            result = await update_dataset_db("ds1")
        assert result == ROW
        assert pool.executed == []

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_dataset_db("ds1", status="ready") is None


class TestTurns:
    @pytest.mark.asyncio
    async def test_create_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_turn_db("t1", text="hello")
        assert result == ROW
        assert "INSERT INTO turns" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_turn_db("t1", text="hello") is None

    @pytest.mark.asyncio
    async def test_create_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await create_turn_db("t1", text="hello") == ROW

    @pytest.mark.asyncio
    async def test_create_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_turn_db("t1", text="hello") is None

    @pytest.mark.asyncio
    async def test_list_sqlite_rows(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            assert await list_turns_db("ds1") == [ROW]

    @pytest.mark.asyncio
    async def test_list_pg_rows(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            assert await list_turns_db("ds1", limit=100, offset=10) == [ROW]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_turns_db("ds1") == []


class TestLabels:
    @pytest.mark.asyncio
    async def test_create_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_label_db("t1", "turn-1", label_value="billing")
        assert result == ROW
        assert "INSERT INTO labels" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_label_db("t1", "turn-1", label_value="billing") is None

    @pytest.mark.asyncio
    async def test_create_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await create_label_db("t1", "turn-1", label_value="billing") == ROW

    @pytest.mark.asyncio
    async def test_create_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_label_db("t1", "turn-1", label_value="billing") is None

    @pytest.mark.asyncio
    async def test_list_sqlite_rows(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            assert await list_labels_db("turn-1") == [ROW]

    @pytest.mark.asyncio
    async def test_list_pg_rows(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            assert await list_labels_db("turn-1") == [ROW]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_labels_db("turn-1") == []


class TestExternalJobs:
    @pytest.mark.asyncio
    async def test_create_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_external_job_db("t1", "m1", "1.0", "ext-1")
        assert result == ROW
        assert "INSERT INTO external_jobs" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_external_job_db("t1", "m1", "1.0", "ext-1") is None

    @pytest.mark.asyncio
    async def test_create_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await create_external_job_db("t1", "m1", "1.0", "ext-1") == ROW

    @pytest.mark.asyncio
    async def test_create_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_external_job_db("t1", "m1", "1.0", "ext-1") is None

    @pytest.mark.asyncio
    async def test_list_sqlite_rows(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            assert await list_external_jobs_db("t1", "m1") == [ROW]

    @pytest.mark.asyncio
    async def test_list_pg_rows(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            assert await list_external_jobs_db("t1", "m1") == [ROW]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_external_jobs_db("t1", "m1") == []


class TestModelAuditLog:
    @pytest.mark.asyncio
    async def test_create_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_model_audit_log_db(
                "t1", "m1", "1.0", "registered", actor="admin"
            )
        assert result == ROW
        assert "INSERT INTO model_audit_log" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_model_audit_log_db("t1", "m1", "1.0", "registered") is None

    @pytest.mark.asyncio
    async def test_create_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await create_model_audit_log_db(
                "t1", "m1", "1.0", "registered", "s", "n", "admin"
            ) == ROW

    @pytest.mark.asyncio
    async def test_create_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_model_audit_log_db("t1", "m1", "1.0", "registered") is None

    @pytest.mark.asyncio
    async def test_get_sqlite_rows(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            assert await get_model_audit_log_db("t1", "m1") == [ROW]

    @pytest.mark.asyncio
    async def test_get_pg_rows(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            assert await get_model_audit_log_db("t1", "m1") == [ROW]

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_model_audit_log_db("t1", "m1") == []


class TestEvalMetrics:
    @pytest.mark.asyncio
    async def test_create_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_eval_metrics_db("t1", "m1", "1.0", '{"acc": 0.9}')
        assert result == ROW
        assert "INSERT INTO eval_metrics" in conn.executed_sqls[0]
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_eval_metrics_db("t1", "m1", "1.0") is None

    @pytest.mark.asyncio
    async def test_create_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            assert await create_eval_metrics_db("t1", "m1", "1.0") == ROW

    @pytest.mark.asyncio
    async def test_create_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_eval_metrics_db("t1", "m1", "1.0") is None

    @pytest.mark.asyncio
    async def test_get_sqlite_rows(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            assert await get_eval_metrics_db("t1", "m1", "1.0") == [ROW]

    @pytest.mark.asyncio
    async def test_get_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await get_eval_metrics_db("t1", "m1", "1.0") == []

    @pytest.mark.asyncio
    async def test_get_pg_rows(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            assert await get_eval_metrics_db("t1", "m1", "1.0") == [ROW]

    @pytest.mark.asyncio
    async def test_get_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_eval_metrics_db("t1", "m1", "1.0") == []
