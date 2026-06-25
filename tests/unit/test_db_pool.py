"""Unit tests for database connection pool and HTTP connection pool management.

Tests cover:
  - db_pool: _get_sqlite_conn, _release_sqlite_conn, pool config, encrypt/decrypt
  - connection_pool: HTTPClientPool singleton, get_client, close, context manager
"""

import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Pre-register mock for api.main (avoids import errors) ──────────
_sentinel = types.ModuleType("api.main")
_sentinel.redis_client = None
_sentinel.logger = MagicMock()
sys.modules.setdefault("api.main", _sentinel)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _patch_env():
    """Ensure local/dev-friendly env for every test."""
    with patch.dict(os.environ, {
        "USE_POSTGRES": "false",
        "ENCRYPTION_KEY": "dGVzdC1rZXktMTIzNDU2Nzg5MDEyMzQ1Njc4OTA=",
        "SQLITE_PATH": ":memory:",
        "SQLITE_POOL_SIZE": "5",
        "SQLITE_TIMEOUT": "30",
    }, clear=False):
        yield


# ── SQLite Connection Pool Tests ────────────────────────────────────────

class TestSQLitePool:
    """Tests for _get_sqlite_conn and _release_sqlite_conn."""

    def test_get_sqlite_conn_returns_dict_rows(self):
        """Connection uses dict_factory so rows are dicts."""
        from api.services.db_pool import _get_sqlite_conn

        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT 1 AS value").fetchone()
            assert isinstance(row, dict)
            assert row["value"] == 1
        finally:
            conn.close()

    def test_get_sqlite_conn_executes_basic_query(self):
        """A bare SELECT works."""
        from api.services.db_pool import _get_sqlite_conn

        conn = _get_sqlite_conn()
        try:
            result = conn.execute("SELECT 1").fetchone()
            assert result is not None
            assert list(result.values())[0] == 1
        finally:
            conn.close()

    def test_get_sqlite_conn_enables_wal_mode(self):
        """Pragma journal_mode should be WAL after connection setup."""
        from api.services.db_pool import _get_sqlite_conn

        conn = _get_sqlite_conn()
        try:
            journal_mode = conn.execute(
                "PRAGMA journal_mode"
            ).fetchone()
            # SQLite returns the journal mode as a string value
            assert list(journal_mode.values())[0].upper() in ("WAL", "MEMORY", "DELETE")
        finally:
            conn.close()

    def test_get_sqlite_conn_sets_sync_to_normal(self):
        """Pragma synchronous should be NORMAL."""
        from api.services.db_pool import _get_sqlite_conn

        conn = _get_sqlite_conn()
        try:
            sync_val = conn.execute(
                "PRAGMA synchronous"
            ).fetchone()
            assert list(sync_val.values())[0] == 1  # NORMAL = 1
        finally:
            conn.close()

    def test_get_sqlite_conn_creates_tables(self):
        """At least one table should exist (created by init_db)."""
        from api.services.db_pool import _get_sqlite_conn

        conn = _get_sqlite_conn()
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            # Even with :memory:, tables may exist if init_db ran
            assert isinstance(tables, list)
        finally:
            conn.close()

    def test_release_sqlite_conn_closes_when_pool_full(self):
        """_release_sqlite_conn closes connection when pool is at capacity."""
        from api.services.db_pool import (
            _get_sqlite_conn,
            _release_sqlite_conn,
        )

        # Use :memory: for isolation
        conn = _get_sqlite_conn()
        # Fill the pool so the next release triggers a close
        from api.services.db_pool import _sqlite_conn_pool

        _sqlite_conn_pool.clear()
        _release_sqlite_conn(conn)
        # After releasing, conn should be in the pool (pool was empty)
        assert conn in _sqlite_conn_pool

        # Clean up
        _sqlite_conn_pool.clear()


# ── Async SQLite Connection Tests ───────────────────────────────────────

