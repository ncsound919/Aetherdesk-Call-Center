import os
import json
import uuid
import asyncio
import structlog
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import asyncpg
import sqlite3

def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

logger = structlog.get_logger()

# ── Configuration ────────────────────────────────────────────────

USE_POSTGRES = os.getenv("USE_POSTGRES", "false").lower() == "true"

DATABASE_URL = os.getenv("DATABASE_URL", None)

# Only require DATABASE_URL when explicitly using Postgres
if USE_POSTGRES and not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable must be set when USE_POSTGRES=true")

# SQLite fallback (local dev)
SQLITE_PATH = os.getenv("SQLITE_PATH", "aetherdesk.db")

# SQLite connection pool settings
SQLITE_POOL_SIZE = int(os.getenv("SQLITE_POOL_SIZE", "5"))
SQLITE_TIMEOUT = int(os.getenv("SQLITE_TIMEOUT", "30"))

# ── Encryption (HIPAA) ──────────────────────────────────────────

try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
except ImportError:
    _FERNET_AVAILABLE = False

# DEV default: a valid 32-byte url-safe base64 key. Override via ENCRYPTION_KEY in production.
_DEV_ENCRYPTION_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if USE_POSTGRES and not ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY environment variable must be set when USE_POSTGRES=true")

if not ENCRYPTION_KEY:
    logger.warning("ENCRYPTION_KEY not set — using insecure dev default. Set this env var in production.")
    ENCRYPTION_KEY = _DEV_ENCRYPTION_KEY

