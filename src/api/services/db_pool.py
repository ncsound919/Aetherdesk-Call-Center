import asyncio
import os
import sqlite3
from contextlib import asynccontextmanager

import asyncpg
import structlog

from api.services.db_config import (
    DATABASE_URL,
    SQLITE_PATH,
    SQLITE_POOL_SIZE,
    SQLITE_TIMEOUT,
    USE_POSTGRES,
)


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


logger = structlog.get_logger()


# ── Encryption (HIPAA) ──────────────────────────────────────────

try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
except ImportError:
    _FERNET_AVAILABLE = False

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    if USE_POSTGRES:
        raise RuntimeError("ENCRYPTION_KEY environment variable must be set for production.")
    else:
        logger.warning("ENCRYPTION_KEY not set for development. Encryption will be disabled.")

_fernet = None
if _FERNET_AVAILABLE and ENCRYPTION_KEY:
    _fernet = Fernet(ENCRYPTION_KEY.encode("utf-8"))


def encrypt_val(val: str) -> str:
    if not val or not _fernet:
        return val
    return _fernet.encrypt(val.encode("utf-8")).decode("utf-8")


def decrypt_val(val: str) -> str:
    if not val or not _fernet:
        return val
    try:
        return _fernet.decrypt(val.encode("utf-8")).decode("utf-8")
    except Exception:
        logger.debug("decrypt_val failed, returning original value")
        return val


# ── Async Context Manager ──────────────────────────────────────────

@asynccontextmanager
async def db_context():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            async with pool.acquire() as conn:
                yield conn
                return
    conn = await _get_sqlite_conn_async()
    try:
        yield conn
    finally:
        _release_sqlite_conn(conn)


# ── Asyncpg Pool (PostgreSQL) ────────────────────────────────────

_pg_pool: asyncpg.Pool | None = None


async def get_pg_pool() -> asyncpg.Pool | None:
    global _pg_pool
    if _pg_pool is None or _pg_pool.is_closed():
        try:
            _pg_pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=5,
                max_size=20,
                timeout=30,
                command_timeout=60,
            )
            logger.info("PostgreSQL pool created")
        except Exception as e:
            logger.error(f"PostgreSQL pool creation failed: {e}")
            _pg_pool = None
    return _pg_pool


async def close_pg_pool():
    global _pg_pool
    if _pg_pool and not _pg_pool.is_closed():
        await _pg_pool.close()
        logger.info("PostgreSQL pool closed")


# ── SQLite Fallback (Local Development) ─────────────────────────

_sqlite_conn_pool: list = []
_sqlite_pool_lock = asyncio.Lock()


def _enable_wal_mode(conn: sqlite3.Connection):
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")


async def _get_sqlite_conn_async() -> sqlite3.Connection:
    global _sqlite_conn_pool
    async with _sqlite_pool_lock:
        if _sqlite_conn_pool:
            conn = _sqlite_conn_pool.pop()
            try:
                conn.execute("SELECT 1")
                return conn
            except sqlite3.ProgrammingError:
                pass
        conn = _get_sqlite_conn()
        return conn


def _release_sqlite_conn(conn: sqlite3.Connection):
    global _sqlite_conn_pool
    if len(_sqlite_conn_pool) < SQLITE_POOL_SIZE:
        _sqlite_conn_pool.append(conn)
    else:
        conn.close()


def _get_sqlite_conn():
    conn = sqlite3.connect(SQLITE_PATH, timeout=SQLITE_TIMEOUT)
    conn.row_factory = _dict_factory
    _enable_wal_mode(conn)
    return conn


