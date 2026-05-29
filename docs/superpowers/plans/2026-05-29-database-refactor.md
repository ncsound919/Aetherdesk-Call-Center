# Database Refactoring & Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor 1553-line database.py (SRP violation) into focused modules, replace global mutable state with DI, centralize error handling, fix stale domain references.

**Architecture:** Split monolithic database.py into 4 files by concern, introduce service classes with dependency injection for in-memory caches/stores, replace inconsistent error returns with typed results, fix stale domain references across k8s configs.

**Tech Stack:** Python 3.10+, FastAPI, asyncpg, sqlite3, cachetools, structlog

---

### Task 1: Create `db_pool.py` — Connection pool management + encryption

**Files:**
- Create: `apps/api/services/db_pool.py`
- Modify: `apps/api/services/__init__.py`
- Remove from: `apps/api/services/database.py` (lines 1-170)

- [ ] **Step 1: Create db_pool.py**

```python
"""Database connection pool management and encryption utilities."""

import os
import asyncio
import structlog
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
import sqlite3

from apps.api.services.db_schema import (
    SCHEMA_SQL, SQLITE_SCHEMA_SQL,
    USE_POSTGRES, DATABASE_URL, SQLITE_PATH,
    SQLITE_POOL_SIZE, SQLITE_TIMEOUT,
)

logger = structlog.get_logger()


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


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
        return val


# ── Asyncpg Pool (PostgreSQL) ────────────────────────────────────

_pg_pool: Optional[asyncpg.Pool] = None


async def get_pg_pool() -> Optional[asyncpg.Pool]:
    global _pg_pool
    if _pg_pool is None or (hasattr(_pg_pool, 'is_closed') and _pg_pool.is_closed()):
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
```

- [ ] **Step 2: Create db_schema.py — Schema SQL + init functions**

```python
"""Database schema definitions and initialization."""

import os
import json
import structlog
from typing import Optional

import asyncpg
import sqlite3

from apps.api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()

# ── Configuration ────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", None)
if not DATABASE_URL:
    if os.getenv("USE_POSTGRES", "false").lower() == "true":
        raise RuntimeError("DATABASE_URL environment variable must be set for production.")
    else:
        print("DATABASE_URL not set. Running with SQLite fallback.")
USE_POSTGRES = os.getenv("USE_POSTGRES", "false").lower() == "true"

SQLITE_PATH = os.getenv("SQLITE_PATH", "aetherdesk.db")
SQLITE_POOL_SIZE = int(os.getenv("SQLITE_POOL_SIZE", "5"))
SQLITE_TIMEOUT = int(os.getenv("SQLITE_TIMEOUT", "30"))

# ── Full PostgreSQL DDL ──
SCHEMA_SQL = """..."""  # Exactly as in current database.py lines 175-618

# ── SQLite DDL ──
SQLITE_SCHEMA_SQL = """..."""  # Exactly as in current database.py lines 623-800


async def init_pg_schema(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        try:
            await conn.execute(SCHEMA_SQL)
            logger.info("PostgreSQL schema initialized successfully")
        except Exception as e:
            logger.error("PostgreSQL schema initialization failed", error=str(e))
            raise


def init_sqlite_schema():
    conn = _get_sqlite_conn()
    conn.executescript(SQLITE_SCHEMA_SQL)
    conn.commit()
    conn.close()
    logger.info("SQLite schema initialized")
```

- [ ] **Step 3: Copy the full SCHEMA_SQL and SQLITE_SCHEMA_SQL verbatim from current database.py lines 175-800 into db_schema.py.**

- [ ] **Step 4: Create `db_tenants.py` — All tenant + agent CRUD**

