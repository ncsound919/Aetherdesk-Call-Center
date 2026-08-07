"""Unit tests for src/api/services/db_schema.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_schema import (
    SCHEMA_SQL,
    SQLITE_SCHEMA_SQL,
    init_pg_schema,
    init_sqlite_schema,
)


class FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return FakeAcquire(self._conn)


class FakeLoop:
    def __init__(self, running=False):
        self._running = running
        self.tasks = []
        self.completed = None

    def is_running(self):
        return self._running

    def create_task(self, coro):
        self.tasks.append(coro)
        return coro

    def run_until_complete(self, coro):
        self.completed = coro
        return coro


class FakeSqliteConn:
    def __init__(self):
        self.executed_sql = None
        self.committed = False
        self.closed = False

    def executescript(self, sql):
        self.executed_sql = sql

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class TestInitPgSchema:
    @pytest.mark.asyncio
    async def test_alembic_success_skips_raw_sql(self):
        conn = MagicMock()
        conn.execute = AsyncMock()
        pool = FakePool(conn)
        with patch(
            "api.services.db_migrations.run_alembic_migrations",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_alembic:
            result = await init_pg_schema(pool)
        assert result is None
        mock_alembic.assert_awaited_once()
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_alembic_false_falls_back_to_raw_sql(self):
        conn = MagicMock()
        conn.execute = AsyncMock()
        pool = FakePool(conn)
        with patch(
            "api.services.db_migrations.run_alembic_migrations",
            new_callable=AsyncMock,
            return_value=False,
        ):
            await init_pg_schema(pool)
        conn.execute.assert_awaited_once_with(SCHEMA_SQL)

    @pytest.mark.asyncio
    async def test_alembic_exception_falls_back(self):
        conn = MagicMock()
        conn.execute = AsyncMock()
        pool = FakePool(conn)
        with patch(
            "api.services.db_migrations.run_alembic_migrations",
            new_callable=AsyncMock,
            side_effect=RuntimeError("alembic broken"),
        ), patch(
            "api.services.db_schema.logger.warning"
        ) as mock_warning:
            await init_pg_schema(pool)
        mock_warning.assert_called_once()
        conn.execute.assert_awaited_once_with(SCHEMA_SQL)

    @pytest.mark.asyncio
    async def test_raw_sql_failure_reraises(self):
        conn = MagicMock()
        conn.execute = AsyncMock(
            side_effect=RuntimeError("sqlite syntax error")
        )
        pool = FakePool(conn)
        with patch(
            "api.services.db_migrations.run_alembic_migrations",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "api.services.db_schema.logger.error"
        ) as mock_error, pytest.raises(RuntimeError, match="sqlite syntax error"):
            await init_pg_schema(pool)
        mock_error.assert_called_once()


class TestInitSqliteSchema:
    def test_running_loop_delegates_migration(self):
        loop = FakeLoop(running=True)
        with patch(
            "asyncio.get_event_loop", return_value=loop
        ), patch(
            "api.services.db_migrations.run_alembic_migrations",
            MagicMock(return_value="migration-task"),
        ) as mock_alembic, patch(
            "api.services.db_pool._get_sqlite_conn",
            MagicMock(),
        ) as mock_conn:
            result = init_sqlite_schema()
        assert result is None
        assert len(loop.tasks) == 1
        mock_alembic.assert_called_once()
        mock_conn.assert_not_called()

    def test_non_running_loop_alembic_ok(self):
        loop = FakeLoop(running=False)
        with patch(
            "asyncio.get_event_loop", return_value=loop
        ), patch(
            "api.services.db_migrations.run_alembic_migrations",
            MagicMock(return_value=True),
        ) as mock_alembic, patch(
            "api.services.db_pool._get_sqlite_conn",
            MagicMock(),
        ) as mock_conn:
            init_sqlite_schema()
        mock_alembic.assert_called_once()
        assert loop.completed is not None
        mock_conn.assert_not_called()

    def test_alembic_false_falls_back_to_sqlite(self):
        loop = FakeLoop(running=False)
        conn = FakeSqliteConn()
        with patch(
            "asyncio.get_event_loop", return_value=loop
        ), patch(
            "api.services.db_migrations.run_alembic_migrations",
            MagicMock(return_value=False),
        ), patch(
            "api.services.db_pool._get_sqlite_conn",
            MagicMock(return_value=conn),
        ), patch(
            "api.services.db_sqlite_transform.postgres_to_sqlite",
            MagicMock(return_value="TRANSLATED SCHEMA SQL"),
        ) as mock_transform:
            init_sqlite_schema()
        mock_transform.assert_called_once_with(SCHEMA_SQL)
        assert conn.executed_sql == "TRANSLATED SCHEMA SQL"
        assert conn.committed is True
        assert conn.closed is True

    def test_alembic_exception_falls_back_to_sqlite(self):
        loop = FakeLoop(running=False)
        conn = FakeSqliteConn()
        with patch(
            "asyncio.get_event_loop", return_value=loop
        ), patch(
            "api.services.db_migrations.run_alembic_migrations",
            MagicMock(side_effect=RuntimeError("alembic broken")),
        ), patch(
            "api.services.db_schema.logger.warning"
        ) as mock_warning, patch(
            "api.services.db_pool._get_sqlite_conn",
            MagicMock(return_value=conn),
        ), patch(
            "api.services.db_sqlite_transform.postgres_to_sqlite",
            MagicMock(return_value="TRANSLATED SCHEMA SQL"),
        ):
            init_sqlite_schema()
        mock_warning.assert_called_once()
        assert conn.executed_sql == "TRANSLATED SCHEMA SQL"
        assert conn.committed is True
        assert conn.closed is True


class TestSchemaConstants:
    def test_schema_sql_contains_plans(self):
        assert "CREATE TABLE IF NOT EXISTS plans" in SCHEMA_SQL
        assert "CREATE TABLE IF NOT EXISTS users" in SCHEMA_SQL
        assert "CREATE POLICY" in SCHEMA_SQL

    def test_sqlite_schema_sql_exists(self):
        assert "CREATE TABLE IF NOT EXISTS" in SQLITE_SCHEMA_SQL
        assert len(SQLITE_SCHEMA_SQL) > 0