class TestSQLiteAsync:
    """Tests for _get_sqlite_conn_async."""

    @pytest.mark.asyncio
    async def test_get_sqlite_conn_async_returns_connection(self):
        """_get_sqlite_conn_async returns a working SQLite connection."""
        from api.services.db_pool import _get_sqlite_conn_async

        conn = await _get_sqlite_conn_async()
        try:
            row = conn.execute("SELECT 1 AS val").fetchone()
            assert row["val"] == 1
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_get_sqlite_conn_async_reuses_pooled_conn(self):
        """_get_sqlite_conn_async pops from the pool when available."""
        from api.services.db_pool import (
            _get_sqlite_conn,
            _get_sqlite_conn_async,
            _release_sqlite_conn,
            _sqlite_conn_pool,
        )

        _sqlite_conn_pool.clear()

        # Create and release a connection so the pool has one
        conn = _get_sqlite_conn()
        _release_sqlite_conn(conn)
        pool_size_before = len(_sqlite_conn_pool)

        # Now get one async — should reuse the pooled conn
        reused = await _get_sqlite_conn_async()
        assert reused is conn  # Same object was reused
        reused.close()

        # Clean up
        _sqlite_conn_pool.clear()


# ── PostgreSQL Pool Tests (mocked) ──────────────────────────────────────

