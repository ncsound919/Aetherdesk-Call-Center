"""initial_schema

Revision ID: 33be689273d2
Revises:
Create Date: 2026-06-21 22:46:04.067019

"""
import os
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '33be689273d2'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USE_POSTGRES = os.getenv("USE_POSTGRES", "false").lower() == "true"


def upgrade() -> None:
    if USE_POSTGRES:
        _upgrade_pg()
    else:
        _upgrade_sqlite()


def downgrade() -> None:
    if USE_POSTGRES:
        _downgrade_pg()
    else:
        _downgrade_sqlite()


# ═══════════════════════════════════════════════════════════════════
#  PostgreSQL (production)
# ═══════════════════════════════════════════════════════════════════

PG_UPGRADE = """
-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";

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

-- Functions
CREATE OR REPLACE FUNCTION encrypt_data(plaintext TEXT, key TEXT)
RETURNS TEXT AS $$ BEGIN RETURN pgp_sym_encrypt(plaintext, key); END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION decrypt_data(ciphertext TEXT, key TEXT)
RETURNS TEXT AS $$ BEGIN RETURN pgp_sym_decrypt(ciphertext::bytea, key); END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_agent_status(
    p_agent_id UUID, p_status VARCHAR(20), p_session_ref VARCHAR(255) DEFAULT NULL
) RETURNS JSON AS $$
DECLARE v_agent agents%ROWTYPE;
BEGIN
    SELECT * INTO v_agent FROM agents WHERE id = p_agent_id;
    IF NOT FOUND THEN RETURN json_build_object('success', false, 'error', 'Agent not found'); END IF;
    UPDATE agents SET status = p_status, last_seen_at = NOW(), updated_at = NOW() WHERE id = p_agent_id;
    INSERT INTO agent_activity (agent_id, tenant_id, activity_type, status_before, status_after, session_ref)
    VALUES (p_agent_id, v_agent.tenant_id, 'status_change', v_agent.status, p_status, p_session_ref);
    RETURN json_build_object('success', true, 'agent_id', p_agent_id, 'new_status', p_status);
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_call_status_by_id(p_call_id UUID, p_status VARCHAR(20))
RETURNS JSON AS $$
DECLARE v_call call_sessions%ROWTYPE;
BEGIN
    SELECT * INTO v_call FROM call_sessions WHERE id = p_call_id;
    IF NOT FOUND THEN RETURN json_build_object('success', false, 'error', 'Call not found'); END IF;
    UPDATE call_sessions SET call_status = p_status, updated_at = NOW() WHERE id = p_call_id;
    RETURN json_build_object('success', true, 'call_id', p_call_id, 'new_status', p_status);
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION calculate_call_cost(p_duration_seconds INT, p_tenant_id UUID)
RETURNS DECIMAL AS $$
DECLARE v_plan plans%ROWTYPE; v_rate DECIMAL;
BEGIN
    SELECT * INTO v_plan FROM plans WHERE id = (SELECT plan_id FROM tenants WHERE id = p_tenant_id);
    IF v_plan.price_per_hour IS NULL THEN RETURN 0.0000; END IF;
    v_rate := v_plan.price_per_hour / 60;
    RETURN ROUND((p_duration_seconds::DECIMAL / 60) * v_rate, 4);
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION assign_agent_to_call(
    p_tenant_id UUID, p_intent VARCHAR(100), p_caller_number VARCHAR(20)
) RETURNS JSON AS $$
DECLARE v_agent agents%ROWTYPE; v_call_id UUID; v_queue_pos INT;
BEGIN
    SELECT * INTO v_agent FROM agents WHERE tenant_id = p_tenant_id AND status = 'available'
        AND skills @> jsonb_build_array(CASE p_intent WHEN 'sales' THEN 'sales' WHEN 'billing' THEN 'billing'
            WHEN 'technical' THEN 'technical' ELSE 'support' END)
        ORDER BY total_calls ASC LIMIT 1;
    IF NOT FOUND THEN
        SELECT COALESCE(MAX(position), 0) + 1 INTO v_queue_pos
        FROM call_queue WHERE tenant_id = p_tenant_id AND status = 'waiting';
        INSERT INTO call_queue (tenant_id, caller_number, position, intent)
        VALUES (p_tenant_id, p_caller_number, v_queue_pos, p_intent);
        RETURN json_build_object('success', true, 'queued', true, 'queue_position', v_queue_pos,
            'message', 'No agents available. Added to queue.');
    END IF;
    INSERT INTO call_sessions (tenant_id, agent_id, caller_number, call_direction, call_status)
    VALUES (p_tenant_id, v_agent.id, p_caller_number, 'inbound', 'ringing') RETURNING id INTO v_call_id;
    UPDATE agents SET status = 'busy' WHERE id = v_agent.id;
    RETURN json_build_object('success', true, 'agent_id', v_agent.id, 'agent_name', v_agent.name,
        'call_id', v_call_id, 'sip_extension', v_agent.sip_extension);
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION gdpr_delete_user_data(p_phone_number VARCHAR(20))
RETURNS JSON AS $$
DECLARE v_calls_updated INT; v_recordings_updated INT;
BEGIN
    UPDATE call_sessions SET caller_number = 'REDACTED', caller_name = NULL, pii_redacted = TRUE
    WHERE caller_number = p_phone_number RETURNING 1 INTO v_calls_updated;
    UPDATE recordings SET retention_until = NOW(), pii_redacted = TRUE
    WHERE call_id IN (SELECT id FROM call_sessions WHERE caller_number = p_phone_number)
    RETURNING 1 INTO v_recordings_updated;
    RETURN json_build_object('success', true, 'calls_anonymized', COALESCE(v_calls_updated, 0),
        'recordings_flagged', COALESCE(v_recordings_updated, 0));
END; $$ LANGUAGE plpgsql;

-- Views
CREATE OR REPLACE VIEW agent_performance AS
SELECT a.id AS agent_id, a.name, a.tenant_id, a.status, a.total_calls, a.total_talk_time_seconds,
    COALESCE(ROUND(a.total_talk_time_seconds::DECIMAL / NULLIF(a.total_calls, 0), 2), 0) AS avg_call_duration,
    a.avg_rating,
    COUNT(DISTINCT cs.id) FILTER (WHERE cs.call_status = 'active' AND cs.start_time > NOW() - INTERVAL '1 day') AS today_calls,
    t.name AS tenant_name
FROM agents a LEFT JOIN call_sessions cs ON cs.agent_id = a.id AND cs.start_time > NOW() - INTERVAL '1 day'
LEFT JOIN tenants t ON t.id = a.tenant_id GROUP BY a.id, a.name, a.tenant_id, a.status, a.total_calls, a.total_talk_time_seconds, a.avg_rating, t.name;

CREATE OR REPLACE VIEW billing_summary AS
SELECT t.id AS tenant_id, t.name AS tenant_name, COUNT(DISTINCT cs.id) AS total_calls,
    SUM(cs.duration_seconds) / 60.0 AS total_minutes, SUM(cs.total_cost) AS total_spent,
    p.name AS current_plan, t.plan_ends_at AS plan_expires
FROM tenants t LEFT JOIN call_sessions cs ON cs.tenant_id = t.id
LEFT JOIN plans p ON p.id = t.plan_id GROUP BY t.id, t.name, p.name, t.plan_ends_at;

-- Triggers
CREATE OR REPLACE FUNCTION update_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;

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

PG_DOWNGRADE = """
DROP TRIGGER IF EXISTS trg_tenants_updated ON tenants;
DROP TRIGGER IF EXISTS trg_agents_updated ON agents;
DROP TRIGGER IF EXISTS trg_calls_updated ON call_sessions;
DROP TRIGGER IF EXISTS trg_transcriptions_updated ON transcriptions;
DROP FUNCTION IF EXISTS update_updated_at() CASCADE;
DROP VIEW IF EXISTS agent_performance;
DROP VIEW IF EXISTS billing_summary;
DROP FUNCTION IF EXISTS gdpr_delete_user_data(VARCHAR(20)) CASCADE;
DROP FUNCTION IF EXISTS assign_agent_to_call(UUID, VARCHAR(100), VARCHAR(20)) CASCADE;
DROP FUNCTION IF EXISTS calculate_call_cost(INT, UUID) CASCADE;
DROP FUNCTION IF EXISTS update_call_status_by_id(UUID, VARCHAR(20)) CASCADE;
DROP FUNCTION IF EXISTS update_agent_status(UUID, VARCHAR(20), VARCHAR(255)) CASCADE;
DROP FUNCTION IF EXISTS decrypt_data(TEXT, TEXT) CASCADE;
DROP FUNCTION IF EXISTS encrypt_data(TEXT, TEXT) CASCADE;
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS billing_records CASCADE;
DROP TABLE IF EXISTS transcriptions CASCADE;
DROP TABLE IF EXISTS recordings CASCADE;
DROP TABLE IF EXISTS agent_activity CASCADE;
DROP TABLE IF EXISTS call_queue CASCADE;
DROP TABLE IF EXISTS call_sessions CASCADE;
DROP TABLE IF EXISTS agents CASCADE;
DROP TABLE IF EXISTS tenants CASCADE;
DROP TABLE IF EXISTS plans CASCADE;
"""


# ═══════════════════════════════════════════════════════════════════
#  SQLite (development)
# ═══════════════════════════════════════════════════════════════════

SQLITE_UPGRADE = """
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
    price_per_hour REAL NOT NULL DEFAULT 0, price_per_day REAL NOT NULL DEFAULT 0,
    price_per_week REAL NOT NULL DEFAULT 0, price_per_month REAL NOT NULL DEFAULT 0,
    max_concurrent_calls INTEGER DEFAULT 10, max_agents INTEGER DEFAULT 5,
    max_recordings_mb INTEGER DEFAULT 1000, features TEXT DEFAULT '[]',
    is_active BOOLEAN DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS agent_profiles (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL, prompt TEXT, parameters TEXT DEFAULT '{}',
    is_active INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tenant_settings (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    api_feeds TEXT DEFAULT '{}', auto_mode_enabled INTEGER DEFAULT 0,
    redact_pii INTEGER DEFAULT 1, require_consent INTEGER DEFAULT 0,
    sync_dnc INTEGER DEFAULT 0, mcp_servers TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS action_approvals (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT, agent_id TEXT, action TEXT NOT NULL, params TEXT,
    status TEXT DEFAULT 'pending', approved_by TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS session_recordings (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL, transcript TEXT, qa_score REAL, qa_feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rentals (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL, start_time TIMESTAMP NOT NULL, end_time TIMESTAMP NOT NULL,
    duration_type TEXT NOT NULL, status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL, email TEXT, phone TEXT,
    company TEXT, status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id TEXT REFERENCES customers(id),
    amount REAL NOT NULL, status TEXT DEFAULT 'pending',
    due_date TEXT, description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id TEXT REFERENCES customers(id),
    status TEXT DEFAULT 'processing', total REAL DEFAULT 0,
    expected_delivery TEXT, tracking_number TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL, contact_name TEXT, phone TEXT NOT NULL,
    email TEXT, industry TEXT, notes TEXT, priority INTEGER DEFAULT 5,
    status TEXT DEFAULT 'new', last_called_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

INSERT OR IGNORE INTO customers (id, tenant_id, name, email, phone, company, status) VALUES
('CUST-001', 'TENANT-001', 'Acme Corp', 'billing@acme.com', '555-0100', 'Acme Corp', 'active'),
('CUST-002', 'TENANT-001', 'Globex Inc', 'support@globex.com', '555-0200', 'Globex Inc', 'active');

INSERT OR IGNORE INTO invoices (id, tenant_id, customer_id, amount, status, due_date, description) VALUES
('INV-5001', 'TENANT-001', 'CUST-001', 150.00, 'Paid', '2026-06-01', 'Monthly subscription'),
('INV-5002', 'TENANT-001', 'CUST-002', 300.00, 'Pending', '2026-07-01', 'Enterprise license');

INSERT OR IGNORE INTO orders (id, tenant_id, customer_id, status, total, expected_delivery) VALUES
('ORD-9001', 'TENANT-001', 'CUST-001', 'Processing', 99.99, '2026-06-10'),
('ORD-9002', 'TENANT-001', 'CUST-002', 'Shipped', 249.99, '2026-06-05');

INSERT OR IGNORE INTO tenants (id, name, slug, email, phone, plan_id, settings, is_active, gdpr_consent, api_key) VALUES
('TENANT-001', 'Default Tenant', 'default-tenant', 'admin@aetherdesk.com', '+15550000000', 'PLAN-PRO', '{}', 1, 1, 'dev-api-key');
"""

SQLITE_DOWNGRADE = """
DROP TABLE IF EXISTS campaign_calls;
DROP TABLE IF EXISTS leads;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS rentals;
DROP TABLE IF EXISTS session_recordings;
DROP TABLE IF EXISTS action_approvals;
DROP TABLE IF EXISTS tenant_settings;
DROP TABLE IF EXISTS agent_profiles;
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS billing_records;
DROP TABLE IF EXISTS transcriptions;
DROP TABLE IF EXISTS recordings;
DROP TABLE IF EXISTS agent_activity;
DROP TABLE IF EXISTS call_queue;
DROP TABLE IF EXISTS call_sessions;
DROP TABLE IF EXISTS agents;
DROP TABLE IF EXISTS tenants;
DROP TABLE IF EXISTS plans;
"""


def _upgrade_pg() -> None:
    op.execute(PG_UPGRADE)


def _upgrade_sqlite() -> None:
    conn = op.get_context().connection.connection
    conn.executescript(SQLITE_UPGRADE)


def _downgrade_pg() -> None:
    op.execute(PG_DOWNGRADE)


def _downgrade_sqlite() -> None:
    conn = op.get_context().connection.connection
    conn.executescript(SQLITE_DOWNGRADE)