```python
"""Tenant and agent database operations."""

import json
import uuid
import structlog
from datetime import datetime, timezone

from apps.api.services.db_pool import get_pg_pool, _get_sqlite_conn
from apps.api.services.db_schema import USE_POSTGRES
from apps.api.services.db_errors import ok, err, NotFound, DatabaseError

logger = structlog.get_logger()


def _parse_skills(skills_value) -> list:
    if skills_value is None:
        return []
    if isinstance(skills_value, list):
        return skills_value
    if isinstance(skills_value, str):
        try:
            parsed = json.loads(skills_value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


# --- Tenants ---

async def create_tenant(name, email, slug, phone=None, plan_id=None, settings=None, gdpr_consent=False):
    import secrets
    tenant_id = str(uuid.uuid4())
    api_key = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if not pool:
            raise DatabaseError("PostgreSQL pool not available")
        await pool.execute("""
            INSERT INTO tenants (id, name, slug, email, phone, plan_id, settings, gdpr_consent, gdpr_consented_at, api_key, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), $9, NOW(), NOW())
        """, tenant_id, name, slug, phone, plan_id, json.dumps(settings or {}), gdpr_consent, api_key)
        return await pool.fetchrow("SELECT * FROM tenants WHERE id = $1", tenant_id)
    else:
        conn = _get_sqlite_conn()
        conn.execute("""
            INSERT INTO tenants (id, name, slug, email, phone, plan_id, settings, gdpr_consent, gdpr_consented_at, api_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tenant_id, name, slug, email, phone, plan_id, json.dumps(settings or {}),
              gdpr_consent, now.isoformat() if gdpr_consent else None, api_key, now.isoformat(), now.isoformat()))
        conn.commit()
        row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        conn.close()
        return row


async def get_tenant_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT * FROM tenants WHERE id = $1", tenant_id)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        conn.close()
        return row


async def list_tenants_db():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetch("SELECT * FROM tenants WHERE is_active = true ORDER BY created_at DESC")
    else:
        conn = _get_sqlite_conn()
        rows = conn.execute("SELECT * FROM tenants WHERE is_active = 1 ORDER BY created_at DESC").fetchall()
        conn.close()
        return rows


async def get_tenant_by_api_key(api_key):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT id, name FROM tenants WHERE api_key = $1", api_key)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT id, name FROM tenants WHERE api_key = ?", (api_key,)).fetchone()
        conn.close()
        return row
    return None


async def verify_tenant_api_key(tenant_id: str, api_key: str) -> bool:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT 1 FROM tenants WHERE id = $1 AND api_key = $2", tenant_id, api_key)
            return row is not None
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT 1 FROM tenants WHERE id = ? AND api_key = ?", (tenant_id, api_key)).fetchone()
        conn.close()
        return row is not None
    return False


async def get_user_by_email_db(email):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT id, tenant_id, email, password_hash, role, display_name FROM users WHERE email = $1", email)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute(
            "SELECT id, tenant_id, email, password_hash, role, display_name FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()
        return row
    return None


async def get_tenant_settings_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT * FROM tenant_settings WHERE tenant_id = $1", tenant_id)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT * FROM tenant_settings WHERE tenant_id = ?", (tenant_id,)).fetchone()
        conn.close()
        return row
    return None


async def update_tenant_settings_db(tenant_id, settings):
    api_feeds = json.dumps(settings.get("api_feeds"))
    auto_mode_enabled = int(settings.get("auto_mode_enabled", 0))
    redact_pii = int(settings.get("redact_pii", 1))
    require_consent = int(settings.get("require_consent", 1))
    sync_dnc = int(settings.get("sync_dnc", 0))
    mcp_servers = json.dumps(settings.get("mcp_servers", "{}"))
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                """INSERT INTO tenant_settings ... ON CONFLICT DO UPDATE ...""",
                tenant_id, api_feeds, auto_mode_enabled, redact_pii, require_consent, sync_dnc, mcp_servers
            )
    else:
        conn = _get_sqlite_conn()
        conn.execute(
            """INSERT INTO tenant_settings ... ON CONFLICT DO UPDATE ...""",
            (tenant_id, api_feeds, auto_mode_enabled, redact_pii, require_consent, sync_dnc, mcp_servers)
        )
        conn.commit()
        conn.close()


# --- Agents ---

async def create_agent(tenant_id, name, display_name, agent_type="ai", skills=None, config=None, phone=None, email=None):
    agent_id = str(uuid.uuid4())
    sip_extension = f"3{agent_id[:6]}"
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO agents (id, tenant_id, name, display_name, agent_type, skills, config, phone, email, sip_extension, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'offline', NOW(), NOW())
            """, agent_id, tenant_id, name, display_name or name, agent_type, json.dumps(skills or []), json.dumps(config or {}), phone, email, sip_extension)
            return await pool.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
    else:
        conn = _get_sqlite_conn()
        conn.execute("""
            INSERT INTO agents (...) VALUES (...)
        """, (...))
        conn.commit()
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        conn.close()
        return row


async def get_agent_db(agent_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        conn.close()
        return row


async def list_agents(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetch("SELECT * FROM agents WHERE tenant_id = $1 ORDER BY name", tenant_id)
    else:
        conn = _get_sqlite_conn()
        rows = conn.execute("SELECT * FROM agents WHERE tenant_id = ? ORDER BY name", (tenant_id,)).fetchall()
        conn.close()
        return rows


async def update_agent_status(agent_id, status, session_ref=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.fetchval("SELECT * FROM update_agent_status($1, $2, $3)", agent_id, status, session_ref)
            return json.loads(result) if result else {"success": False, "error": "function returned null"}
    else:
        conn = _get_sqlite_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE agents SET status = ?, last_seen_at = ?, updated_at = ? WHERE id = ?", (status, now, now, agent_id))
        agent_row = conn.execute("SELECT tenant_id, status FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if agent_row:
            conn.execute("INSERT INTO agent_activity (...) VALUES (...)", (...))
        conn.commit()
        conn.close()
        return {"success": True, "agent_id": agent_id, "new_status": status}


async def update_agent_db(agent_id, tenant_id, name=None, display_name=None, agent_type=None, skills=None, config=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            fields = []; values = []; idx = 1
            if name is not None: fields.append(f"name = ${idx}"); values.append(name); idx += 1
            ...  # Same pattern as current
    else:
        conn = _get_sqlite_conn()
        ...  # Same pattern


async def delete_agent_db(agent_id, tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.execute("DELETE FROM agents WHERE id = $1 AND tenant_id = $2", agent_id, tenant_id)
            return result != "DELETE 0"
    else:
        conn = _get_sqlite_conn()
        conn.execute("DELETE FROM agents WHERE id = ? AND tenant_id = ?", (agent_id, tenant_id))
        affected = conn.total_changes
        conn.commit(); conn.close()
        return affected > 0


async def get_available_agents(tenant_id, skills=None):
    skills_filter = skills or []
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if skills_filter:
                return await pool.fetch("SELECT * FROM agents WHERE tenant_id = $1 AND status = 'available' AND skills @> $2 ORDER BY total_calls ASC", tenant_id, json.dumps(skills_filter))
            return await pool.fetch("SELECT * FROM agents WHERE tenant_id = $1 AND status = 'available' ORDER BY total_calls ASC", tenant_id)
    else:
        conn = _get_sqlite_conn()
        rows = conn.execute("SELECT * FROM agents WHERE tenant_id = ? AND status = 'available' ORDER BY total_calls ASC", (tenant_id,)).fetchall()
        conn.close()
        if skills_filter:
            return [r for r in rows if any(s in _parse_skills(r.get('skills')) for s in skills_filter)]
        return rows


async def create_agent_profile_db(profile_id, tenant_id, name, prompt, parameters):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("INSERT INTO agent_profiles (id, tenant_id, name, prompt, parameters) VALUES ($1, $2, $3, $4, $5)", profile_id, tenant_id, name, prompt, json.dumps(parameters))
    else:
        conn = _get_sqlite_conn()
        conn.execute("INSERT INTO agent_profiles (id, tenant_id, name, prompt, parameters) VALUES (?, ?, ?, ?, ?)", (profile_id, tenant_id, name, prompt, json.dumps(parameters)))
        conn.commit(); conn.close()
```

