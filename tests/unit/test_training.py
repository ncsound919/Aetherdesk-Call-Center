"""Unit tests for api.services.training."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.services.training as training_module

service = training_module.TrainingService()


def _make_conn(fetchone=None, fetchall=None):
    conn = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = fetchone
    result.fetchall.return_value = fetchall
    conn.execute.return_value = result
    return conn


def _make_pool(fetch=None, fetchrow=None):
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=fetch if fetch is not None else [])
    pool.fetchrow = AsyncMock(return_value=fetchrow)
    pool.execute = AsyncMock(return_value=None)
    return pool


class TestListCourses:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = _make_conn(fetchall=[{"id": "c1"}, {"id": "c2"}])
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.list_courses("tenant-1")

        assert out == [{"id": "c1"}, {"id": "c2"}]
        assert conn.close.called

    @pytest.mark.asyncio
    async def test_postgres_with_pool(self):
        pool = _make_pool(fetch=[{"id": "c1"}])
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=pool)),
        ):
            out = await service.list_courses("tenant-1")

        assert out == [{"id": "c1"}]

    @pytest.mark.asyncio
    async def test_postgres_no_pool_returns_none(self):
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=None)),
        ):
            out = await service.list_courses("tenant-1")

        assert out is None


class TestCreateCourse:
    @pytest.mark.asyncio
    async def test_sqlite_with_module_list(self):
        modules = [{"id": "m1"}]
        row = {"id": "c1", "modules_json": json.dumps(modules)}
        conn = _make_conn(fetchone=row)
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.create_course(
                "tenant-1", "Title", "desc", modules, 2.0
            )

        assert out == row
        executed_sql = [c[0][0] for c in conn.execute.call_args_list]
        assert "INSERT INTO training_courses" in executed_sql[0]
        insert_args = conn.execute.call_args_list[0][0][1]
        assert insert_args[4] == json.dumps(modules)

    @pytest.mark.asyncio
    async def test_sqlite_with_modules_string_passthrough(self):
        modules = '{"prebuilt": true}'
        conn = _make_conn(fetchone={"id": "c1"})
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.create_course(
                "tenant-1", "Title", "desc", modules, 1.0
            )

        assert out == {"id": "c1"}
        insert_args = conn.execute.call_args_list[0][0][1]
        assert insert_args[4] == '{"prebuilt": true}'

    @pytest.mark.asyncio
    async def test_postgres_with_pool(self):
        pool = _make_pool(fetchrow={"id": "c1"})
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=pool)),
        ):
            out = await service.create_course(
                "tenant-1", "Title", "desc", [{"id": "m1"}], 2.0
            )

        assert out == {"id": "c1"}
        executed = [c[0][0] for c in pool.execute.call_args_list]
        assert "INSERT INTO training_courses" in executed[0]

    @pytest.mark.asyncio
    async def test_postgres_no_pool_returns_none(self):
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=None)),
        ):
            out = await service.create_course(
                "tenant-1", "Title", "desc", [], 0.0
            )

        assert out is None


class TestEnrollAgent:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        row = {"id": "e1", "status": "enrolled"}
        conn = _make_conn(fetchone=row)
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.enroll_agent("tenant-1", "a1", "course-1")

        assert out == row
        sql = conn.execute.call_args_list[0][0][0]
        assert "INSERT INTO training_enrollments" in sql

    @pytest.mark.asyncio
    async def test_postgres_with_pool(self):
        pool = _make_pool(fetchrow={"id": "e1"})
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=pool)),
        ):
            out = await service.enroll_agent("tenant-1", "a1", "course-1")

        assert out == {"id": "e1"}

    @pytest.mark.asyncio
    async def test_postgres_no_pool_returns_none(self):
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=None)),
        ):
            out = await service.enroll_agent("tenant-1", "a1", "course-1")

        assert out is None


class TestTrackProgress:
    @pytest.mark.asyncio
    async def test_sqlite_row_not_found(self):
        conn = _make_conn(fetchone=None)
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.track_progress("e1", "m1", "completed")

        assert out is None

    @pytest.mark.asyncio
    async def test_sqlite_in_progress(self):
        select_result = MagicMock()
        select_result.fetchone.return_value = {"id": "e1", "progress_pct": 0}
        update_result = MagicMock()
        final_result = MagicMock()
        final_result.fetchone.return_value = {"id": "e1", "progress_pct": 20.0, "status": "in_progress"}
        conn = MagicMock()
        conn.execute.side_effect = [select_result, update_result, final_result]
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.track_progress("e1", "m1", "started")

        assert out["progress_pct"] == 20.0
        assert out["status"] == "in_progress"
        update_sql = conn.execute.call_args_list[1][0][0]
        assert "completed_at" not in update_sql

    @pytest.mark.asyncio
    async def test_sqlite_completed(self):
        select_result = MagicMock()
        select_result.fetchone.return_value = {"id": "e1", "progress_pct": 80}
        update_result = MagicMock()
        final_result = MagicMock()
        final_result.fetchone.return_value = {"id": "e1", "progress_pct": 100.0, "status": "completed"}
        conn = MagicMock()
        conn.execute.side_effect = [select_result, update_result, final_result]
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.track_progress("e1", "m1", "started")

        assert out["progress_pct"] == 100.0
        assert out["status"] == "completed"
        update_sql = conn.execute.call_args_list[1][0][0]
        assert "completed_at" in update_sql

    @pytest.mark.asyncio
    async def test_postgres_row_not_found(self):
        pool = _make_pool(fetchrow=None)
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=pool)),
        ):
            out = await service.track_progress("e1", "m1", "started")

        assert out is None

    @pytest.mark.asyncio
    async def test_postgres_in_progress(self):
        pool = AsyncMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                {"id": "e1", "progress_pct": 0},
                {"id": "e1", "progress_pct": 20.0, "status": "in_progress"},
            ]
        )
        pool.execute = AsyncMock(return_value=None)
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=pool)),
        ):
            out = await service.track_progress("e1", "m1", "started")

        assert out["status"] == "in_progress"
        executed = [c[0][0] for c in pool.execute.call_args_list]
        assert "completed_at" not in executed[0]

    @pytest.mark.asyncio
    async def test_postgres_completed(self):
        pool = AsyncMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                {"id": "e1", "progress_pct": 80},
                {"id": "e1", "progress_pct": 100.0, "status": "completed"},
            ]
        )
        pool.execute = AsyncMock(return_value=None)
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=pool)),
        ):
            out = await service.track_progress("e1", "m1", "started")

        assert out["status"] == "completed"
        executed = [c[0][0] for c in pool.execute.call_args_list]
        assert "completed_at = NOW()" in executed[0]


class TestGetAgentCertifications:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = _make_conn(fetchall=[{"id": "e1", "title": "T"}])
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.get_agent_certifications("tenant-1", "a1")

        assert out == [{"id": "e1", "title": "T"}]
        sql = conn.execute.call_args_list[0][0][0]
        assert "status = 'completed'" in sql

    @pytest.mark.asyncio
    async def test_postgres_with_pool(self):
        pool = _make_pool(fetch=[{"id": "e1"}])
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=pool)),
        ):
            out = await service.get_agent_certifications("tenant-1", "a1")

        assert out == [{"id": "e1"}]

    @pytest.mark.asyncio
    async def test_postgres_no_pool_returns_none(self):
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=None)),
        ):
            out = await service.get_agent_certifications("tenant-1", "a1")

        assert out is None


class TestCreateCoachingSession:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        row = {"id": "s1", "status": "scheduled"}
        conn = _make_conn(fetchone=row)
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.create_coaching_session(
                "tenant-1", "a1", "coach-1", "focus", "notes"
            )

        assert out == row
        sql = conn.execute.call_args_list[0][0][0]
        assert "INSERT INTO coaching_sessions" in sql

    @pytest.mark.asyncio
    async def test_postgres_with_pool(self):
        pool = _make_pool(fetchrow={"id": "s1"})
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=pool)),
        ):
            out = await service.create_coaching_session(
                "tenant-1", "a1", "coach-1", "focus", "notes"
            )

        assert out == {"id": "s1"}

    @pytest.mark.asyncio
    async def test_postgres_no_pool_returns_none(self):
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=None)),
        ):
            out = await service.create_coaching_session(
                "tenant-1", "a1", "coach-1", "focus", None
            )

        assert out is None


class TestListCoachingSessions:
    @pytest.mark.asyncio
    async def test_sqlite_with_agent(self):
        conn = _make_conn(fetchall=[{"id": "s1"}])
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.list_coaching_sessions("tenant-1", "a1")

        assert out == [{"id": "s1"}]
        sql = conn.execute.call_args_list[0][0][0]
        assert "AND agent_id = ?" in sql

    @pytest.mark.asyncio
    async def test_sqlite_without_agent(self):
        conn = _make_conn(fetchall=[])
        with patch("api.services.training._get_sqlite_conn", return_value=conn):
            out = await service.list_coaching_sessions("tenant-1")

        assert out == []
        sql = conn.execute.call_args_list[0][0][0]
        assert "AND agent_id" not in sql

    @pytest.mark.asyncio
    async def test_postgres_with_agent(self):
        pool = _make_pool(fetch=[{"id": "s1"}])
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=pool)),
        ):
            out = await service.list_coaching_sessions("tenant-1", "a1")

        assert out == [{"id": "s1"}]

    @pytest.mark.asyncio
    async def test_postgres_without_agent(self):
        pool = _make_pool(fetch=[])
        with (
            patch("api.services.training.USE_POSTGRES", True),
            patch("api.services.training.get_pg_pool", new=AsyncMock(return_value=pool)),
        ):
            out = await service.list_coaching_sessions("tenant-1")

        assert out == []