_fernet = None
if _FERNET_AVAILABLE:
    try:
        _fernet = Fernet(ENCRYPTION_KEY.encode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to initialize Fernet with provided ENCRYPTION_KEY: {e}. Encryption disabled.")
        _fernet = None


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


# ── Async Context Manager ──────────────────────────────────────────

@asynccontextmanager
async def db_context():
    """Async context manager that yields a database connection.

    Uses PostgreSQL pool in production, SQLite with connection pooling for dev mode.
    """
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

_pg_pool: Optional[asyncpg.Pool] = None


async def get_pg_pool() -> Optional[asyncpg.Pool]:
    """Get or create the asyncpg connection pool."""
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
    """Close the asyncpg connection pool."""
    global _pg_pool
    if _pg_pool and not _pg_pool.is_closed():
        await _pg_pool.close()
        logger.info("PostgreSQL pool closed")


# ── SQLite Fallback (Local Development) ─────────────────────────

_sqlite_conn_pool: list = []
_sqlite_pool_lock = asyncio.Lock()


def _enable_wal_mode(conn: sqlite3.Connection):
    """Enable WAL mode for better concurrent read/write performance."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap


async def _get_sqlite_conn_async() -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode from the pool (async-safe)."""
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
    """Return a connection to the pool."""
    global _sqlite_conn_pool
    if len(_sqlite_conn_pool) < SQLITE_POOL_SIZE:
        _sqlite_conn_pool.append(conn)
    else:
        conn.close()


def _get_sqlite_conn():
    """Get a SQLite connection for local development."""
    conn = sqlite3.connect(SQLITE_PATH, timeout=SQLITE_TIMEOUT)
    conn.row_factory = _dict_factory
    _enable_wal_mode(conn)
    return conn


# ── Schema Initialization ───────────────────────────────────────

SCHEMA_SQL = """
-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tenants
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20),
    plan_id UUID REFERENCES plans(id),
    plan_started_at TIMESTAMPTZ DEFAULT NOW(),
    plan_ends_at TIMESTAMPTZ,
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    gdpr_consent BOOLEAN DEFAULT FALSE,
    gdpr_consented_at TIMESTAMPTZ,
    data_processing_agreement BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

-- Plans
CREATE TABLE IF NOT EXISTS plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    price_per_hour DECIMAL(10, 2) NOT NULL DEFAULT 0,
    price_per_day DECIMAL(10, 2) NOT NULL DEFAULT 0,
    price_per_week DECIMAL(10, 2) NOT NULL DEFAULT 0,
    price_per_month DECIMAL(10, 2) NOT NULL DEFAULT 0,
    max_concurrent_calls INT DEFAULT 10,
    max_agents INT DEFAULT 5,
    max_recordings_mb INT DEFAULT 1000,
    features JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agents
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(20),
    agent_type VARCHAR(20) NOT NULL DEFAULT 'ai',
    status VARCHAR(20) NOT NULL DEFAULT 'offline',
    skills JSONB DEFAULT '[]',
    config JSONB DEFAULT '{}',
    sip_extension VARCHAR(20) UNIQUE,
    sip_password VARCHAR(128),
    encryption_key VARCHAR(256),
    total_calls INT DEFAULT 0,
    total_talk_time_seconds INT DEFAULT 0,
    avg_rating DECIMAL(3, 2) DEFAULT 0.0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

-- Call Sessions
CREATE TABLE IF NOT EXISTS call_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
    caller_number VARCHAR(20) NOT NULL,
    caller_name VARCHAR(255),
    called_number VARCHAR(20) NOT NULL,
    call_direction VARCHAR(10) NOT NULL,
    call_status VARCHAR(20) NOT NULL DEFAULT 'initiated',
    call_type VARCHAR(20) DEFAULT 'voice',
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    duration_seconds INT DEFAULT 0,
    talk_time_seconds INT DEFAULT 0,
    hold_time_seconds INT DEFAULT 0,
    wait_time_seconds INT DEFAULT 0,
    cost_per_minute DECIMAL(8, 4) DEFAULT 0,
    total_cost DECIMAL(12, 4) DEFAULT 0,
    currency VARCHAR(3) DEFAULT 'USD',
    sip_call_id VARCHAR(255),
    sip_from VARCHAR(255),
    sip_to VARCHAR(255),
    transcription_id UUID,
    recording_id UUID,
    sentiment_score DECIMAL(5, 4),
    intent_detected VARCHAR(100),
    ai_summary TEXT,
    pii_redacted BOOLEAN DEFAULT FALSE,
    encryption_key VARCHAR(256),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Call Queue
CREATE TABLE IF NOT EXISTS call_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id UUID REFERENCES call_sessions(id) ON DELETE CASCADE,
    caller_number VARCHAR(20) NOT NULL,
    position INT NOT NULL,
    priority INT DEFAULT 5,
    estimated_wait_seconds INT,
    status VARCHAR(20) DEFAULT 'waiting',
    intent VARCHAR(100),
    skills_required JSONB DEFAULT '[]',
    enqueued_at TIMESTAMPTZ DEFAULT NOW(),
    assigned_at TIMESTAMPTZ,
    abandoned_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agent Activity Log
CREATE TABLE IF NOT EXISTS agent_activity (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    activity_type VARCHAR(20) NOT NULL,
    status_before VARCHAR(20),
    status_after VARCHAR(20),
    call_id UUID REFERENCES call_sessions(id),
    session_ref VARCHAR(255),
    duration_seconds INT DEFAULT 0,
    ip_address INET,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Recordings
CREATE TABLE IF NOT EXISTS recordings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id UUID REFERENCES call_sessions(id),
    agent_id UUID REFERENCES agents(id),
    file_path VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT,
    duration_seconds INT,
    format VARCHAR(10) DEFAULT 'wav',
    encryption_algorithm VARCHAR(20) DEFAULT 'AES-256-GCM',
    encryption_key_id VARCHAR(255),
    checksum VARCHAR(255),
    transcription TEXT,
    pii_redacted BOOLEAN DEFAULT FALSE,
    access_policy JSONB DEFAULT '{}',
    retention_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- Transcriptions
CREATE TABLE IF NOT EXISTS transcriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id UUID REFERENCES call_sessions(id),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stt_engine VARCHAR(50) DEFAULT 'deepgram',
    language_code VARCHAR(10) DEFAULT 'en-US',
    confidence_score DECIMAL(5, 4),
    full_text TEXT,
    segments JSONB DEFAULT '[]',
    speaker_diarization JSONB DEFAULT '[]',
    pii_redacted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Billing
CREATE TABLE IF NOT EXISTS billing_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    total_calls INT DEFAULT 0,
    total_minutes DECIMAL(12, 2) DEFAULT 0,
    total_talk_minutes DECIMAL(12, 2) DEFAULT 0,
    total_agent_hours DECIMAL(12, 2) DEFAULT 0,
    storage_used_mb DECIMAL(12, 2) DEFAULT 0,
    subtotal DECIMAL(12, 4) DEFAULT 0,
    tax_rate DECIMAL(5, 4) DEFAULT 0,
    tax_amount DECIMAL(12, 4) DEFAULT 0,
    total_amount DECIMAL(12, 4) DEFAULT 0,
    currency VARCHAR(3) DEFAULT 'USD',
    status VARCHAR(20) DEFAULT 'pending',
    stripe_invoice_id VARCHAR(255),
    stripe_payment_id VARCHAR(255),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit Log
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id),
    user_id UUID,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    old_values JSONB,
    new_values JSONB,
    ip_address INET,
    user_agent VARCHAR(500),
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_calls_tenant ON call_sessions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_calls_agent ON call_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_calls_status ON call_sessions(call_status);
CREATE INDEX IF NOT EXISTS idx_calls_start_time ON call_sessions(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_agents_tenant ON agents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_queue_waiting ON call_queue(status) WHERE status = 'waiting';
CREATE INDEX IF NOT EXISTS idx_activity_agent ON agent_activity(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_tenant ON agent_activity(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recordings_call ON recordings(call_id);
CREATE INDEX IF NOT EXISTS idx_billing_tenant ON billing_records(tenant_id, period_start DESC);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id, created_at DESC);

-- Row Level Security
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE recordings ENABLE ROW LEVEL SECURITY;
ALTER TABLE transcriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_agents ON agents
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
CREATE POLICY tenant_isolation_calls ON call_sessions
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
CREATE POLICY tenant_isolation_queue ON call_queue
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
CREATE POLICY tenant_isolation_activity ON agent_activity
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
CREATE POLICY tenant_isolation_recordings ON recordings
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
CREATE POLICY tenant_isolation_transcriptions ON transcriptions
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
CREATE POLICY tenant_isolation_billing ON billing_records
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Encryption function
CREATE OR REPLACE FUNCTION encrypt_data(plaintext TEXT, key TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN pgp_sym_encrypt(plaintext, key);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION decrypt_data(ciphertext TEXT, key TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN pgp_sym_decrypt(ciphertext::bytea, key);
END;
$$ LANGUAGE plpgsql;

-- Agent status function
CREATE OR REPLACE FUNCTION update_agent_status(
    p_agent_id UUID,
    p_status VARCHAR(20),
    p_session_ref VARCHAR(255) DEFAULT NULL
) RETURNS JSON AS $$
DECLARE
    v_agent agents%ROWTYPE;
BEGIN
    SELECT * INTO v_agent FROM agents WHERE id = p_agent_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Agent not found');
    END IF;
    UPDATE agents SET status = p_status, last_seen_at = NOW(), updated_at = NOW()
    WHERE id = p_agent_id;
    INSERT INTO agent_activity (agent_id, tenant_id, activity_type, status_before, status_after, session_ref)
    VALUES (p_agent_id, v_agent.tenant_id, 'status_change', v_agent.status, p_status, p_session_ref);
    RETURN json_build_object('success', true, 'agent_id', p_agent_id, 'new_status', p_status);
END;
$$ LANGUAGE plpgsql;

-- Call status update function
CREATE OR REPLACE FUNCTION update_call_status_by_id(
    p_call_id UUID,
    p_status VARCHAR(20)
) RETURNS JSON AS $$
DECLARE
    v_call call_sessions%ROWTYPE;
BEGIN
    SELECT * INTO v_call FROM call_sessions WHERE id = p_call_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Call not found');
    END IF;
    UPDATE call_sessions SET call_status = p_status, updated_at = NOW()
    WHERE id = p_call_id;
    RETURN json_build_object('success', true, 'call_id', p_call_id, 'new_status', p_status);
END;
$$ LANGUAGE plpgsql;

-- Cost calculation
CREATE OR REPLACE FUNCTION calculate_call_cost(
    p_duration_seconds INT,
    p_tenant_id UUID
) RETURNS DECIMAL AS $$
DECLARE
    v_plan plans%ROWTYPE;
    v_rate DECIMAL;
BEGIN
    SELECT * INTO v_plan FROM plans WHERE id = (
        SELECT plan_id FROM tenants WHERE id = p_tenant_id
    );
    v_rate := v_plan.price_per_hour / 60;
    RETURN ROUND((p_duration_seconds::DECIMAL / 60) * v_rate, 4);
END;
$$ LANGUAGE plpgsql;

-- Auto-assign agent function
CREATE OR REPLACE FUNCTION assign_agent_to_call(
    p_tenant_id UUID,
    p_intent VARCHAR(100),
    p_caller_number VARCHAR(20)
) RETURNS JSON AS $$
DECLARE
    v_agent agents%ROWTYPE;
    v_call_id UUID;
    v_queue_pos INT;
BEGIN
    SELECT * INTO v_agent
    FROM agents
    WHERE tenant_id = p_tenant_id
      AND status = 'available'
      AND skills @> jsonb_build_array(
          CASE p_intent
              WHEN 'sales' THEN 'sales'
              WHEN 'billing' THEN 'billing'
              WHEN 'technical' THEN 'technical'
              ELSE 'support'
          END
      )
    ORDER BY total_calls ASC
    LIMIT 1;

    IF NOT FOUND THEN
        SELECT COALESCE(MAX(position), 0) + 1 INTO v_queue_pos
        FROM call_queue WHERE tenant_id = p_tenant_id AND status = 'waiting';
        INSERT INTO call_queue (tenant_id, caller_number, position, intent)
        VALUES (p_tenant_id, p_caller_number, v_queue_pos, p_intent);
        RETURN json_build_object(
            'success', true, 'queued', true,
            'queue_position', v_queue_pos,
            'message', 'No agents available. Added to queue.'
        );
    END IF;

    INSERT INTO call_sessions (tenant_id, agent_id, caller_number, call_direction, call_status)
    VALUES (p_tenant_id, v_agent.id, p_caller_number, 'inbound', 'ringing')
    RETURNING id INTO v_call_id;
    UPDATE agents SET status = 'busy' WHERE id = v_agent.id;
    RETURN json_build_object(
        'success', true, 'agent_id', v_agent.id,
        'agent_name', v_agent.name, 'call_id', v_call_id,
        'sip_extension', v_agent.sip_extension
    );
END;
$$ LANGUAGE plpgsql;

-- GDPR deletion function
CREATE OR REPLACE FUNCTION gdpr_delete_user_data(p_phone_number VARCHAR(20))
RETURNS JSON AS $$
DECLARE
    v_calls_updated INT;
    v_recordings_updated INT;
BEGIN
    UPDATE call_sessions SET caller_number = 'REDACTED', caller_name = NULL, pii_redacted = TRUE
    WHERE caller_number = p_phone_number RETURNING 1 INTO v_calls_updated;
    UPDATE recordings SET retention_until = NOW(), pii_redacted = TRUE
    WHERE call_id IN (SELECT id FROM call_sessions WHERE caller_number = p_phone_number)
    RETURNING 1 INTO v_recordings_updated;
    RETURN json_build_object('success', true,
        'calls_anonymized', COALESCE(v_calls_updated, 0),
        'recordings_flagged', COALESCE(v_recordings_updated, 0));
END;
$$ LANGUAGE plpgsql;

-- Agent performance view
CREATE OR REPLACE VIEW agent_performance AS
SELECT
    a.id AS agent_id, a.name, a.tenant_id, a.status,
    a.total_calls, a.total_talk_time_seconds,
    COALESCE(ROUND(a.total_talk_time_seconds::DECIMAL / NULLIF(a.total_calls, 0), 2), 0) AS avg_call_duration,
    a.avg_rating,
    COUNT(DISTINCT cs.id) FILTER (WHERE cs.call_status = 'active' AND cs.start_time > NOW() - INTERVAL '1 day') AS today_calls,
    t.name AS tenant_name
FROM agents a
LEFT JOIN call_sessions cs ON cs.agent_id = a.id AND cs.start_time > NOW() - INTERVAL '1 day'
LEFT JOIN tenants t ON t.id = a.tenant_id
GROUP BY a.id, a.name, a.tenant_id, a.status, a.total_calls, a.total_talk_time_seconds, a.avg_rating, t.name;

-- Billing summary view
CREATE OR REPLACE VIEW billing_summary AS
SELECT
    t.id AS tenant_id, t.name AS tenant_name,
    COUNT(DISTINCT cs.id) AS total_calls,
    SUM(cs.duration_seconds) / 60.0 AS total_minutes,
    SUM(cs.total_cost) AS total_spent,
    p.name AS current_plan, t.plan_ends_at AS plan_expires
FROM tenants t
LEFT JOIN call_sessions cs ON cs.tenant_id = t.id
LEFT JOIN plans p ON p.id = t.plan_id
GROUP BY t.id, t.name, p.name, t.plan_ends_at;

-- Triggers
CREATE OR REPLACE FUNCTION update_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tenants_updated BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_agents_updated BEFORE UPDATE ON agents FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_calls_updated BEFORE UPDATE ON call_sessions FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_transcriptions_updated BEFORE UPDATE ON transcriptions FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Seed default plans
INSERT INTO plans (name, description, price_per_hour, price_per_day, price_per_week, price_per_month, max_concurrent_calls, max_agents, max_recordings_mb, features) VALUES
('Starter', 'Small business plan', 2.50, 20.00, 80.00, 299.00, 2, 2, 500, '["basic_ivr","call_recording","basic_analytics"]'),
('Pro', 'Growing business plan', 4.00, 35.00, 120.00, 499.00, 5, 5, 2000, '["smart_routing","ai_assistant","advanced_analytics","multi_channel"]'),
('Enterprise', 'Large scale operations', 6.50, 55.00, 200.00, 999.00, 20, 20, 10000, '["custom_ai","predictive_routing","real_time_monitoring","api_access","dedicated_support"]')
ON CONFLICT (name) DO NOTHING;
"""


# ── SQLite Schema (local dev fallback) ──────────────────────────

SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL UNIQUE, phone TEXT, plan_id TEXT REFERENCES plans(id),
    plan_started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, plan_ends_at TIMESTAMP,
    stripe_customer_id TEXT, stripe_subscription_id TEXT,
    settings TEXT DEFAULT '{}', is_active BOOLEAN DEFAULT 1,
    is_verified BOOLEAN DEFAULT 0, gdpr_consent BOOLEAN DEFAULT 0,
    gdpr_consented_at TIMESTAMP, data_processing_agreement BOOLEAN DEFAULT 0,
    api_key TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, deleted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
    price_per_hour REAL NOT NULL DEFAULT 0, price_per_day REAL NOT NULL DEFAULT 0,
    price_per_week REAL NOT NULL DEFAULT 0, price_per_month REAL NOT NULL DEFAULT 0,
    max_concurrent_calls INTEGER DEFAULT 10, max_agents INTEGER DEFAULT 5,
    max_recordings_mb INTEGER DEFAULT 1000, features TEXT DEFAULT '[]',
    is_active BOOLEAN DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL, display_name TEXT, email TEXT, phone TEXT,
    agent_type TEXT NOT NULL DEFAULT 'ai', status TEXT NOT NULL DEFAULT 'offline',
    skills TEXT DEFAULT '[]', config TEXT DEFAULT '{}', sip_extension TEXT UNIQUE,
    sip_password TEXT, encryption_key TEXT, total_calls INTEGER DEFAULT 0,
    total_talk_time_seconds INTEGER DEFAULT 0, avg_rating REAL DEFAULT 0.0,
    is_active BOOLEAN DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_seen_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS call_sessions (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
    caller_number TEXT NOT NULL, caller_name TEXT, called_number TEXT NOT NULL,
    call_direction TEXT NOT NULL, call_status TEXT NOT NULL DEFAULT 'initiated',
    call_type TEXT DEFAULT 'voice', start_time TIMESTAMP, end_time TIMESTAMP,
    duration_seconds INTEGER DEFAULT 0, talk_time_seconds INTEGER DEFAULT 0,
    hold_time_seconds INTEGER DEFAULT 0, wait_time_seconds INTEGER DEFAULT 0,
    cost_per_minute REAL DEFAULT 0, total_cost REAL DEFAULT 0, currency TEXT DEFAULT 'USD',
    sip_call_id TEXT, sip_from TEXT, sip_to TEXT, transcription_id TEXT,
    recording_id TEXT, sentiment_score REAL, intent_detected TEXT, ai_summary TEXT,
    pii_redacted BOOLEAN DEFAULT 0, encryption_key TEXT, metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS call_queue (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES call_sessions(id) ON DELETE CASCADE,
    caller_number TEXT NOT NULL, position INTEGER NOT NULL, priority INTEGER DEFAULT 5,
    estimated_wait_seconds INTEGER, status TEXT DEFAULT 'waiting', intent TEXT,
    skills_required TEXT DEFAULT '[]', enqueued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_at TIMESTAMP, abandoned_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_activity (
    id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    activity_type TEXT NOT NULL, status_before TEXT, status_after TEXT,
    call_id TEXT REFERENCES call_sessions(id), session_ref TEXT,
    duration_seconds INTEGER DEFAULT 0, ip_address TEXT, metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recordings (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id TEXT REFERENCES call_sessions(id), agent_id TEXT REFERENCES agents(id),
    file_path TEXT NOT NULL, file_size_bytes INTEGER, duration_seconds INTEGER,
    format TEXT DEFAULT 'wav', encryption_algorithm TEXT DEFAULT 'AES-256-GCM',
    encryption_key_id TEXT, checksum TEXT, transcription TEXT, pii_redacted BOOLEAN DEFAULT 0,
    access_policy TEXT DEFAULT '{}', retention_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transcriptions (
    id TEXT PRIMARY KEY, call_id TEXT REFERENCES call_sessions(id),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stt_engine TEXT DEFAULT 'deepgram', language_code TEXT DEFAULT 'en-US',
    confidence_score REAL, full_text TEXT, segments TEXT DEFAULT '[]',
    speaker_diarization TEXT DEFAULT '[]', pii_redacted BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS billing_records (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    period_start TIMESTAMP NOT NULL, period_end TIMESTAMP NOT NULL,
    total_calls INTEGER DEFAULT 0, total_minutes REAL DEFAULT 0,
    total_talk_minutes REAL DEFAULT 0, total_agent_hours REAL DEFAULT 0,
    storage_used_mb REAL DEFAULT 0, subtotal REAL DEFAULT 0,
    tax_rate REAL DEFAULT 0, tax_amount REAL DEFAULT 0, total_amount REAL DEFAULT 0,
    currency TEXT DEFAULT 'USD', status TEXT DEFAULT 'pending',
    stripe_invoice_id TEXT, stripe_payment_id TEXT, notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY, tenant_id TEXT REFERENCES tenants(id), user_id TEXT,
    action TEXT NOT NULL, resource_type TEXT, resource_id TEXT,
    old_values TEXT, new_values TEXT, ip_address TEXT, user_agent TEXT, reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent Profiles (for AI agent configurations)
CREATE TABLE IF NOT EXISTS agent_profiles (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL, prompt TEXT, parameters TEXT DEFAULT '{}',
    is_active INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tenant Settings
CREATE TABLE IF NOT EXISTS tenant_settings (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    api_feeds TEXT DEFAULT '{}', auto_mode_enabled INTEGER DEFAULT 0,
    redact_pii INTEGER DEFAULT 1, require_consent INTEGER DEFAULT 0,
    sync_dnc INTEGER DEFAULT 0, mcp_servers TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Action Approvals (for human-in-the-loop)
CREATE TABLE IF NOT EXISTS action_approvals (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT, agent_id TEXT, action TEXT NOT NULL, params TEXT,
    status TEXT DEFAULT 'pending', approved_by TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Session Recordings (for QA)
CREATE TABLE IF NOT EXISTS session_recordings (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL, transcript TEXT, qa_score REAL, qa_feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rentals (agent rental tracking)
CREATE TABLE IF NOT EXISTS rentals (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL, start_time TIMESTAMP NOT NULL, end_time TIMESTAMP NOT NULL,
    duration_type TEXT NOT NULL, status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Leads (for campaign/outreach)
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL, contact_name TEXT, phone TEXT NOT NULL,
    email TEXT, industry TEXT, notes TEXT, priority INTEGER DEFAULT 5,
    status TEXT DEFAULT 'new', last_called_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Campaign Calls (call tracking)
CREATE TABLE IF NOT EXISTS campaign_calls (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    profile_id TEXT, call_sid TEXT, status TEXT DEFAULT 'initiated',
    outcome TEXT, needs_human_follow_up INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, ended_at TIMESTAMP,
    duration_seconds INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_calls_tenant ON call_sessions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_calls_agent ON call_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_calls_status ON call_sessions(call_status);
CREATE INDEX IF NOT EXISTS idx_agents_tenant ON agents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_profiles_tenant ON agent_profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_leads_tenant ON leads(tenant_id);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_campaign_calls_tenant ON campaign_calls(tenant_id);

INSERT OR IGNORE INTO plans (id, name, description, price_per_hour, price_per_day, price_per_week, price_per_month, max_concurrent_calls, max_agents, max_recordings_mb, features) VALUES
('PLAN-STARTER', 'Starter', 'Small business plan', 2.50, 20.00, 80.00, 299.00, 2, 2, 500, '["basic_ivr","call_recording","basic_analytics"]'),
('PLAN-PRO', 'Pro', 'Growing business plan', 4.00, 35.00, 120.00, 499.00, 5, 5, 2000, '["smart_routing","ai_assistant","advanced_analytics","multi_channel"]'),
('PLAN-ENTERPRISE', 'Enterprise', 'Large scale operations', 6.50, 55.00, 200.00, 999.00, 20, 20, 10000, '["custom_ai","predictive_routing","real_time_monitoring","api_access","dedicated_support"]');
"""


async def init_pg_schema(pool: asyncpg.Pool):
    """Initialize PostgreSQL schema if not exists."""
    statements = [s.strip() for s in SCHEMA_SQL.split(";") if s.strip()]
    async with pool.acquire() as conn:
        for stmt in statements:
            try:
                await conn.execute(stmt)
            except asyncpg.exceptions.DuplicateTableDefinitionError:
                pass
            except Exception as e:
                logger.warning("schema_init_warning", statement=stmt[:80], error=str(e))
    logger.info("PostgreSQL schema initialized")


def init_sqlite_schema():
    """Initialize SQLite schema if not exists."""
    conn = _get_sqlite_conn()
    conn.executescript(SQLITE_SCHEMA_SQL)
    conn.commit()
    conn.close()
    logger.info("SQLite schema initialized")


# ── Database Operations ─────────────────────────────────────────

# --- Tenants ---

async def create_tenant(name, email, slug, phone=None, plan_id=None, settings=None, gdpr_consent=False):
    import secrets
    tenant_id = str(uuid.uuid4())
    api_key = secrets.token_urlsafe(32)  # Generate unique API key
    now = datetime.now(timezone.utc)
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
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
    pool = await get_pg_pool()
    if pool:
        return await pool.fetchrow("SELECT id, name FROM tenants WHERE api_key = $1", api_key)
    return None


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
            INSERT INTO agents (id, tenant_id, name, display_name, agent_type, skills, config, phone, email, sip_extension, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'offline', ?, ?)
        """, (agent_id, tenant_id, name, display_name or name, agent_type, json.dumps(skills or []), json.dumps(config or {}), phone, email, sip_extension, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
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
            result = await pool.fetchval("""
                SELECT * FROM update_agent_status($1, $2, $3)
            """, agent_id, status, session_ref)
            return json.loads(result) if result else {"success": False, "error": "function returned null"}
    else:
        conn = _get_sqlite_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE agents SET status = ?, last_seen_at = ?, updated_at = ? WHERE id = ?",
                     (status, now, now, agent_id))
        agent_row = conn.execute("SELECT tenant_id, status FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if agent_row:
            conn.execute("""
                INSERT INTO agent_activity (agent_id, tenant_id, activity_type, status_before, status_after, session_ref, created_at)
                VALUES (?, ?, 'status_change', ?, ?, ?, ?)
            """, (agent_id, agent_row['tenant_id'], agent_row['status'], status, session_ref, now))
        conn.commit()
        conn.close()
        return {"success": True, "agent_id": agent_id, "new_status": status}


async def update_agent_db(agent_id, tenant_id, name=None, display_name=None, agent_type=None, skills=None, config=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            fields = []
            values = []
            idx = 1
            if name is not None:
                fields.append(f"name = ${idx}"); values.append(name); idx += 1
            if display_name is not None:
                fields.append(f"display_name = ${idx}"); values.append(display_name); idx += 1
            if agent_type is not None:
                fields.append(f"agent_type = ${idx}"); values.append(agent_type); idx += 1
            if skills is not None:
                fields.append(f"skills = ${idx}"); values.append(json.dumps(skills)); idx += 1
            if config is not None:
                fields.append(f"config = ${idx}"); values.append(json.dumps(config)); idx += 1
            if fields:
                fields.append(f"updated_at = NOW()")
                values.extend([agent_id, tenant_id])
                query = f"UPDATE agents SET {', '.join(fields)} WHERE id = ${idx} AND tenant_id = ${idx+1}"
                await pool.execute(query, *values)
            return await pool.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
    else:
        conn = _get_sqlite_conn()
        fields = []
        values = []
        if name is not None:
            fields.append("name = ?"); values.append(name)
        if display_name is not None:
            fields.append("display_name = ?"); values.append(display_name)
        if agent_type is not None:
            fields.append("agent_type = ?"); values.append(agent_type)
        if skills is not None:
            fields.append("skills = ?"); values.append(json.dumps(skills))
        if config is not None:
            fields.append("config = ?"); values.append(json.dumps(config))
        if fields:
            fields.append("updated_at = ?"); values.append(datetime.now(timezone.utc).isoformat())
            values.extend([agent_id, tenant_id])
            conn.execute(f"UPDATE agents SET {', '.join(fields)} WHERE id = ? AND tenant_id = ?", values)
            conn.commit()
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        conn.close()
        return row


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
        conn.commit()
        conn.close()
        return affected > 0


def _parse_skills(skills_value) -> list:
    """Safely parse skills JSON, handling edge cases."""
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


async def get_available_agents(tenant_id, skills=None):
    skills_filter = skills or []
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if skills_filter:
                return await pool.fetch("""
                    SELECT * FROM agents WHERE tenant_id = $1 AND status = 'available'
                    AND skills @> $2 ORDER BY total_calls ASC
                """, tenant_id, json.dumps(skills_filter))
            return await pool.fetch("""
                SELECT * FROM agents WHERE tenant_id = $1 AND status = 'available' ORDER BY total_calls ASC
            """, tenant_id)
    else:
        conn = _get_sqlite_conn()
        rows = conn.execute("SELECT * FROM agents WHERE tenant_id = ? AND status = 'available' ORDER BY total_calls ASC", (tenant_id,)).fetchall()
        conn.close()
        if skills_filter:
            return [r for r in rows if any(s in _parse_skills(r.get('skills')) for s in skills_filter)]
        return rows


# --- Call Sessions ---

async def create_call_session(tenant_id, agent_id, caller_number, caller_name=None, called_number=None,
                              call_direction="inbound", intent_detected=None, sip_call_id=None):
    call_id = str(uuid.uuid4())
    status = "ringing" if agent_id else "initiated"
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO call_sessions (id, tenant_id, agent_id, caller_number, caller_name, called_number,
                    call_direction, call_status, sip_call_id, intent_detected, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW())
            """, call_id, tenant_id, agent_id, caller_number, caller_name, called_number or caller_number,
                call_direction, status, sip_call_id, intent_detected)
            return await pool.fetchrow("SELECT * FROM call_sessions WHERE id = $1", call_id)
    else:
        conn = _get_sqlite_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO call_sessions (id, tenant_id, agent_id, caller_number, caller_name, called_number,
                call_direction, call_status, sip_call_id, intent_detected, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (call_id, tenant_id, agent_id, caller_number, caller_name, called_number or caller_number,
              call_direction, status, sip_call_id, intent_detected, now, now))
        conn.commit()
        row = conn.execute("SELECT * FROM call_sessions WHERE id = ?", (call_id,)).fetchone()
        conn.close()
        return row


async def get_call_session(call_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT * FROM call_sessions WHERE id = $1", call_id)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT * FROM call_sessions WHERE id = ?", (call_id,)).fetchone()
        conn.close()
        return row


async def update_call_status(call_id, status):
    """Update the status of a call session."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("UPDATE call_sessions SET call_status = $1, updated_at = NOW() WHERE id = $2", status, call_id)
            return await pool.fetchrow("SELECT * FROM call_sessions WHERE id = $1", call_id)
    else:
        conn = _get_sqlite_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE call_sessions SET call_status = ?, updated_at = ? WHERE id = ?",
                     (status, now, call_id))
        conn.commit()
        row = conn.execute("SELECT * FROM call_sessions WHERE id = ?", (call_id,)).fetchone()
        conn.close()
        return row


async def list_calls(tenant_id, status=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if status:
                return await pool.fetch("SELECT * FROM call_sessions WHERE tenant_id = $1 AND call_status = $2 ORDER BY created_at DESC", tenant_id, status)
            return await pool.fetch("SELECT * FROM call_sessions WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
    else:
        conn = _get_sqlite_conn()
        if status:
            rows = conn.execute("SELECT * FROM call_sessions WHERE tenant_id = ? AND call_status = ? ORDER BY created_at DESC", (tenant_id, status)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM call_sessions WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
        conn.close()
        return rows


# --- Call Queue ---

async def enqueue_call(tenant_id, caller_number, intent=None, skills_required=None):
    position = 1
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            max_pos = await pool.fetchval("SELECT COALESCE(MAX(position), 0) + 1 FROM call_queue WHERE tenant_id = $1 AND status = 'waiting'", tenant_id)
            position = max_pos or 1
            queue_id = str(uuid.uuid4())
            await pool.execute("""
                INSERT INTO call_queue (id, tenant_id, caller_number, position, intent, status, skills_required)
                VALUES ($1, $2, $3, $4, $5, 'waiting', $6)
            """, queue_id, tenant_id, caller_number, position, intent, json.dumps(skills_required or []))
            return await pool.fetchrow("SELECT * FROM call_queue WHERE id = $1", queue_id)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 AS max_pos FROM call_queue WHERE tenant_id = ? AND status = 'waiting'", (tenant_id,)).fetchone()
        position = row["max_pos"] if row and row["max_pos"] else 1
        queue_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO call_queue (id, tenant_id, caller_number, position, intent, status, skills_required)
            VALUES (?, ?, ?, ?, ?, 'waiting', ?)
        """, (queue_id, tenant_id, caller_number, position, intent, json.dumps(skills_required or [])))
        conn.commit()
        row = conn.execute("SELECT * FROM call_queue WHERE id = ?", (queue_id,)).fetchone()
        conn.close()
        return row


async def dequeue_call(tenant_id, agent_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        "SELECT * FROM call_queue WHERE tenant_id = $1 AND status = 'waiting' ORDER BY position LIMIT 1",
                        tenant_id
                    )
                    if row:
                        await conn.execute("UPDATE call_queue SET status = 'assigned', assigned_at = NOW() WHERE id = $1", row['id'])
                        return dict(row)
    else:
        conn = _get_sqlite_conn()
        now = datetime.now(timezone.utc).isoformat()
        row = conn.execute("SELECT * FROM call_queue WHERE tenant_id = ? AND status = 'waiting' ORDER BY position LIMIT 1", (tenant_id,)).fetchone()
        if row:
            conn.execute("UPDATE call_queue SET status = 'assigned', assigned_at = ? WHERE id = ?", (now, row['id']))
            conn.commit()
            conn.close()
            return dict(row)
        conn.close()
    return None


# --- Usage / Analytics ---

async def get_usage_stats(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            total_agents = await pool.fetchval("SELECT COUNT(*) FROM agents WHERE tenant_id = $1", tenant_id)
            active_agents = await pool.fetchval("SELECT COUNT(*) FROM agents WHERE tenant_id = $1 AND status IN ('available','busy','on_call')", tenant_id)
            total_calls = await pool.fetchval("SELECT COUNT(*) FROM call_sessions WHERE tenant_id = $1", tenant_id)
            active_calls = await pool.fetchval("SELECT COUNT(*) FROM call_sessions WHERE tenant_id = $1 AND call_status = 'active'", tenant_id)
            total_minutes = await pool.fetchval("SELECT COALESCE(SUM(duration_seconds)/60.0, 0) FROM call_sessions WHERE tenant_id = $1", tenant_id)
            return {
                "total_agents": total_agents, "active_agents": active_agents or 0,
                "total_calls": total_calls, "active_calls": active_calls or 0,
                "total_minutes": float(total_minutes or 0), "queue_depth": 0
            }
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM agents WHERE tenant_id = ?", (tenant_id,)).fetchone()
        total_agents = row["cnt"] if row else 0
        row = conn.execute("SELECT COUNT(*) as cnt FROM agents WHERE tenant_id = ? AND status IN ('available','busy','on_call')", (tenant_id,)).fetchone()
        active_agents = row["cnt"] if row else 0
        row = conn.execute("SELECT COUNT(*) as cnt FROM call_sessions WHERE tenant_id = ?", (tenant_id,)).fetchone()
        total_calls = row["cnt"] if row else 0
        row = conn.execute("SELECT COUNT(*) as cnt FROM call_sessions WHERE tenant_id = ? AND call_status = 'active'", (tenant_id,)).fetchone()
        active_calls = row["cnt"] if row else 0
        row = conn.execute("SELECT COALESCE(SUM(duration_seconds)/60.0, 0) as val FROM call_sessions WHERE tenant_id = ?", (tenant_id,)).fetchone()
        total_minutes = row["val"] if row else 0
        conn.close()
        return {
            "total_agents": total_agents, "active_agents": active_agents or 0,
            "total_calls": total_calls or 0, "active_calls": active_calls or 0,
            "total_minutes": float(total_minutes or 0), "queue_depth": 0
        }


async def get_billing_summary(tenant_id, period_start, period_end):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            total_calls = await pool.fetchval("SELECT COUNT(*) FROM call_sessions WHERE tenant_id = $1 AND created_at BETWEEN $2 AND $3", tenant_id, period_start, period_end)
            total_minutes = await pool.fetchval("SELECT COALESCE(SUM(duration_seconds)/60.0, 0) FROM call_sessions WHERE tenant_id = $1 AND created_at BETWEEN $2 AND $3", tenant_id, period_start, period_end)
            return {"total_calls": total_calls, "total_minutes": float(total_minutes or 0), "total_cost": float(total_minutes or 0) * 0.015, "currency": "USD"}
    else:
        conn = _get_sqlite_conn()
        total_calls = conn.execute("SELECT COUNT(*) FROM call_sessions WHERE tenant_id = ? AND created_at BETWEEN ? AND ?", (tenant_id, period_start, period_end)).fetchone()[0]
        total_minutes = conn.execute("SELECT COALESCE(SUM(duration_seconds)/60.0, 0) FROM call_sessions WHERE tenant_id = ? AND created_at BETWEEN ? AND ?", (tenant_id, period_start, period_end)).fetchone()[0]
        conn.close()
        return {"total_calls": total_calls or 0, "total_minutes": float(total_minutes or 0), "total_cost": float(total_minutes or 0) * 0.015, "currency": "USD"}


# --- Audit Logging ---

async def log_audit_event(tenant_id, user_id, action, resource_type, resource_id, old_values=None, new_values=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO audit_log (tenant_id, user_id, action, resource_type, resource_id, old_values, new_values, ip_address)
                VALUES ($1, $2, $3, $4, $5, $6, $7, '127.0.0.1')
            """, tenant_id, user_id, action, resource_type, resource_id, json.dumps(old_values or {}), json.dumps(new_values or {}))
    else:
        conn = _get_sqlite_conn()
        conn.execute("""
            INSERT INTO audit_log (tenant_id, user_id, action, resource_type, resource_id, old_values, new_values, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, '127.0.0.1')
        """, (tenant_id, user_id, action, resource_type, resource_id, json.dumps(old_values or {}), json.dumps(new_values or {})))
        conn.commit()
        conn.close()


# --- Database Context Manager ---
@asynccontextmanager
async def db_context():
    """Async context manager providing a database connection.
    Uses PostgreSQL in production, SQLite for local dev fallback.
    """
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            async with pool.acquire() as conn:
                yield conn
                return
    conn = _get_sqlite_conn()
    try:
        yield conn
    finally:
        conn.close()


# --- Synchronous Context Manager (for use in non-async contexts) ---
import sqlite3
from contextlib import contextmanager

@contextmanager
def db_context_sync():
    """Synchronous context manager for database operations in non-async contexts.
    Uses SQLite directly (not async-safe, use only when async not possible).
    """
    if USE_POSTGRES:
        raise RuntimeError("db_context_sync not supported for PostgreSQL. Use async db_context instead.")
    conn = _get_sqlite_conn()
    try:
        yield conn
    finally:
        conn.close()