- [ ] **Step 5: Create `db_calls.py` — Call sessions, queue, analytics, audit, misc**

```python
"""Call sessions, queue, analytics, audit, and integration helpers."""

import json
import uuid
from datetime import datetime, timezone

from apps.api.services.db_pool import get_pg_pool, _get_sqlite_conn
from apps.api.services.db_schema import USE_POSTGRES
from apps.api.services.db_errors import NotFound, DatabaseError

# --- Call Sessions ---

async def create_call_session(tenant_id, agent_id, caller_number, caller_name=None, called_number=None,
                              call_direction="inbound", intent_detected=None, sip_call_id=None):
    call_id = str(uuid.uuid4())
    status = "ringing" if agent_id else "initiated"
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO call_sessions (...) VALUES (...)
            """, ...)
            return await pool.fetchrow("SELECT * FROM call_sessions WHERE id = $1", call_id)
    else:
        conn = _get_sqlite_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""INSERT INTO call_sessions (...) VALUES (?)""", (...))
        conn.commit()
        row = conn.execute("SELECT * FROM call_sessions WHERE id = ?", (call_id,)).fetchone()
        conn.close()
        return row


async def get_call_session(call_id):
    # Same pattern as current


async def update_call_status(call_id, status):
    # Same pattern as current


async def list_calls(tenant_id, status=None):
    # Same pattern as current


async def enqueue_call(tenant_id, caller_number, intent=None, skills_required=None):
    # Same pattern as current


async def dequeue_call(tenant_id, agent_id):
    # Same pattern as current


async def get_usage_stats(tenant_id):
    # Same pattern as current


async def get_billing_summary(tenant_id, period_start, period_end):
    # Same pattern as current


async def log_audit_event(tenant_id, user_id, action, resource_type, resource_id, old_values=None, new_values=None):
    # Same pattern as current


async def get_saas_dashboard_db(tenant_id):
    # Same pattern as current


async def rent_agent_db(rental_id, tenant_id, profile_id, duration_type, end_time):
    # Same pattern as current


async def get_session_recordings_db(tenant_id):
    # Same pattern as current


async def get_pending_approvals_db(tenant_id):
    # Same pattern as current


async def process_approval_db(approval_id, status, tenant_id):
    # Same pattern as current


async def get_webhook_url_db(tenant_id):
    # Same pattern as current


async def lookup_invoice_db(invoice_id):
    # Same pattern as current


async def get_order_status_db(order_id):
    # Same pattern as current
```

