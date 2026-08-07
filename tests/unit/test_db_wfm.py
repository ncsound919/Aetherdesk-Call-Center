"""Unit tests for src/api/services/db_wfm.py (Workforce Management data access)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_wfm import (
    create_qa_rubric_db,
    create_qa_score_db,
    create_schedule_db,
    create_shift_db,
    delete_shift_db,
    get_agent_qa_summary_db,
    get_agent_status_history_db,
    get_call_volume_history_db,
    get_schedule_db,
    list_qa_rubrics_db,
    list_qa_scores_db,
    list_schedules_db,
    list_shifts_db,
    update_schedule_adherence_db,
    update_shift_db,
)


class FakeCursor:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self


class FakeConn:
    def __init__(self, fetchone=None, fetchall=None, cursor_rowcount=1):
        self._one = fetchone
        self._all = fetchall
        self.closed = False
        self.committed = False
        self.last_sql = None
        self.last_params = None
        self.executed_sqls = []
        self.executed = []
        self._cursor_rowcount = cursor_rowcount

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed_sqls.append(sql)
        self.executed.append((sql, params))
        return self

    def fetchone(self):
        if isinstance(self._one, list):
            return self._one.pop(0) if self._one else None
        return self._one

    def fetchall(self):
        return self._all

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True

    def cursor(self):
        return FakeCursor(self._cursor_rowcount)


class FakePool:
    def __init__(self, fetchrow=None, fetch=None, fetchval=None, execute_result="OK"):
        self._row = fetchrow
        self._rows = fetch if fetch is not None else []
        self._val = fetchval
        self.execute_result = execute_result
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
        if isinstance(self._val, list):
            return self._val.pop(0) if self._val else None
        return self._val

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return self.execute_result


def _patch_conn(conn):
    return patch("api.services.db_wfm._get_sqlite_conn", MagicMock(return_value=conn))


def _find_sql(conn, fragment):
    for sql, params in conn.executed:
        if fragment in sql:
            return sql, params
    return None, None


def _patch_conns(*conns):
    return patch("api.services.db_wfm._get_sqlite_conn", MagicMock(side_effect=list(conns)))


def _patch_pg(pool):
    return patch(
        "api.services.db_wfm.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_wfm.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_wfm.USE_POSTGRES", False)


class TestCreateShift:
    @pytest.mark.asyncio
    async def test_sqlite_inserts_and_returns(self):
        conn = FakeConn(fetchone={"id": "s1", "status": "scheduled"})
        with _pg_false(), _patch_conn(conn):
            result = await create_shift_db("t1", "a1", "09:00", "17:00", "regular", "note")
        assert result == {"id": "s1", "status": "scheduled"}
        sql, params = _find_sql(conn, "INSERT INTO wfm_shifts")
        assert sql is not None
        assert params[1] == "t1"
        assert params[2] == "a1"
        assert conn.committed is True
        assert conn.closed is True
        assert "SELECT * FROM wfm_shifts WHERE id = ?" in conn.last_sql
        assert len(conn.last_params) == 1

    @pytest.mark.asyncio
    async def test_sqlite_missing_after_insert_returns_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_shift_db("t1", "a1", "09:00", "17:00") is None

    @pytest.mark.asyncio
    async def test_pg_inserts_and_returns(self):
        pool = FakePool(fetchrow={"id": "s1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_shift_db("t1", "a1", "09:00", "17:00")
        assert result == {"id": "s1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO wfm_shifts" in sql
        assert len(params) == 7
        assert params[1] == "t1"
        assert params[2] == "a1"

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_shift_db("t1", "a1", "09:00", "17:00") is None


class TestListShifts:
    @pytest.mark.asyncio
    async def test_sqlite_no_filters(self):
        conn = FakeConn(fetchall=[{"id": "s1", "agent_name": "Alice"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_shifts_db("t1")
        assert result == [{"id": "s1", "agent_name": "Alice"}]
        assert "ORDER BY s.start_time ASC" in conn.last_sql
        assert conn.last_params == ["t1"]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_filters(self):
        conn = FakeConn(fetchall=[{"id": "s1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_shifts_db("t1", date_from="2024-01-01", date_to="2024-01-31", agent_id="a1")
        assert result == [{"id": "s1"}]
        assert "s.start_time >= ?" in conn.last_sql
        assert "s.start_time <= ?" in conn.last_sql
        assert "s.agent_id = ?" in conn.last_sql
        assert conn.last_params == ["t1", "2024-01-01", "2024-01-31", "a1"]

    @pytest.mark.asyncio
    async def test_pg_with_filters(self):
        pool = FakePool(fetch=[{"id": "s1", "agent_name": "Alice"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_shifts_db("t1", date_from="2024-01-01", agent_id="a1")
        assert result == [{"id": "s1", "agent_name": "Alice"}]
        sql, params = pool.fetch_calls[0]
        assert "AND s.start_time >= $2" in sql
        assert "AND s.agent_id = $3" in sql
        assert params == ("t1", "2024-01-01", "a1")

    @pytest.mark.asyncio
    async def test_pg_with_date_to_filter(self):
        pool = FakePool(fetch=[{"id": "s1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_shifts_db("t1", date_to="2024-01-31")
        assert result == [{"id": "s1"}]
        sql, params = pool.fetch_calls[0]
        assert "AND s.start_time <= $2" in sql
        assert params == ("t1", "2024-01-31")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_shifts_db("t1") is None


class TestUpdateShift:
    @pytest.mark.asyncio
    async def test_no_updates_returns_none(self):
        with _pg_false():
            assert await update_shift_db("s1", "t1") is None
            assert await update_shift_db("s1", "t1", end_time=None) is None

    @pytest.mark.asyncio
    async def test_sqlite_builds_set_clause(self):
        conn = FakeConn(fetchone={"id": "s1", "status": "completed"})
        with _pg_false(), _patch_conn(conn):
            result = await update_shift_db(
                "s1", "t1", start_time="10:00", end_time=None, status="completed"
            )
        assert result == {"id": "s1", "status": "completed"}
        sql, params = _find_sql(conn, "UPDATE wfm_shifts SET")
        assert sql is not None
        assert "start_time = ?" in sql
        assert "status = ?" in sql
        assert "end_time" not in sql
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_missing_returns_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await update_shift_db("s1", "t1", status="completed") is None

    @pytest.mark.asyncio
    async def test_pg_updates_and_returns(self):
        pool = FakePool(fetchrow={"id": "s1"})
        with _pg_true(), _patch_pg(pool):
            result = await update_shift_db("s1", "t1", status="completed")
        assert result == {"id": "s1"}
        sql, params = pool.executed[0]
        assert "UPDATE wfm_shifts SET status = $1" in sql
        assert params == ("completed", "s1", "t1")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_shift_db("s1", "t1", status="completed") is None


class TestDeleteShift:
    @pytest.mark.asyncio
    async def test_sqlite_rowcount_positive(self):
        conn = FakeConn(cursor_rowcount=2)
        with _pg_false(), _patch_conn(conn):
            assert await delete_shift_db("s1", "t1") is True
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_rowcount_zero(self):
        conn = FakeConn(cursor_rowcount=0)
        with _pg_false(), _patch_conn(conn):
            assert await delete_shift_db("s1", "t1") is False

    @pytest.mark.asyncio
    async def test_pg_delete_reported(self):
        pool = FakePool(execute_result="DELETE 1")
        with _pg_true(), _patch_pg(pool):
            assert await delete_shift_db("s1", "t1") is True
        sql, params = pool.executed[0]
        assert "DELETE FROM wfm_shifts" in sql
        assert params == ("s1", "t1")

    @pytest.mark.asyncio
    async def test_pg_delete_not_reported(self):
        pool = FakePool(execute_result="UPDATE 0")
        with _pg_true(), _patch_pg(pool):
            assert await delete_shift_db("s1", "t1") is False

    @pytest.mark.asyncio
    async def test_pg_no_pool_returns_false(self):
        with _pg_true(), _patch_pg(None):
            assert await delete_shift_db("s1", "t1") is False


class TestCreateSchedule:
    @pytest.mark.asyncio
    async def test_sqlite_inserts_and_returns(self):
        conn = FakeConn(fetchone={"id": "sc1", "date": "2024-01-01"})
        with _pg_false(), _patch_conn(conn):
            result = await create_schedule_db("t1", "2024-01-01", 100, 5, "note")
        assert result == {"id": "sc1", "date": "2024-01-01"}
        sql, params = _find_sql(conn, "INSERT INTO wfm_schedules")
        assert sql is not None
        assert params[1] == "t1"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_missing_returns_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_schedule_db("t1", "2024-01-01", 100, 5) is None

    @pytest.mark.asyncio
    async def test_pg_inserts_and_returns(self):
        pool = FakePool(fetchrow={"id": "sc1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_schedule_db("t1", "2024-01-01", 100, 5)
        assert result == {"id": "sc1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO wfm_schedules" in sql
        assert params[1] == "t1"
        assert params[2] == "2024-01-01"

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_schedule_db("t1", "2024-01-01", 100, 5) is None


class TestGetSchedule:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "sc1", "date": "2024-01-01"})
        with _pg_false(), _patch_conn(conn):
            assert (await get_schedule_db("t1", "2024-01-01"))["date"] == "2024-01-01"
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_schedule_db("t1", "2024-01-01") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "sc1"})
        with _pg_true(), _patch_pg(pool):
            assert (await get_schedule_db("t1", "2024-01-01"))["id"] == "sc1"

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_schedule_db("t1", "2024-01-01") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_schedule_db("t1", "2024-01-01") is None


class TestUpdateScheduleAdherence:
    @pytest.mark.asyncio
    async def test_sqlite_updates_and_returns(self):
        conn = FakeConn(fetchone={"id": "sc1", "adherence_pct": 95})
        with _pg_false(), _patch_conn(conn):
            result = await update_schedule_adherence_db("sc1", 120, 6, 95)
        assert result == {"id": "sc1", "adherence_pct": 95}
        sql, params = _find_sql(conn, "UPDATE wfm_schedules SET")
        assert sql is not None
        assert "actual_volume = ?" in sql
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_missing_returns_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await update_schedule_adherence_db("sc1", 120, 6, 95) is None

    @pytest.mark.asyncio
    async def test_pg_updates_and_returns(self):
        pool = FakePool(fetchrow={"id": "sc1"})
        with _pg_true(), _patch_pg(pool):
            result = await update_schedule_adherence_db("sc1", 120, 6, 95)
        assert result == {"id": "sc1"}
        sql, params = pool.executed[0]
        assert "UPDATE wfm_schedules SET actual_volume = $1" in sql
        assert params == (120, 6, 95, "sc1")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await update_schedule_adherence_db("sc1", 120, 6, 95) is None


class TestListSchedules:
    @pytest.mark.asyncio
    async def test_sqlite_no_filters(self):
        conn = FakeConn(fetchall=[{"id": "sc1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_schedules_db("t1")
        assert result == [{"id": "sc1"}]
        assert "ORDER BY date ASC" in conn.last_sql
        assert conn.last_params == ["t1"]

    @pytest.mark.asyncio
    async def test_sqlite_with_filters(self):
        conn = FakeConn(fetchall=[{"id": "sc1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_schedules_db("t1", date_from="2024-01-01", date_to="2024-01-31")
        assert result == [{"id": "sc1"}]
        assert "date >= ?" in conn.last_sql
        assert "date <= ?" in conn.last_sql
        assert conn.last_params == ["t1", "2024-01-01", "2024-01-31"]

    @pytest.mark.asyncio
    async def test_pg_with_filters(self):
        pool = FakePool(fetch=[{"id": "sc1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_schedules_db("t1", date_from="2024-01-01")
        assert result == [{"id": "sc1"}]
        sql, params = pool.fetch_calls[0]
        assert "AND date >= $2" in sql
        assert params == ("t1", "2024-01-01")

    @pytest.mark.asyncio
    async def test_pg_with_date_to_filter(self):
        pool = FakePool(fetch=[{"id": "sc1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_schedules_db("t1", date_to="2024-01-31")
        assert result == [{"id": "sc1"}]
        sql, params = pool.fetch_calls[0]
        assert "AND date <= $2" in sql
        assert params == ("t1", "2024-01-31")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_schedules_db("t1") is None


class TestCreateQaRubric:
    @pytest.mark.asyncio
    async def test_sqlite_list_criteria_json(self):
        conn = FakeConn(fetchone={"id": "r1", "name": "Sales"})
        criteria = ["greeting", "tone"]
        with _pg_false(), _patch_conn(conn):
            result = await create_qa_rubric_db("t1", "Sales", criteria, "desc")
        assert result == {"id": "r1", "name": "Sales"}
        sql, params = _find_sql(conn, "INSERT INTO qa_rubrics")
        assert sql is not None
        assert params[4] == json.dumps(criteria)
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_non_list_criteria_empty_json(self):
        conn = FakeConn(fetchone={"id": "r1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_qa_rubric_db("t1", "Sales", "not-a-list")
        assert result == {"id": "r1"}
        _, params = _find_sql(conn, "INSERT INTO qa_rubrics")
        assert params[4] == "[]"

    @pytest.mark.asyncio
    async def test_sqlite_missing_returns_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_qa_rubric_db("t1", "Sales", []) is None

    @pytest.mark.asyncio
    async def test_pg_inserts_and_returns(self):
        pool = FakePool(fetchrow={"id": "r1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_qa_rubric_db("t1", "Sales", ["tone"])
        assert result == {"id": "r1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO qa_rubrics" in sql
        assert params[4] == '["tone"]'

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_qa_rubric_db("t1", "Sales", []) is None


class TestListQaRubrics:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[{"id": "r1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_qa_rubrics_db("t1")
        assert result == [{"id": "r1"}]
        assert "is_active = 1" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_qa_rubrics_db("t1") == []

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[{"id": "r1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_qa_rubrics_db("t1")
        assert result == [{"id": "r1"}]
        assert "is_active = TRUE" in pool.fetch_calls[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_qa_rubrics_db("t1") is None


class TestCreateQaScore:
    @pytest.mark.asyncio
    async def test_sqlite_non_dict_scores_empty_json(self):
        conn = FakeConn(fetchone={"id": "score1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_qa_score_db(
                "t1", "c1", "a1", "rev1", "r1", "not-a-dict"
            )
        assert result == {"id": "score1"}
        sql, params = _find_sql(conn, "INSERT INTO qa_scores")
        assert sql is not None
        assert params[8] == "{}"
        assert params[6] == 0.0
        assert params[7] == 100.0
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_dict_scores_with_str_criteria(self):
        rubric = {"criteria": '[{"name": "Tone", "weight": 40}, {"name": "Empathy", "weight": 60}]'}
        rubric_conn = FakeConn(fetchone=rubric)
        insert_conn = FakeConn(fetchone={"id": "score1"})
        with _pg_false(), _patch_conns(rubric_conn, insert_conn):
            result = await create_qa_score_db(
                "t1", "c1", "a1", "rev1", "r1",
                {"Tone": 5, "Empathy": 4},
            )
        assert result == {"id": "score1"}
        assert rubric_conn.closed is True
        _, params = _find_sql(insert_conn, "INSERT INTO qa_scores")
        assert params[6] == 88.0
        assert params[7] == 100.0
        assert params[8] == json.dumps({"Tone": 5, "Empathy": 4})

    @pytest.mark.asyncio
    async def test_sqlite_dict_scores_with_list_criteria(self):
        rubric = {"criteria": [{"name": "X", "weight": 10}]}
        rubric_conn = FakeConn(fetchone=rubric)
        insert_conn = FakeConn(fetchone={"id": "score1"})
        with _pg_false(), _patch_conns(rubric_conn, insert_conn):
            result = await create_qa_score_db(
                "t1", "c1", "a1", "rev1", "r1", {"X": 3}
            )
        assert result == {"id": "score1"}
        _, params = _find_sql(insert_conn, "INSERT INTO qa_scores")
        assert params[6] == 6.0
        assert params[7] == 10.0

    @pytest.mark.asyncio
    async def test_sqlite_dict_scores_rubric_missing_defaults_max(self):
        rubric_conn = FakeConn(fetchone=None)
        insert_conn = FakeConn(fetchone={"id": "score1"})
        with _pg_false(), _patch_conns(rubric_conn, insert_conn):
            result = await create_qa_score_db(
                "t1", "c1", "a1", "rev1", "r1", {"Tone": 5}
            )
        assert result == {"id": "score1"}
        _, params = _find_sql(insert_conn, "INSERT INTO qa_scores")
        assert params[6] == 0.0
        assert params[7] == 100.0

    @pytest.mark.asyncio
    async def test_pg_dict_scores(self):
        rubric_row = {"criteria": '[{"name": "Tone", "weight": 40}]'}
        insert_row = {"id": "score1"}
        pool = FakePool(fetchrow=[rubric_row, insert_row])
        with _pg_true(), _patch_pg(pool):
            result = await create_qa_score_db(
                "t1", "c1", "a1", "rev1", "r1", {"Tone": 5}
            )
        assert result == {"id": "score1"}
        assert len(pool.fetchrow_sqls) == 2
        sql, params = pool.executed[0]
        assert "INSERT INTO qa_scores" in sql
        assert params[6] == 40.0
        assert params[7] == 40.0

    @pytest.mark.asyncio
    async def test_pg_non_dict_scores(self):
        pool = FakePool(fetchrow=[{"id": "score1"}])
        with _pg_true(), _patch_pg(pool):
            result = await create_qa_score_db(
                "t1", "c1", "a1", "rev1", "r1", "nope"
            )
        assert result == {"id": "score1"}
        assert len(pool.fetchrow_sqls) == 1
        sql, params = pool.executed[0]
        assert params[8] == "{}"

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_qa_score_db(
                "t1", "c1", "a1", "rev1", "r1", {"Tone": 5}
            ) is None


class TestListQaScores:
    @pytest.mark.asyncio
    async def test_sqlite_no_filters(self):
        conn = FakeConn(fetchall=[{"id": "score1", "agent_name": "Alice"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_qa_scores_db("t1")
        assert result == [{"id": "score1", "agent_name": "Alice"}]
        assert "ORDER BY qs.reviewed_at DESC LIMIT 100" in conn.last_sql
        assert conn.last_params == ["t1"]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_with_filters(self):
        conn = FakeConn(fetchall=[{"id": "score1"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_qa_scores_db(
                "t1", agent_id="a1", date_from="2024-01-01", date_to="2024-01-31", limit=50
            )
        assert result == [{"id": "score1"}]
        assert "qs.agent_id = ?" in conn.last_sql
        assert "qs.reviewed_at >= ?" in conn.last_sql
        assert "qs.reviewed_at <= ?" in conn.last_sql
        assert "LIMIT 50" in conn.last_sql
        assert conn.last_params == ["t1", "a1", "2024-01-01", "2024-01-31"]

    @pytest.mark.asyncio
    async def test_pg_with_filters(self):
        pool = FakePool(fetch=[{"id": "score1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_qa_scores_db("t1", agent_id="a1")
        assert result == [{"id": "score1"}]
        sql, params = pool.fetch_calls[0]
        assert "AND qs.agent_id = $2" in sql
        assert params == ("t1", "a1")

    @pytest.mark.asyncio
    async def test_pg_with_date_filters(self):
        pool = FakePool(fetch=[{"id": "score1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_qa_scores_db(
                "t1", date_from="2024-01-01", date_to="2024-01-31"
            )
        assert result == [{"id": "score1"}]
        sql, params = pool.fetch_calls[0]
        assert "AND qs.reviewed_at >= $2" in sql
        assert "AND qs.reviewed_at <= $3" in sql
        assert params == ("t1", "2024-01-01", "2024-01-31")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_qa_scores_db("t1") is None


class TestGetAgentQaSummary:
    @pytest.mark.asyncio
    async def test_sqlite_full(self):
        conn = FakeConn(
            fetchone=[
                {"total": 3, "avg_score": 80.0},
                {"avg": 85.0},
                {"avg": 70.0},
                {"scores_per_criterion": '{"Tone": 4}'},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_agent_qa_summary_db("a1")
        assert result["total_reviewed"] == 3
        assert result["avg_score"] == 80.0
        assert result["trend"] == 15.0
        assert result["criteria_breakdown"] == {"Tone": 4}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_rows_defaults(self):
        conn = FakeConn(fetchone=[None])
        with _pg_false(), _patch_conn(conn):
            result = await get_agent_qa_summary_db("a1")
        assert result["avg_score"] == 0.0
        assert result["total_reviewed"] == 0
        assert result["trend"] == 0.0
        assert result["criteria_breakdown"] == {}

    @pytest.mark.asyncio
    async def test_sqlite_bad_criteria_json_falls_back(self):
        conn = FakeConn(
            fetchone=[
                {"total": 1, "avg_score": 90.0},
                {"avg": 90.0},
                {"avg": 0.0},
                {"scores_per_criterion": "not-json"},
            ]
        )
        with _pg_false(), _patch_conn(conn):
            result = await get_agent_qa_summary_db("a1")
        assert result["criteria_breakdown"] == "not-json"

    @pytest.mark.asyncio
    async def test_pg_full(self):
        pool = FakePool(
            fetchrow=[
                {"total": 2, "avg_score": 90.0},
                {"scores_per_criterion": {"Tone": 5}},
            ],
            fetchval=[80.0, 70.0],
        )
        with _pg_true(), _patch_pg(pool):
            result = await get_agent_qa_summary_db("a1")
        assert result["total_reviewed"] == 2
        assert result["avg_score"] == 90.0
        assert result["trend"] == 10.0
        assert result["criteria_breakdown"] == {"Tone": 5}

    @pytest.mark.asyncio
    async def test_pg_no_pool_defaults(self):
        with _pg_true(), _patch_pg(None):
            result = await get_agent_qa_summary_db("a1")
        assert result["avg_score"] == 0.0
        assert result["total_reviewed"] == 0


class TestCallVolumeHistory:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[{"date": "2024-01-01", "hour": 10, "count": 5}])
        with _pg_false(), _patch_conn(conn):
            result = await get_call_volume_history_db("t1", days=90)
        assert result == [{"date": "2024-01-01", "hour": 10, "count": 5}]
        assert conn.last_params == ("t1", "-90 days")
        assert "SELECT DATE(start_time) as date" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[{"date": "2024-01-01", "hour": 10, "count": 5}])
        with _pg_true(), _patch_pg(pool):
            result = await get_call_volume_history_db("t1", days=30)
        assert result == [{"date": "2024-01-01", "hour": 10, "count": 5}]
        assert "INTERVAL '30 days'" in pool.fetch_calls[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_call_volume_history_db("t1") is None


class TestAgentStatusHistory:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[{"activity_type": "busy", "duration_seconds": 60}])
        with _pg_false(), _patch_conn(conn):
            result = await get_agent_status_history_db("t1", "a1", "2024-01-01")
        assert result == [{"activity_type": "busy", "duration_seconds": 60}]
        assert conn.last_params == ("t1", "a1", "2024-01-01")
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[{"activity_type": "busy"}])
        with _pg_true(), _patch_pg(pool):
            result = await get_agent_status_history_db("t1", "a1", "2024-01-01")
        assert result == [{"activity_type": "busy"}]
        assert "DATE(created_at) = $3" in pool.fetch_calls[0][0]

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_agent_status_history_db("t1", "a1", "2024-01-01") is None
