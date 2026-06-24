import pytest
from unittest.mock import MagicMock, patch, mock_open


class TestDatabaseContextSync:
    @patch("apps.api.services.database.USE_POSTGRES", False)
    @patch("apps.api.services.database._get_sqlite_conn")
    def test_db_context_sync_yields_connection(self, mock_get_conn):
        from apps.api.services.database import db_context_sync

        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        with db_context_sync() as conn:
            assert conn is mock_conn

        mock_conn.close.assert_called_once()

    @patch("apps.api.services.database.USE_POSTGRES", True)
    def test_db_context_sync_postgres_raises(self):
        from apps.api.services.database import db_context_sync

        with pytest.raises(RuntimeError, match="db_context_sync not supported for PostgreSQL"):
            with db_context_sync():
                pass

    @patch("apps.api.services.database.USE_POSTGRES", False)
    @patch("apps.api.services.database._get_sqlite_conn")
    def test_db_context_sync_closes_on_error(self, mock_get_conn):
        from apps.api.services.database import db_context_sync

        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        with pytest.raises(ValueError, match="test error"):
            with db_context_sync():
                raise ValueError("test error")

        mock_conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_db_run_sync():
    from apps.api.services.database import db_run_sync

    def sync_func():
        return 42

    result = await db_run_sync(sync_func)
    assert result == 42


@pytest.mark.asyncio
async def test_db_run_sync_with_args():
    from apps.api.services.database import db_run_sync

    def sync_func(x, y=10):
        return x + y

    with patch("asyncio.to_thread") as mock_to_thread:
        mock_to_thread.return_value = 30
        result = await db_run_sync(lambda: sync_func(20, y=10))

    assert result == 30