- [ ] **Step 6: Create `db_errors.py` — Centralized error types**

```python
"""Centralized database error types.

Replaces inconsistent patterns: bare returns, {"success": False} dicts,
and silent Exception catches with typed results.
"""

from typing import TypeVar, Union, Generic, Optional

T = TypeVar('T')


class DatabaseError(Exception):
    """Base for all database errors."""
    def __init__(self, message: str, detail: Optional[dict] = None):
        self.message = message
        self.detail = detail or {}
        super().__init__(self.message)


class NotFoundError(DatabaseError):
    """Record not found."""
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} not found: {resource_id}", {"resource": resource, "id": resource_id})


class PoolNotAvailableError(DatabaseError):
    """Database connection pool unavailable."""
    def __init__(self):
        super().__init__("Database pool not available")


def ok(data: T) -> dict:
    """Standard success result."""
    return {"success": True, "data": data}


def err(message: str, code: str = "error") -> dict:
    """Standard error result."""
    return {"success": False, "error": message, "code": code}
```

- [ ] **Step 7: Reduce database.py to a re-exports shim**

After creating all new modules, replace database.py content with:

```python
"""Database layer — re-exports from focused modules.

Split from monolithic database.py into:
  - db_pool.py:      Connection pool, encryption, context managers
  - db_schema.py:    Schema SQL, init functions, config constants
  - db_tenants.py:   Tenant and agent CRUD operations
  - db_calls.py:     Call sessions, queue, analytics, audit, helpers
  - db_errors.py:    Centralized error types

All symbols are re-exported here for backward compatibility.
See individual modules for documentation.
"""

# Re-export all public symbols
from apps.api.services.db_pool import (
    encrypt_val, decrypt_val,
    get_pg_pool, close_pg_pool,
    db_context,
    _get_sqlite_conn, _release_sqlite_conn, _get_sqlite_conn_async,
)

from apps.api.services.db_schema import (
    USE_POSTGRES, DATABASE_URL, SQLITE_PATH,
    SCHEMA_SQL, SQLITE_SCHEMA_SQL,
    init_pg_schema, init_sqlite_schema,
)

from apps.api.services.db_tenants import (
    create_tenant, get_tenant_db, list_tenants_db,
    get_tenant_by_api_key, verify_tenant_api_key,
    get_user_by_email_db,
    get_tenant_settings_db, update_tenant_settings_db,
    create_agent, get_agent_db, list_agents,
    update_agent_status, update_agent_db, delete_agent_db,
    get_available_agents,
    create_agent_profile_db,
    _parse_skills,
)

from apps.api.services.db_calls import (
    create_call_session, get_call_session,
    update_call_status, list_calls,
    enqueue_call, dequeue_call,
    get_usage_stats, get_billing_summary,
    log_audit_event,
    get_saas_dashboard_db,
    rent_agent_db,
    get_session_recordings_db,
    get_pending_approvals_db,
    process_approval_db,
    get_webhook_url_db,
    lookup_invoice_db,
    get_order_status_db,
)

from apps.api.services.db_errors import (
    DatabaseError, NotFoundError, PoolNotAvailableError,
    ok, err,
)

# Sync context manager (only works with SQLite)
from contextlib import contextmanager
from apps.api.services.db_pool import _get_sqlite_conn, USE_POSTGRES


@contextmanager
def db_context_sync():
    if USE_POSTGRES:
        raise RuntimeError("db_context_sync not supported for PostgreSQL. Use async db_context instead.")
    conn = _get_sqlite_conn()
    try:
        yield conn
    finally:
        conn.close()


__all__ = [
    "encrypt_val", "decrypt_val",
    "get_pg_pool", "close_pg_pool",
    "db_context", "db_context_sync",
    "USE_POSTGRES", "DATABASE_URL", "SQLITE_PATH",
    "init_pg_schema", "init_sqlite_schema",
    "create_tenant", "get_tenant_db", "list_tenants_db",
    "get_tenant_by_api_key", "verify_tenant_api_key",
    "get_user_by_email_db",
    "get_tenant_settings_db", "update_tenant_settings_db",
    "create_agent", "get_agent_db", "list_agents",
    "update_agent_status", "update_agent_db", "delete_agent_db",
    "get_available_agents", "create_agent_profile_db",
    "create_call_session", "get_call_session",
    "update_call_status", "list_calls",
    "enqueue_call", "dequeue_call",
    "get_usage_stats", "get_billing_summary",
    "log_audit_event",
    "get_saas_dashboard_db", "rent_agent_db",
    "get_session_recordings_db", "get_pending_approvals_db",
    "process_approval_db",
    "get_webhook_url_db", "lookup_invoice_db", "get_order_status_db",
    "DatabaseError", "NotFoundError", "PoolNotAvailableError",
    "ok", "err",
]
```