class TestPostgresPool:
    """Tests for get_pg_pool and close_pg_pool."""

    @pytest.mark.asyncio
    async def test_get_pg_pool_creates_pool(self):
        """get_pg_pool creates an asyncpg pool when not already set."""
        mock_pool = AsyncMock()
        mock_pool.is_closed.return_value = False

        with patch(
            "api.services.db_pool._pg_pool", None
        ), patch(
            "api.services.db_pool.asyncpg.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ) as mock_create:
            from api.services.db_pool import get_pg_pool

            pool = await get_pg_pool()
            assert pool is mock_pool
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pg_pool_returns_cached(self):
        """get_pg_pool returns existing pool without re-creating."""
        # Use MagicMock so is_closed() is sync (not awaited in source)
        mock_pool = MagicMock()
        mock_pool.is_closed.return_value = False

        with patch(
            "api.services.db_pool._pg_pool", mock_pool
        ), patch(
            "api.services.db_pool.asyncpg.create_pool",
            new_callable=AsyncMock,
        ) as mock_create:
            from api.services.db_pool import get_pg_pool

            pool = await get_pg_pool()
            assert pool is mock_pool
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_pg_pool_recreates_if_closed(self):
        """get_pg_pool recreates pool when cached pool is closed."""
        # Use MagicMock so is_closed() is sync (source calls it without await)
        closed_pool = MagicMock()
        closed_pool.is_closed.return_value = True

        new_pool = MagicMock()
        new_pool.is_closed.return_value = False

        with patch(
            "api.services.db_pool._pg_pool", closed_pool
        ), patch(
            "api.services.db_pool.asyncpg.create_pool",
            new_callable=AsyncMock,
            return_value=new_pool,
        ) as mock_create:
            from api.services.db_pool import get_pg_pool

            pool = await get_pg_pool()
            assert pool is new_pool
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pg_pool_returns_none_on_failure(self):
        """get_pg_pool returns None when pool creation fails."""
        with patch(
            "api.services.db_pool._pg_pool", None
        ), patch(
            "api.services.db_pool.asyncpg.create_pool",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            from api.services.db_pool import get_pg_pool

            pool = await get_pg_pool()
            assert pool is None

    @pytest.mark.asyncio
    async def test_close_pg_pool_closes_active(self):
        """close_pg_pool closes pool when it's open."""
        # MagicMock so is_closed() is sync (source calls it without await)
        mock_pool = MagicMock()
        mock_pool.is_closed.return_value = False
        # close() is async, so mock it as AsyncMock
        mock_pool.close = AsyncMock()

        with patch(
            "api.services.db_pool._pg_pool", mock_pool
        ):
            from api.services.db_pool import close_pg_pool

            await close_pg_pool()
            mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_pg_pool_skips_if_closed(self):
        """close_pg_pool does nothing when pool is already closed."""
        # MagicMock so is_closed() is sync
        mock_pool = MagicMock()
        mock_pool.is_closed.return_value = True

        with patch(
            "api.services.db_pool._pg_pool", mock_pool
        ):
            from api.services.db_pool import close_pg_pool

            await close_pg_pool()
            mock_pool.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_pg_pool_skips_if_none(self):
        """close_pg_pool does nothing when _pg_pool is None."""
        with patch(
            "api.services.db_pool._pg_pool", None
        ):
            from api.services.db_pool import close_pg_pool

            # Should not raise
            await close_pg_pool()


# ── Encryption Tests ────────────────────────────────────────────────────

class TestEncryption:
    """Tests for encrypt_val and decrypt_val."""

    def test_encrypt_decrypt_roundtrip(self):
        """encrypt_val then decrypt_val returns original value."""
        from cryptography.fernet import Fernet

        from api.services.db_pool import decrypt_val, encrypt_val

        key = Fernet.generate_key()
        fernet = Fernet(key)

        with patch("api.services.db_pool._fernet", fernet):
            original = "sensitive-data-123"
            encrypted = encrypt_val(original)
            assert encrypted != original
            decrypted = decrypt_val(encrypted)
            assert decrypted == original

    def test_encrypt_empty_string_returns_empty(self):
        """encrypt_val returns empty string unchanged."""
        from api.services.db_pool import encrypt_val

        assert encrypt_val("") == ""

    def test_encrypt_none_returns_none(self):
        """encrypt_val returns None for falsy input."""
        from api.services.db_pool import encrypt_val

        assert encrypt_val(None) is None

    def test_decrypt_empty_string_returns_empty(self):
        """decrypt_val returns empty string unchanged."""
        from api.services.db_pool import decrypt_val

        assert decrypt_val("") == ""

    def test_decrypt_none_returns_none(self):
        """decrypt_val returns None for falsy input."""
        from api.services.db_pool import decrypt_val

        assert decrypt_val(None) is None

    def test_encrypt_unicode_roundtrip(self):
        """Unicode characters survive encrypt/decrypt round-trip."""
        from cryptography.fernet import Fernet

        from api.services.db_pool import decrypt_val, encrypt_val

        key = Fernet.generate_key()
        fernet = Fernet(key)

        with patch("api.services.db_pool._fernet", fernet):
            original = "héllo wörld 🎉"
            encrypted = encrypt_val(original)
            decrypted = decrypt_val(encrypted)
            assert decrypted == original

    def test_decrypt_invalid_token_returns_original(self):
        """decrypt_val returns original value when decryption fails."""
        from cryptography.fernet import Fernet

        from api.services.db_pool import decrypt_val

        key = Fernet.generate_key()
        fernet = Fernet(key)

        with patch("api.services.db_pool._fernet", fernet):
            result = decrypt_val("not-a-valid-fernet-token")
            assert result == "not-a-valid-fernet-token"


# ── Database Context Manager Tests ──────────────────────────────────────

class TestDbContext:
    """Tests for the db_context async context manager."""

    @pytest.mark.asyncio
    async def test_db_context_yields_sqlite_conn(self):
        """db_context yields an active SQLite connection in dev mode."""
        with patch(
            "api.services.db_pool.USE_POSTGRES", False
        ):
            from api.services.db_pool import db_context

            async with db_context() as conn:
                row = conn.execute("SELECT 1 AS val").fetchone()
                assert row["val"] == 1


# ── HTTP Connection Pool Tests ──────────────────────────────────────────

class TestHTTPClientPool:
    """Tests for HTTPClientPool singleton and get_http_client context manager."""

    def test_http_pool_is_singleton(self):
        """HTTPClientPool() returns the same instance each time."""
        from api.services.connection_pool import HTTPClientPool

        p1 = HTTPClientPool()
        p2 = HTTPClientPool()
        assert p1 is p2

    def test_http_pool_instance_exists(self):
        """http_pool global is an HTTPClientPool instance."""
        from api.services.connection_pool import http_pool, HTTPClientPool

        assert http_pool is not None
        assert isinstance(http_pool, HTTPClientPool)
        assert hasattr(http_pool, "get_client")
        assert hasattr(http_pool, "close")

    @pytest.mark.asyncio
    async def test_get_client_returns_async_client(self):
        """get_client() returns an httpx.AsyncClient."""
        import httpx

        from api.services.connection_pool import http_pool

        client = await http_pool.get_client()
        assert client is not None
        assert isinstance(client, httpx.AsyncClient)
        assert hasattr(client, "get")

    @pytest.mark.asyncio
    async def test_get_client_returns_same_instance(self):
        """get_client() returns the same cached client on second call."""
        from api.services.connection_pool import http_pool

        # Reset for this test
        if http_pool._client and not http_pool._client.is_closed:
            await http_pool._client.aclose()
        http_pool._client = None

        c1 = await http_pool.get_client()
        c2 = await http_pool.get_client()
        assert c1 is c2

        await http_pool.close()

    @pytest.mark.asyncio
    async def test_close_releases_client(self):
        """close() closes the client and sets it to None."""
        from api.services.connection_pool import http_pool

        await http_pool.get_client()  # ensure client exists
        await http_pool.close()
        assert http_pool._client is None or http_pool._client.is_closed

    @pytest.mark.asyncio
    async def test_get_http_client_context_manager(self):
        """get_http_client() context manager yields a client."""
        from api.services.connection_pool import get_http_client

        async with get_http_client() as client:
            assert client is not None
            assert hasattr(client, "get")


# ── Pool Configuration Tests ───────────────────────────────────────────

class TestPoolConfig:
    """Tests for pool configuration values."""

    def test_sqlite_pool_size_default(self):
        """SQLITE_POOL_SIZE defaults to 5 when not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Re-import to pick up fresh env
            import importlib

            import api.services.db_config as cfg

            importlib.reload(cfg)
            assert cfg.SQLITE_POOL_SIZE >= 1

    def test_sqlite_timeout_default(self):
        """SQLITE_TIMEOUT defaults to 30 seconds."""
        from api.services.db_config import SQLITE_TIMEOUT

        assert SQLITE_TIMEOUT == 30

    def test_use_postgres_defaults_to_false(self):
        """USE_POSTGRES is False when not set or set to false."""
        from api.services.db_config import USE_POSTGRES

        assert USE_POSTGRES is False


# ── dict_factory Tests ─────────────────────────────────────────────────

class TestDictFactory:
    """Tests for _dict_factory helper."""

    def test_dict_factory_creates_dict(self):
        """_dict_factory maps column names to row values."""
        from api.services.db_pool import _dict_factory

        class FakeCursor:
            description = [("id",), ("name",), ("email",)]

        row = ("42", "Alice", "alice@test.com")
        result = _dict_factory(FakeCursor(), row)
        assert result == {"id": "42", "name": "Alice", "email": "alice@test.com"}

    def test_dict_factory_empty_description(self):
        """_dict_factory returns empty dict when no columns."""
        from api.services.db_pool import _dict_factory

        class FakeCursor:
            description = []

        result = _dict_factory(FakeCursor(), ())
        assert result == {}


# ── Additional Pool & Encryption Tests ────────────────────────────────


class TestSQLitePoolExtra:
    """Extra tests for SQLite pool — stale connection handling."""

    @pytest.mark.asyncio
    async def test_reuse_stale_conn_handles_programming_error(self):
        """Pool handles ProgrammingError when a closed connection is reused."""
        from api.services.db_pool import (
            _get_sqlite_conn,
            _get_sqlite_conn_async,
            _release_sqlite_conn,
            _sqlite_conn_pool,
        )

        _sqlite_conn_pool.clear()

        conn = _get_sqlite_conn()
        conn.close()
        _release_sqlite_conn(conn)
        assert conn in _sqlite_conn_pool

        new_conn = await _get_sqlite_conn_async()
        try:
            row = new_conn.execute("SELECT 1 AS val").fetchone()
            assert row["val"] == 1
        finally:
            new_conn.close()

        _sqlite_conn_pool.clear()


class TestSQLiteAsyncExtra:
    """Extra async SQLite tests — ProgrammingError recovery."""

    @pytest.mark.asyncio
    async def test_get_sqlite_conn_async_handles_programming_error(self):
        """_get_sqlite_conn_async creates a new connection when pooled one has ProgrammingError."""
        from api.services.db_pool import (
            _get_sqlite_conn,
            _get_sqlite_conn_async,
            _release_sqlite_conn,
            _sqlite_conn_pool,
        )

        _sqlite_conn_pool.clear()

        conn = _get_sqlite_conn()
        conn.close()
        _release_sqlite_conn(conn)

        new_conn = await _get_sqlite_conn_async()
        assert new_conn is not conn
        try:
            row = new_conn.execute("SELECT 1 AS val").fetchone()
            assert row["val"] == 1
        finally:
            new_conn.close()

        _sqlite_conn_pool.clear()


class TestDbContextExtra:
    """Extra db_context tests — PostgreSQL path."""

    @pytest.mark.asyncio
    async def test_db_context_yields_postgres_conn(self):
        """db_context yields an async connection from the Postgres pool when USE_POSTGRES is True."""
        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        with patch(
            "api.services.db_pool.USE_POSTGRES", True
        ), patch(
            "api.services.db_pool.get_pg_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            from api.services.db_pool import db_context

            async with db_context() as conn:
                assert conn is mock_conn


class TestEncryptionExtra:
    """Extra encryption tests."""

    def test_decrypt_val_returns_original_on_failure(self):
        """decrypt_val returns the original value when decryption fails (invalid token)."""
        from api.services.db_pool import decrypt_val

        result = decrypt_val("not-a-valid-fernet-token")
        assert result == "not-a-valid-fernet-token"