**IMPORTANT**: Every function body in db_tenants.py and db_calls.py must contain exact copies of the current database.py logic — all the INSERT/UPDATE/SELECT statements. The plan above shows placeholders; the actual implementation must paste the full SQL and logic from the original lines.

---

### Task 2: Replace global mutable state with dependency injection

**Files:**
- Modify: `apps/api/routers/realtime.py`  (CALL_TRANSCRIPTS global → injected)
- Modify: `apps/api/routers/voice_cloning.py` (voice_profiles global → injected)
- Modify: `apps/api/services/queue.py` (_in_memory_queue global → injected)
- Create: `apps/api/services/transcript_store.py` (new service)
- Create: `apps/api/services/voice_profile_store.py` (new service)
- Modify: `apps/api/main.py` (pass dependencies in lifespan)

- [ ] **Step 1: Create `TranscriptStore` service**

```python
"""Transcript storage service — replaces global CALL_TRANSCRIPTS dict."""

import time
import asyncio
from cachetools import LRUCache
import structlog

logger = structlog.get_logger()


class TranscriptStore:
    """Manages in-memory call transcripts with bounded LRU cache.

    Replaces the module-level CALL_TRANSCRIPTS and CALL_LAST_ACTIVITY
    global dicts with an injectable service.
    """

    def __init__(self, max_calls: int = 1000, max_transcripts_per_call: int = 200, stale_ttl: int = 3600):
        self._transcripts: LRUCache = LRUCache(maxsize=max_calls)
        self._last_activity: LRUCache = LRUCache(maxsize=max_calls)
        self._max_per_call = max_transcripts_per_call
        self._stale_ttl = stale_ttl

    def add_transcript(self, call_sid: str, entry: dict) -> None:
        self._transcripts.setdefault(call_sid, [])
        self._last_activity[call_sid] = time.time()
        transcripts = self._transcripts[call_sid]
        transcripts.append(entry)
        if len(transcripts) > self._max_per_call:
            self._transcripts[call_sid] = transcripts[-self._max_per_call:]

    def get_transcripts(self, call_sid: str) -> list:
        return list(self._transcripts.get(call_sid, []))

    def get_or_create(self, call_sid: str) -> list:
        return self._transcripts.setdefault(call_sid, [])

    def cleanup(self, call_sid: str) -> None:
        self._transcripts.pop(call_sid, None)
        self._last_activity.pop(call_sid, None)

    def touch(self, call_sid: str) -> None:
        self._last_activity[call_sid] = time.time()

    async def cleanup_stale_loop(self) -> None:
        while True:
            await asyncio.sleep(600)
            now = time.time()
            stale = [sid for sid, ts in list(self._last_activity.items()) if now - ts > self._stale_ttl]
            for sid in stale:
                self.cleanup(sid)
                logger.info("stale_transcript_purged", call_sid=sid)
```

- [ ] **Step 2: Create `VoiceProfileStore` service**

```python
"""Voice profile storage service — replaces global voice_profiles LRUCache."""

import os
import json
import structlog
from cachetools import LRUCache
from threading import Lock

logger = structlog.get_logger()


class VoiceProfileStore:
    """Manages in-memory voice profiles with thread-safe access.

    Replaces module-level voice_profiles + _voice_profiles_lock.
    """

    def __init__(self, max_profiles: int = 100):
        self._profiles: LRUCache = LRUCache(maxsize=max_profiles)
        self._lock = Lock()

    def put(self, voice_id: str, profile: dict) -> None:
        with self._lock:
            self._profiles[voice_id] = profile

    def get(self, voice_id: str) -> dict | None:
        with self._lock:
            return self._profiles.get(voice_id)

    def get_copy(self, voice_id: str) -> dict | None:
        with self._lock:
            val = self._profiles.get(voice_id)
            return val.copy() if val else None

    def delete(self, voice_id: str) -> bool:
        with self._lock:
            if voice_id in self._profiles:
                del self._profiles[voice_id]
                return True
            return False

    def list_all(self) -> list[dict]:
        with self._lock:
            return [
                {"voice_id": vid, **{k: v for k, v in prof.items() if k in ("name", "language", "engine", "fallback")}}
                for vid, prof in self._profiles.items()
            ]

    def contains(self, voice_id: str) -> bool:
        with self._lock:
            return voice_id in self._profiles
```

- [ ] **Step 3: Modify `queue.py` — Inject InMemoryQueue instead of global**

```python
# Remove line 71: _in_memory_queue = InMemoryQueue()

class QueueManager:
    def __init__(self, redis_client, use_fallback: bool = True, in_memory_queue: InMemoryQueue | None = None):
        self.r = redis_client
        self._use_fallback = use_fallback
        self._in_memory = in_memory_queue or InMemoryQueue()  # Injected
        self._last_health_check = 0
        self._redis_ok = False
```

- [ ] **Step 4: Modify `realtime.py` — Inject TranscriptStore**

```python
# Remove lines 17-18: CALL_TRANSCRIPTS and CALL_LAST_ACTIVITY globals
# Remove _cleanup_stale_transcripts_task method from ConnectionManager

class ConnectionManager:
    def __init__(self, transcript_store: TranscriptStore | None = None):
        self.active_connections: dict[str, WebSocket] = {}
        self.voice_connections: dict[str, tuple[WebSocket, str]] = {}
        self._store = transcript_store or TranscriptStore()

    # All methods that used CALL_TRANSCRIPTS now use self._store
    # ...

# Module-level helper functions must also use the store
# Solution: make broadcast_transcript and cleanup_call_transcripts
# accept transcript_store parameter, or move them into ConnectionManager

def broadcast_transcript(call_sid: str, transcript_entry: dict, store: TranscriptStore | None = None):
    _store = store or _default_store
    _store.add_transcript(call_sid, transcript_entry)
    # ...
```

- [ ] **Step 5: Modify `voice_cloning.py` — Inject VoiceProfileStore**

```python
# Remove line 22-23: voice_profiles and _voice_profiles_lock globals
# Remove import: from cachetools import LRUCache

class VoiceCloningService:
    def __init__(self, profile_store: VoiceProfileStore | None = None):
        self._store = profile_store or VoiceProfileStore()

# Router endpoints get store from app.state
```

- [ ] **Step 6: Wire dependencies in `main.py` lifespan**

```python
# At module level in main.py:
from apps.api.services.transcript_store import TranscriptStore
from apps.api.services.voice_profile_store import VoiceProfileStore
from apps.api.services.queue import InMemoryQueue

# In lifespan():
app.state.transcript_store = TranscriptStore()
app.state.voice_profile_store = VoiceProfileStore()
app.state.in_memory_queue = InMemoryQueue()

# Start cleanup loop
transcript_cleanup = asyncio.create_task(app.state.transcript_store.cleanup_stale_loop())

# Pass to routers
from apps.api.routers.realtime import manager as rt_manager
rt_manager._store = app.state.transcript_store
```

---

### Task 3: Centralize error handling

**Files:**
- Modify: `apps/api/services/db_errors.py` (already created in Task 1)
- Modify: `apps/api/main.py` (add global exception handlers)
- Modify: `apps/api/routers/voice.py`, `saas.py`, `campaign.py`, `auth.py`, `agent.py`

- [ ] **Step 1: Add global exception handlers to main.py**

```python
from apps.api.services.db_errors import DatabaseError, NotFoundError, PoolNotAvailableError


@app.exception_handler(DatabaseError)
async def database_error_handler(request: Request, exc: DatabaseError):
    logger.error("database_error", error=exc.message, detail=exc.detail)
    return JSONResponse(
        status_code=503 if isinstance(exc, PoolNotAvailableError) else 500,
        content={"success": False, "error": exc.message, "code": exc.detail.get("code", "database_error")},
    )


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"success": False, "error": exc.message, "code": "not_found"},
    )
```

- [ ] **Step 2: Audit all db_ function callers — replace `if not result: raise HTTPException(404)`** with raising `NotFoundError` at the DB layer instead. This way callers don't need to check.

- [ ] **Step 3: Replace bare except: pass patterns** — In db_calls.py, replace `except Exception: pass` with `except Exception: logger.warning(...)` for `get_webhook_url_db`, `lookup_invoice_db`, `get_order_status_db`.

- [ ] **Step 4: Replace `except: return True` at line 1469** with proper parsing:

```python
try:
    rows_updated = int(result.split()[-1])
    return rows_updated > 0
except (ValueError, IndexError, AttributeError):
    logger.warning("process_approval_db: unexpected result format", result=result)
    return False
```

---

### Task 4: Fix stale domain references — **DONE**

**Files modified:**
- `kubernetes/deployment.yml` — 6 occurrences
- `kubernetes/ssl.yml` — 9 occurrences
- `kubernetes/services.yml` — 2 occurrences
- `config/fonster/config.json` — 1 occurrence
- `scripts/deploy_gke.bat` — 6 occurrences
- `AUDIT_REPORT.md` — 3 occurrences

All stale domain references updated.

---

### Task 5: Fix broken test imports

**Files:**
- Modify: `tests/test_e2e.py` — lines 23, 27, 38, 50, 61, 71
- Modify: `tests/integration/test_affiliate_funnel.py` — line 5

- [ ] **Step 1: Fix `tests/test_e2e.py`**

Replace `from apps.api.services.database import DB_PATH` with `from apps.api.services.database import SQLITE_PATH`
Replace `from apps.api.services.database import get_db_connection` with `from apps.api.services.database import db_context`

- [ ] **Step 2: Fix `tests/integration/test_affiliate_funnel.py`**

Replace `from apps.api.services.database import init_db` with `from apps.api.services.database import init_sqlite_schema`

---

### Task 6: Fix duplicate db_context() definition

**Files:**
- Modify: `database.py` (the shim) — ensure no duplicate

The current database.py defines `db_context()` at line 75 and again at line 1282 (overwriting). The new db_pool.py has it only once. This is already fixed by the split.

---

### Verification

- [ ] **Step 1: Run tests**

```bash
cd C:\Users\User\Desktop\Aetherdesk-Call-Center-main
python -m pytest tests/ -x -v --tb=short 2>&1 | head -100
```

- [ ] **Step 2: Verify imports**

```bash
cd C:\Users\User\Desktop\Aetherdesk-Call-Center-main
python -c "from apps.api.services.database import db_context, get_pg_pool, create_tenant, create_call_session; print('All imports OK')"
```

- [ ] **Step 3: Verify k8s domain fix**

```bash
cd C:\Users\User\Desktop\Aetherdesk-Call-Center-main
if grep -r "overlay365.com" kubernetes/ config/ scripts/ --include="*.yml" --include="*.yaml" --include="*.bat" --include="*.json"; then echo "ERROR: overlay365.com still found"; else echo "OK: all domains migrated"; fi
```
