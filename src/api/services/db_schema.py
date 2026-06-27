import asyncpg
import structlog

logger = structlog.get_logger()


# ── Schema Initialization ───────────────────────────────────────

SCHEMA_SQL = """
-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Plans (MUST be created before tenants which references it)
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

-- Users
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    verification_token VARCHAR(255),
    reset_token VARCHAR(255),
    reset_token_expires TIMESTAMP,
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    role VARCHAR(50) DEFAULT 'owner',
    avatar_url VARCHAR(500),
    onboarding_completed BOOLEAN DEFAULT FALSE,
    onboarding_step INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);

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

-- Agent Profiles (for AI agent configurations)
CREATE TABLE IF NOT EXISTS agent_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    prompt TEXT,
    parameters JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_profiles_tenant ON agent_profiles(tenant_id);

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

-- Scripts
CREATE TABLE IF NOT EXISTS scripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    content JSONB NOT NULL DEFAULT '{}',
    variables JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT FALSE,
    version INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_scripts_tenant ON scripts(tenant_id);

-- Script Templates
CREATE TABLE IF NOT EXISTS script_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    industry VARCHAR(100),
    content JSONB NOT NULL DEFAULT '{}',
    variables JSONB DEFAULT '[]',
    is_public BOOLEAN DEFAULT TRUE,
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
    IF v_plan.price_per_hour IS NULL THEN
        RETURN 0.0000;
    END IF;
    v_rate := v_plan.price_per_hour / 60;
    RETURN ROUND((p_duration_seconds::DECIMAL / 60) * v_rate, 4);
END;
$$ LANGUAGE plpgsql;

-- Enterprise: Conversation Quality Scores
CREATE TABLE IF NOT EXISTS conversation_quality_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
    call_id UUID REFERENCES call_sessions(id) ON DELETE SET NULL,
    transcript_hash VARCHAR(64),
    rubric_name VARCHAR(100) DEFAULT 'standard',
    total_score DECIMAL(5,2) NOT NULL DEFAULT 0,
    criteria_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cqs_tenant ON conversation_quality_scores(tenant_id);
CREATE INDEX IF NOT EXISTS idx_cqs_agent ON conversation_quality_scores(agent_id);

-- Enterprise: API Versions
CREATE TABLE IF NOT EXISTS api_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    version VARCHAR(20) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    release_date DATE NOT NULL,
    sunset_date DATE,
    changelog TEXT,
    migration_notes TEXT
);

-- Enterprise: Customer Portal Sessions
CREATE TABLE IF NOT EXISTS customer_portal_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id VARCHAR(255) NOT NULL,
    session_data_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cps_tenant ON customer_portal_sessions(tenant_id, customer_id);

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

-- WFM Metrics: AHT
CREATE TABLE IF NOT EXISTS wfm_aht (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL,
    call_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
    duration_seconds INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wfm_aht_tenant ON wfm_aht(tenant_id, created_at);

-- WFM Metrics: FCR
CREATE TABLE IF NOT EXISTS wfm_fcr (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id VARCHAR(255),
    call_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
    resolved INT NOT NULL DEFAULT 0,
    follow_up_call_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wfm_fcr_tenant ON wfm_fcr(tenant_id, created_at);

-- WFM Metrics: CSAT
CREATE TABLE IF NOT EXISTS wfm_csat (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id VARCHAR(255),
    call_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
    rating INT NOT NULL CHECK(rating >= 1 AND rating <= 5),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wfm_csat_tenant ON wfm_csat(tenant_id, created_at);

-- WFM Metrics: NPS
CREATE TABLE IF NOT EXISTS wfm_nps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id VARCHAR(255),
    call_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
    score INT NOT NULL CHECK(score >= 0 AND score <= 10),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wfm_nps_tenant ON wfm_nps(tenant_id, created_at);

-- Training Courses
CREATE TABLE IF NOT EXISTS training_courses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    modules_json JSONB DEFAULT '[]',
    duration_hours DECIMAL(5,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_training_courses_tenant ON training_courses(tenant_id);

-- Training Enrollments
CREATE TABLE IF NOT EXISTS training_enrollments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL,
    course_id UUID NOT NULL REFERENCES training_courses(id) ON DELETE CASCADE,
    progress_pct DECIMAL(5,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'enrolled',
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_training_enrollments_tenant ON training_enrollments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_training_enrollments_agent ON training_enrollments(agent_id);

-- Coaching Sessions
CREATE TABLE IF NOT EXISTS coaching_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL,
    coach_id VARCHAR(255),
    focus_area TEXT,
    notes TEXT,
    status VARCHAR(20) DEFAULT 'scheduled',
    scheduled_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_coaching_sessions_tenant ON coaching_sessions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_coaching_sessions_agent ON coaching_sessions(agent_id);

-- Failover Tests
CREATE TABLE IF NOT EXISTS failover_tests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    service VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    result_json JSONB DEFAULT '{}',
    duration_seconds DECIMAL(10,2) DEFAULT 0,
    tested_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_failover_tests_tenant ON failover_tests(tenant_id);

-- Chaos Experiments
CREATE TABLE IF NOT EXISTS chaos_experiments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    target VARCHAR(100) NOT NULL,
    fault_type VARCHAR(100) NOT NULL,
    duration_seconds INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    result_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chaos_exp_tenant ON chaos_experiments(tenant_id);

-- Vendor Contracts
CREATE TABLE IF NOT EXISTS vendor_contracts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vendor VARCHAR(255) NOT NULL,
    terms TEXT,
    renewal_date DATE,
    status VARCHAR(20) DEFAULT 'active',
    cost DECIMAL(12,2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vendor_contracts_tenant ON vendor_contracts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vendor_contracts_renewal ON vendor_contracts(tenant_id, renewal_date);

-- Backup Channels
CREATE TABLE IF NOT EXISTS backup_channels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    channel_type VARCHAR(50) NOT NULL,
    config_json JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'active',
    last_test_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_backup_channels_tenant ON backup_channels(tenant_id);

-- AI Platform: Models
CREATE TABLE IF NOT EXISTS ai_models (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    model_type TEXT NOT NULL DEFAULT 'intent',
    config_json TEXT DEFAULT '{}',
    metrics_json TEXT DEFAULT '{}',
    status TEXT DEFAULT 'staging',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, name, version)
);
CREATE INDEX IF NOT EXISTS idx_ai_models_tenant ON ai_models(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_models_type ON ai_models(tenant_id, model_type);

-- AI Platform: Training Jobs
CREATE TABLE IF NOT EXISTS training_jobs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    model_base TEXT NOT NULL,
    hyperparams_json TEXT DEFAULT '{}',
    status TEXT DEFAULT 'pending',
    progress REAL DEFAULT 0.0,
    example_count INTEGER DEFAULT 0,
    result_json TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_training_jobs_tenant ON training_jobs(tenant_id);

-- AI Platform: Voice Profiles
CREATE TABLE IF NOT EXISTS voice_profiles (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    speaker_name TEXT NOT NULL,
    features_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_voice_profiles_tenant ON voice_profiles(tenant_id);

-- AI Platform: Emotion Logs
CREATE TABLE IF NOT EXISTS emotion_logs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id TEXT,
    speaker TEXT,
    emotion TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    timestamp_ms INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_emotion_logs_tenant ON emotion_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_emotion_logs_call ON emotion_logs(tenant_id, call_id);

-- Datasets (versioned training data)
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0.0',
    recipe_type TEXT NOT NULL DEFAULT 'dialogue',
    recipe_version TEXT NOT NULL DEFAULT '1.0',
    source_start_date TEXT,
    source_end_date TEXT,
    total_examples INTEGER DEFAULT 0,
    total_turns INTEGER DEFAULT 0,
    quality_score REAL DEFAULT 0.0,
    stats_json TEXT DEFAULT '{}',
    status TEXT DEFAULT 'building',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, name, version)
);
CREATE INDEX IF NOT EXISTS idx_datasets_tenant ON datasets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_datasets_recipe ON datasets(recipe_type);

-- Turns (individual conversational turns with speaker labels)
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id TEXT,
    dataset_id TEXT,
    speaker TEXT NOT NULL DEFAULT 'customer',
    text TEXT NOT NULL,
    turn_index INTEGER DEFAULT 0,
    start_ms INTEGER DEFAULT 0,
    end_ms INTEGER DEFAULT 0,
    asr_confidence REAL DEFAULT 0.0,
    sentiment TEXT DEFAULT 'neutral',
    emotion TEXT DEFAULT 'neutral',
    intent TEXT,
    is_low_quality INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_turns_dataset ON turns(dataset_id);
CREATE INDEX IF NOT EXISTS idx_turns_call ON turns(call_id);

-- Labels (human QA labels for training data)
CREATE TABLE IF NOT EXISTS labels (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    turn_id TEXT REFERENCES turns(id) ON DELETE CASCADE,
    labeler_id TEXT,
    label_type TEXT NOT NULL DEFAULT 'intent',
    label_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_labels_turn ON labels(turn_id);
CREATE INDEX IF NOT EXISTS idx_labels_type ON labels(label_type);

-- External Training Jobs
CREATE TABLE IF NOT EXISTS external_jobs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    external_job_id TEXT NOT NULL,
    external_provider TEXT NOT NULL DEFAULT 'modal',
    status TEXT DEFAULT 'submitted',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ext_jobs_tenant ON external_jobs(tenant_id, model_id);

-- Model Audit Log
CREATE TABLE IF NOT EXISTS model_audit_log (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_state TEXT,
    new_state TEXT,
    actor TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_model_audit ON model_audit_log(tenant_id, model_id);

-- Evaluation Metrics
CREATE TABLE IF NOT EXISTS eval_metrics (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    metrics_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_eval_metrics ON eval_metrics(tenant_id, model_id, model_version);

-- Seed default plans
INSERT INTO plans (name, description, price_per_hour, price_per_day, price_per_week, price_per_month, max_concurrent_calls, max_agents, max_recordings_mb, features) VALUES
('Starter', 'Entry plan — small teams', 8.00, 30.00, 100.00, 49.00, 2, 2, 500, '["basic_scripts","csv_import","email_support"]'),
('Pro', 'Growing teams', 20.00, 70.00, 250.00, 149.00, 10, 10, 2000, '["templates","ab_testing","analytics","priority_support"]'),
('Enterprise', 'Large scale operations', 60.00, 200.00, 700.00, 499.00, 50, 50, 10000, '["custom_scripts","api_access","dedicated_support","sla"]')
ON CONFLICT (name) DO NOTHING;

-- AI Experiments
CREATE TABLE IF NOT EXISTS ai_experiments (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    model_a TEXT NOT NULL,
    model_b TEXT NOT NULL,
    traffic_split REAL NOT NULL DEFAULT 0.5,
    status TEXT NOT NULL DEFAULT 'active',
    winner TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stopped_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_exp_tenant ON ai_experiments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_exp_status ON ai_experiments(status);

-- AI Evaluation Results
CREATE TABLE IF NOT EXISTS ai_evaluation_results (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    experiment_id TEXT REFERENCES ai_experiments(id),
    call_id TEXT,
    predicted_intent TEXT NOT NULL,
    actual_intent TEXT,
    confidence REAL NOT NULL DEFAULT 0.0,
    is_correct INTEGER DEFAULT 0,
    model_used TEXT,
    latency_ms REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_eval_tenant ON ai_evaluation_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_eval_experiment ON ai_evaluation_results(experiment_id);
CREATE INDEX IF NOT EXISTS idx_ai_eval_intent ON ai_evaluation_results(predicted_intent);

-- WFM Shifts
CREATE TABLE IF NOT EXISTS wfm_shifts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    shift_type VARCHAR(20) DEFAULT 'regular',
    status VARCHAR(20) DEFAULT 'scheduled',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wfm_shifts_tenant_date ON wfm_shifts(tenant_id, start_time);
CREATE INDEX IF NOT EXISTS idx_wfm_shifts_agent ON wfm_shifts(agent_id);

-- WFM Schedules (daily staffing plans)
CREATE TABLE IF NOT EXISTS wfm_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    forecasted_volume INT DEFAULT 0,
    forecasted_agents INT DEFAULT 0,
    actual_volume INT DEFAULT 0,
    actual_agents INT DEFAULT 0,
    adherence_pct DECIMAL(5,2) DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wfm_schedules_tenant_date ON wfm_schedules(tenant_id, date);

-- QA Rubrics
CREATE TABLE IF NOT EXISTS qa_rubrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    criteria JSONB NOT NULL DEFAULT '[]',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- QA Scores
CREATE TABLE IF NOT EXISTS qa_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id UUID REFERENCES call_sessions(id) ON DELETE SET NULL,
    agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
    reviewer_id VARCHAR(255),
    rubric_id UUID REFERENCES qa_rubrics(id) ON DELETE SET NULL,
    total_score DECIMAL(5,2) NOT NULL,
    max_score DECIMAL(5,2) NOT NULL DEFAULT 100,
    scores_per_criterion JSONB NOT NULL DEFAULT '{}',
    notes TEXT,
    reviewed_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_qa_scores_agent ON qa_scores(agent_id, reviewed_at);
CREATE INDEX IF NOT EXISTS idx_qa_scores_tenant ON qa_scores(tenant_id);

-- Voice Quality Metrics
CREATE TABLE IF NOT EXISTS voice_quality_metrics (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id TEXT NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
    agent_id TEXT REFERENCES agents(id),
    mos REAL NOT NULL DEFAULT 0.0,
    jitter_ms REAL NOT NULL DEFAULT 0.0,
    packet_loss_pct REAL NOT NULL DEFAULT 0.0,
    latency_ms REAL NOT NULL DEFAULT 0.0,
    rtt_samples_json TEXT DEFAULT '[]',
    codec TEXT DEFAULT 'opus',
    quality_rating TEXT NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_vqm_tenant_date ON voice_quality_metrics(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_vqm_call ON voice_quality_metrics(call_id);
CREATE INDEX IF NOT EXISTS idx_vqm_mos ON voice_quality_metrics(mos);

-- CSAT Surveys
CREATE TABLE IF NOT EXISTS csat_surveys (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id TEXT REFERENCES call_sessions(id),
    customer_id TEXT,     rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
    feedback TEXT, channel TEXT NOT NULL DEFAULT 'voice',
    responded INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_csat_tenant_date ON csat_surveys(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_csat_rating ON csat_surveys(rating);
CREATE INDEX IF NOT EXISTS idx_csat_customer ON csat_surveys(customer_id);

-- Data Lineage
CREATE TABLE IF NOT EXISTS data_lineage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source_table VARCHAR(100) NOT NULL,
    source_id VARCHAR(100) NOT NULL,
    target_table VARCHAR(100) NOT NULL,
    target_id VARCHAR(100) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    column_name VARCHAR(100),
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dl_tenant ON data_lineage(tenant_id);
CREATE INDEX IF NOT EXISTS idx_dl_source ON data_lineage(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_dl_target ON data_lineage(target_table, target_id);
CREATE INDEX IF NOT EXISTS idx_dl_created ON data_lineage(tenant_id, created_at DESC);

-- Customer Interactions
CREATE TABLE IF NOT EXISTS customer_interactions (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id TEXT NOT NULL, interaction_type TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'voice', call_id TEXT,
    agent_id TEXT, sentiment TEXT DEFAULT 'neutral', summary TEXT,
    duration_seconds INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cust_int_tenant ON customer_interactions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_cust_int_customer ON customer_interactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_cust_int_type ON customer_interactions(interaction_type);

-- Integration Configs
CREATE TABLE IF NOT EXISTS integration_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(100) NOT NULL,
    integration_type VARCHAR(20) NOT NULL,
    config_json JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'active',
    last_sync_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, provider)
);
CREATE INDEX IF NOT EXISTS idx_int_config_tenant ON integration_configs(tenant_id, integration_type);

-- Ticket Sync Log
CREATE TABLE IF NOT EXISTS ticket_sync_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    ticket_id VARCHAR(255),
    call_id UUID REFERENCES call_sessions(id),
    direction VARCHAR(10) DEFAULT 'outbound',
    status VARCHAR(20) DEFAULT 'success',
    payload_json JSONB DEFAULT '{}',
    response_json JSONB DEFAULT '{}',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tsl_tenant ON ticket_sync_log(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tsl_status ON ticket_sync_log(status);

-- Knowledge Snippets
CREATE TABLE IF NOT EXISTS knowledge_snippets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags JSONB DEFAULT '[]',
    category TEXT DEFAULT 'general',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kb_tenant ON knowledge_snippets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_snippets(category);

-- Seed script templates
INSERT INTO script_templates (id, name, description, industry, content, variables, is_public) VALUES
('TPL-B2B-SAAS', 'B2B SaaS Sales', 'Cold outreach to software decision makers', 'sales',
 '{"blocks": [{"type": "greeting", "text": "Hi {{first_name}}, this is {{agent_name}} from {{company}}. Got 60 seconds?"}, {"type": "pitch", "text": "We help {{industry}} companies cut call volume by 40% with AI agents. {{company}} already sees ROI in week one."}, {"type": "branch", "condition": "industry == ''tech''", "true_block": "tech_pitch", "false_block": "generic_pitch"}, {"type": "objection", "trigger": "no_need", "response": "Most customers said that before. Worth a 5-min demo to see?"}, {"type": "close", "text": "Can I schedule a quick demo this week?"}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "company", "type": "string", "source": "lead"}, {"name": "industry", "type": "string", "source": "lead"}, {"name": "agent_name", "type": "string", "default": "Alex"}]',
 TRUE),
('TPL-HEALTHCARE', 'Healthcare Outreach', 'Patient appointment reminders and follow-ups', 'healthcare',
 '{"blocks": [{"type": "greeting", "text": "Hello, this is {{agent_name}} calling from {{company}} on behalf of Dr. {{doctor_name}}."}, {"type": "verify", "text": "Am I speaking with {{patient_name}}?"}, {"type": "purpose", "text": "We are calling to confirm your appointment on {{appointment_date}}."}, {"type": "reschedule", "trigger": "need_reschedule", "response": "I can help reschedule. What day works better for you?"}, {"type": "close", "text": "Thank you. See you on {{appointment_date}}."}]}',
 '[{"name": "patient_name", "type": "string", "source": "lead"}, {"name": "doctor_name", "type": "string", "default": ""}, {"name": "appointment_date", "type": "string", "source": "custom"}]',
 TRUE),
('TPL-REAL-ESTATE', 'Real Estate Follow-up', 'Property inquiry follow-up', 'real_estate',
 '{"blocks": [{"type": "greeting", "text": "Hi {{first_name}}, {{agent_name}} from {{company}}. Following up on your interest in {{property_address}}."}, {"type": "qualify", "text": "Are you still looking, or has anything changed?"}, {"type": "pitch", "text": "We have similar properties in {{area}} that might fit your needs."}, {"type": "close", "text": "Want to schedule a viewing this weekend?"}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "property_address", "type": "string", "source": "custom"}, {"name": "area", "type": "string", "default": ""}]',
 TRUE),
('TPL-INSURANCE', 'Insurance Quotes', 'Quote delivery and follow-up', 'insurance',
 '{"blocks": [{"type": "greeting", "text": "Hi {{first_name}}, calling about your {{insurance_type}} quote from {{company}}."}, {"type": "recap", "text": "Your monthly premium would be {{premium}}, with {{coverage}} coverage."}, {"type": "objection", "trigger": "too_expensive", "response": "We can adjust the deductible to lower your premium."}, {"type": "close", "text": "Ready to enroll today?"}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "insurance_type", "type": "string", "default": "auto"}, {"name": "premium", "type": "string", "source": "custom"}, {"name": "coverage", "type": "string", "source": "custom"}]',
 TRUE),
('TPL-APPOINTMENT', 'Appointment Setting', 'Schedule appointments with prospects', 'sales',
 '{"blocks": [{"type": "greeting", "text": "Hi {{first_name}}, this is {{agent_name}}. Got a minute?"}, {"type": "intro", "text": "I am reaching out about {{topic}}. We help companies like {{company}} achieve {{benefit}}."}, {"type": "qualify", "text": "Is solving {{pain_point}} a priority for you right now?"}, {"type": "close", "text": "Can we schedule a 15-minute call to explore this further?"}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "company", "type": "string", "source": "lead"}, {"name": "topic", "type": "string", "default": ""}, {"name": "benefit", "type": "string", "default": ""}, {"name": "pain_point", "type": "string", "default": ""}]',
 TRUE),
('TPL-SUPPORT', 'Technical Support', 'Tier 1 technical support triage', 'support',
 '{"blocks": [{"type": "greeting", "text": "Thank you for calling {{company}} support. This is {{agent_name}}."}, {"type": "verify", "text": "Can I get your account email or phone number?"}, {"type": "diagnose", "text": "I am sorry you are experiencing {{issue}}. Let me help troubleshoot."}, {"type": "escalate", "trigger": "complex_issue", "response": "Let me transfer you to a specialist who can better assist."}, {"type": "close", "text": "Is there anything else I can help with today?"}]}',
 '[{"name": "company", "type": "string", "default": ""}, {"name": "agent_name", "type": "string", "default": "Sam"}, {"name": "issue", "type": "string", "source": "call"}]',
 TRUE),
('TPL-DEBT', 'Debt Collection', 'Friendly debt collection outreach', 'finance',
 '{"blocks": [{"type": "greeting", "text": "Hello {{first_name}}, this is {{agent_name}} calling from {{company}} regarding your account."}, {"type": "verify", "text": "Can you confirm your date of birth for security?"}, {"type": "purpose", "text": "You have an outstanding balance of {{balance}} that is now {{days_overdue}} days overdue."}, {"type": "options", "text": "We can offer a payment plan or settlement. Which works better?"}, {"type": "close", "text": "I will send confirmation to your email. Thank you."}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "balance", "type": "string", "source": "custom"}, {"name": "days_overdue", "type": "string", "source": "custom"}]',
 TRUE),
('TPL-EVENT', 'Event Promotion', 'Webinar or event registration', 'marketing',
 '{"blocks": [{"type": "greeting", "text": "Hi {{first_name}}, this is {{agent_name}} from {{company}}."}, {"type": "intro", "text": "We are hosting {{event_name}} on {{event_date}} and thought you would be interested."}, {"type": "pitch", "text": "You will learn {{benefit_1}}, {{benefit_2}}, and {{benefit_3}}."}, {"type": "close", "text": "Can I register you? It is free and only takes a minute."}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "event_name", "type": "string", "default": ""}, {"name": "event_date", "type": "string", "default": ""}, {"name": "benefit_1", "type": "string", "default": ""}, {"name": "benefit_2", "type": "string", "default": ""}, {"name": "benefit_3", "type": "string", "default": ""}]',
 TRUE)
ON CONFLICT (id) DO NOTHING;

-- Customer Profiles (CDP)
CREATE TABLE IF NOT EXISTS customer_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_id VARCHAR(255),
    phone VARCHAR(20),
    email VARCHAR(255),
    name VARCHAR(255),
    tags_json JSONB DEFAULT '[]',
    metadata_json JSONB DEFAULT '{}',
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cp_tenant_phone ON customer_profiles(tenant_id, phone);
CREATE INDEX IF NOT EXISTS idx_cp_tenant_email ON customer_profiles(tenant_id, email);

-- Customer Segments (CDP)
CREATE TABLE IF NOT EXISTS customer_segments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    criteria_json JSONB NOT NULL DEFAULT '{}',
    member_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vertical Deployments
CREATE TABLE IF NOT EXISTS vertical_deployments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vertical_id VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    config_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
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

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email_verified INTEGER DEFAULT 0,
    verification_token TEXT,
    reset_token TEXT,
    reset_token_expires TEXT,
    tenant_id TEXT REFERENCES tenants(id) ON DELETE SET NULL,
    role TEXT DEFAULT 'owner',
    avatar_url TEXT,
    onboarding_completed INTEGER DEFAULT 0,
    onboarding_step INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);

-- Agents
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    display_name TEXT,
    email TEXT,
    phone TEXT,
    agent_type TEXT NOT NULL DEFAULT 'ai',
    status TEXT NOT NULL DEFAULT 'offline',
    skills TEXT DEFAULT '[]',
    config TEXT DEFAULT '{}',
    sip_extension TEXT UNIQUE,
    sip_password TEXT,
    encryption_key TEXT,
    total_calls INTEGER DEFAULT 0,
    total_talk_time_seconds INTEGER DEFAULT 0,
    avg_rating REAL DEFAULT 0.0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    last_seen_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_agents_tenant ON agents(tenant_id);

-- Agent Profiles (for AI agent configurations)
CREATE TABLE IF NOT EXISTS agent_profiles (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    prompt TEXT,
    parameters TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_profiles_tenant ON agent_profiles(tenant_id);

CREATE TABLE IF NOT EXISTS script_templates (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    description TEXT, industry TEXT,
    content TEXT DEFAULT '{}', variables TEXT DEFAULT '[]',
    is_public INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
CREATE TABLE IF NOT EXISTS scripts (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL, content TEXT DEFAULT '{}',
    variables TEXT DEFAULT '[]', is_active INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_scripts_tenant ON scripts(tenant_id);



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

-- WFM Shifts
CREATE TABLE IF NOT EXISTS wfm_shifts (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    start_time TEXT NOT NULL, end_time TEXT NOT NULL,
    shift_type TEXT DEFAULT 'regular', status TEXT DEFAULT 'scheduled',
    notes TEXT, created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_wfm_shifts_tenant_date ON wfm_shifts(tenant_id, start_time);
CREATE INDEX IF NOT EXISTS idx_wfm_shifts_agent ON wfm_shifts(agent_id);

-- WFM Schedules (daily staffing plans)
CREATE TABLE IF NOT EXISTS wfm_schedules (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    date TEXT NOT NULL, forecasted_volume INTEGER DEFAULT 0,
    forecasted_agents INTEGER DEFAULT 0, actual_volume INTEGER DEFAULT 0,
    actual_agents INTEGER DEFAULT 0, adherence_pct REAL DEFAULT 0,
    notes TEXT, created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_wfm_schedules_tenant_date ON wfm_schedules(tenant_id, date);

-- QA Rubrics
CREATE TABLE IF NOT EXISTS qa_rubrics (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL, description TEXT, criteria TEXT DEFAULT '[]',
    is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now'))
);

-- QA Scores
CREATE TABLE IF NOT EXISTS qa_scores (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id TEXT REFERENCES call_sessions(id) ON DELETE SET NULL,
    agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
    reviewer_id TEXT, rubric_id TEXT REFERENCES qa_rubrics(id) ON DELETE SET NULL,
    total_score REAL NOT NULL, max_score REAL NOT NULL DEFAULT 100,
    scores_per_criterion TEXT DEFAULT '{}', notes TEXT,
    reviewed_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_qa_scores_agent ON qa_scores(agent_id, reviewed_at);
CREATE INDEX IF NOT EXISTS idx_qa_scores_tenant ON qa_scores(tenant_id);

-- Voice Quality Metrics
CREATE TABLE IF NOT EXISTS voice_quality_metrics (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id TEXT NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
    agent_id TEXT REFERENCES agents(id),
    mos REAL NOT NULL DEFAULT 0.0,
    jitter_ms REAL NOT NULL DEFAULT 0.0,
    packet_loss_pct REAL NOT NULL DEFAULT 0.0,
    latency_ms REAL NOT NULL DEFAULT 0.0,
    rtt_samples_json TEXT DEFAULT '[]',
    codec TEXT DEFAULT 'opus',
    quality_rating TEXT NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_vqm_tenant_date ON voice_quality_metrics(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_vqm_call ON voice_quality_metrics(call_id);
CREATE INDEX IF NOT EXISTS idx_vqm_mos ON voice_quality_metrics(mos);

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
    company_name TEXT, contact_name TEXT, first_name TEXT, last_name TEXT,
    phone TEXT NOT NULL, email TEXT, industry TEXT, notes TEXT,
    priority INTEGER DEFAULT 5, status TEXT DEFAULT 'new', score REAL DEFAULT 0.0,
    source TEXT, imported_at TIMESTAMP, last_called_at TIMESTAMP,
    custom_fields TEXT DEFAULT '{}', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
-- idx_agents_tenant and idx_profiles_tenant are defined earlier in the SQLite section
-- (immediately after each CREATE TABLE) to guarantee the tables exist first.
CREATE INDEX IF NOT EXISTS idx_leads_tenant ON leads(tenant_id);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_campaign_calls_tenant ON campaign_calls(tenant_id);

-- CRM tables
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

INSERT OR IGNORE INTO plans (id, name, description, price_per_hour, price_per_day, price_per_week, price_per_month, max_concurrent_calls, max_agents, max_recordings_mb, features) VALUES
('PLAN-STARTER', 'Starter', 'Entry plan — small teams', 8.00, 30.00, 100.00, 49.00, 2, 2, 500, '["basic_scripts","csv_import","email_support"]'),
('PLAN-PRO', 'Pro', 'Growing teams', 20.00, 70.00, 250.00, 149.00, 10, 10, 2000, '["templates","ab_testing","analytics","priority_support"]'),
('PLAN-ENTERPRISE', 'Enterprise', 'Large scale operations', 60.00, 200.00, 700.00, 499.00, 50, 50, 10000, '["custom_scripts","api_access","dedicated_support","sla"]');

INSERT OR IGNORE INTO customers (id, tenant_id, name, email, phone, company, status) VALUES
('CUST-001', 'TENANT-001', 'Acme Corp', 'billing@acme.com', '555-0100', 'Acme Corp', 'active'),
('CUST-002', 'TENANT-001', 'Globex Inc', 'support@globex.com', '555-0200', 'Globex Inc', 'active');

INSERT OR IGNORE INTO invoices (id, tenant_id, customer_id, amount, status, due_date, description) VALUES
('INV-5001', 'TENANT-001', 'CUST-001', 150.00, 'Paid', '2026-06-01', 'Monthly subscription'),
('INV-5002', 'TENANT-001', 'CUST-002', 300.00, 'Pending', '2026-07-01', 'Enterprise license');

INSERT OR IGNORE INTO orders (id, tenant_id, customer_id, status, total, expected_delivery) VALUES
('ORD-9001', 'TENANT-001', 'CUST-001', 'Processing', 99.99, '2026-06-10'),
('ORD-9002', 'TENANT-001', 'CUST-002', 'Shipped', 249.99, '2026-06-05');

-- Seed script templates
-- AI Evaluation Results
CREATE TABLE IF NOT EXISTS ai_evaluation_results (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    experiment_id TEXT REFERENCES ai_experiments(id),
    call_id TEXT, predicted_intent TEXT NOT NULL, actual_intent TEXT,
    confidence REAL NOT NULL DEFAULT 0.0, is_correct INTEGER DEFAULT 0,
    model_used TEXT, latency_ms REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_eval_tenant ON ai_evaluation_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_eval_experiment ON ai_evaluation_results(experiment_id);
CREATE INDEX IF NOT EXISTS idx_ai_eval_intent ON ai_evaluation_results(predicted_intent);

-- AI Experiments
CREATE TABLE IF NOT EXISTS ai_experiments (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL, description TEXT, model_a TEXT NOT NULL, model_b TEXT NOT NULL,
    traffic_split REAL NOT NULL DEFAULT 0.5, status TEXT NOT NULL DEFAULT 'active',
    winner TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, stopped_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_exp_tenant ON ai_experiments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_exp_status ON ai_experiments(status);

-- CSAT Surveys
CREATE TABLE IF NOT EXISTS csat_surveys (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id TEXT REFERENCES call_sessions(id), customer_id TEXT,
    rating INTEGER NOT NULL, feedback TEXT, channel TEXT NOT NULL DEFAULT 'voice',
    responded INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_csat_tenant_date ON csat_surveys(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_csat_rating ON csat_surveys(rating);
CREATE INDEX IF NOT EXISTS idx_csat_customer ON csat_surveys(customer_id);

-- Data Lineage
CREATE TABLE IF NOT EXISTS data_lineage (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source_table TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    column_name TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dl_tenant ON data_lineage(tenant_id);
CREATE INDEX IF NOT EXISTS idx_dl_source ON data_lineage(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_dl_target ON data_lineage(target_table, target_id);
CREATE INDEX IF NOT EXISTS idx_dl_created ON data_lineage(tenant_id, created_at DESC);

-- Customer Interactions
CREATE TABLE IF NOT EXISTS customer_interactions (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id TEXT NOT NULL, interaction_type TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'voice', call_id TEXT, agent_id TEXT,
    sentiment TEXT DEFAULT 'neutral', summary TEXT,
    duration_seconds INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cust_int_tenant ON customer_interactions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_cust_int_customer ON customer_interactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_cust_int_type ON customer_interactions(interaction_type);

-- Integration Configs
CREATE TABLE IF NOT EXISTS integration_configs (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider TEXT NOT NULL, integration_type TEXT NOT NULL,
    config_json TEXT DEFAULT '{}', status TEXT DEFAULT 'active',
    last_sync_at TIMESTAMP, error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, provider)
);
CREATE INDEX IF NOT EXISTS idx_int_config_tenant ON integration_configs(tenant_id, integration_type);

-- Ticket Sync Log
CREATE TABLE IF NOT EXISTS ticket_sync_log (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    ticket_id TEXT, call_id TEXT REFERENCES call_sessions(id),
    direction TEXT DEFAULT 'outbound', status TEXT DEFAULT 'success',
    payload_json TEXT DEFAULT '{}', response_json TEXT DEFAULT '{}',
    error_message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tsl_tenant ON ticket_sync_log(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tsl_status ON ticket_sync_log(status);

-- WFM Metrics: AHT
CREATE TABLE IF NOT EXISTS wfm_aht (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL, call_id TEXT NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
    duration_seconds INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_wfm_aht_tenant ON wfm_aht(tenant_id, created_at);

-- WFM Metrics: FCR
CREATE TABLE IF NOT EXISTS wfm_fcr (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id TEXT, call_id TEXT NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
    resolved INTEGER NOT NULL DEFAULT 0, follow_up_call_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_wfm_fcr_tenant ON wfm_fcr(tenant_id, created_at);

-- WFM Metrics: CSAT
CREATE TABLE IF NOT EXISTS wfm_csat (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id TEXT, call_id TEXT NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_wfm_csat_tenant ON wfm_csat(tenant_id, created_at);

-- WFM Metrics: NPS
CREATE TABLE IF NOT EXISTS wfm_nps (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id TEXT, call_id TEXT NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
    score INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_wfm_nps_tenant ON wfm_nps(tenant_id, created_at);

-- Training Courses
CREATE TABLE IF NOT EXISTS training_courses (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL, description TEXT, modules_json TEXT DEFAULT '[]',
    duration_hours REAL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_training_courses_tenant ON training_courses(tenant_id);

-- Training Enrollments
CREATE TABLE IF NOT EXISTS training_enrollments (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL, course_id TEXT NOT NULL REFERENCES training_courses(id) ON DELETE CASCADE,
    progress_pct REAL DEFAULT 0, status TEXT DEFAULT 'enrolled',
    completed_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_training_enrollments_tenant ON training_enrollments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_training_enrollments_agent ON training_enrollments(agent_id);

-- Coaching Sessions
CREATE TABLE IF NOT EXISTS coaching_sessions (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL, coach_id TEXT, focus_area TEXT, notes TEXT,
    status TEXT DEFAULT 'scheduled', scheduled_at TIMESTAMP, completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_coaching_sessions_tenant ON coaching_sessions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_coaching_sessions_agent ON coaching_sessions(agent_id);

-- Failover Tests
CREATE TABLE IF NOT EXISTS failover_tests (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    service TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'unknown',
    result_json TEXT DEFAULT '{}', duration_seconds REAL DEFAULT 0,
    tested_by TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_failover_tests_tenant ON failover_tests(tenant_id);

-- Chaos Experiments
CREATE TABLE IF NOT EXISTS chaos_experiments (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    target TEXT NOT NULL, fault_type TEXT NOT NULL, duration_seconds INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running', result_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chaos_exp_tenant ON chaos_experiments(tenant_id);

-- Vendor Contracts
CREATE TABLE IF NOT EXISTS vendor_contracts (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vendor TEXT NOT NULL, terms TEXT, renewal_date TEXT, status TEXT DEFAULT 'active',
    cost REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_vendor_contracts_tenant ON vendor_contracts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vendor_contracts_renewal ON vendor_contracts(tenant_id, renewal_date);

-- Backup Channels
CREATE TABLE IF NOT EXISTS backup_channels (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    channel_type TEXT NOT NULL, config_json TEXT DEFAULT '{}', status TEXT DEFAULT 'active',
    last_test_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_backup_channels_tenant ON backup_channels(tenant_id);

-- SMS Templates
CREATE TABLE IF NOT EXISTS sms_templates (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sms_templates_tenant ON sms_templates(tenant_id);

-- SMS Log
CREATE TABLE IF NOT EXISTS sms_log (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    to_number TEXT NOT NULL,
    from_number TEXT,
    body TEXT NOT NULL,
    status TEXT DEFAULT 'sent',
    direction TEXT DEFAULT 'outbound',
    sid TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sms_log_tenant ON sms_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sms_log_status ON sms_log(status);

-- Chat Sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    visitor_id TEXT NOT NULL,
    visitor_name TEXT,
    visitor_email TEXT,
    agent_id TEXT REFERENCES agents(id),
    status TEXT DEFAULT 'waiting',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_at TIMESTAMP,
    closed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_tenant ON chat_sessions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_status ON chat_sessions(status);

-- Chat Messages
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    sender_type TEXT NOT NULL,
    sender_name TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);

-- Knowledge Snippets
CREATE TABLE IF NOT EXISTS knowledge_snippets (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    category TEXT DEFAULT 'general',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_kb_tenant ON knowledge_snippets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_snippets(category);

-- Enterprise: Conversation Quality Scores
CREATE TABLE IF NOT EXISTS conversation_quality_scores (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
    call_id TEXT REFERENCES call_sessions(id) ON DELETE SET NULL,
    transcript_hash TEXT, rubric_name TEXT DEFAULT 'standard',
    total_score REAL NOT NULL DEFAULT 0, criteria_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cqs_tenant ON conversation_quality_scores(tenant_id);
CREATE INDEX IF NOT EXISTS idx_cqs_agent ON conversation_quality_scores(agent_id);

-- Enterprise: API Versions
CREATE TABLE IF NOT EXISTS api_versions (
    id TEXT PRIMARY KEY, version TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active', release_date TEXT NOT NULL,
    sunset_date TEXT, changelog TEXT, migration_notes TEXT
);

-- Enterprise: Customer Portal Sessions
CREATE TABLE IF NOT EXISTS customer_portal_sessions (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id TEXT NOT NULL, session_data_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cps_tenant ON customer_portal_sessions(tenant_id, customer_id);

-- Penetration Test Scans
CREATE TABLE IF NOT EXISTS pen_test_scans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    target_url TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'running',
    findings_json JSONB DEFAULT '[]',
    severity VARCHAR(20) DEFAULT 'medium',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_pen_test_tenant ON pen_test_scans(tenant_id);

-- WAF Events
CREATE TABLE IF NOT EXISTS waf_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    rule_id VARCHAR(50) NOT NULL,
    action VARCHAR(20) NOT NULL,
    source_ip INET,
    request_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_waf_events_tenant ON waf_events(tenant_id, created_at DESC);

-- Data Classification
CREATE TABLE IF NOT EXISTS data_classification (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    schema_name VARCHAR(100) DEFAULT 'public',
    table_name VARCHAR(100) NOT NULL,
    column_name VARCHAR(100) NOT NULL,
    sensitivity VARCHAR(20) NOT NULL DEFAULT 'internal',
    description TEXT,
    UNIQUE(tenant_id, schema_name, table_name, column_name)
);
CREATE INDEX IF NOT EXISTS idx_data_class_tenant ON data_classification(tenant_id);

-- RBAC Audit Results
CREATE TABLE IF NOT EXISTS rbac_audit_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    resource VARCHAR(100) NOT NULL,
    action VARCHAR(20) NOT NULL,
    expected BOOLEAN NOT NULL,
    actual BOOLEAN NOT NULL,
    passed BOOLEAN NOT NULL,
    tested_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rbac_audit_tenant ON rbac_audit_results(tenant_id);

-- DR Tests
CREATE TABLE IF NOT EXISTS dr_tests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    test_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    result_json JSONB DEFAULT '{}',
    duration_seconds REAL DEFAULT 0,
    tested_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dr_tests_tenant ON dr_tests(tenant_id);

-- Rate Limit Configs
CREATE TABLE IF NOT EXISTS rate_limit_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    route_key VARCHAR(255) NOT NULL,
    max_requests INT NOT NULL DEFAULT 100,
    window_seconds INT NOT NULL DEFAULT 60,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, route_key)
);
CREATE INDEX IF NOT EXISTS idx_rl_config_tenant ON rate_limit_configs(tenant_id);

-- API Keys
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(10) NOT NULL,
    key_hash VARCHAR(64) NOT NULL,
    scopes_json JSONB DEFAULT '["all"]',
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ak_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_ak_tenant ON api_keys(tenant_id);

-- Webhook Configs
CREATE TABLE IF NOT EXISTS webhook_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    events_json JSONB DEFAULT '[]',
    secret TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Webhook Delivery Logs
CREATE TABLE IF NOT EXISTS webhook_delivery_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    webhook_id UUID NOT NULL REFERENCES webhook_configs(id),
    event_type VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    request_body TEXT,
    response_status INT,
    response_body TEXT,
    error_message TEXT,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Circuit Breaker Events
CREATE TABLE IF NOT EXISTS circuit_breaker_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    breaker_name VARCHAR(100) NOT NULL,
    from_state VARCHAR(20) NOT NULL,
    to_state VARCHAR(20) NOT NULL,
    failure_count INT DEFAULT 0,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cb_events_name ON circuit_breaker_events(breaker_name, timestamp DESC);

-- Tenant Branding (White-Label)
CREATE TABLE IF NOT EXISTS tenant_branding (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
    company_name VARCHAR(255),
    logo_url VARCHAR(500),
    primary_color VARCHAR(7) DEFAULT '#2563eb',
    secondary_color VARCHAR(7) DEFAULT '#7c3aed',
    favicon_url VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tb_tenant ON tenant_branding(tenant_id);

-- Custom Domains
CREATE TABLE IF NOT EXISTS custom_domains (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    domain VARCHAR(255) NOT NULL UNIQUE,
    ssl_status VARCHAR(20) DEFAULT 'pending',
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cd_tenant ON custom_domains(tenant_id);

-- Onboarding Progress
CREATE TABLE IF NOT EXISTS onboarding_progress (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    steps_completed_json JSONB DEFAULT '[]',
    current_step VARCHAR(50) DEFAULT 'welcome',
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_op_tenant ON onboarding_progress(tenant_id);

-- Tenant Config (key-value for self-serve provisioning)
CREATE TABLE IF NOT EXISTS tenant_config (
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key VARCHAR(100) NOT NULL,
    value TEXT,
    PRIMARY KEY (tenant_id, key)
);

-- Seed script templates
INSERT OR IGNORE INTO script_templates (id, name, description, industry, content, variables, is_public) VALUES
('TPL-B2B-SAAS', 'B2B SaaS Sales', 'Cold outreach to software decision makers', 'sales',
 '{"blocks": [{"type": "greeting", "text": "Hi {{first_name}}, this is {{agent_name}} from {{company}}. Got 60 seconds?"}, {"type": "pitch", "text": "We help {{industry}} companies cut call volume by 40% with AI agents. {{company}} already sees ROI in week one."}, {"type": "branch", "condition": "industry == ''tech''", "true_block": "tech_pitch", "false_block": "generic_pitch"}, {"type": "objection", "trigger": "no_need", "response": "Most customers said that before. Worth a 5-min demo to see?"}, {"type": "close", "text": "Can I schedule a quick demo this week?"}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "company", "type": "string", "source": "lead"}, {"name": "industry", "type": "string", "source": "lead"}, {"name": "agent_name", "type": "string", "default": "Alex"}]',
 1),
('TPL-HEALTHCARE', 'Healthcare Outreach', 'Patient appointment reminders and follow-ups', 'healthcare',
 '{"blocks": [{"type": "greeting", "text": "Hello, this is {{agent_name}} calling from {{company}} on behalf of Dr. {{doctor_name}}."}, {"type": "verify", "text": "Am I speaking with {{patient_name}}?"}, {"type": "purpose", "text": "We are calling to confirm your appointment on {{appointment_date}}."}, {"type": "reschedule", "trigger": "need_reschedule", "response": "I can help reschedule. What day works better for you?"}, {"type": "close", "text": "Thank you. See you on {{appointment_date}}."}]}',
 '[{"name": "patient_name", "type": "string", "source": "lead"}, {"name": "doctor_name", "type": "string", "default": ""}, {"name": "appointment_date", "type": "string", "source": "custom"}]',
 1),
('TPL-REAL-ESTATE', 'Real Estate Follow-up', 'Property inquiry follow-up', 'real_estate',
 '{"blocks": [{"type": "greeting", "text": "Hi {{first_name}}, {{agent_name}} from {{company}}. Following up on your interest in {{property_address}}."}, {"type": "qualify", "text": "Are you still looking, or has anything changed?"}, {"type": "pitch", "text": "We have similar properties in {{area}} that might fit your needs."}, {"type": "close", "text": "Want to schedule a viewing this weekend?"}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "property_address", "type": "string", "source": "custom"}, {"name": "area", "type": "string", "default": ""}]',
 1),
('TPL-INSURANCE', 'Insurance Quotes', 'Quote delivery and follow-up', 'insurance',
 '{"blocks": [{"type": "greeting", "text": "Hi {{first_name}}, calling about your {{insurance_type}} quote from {{company}}."}, {"type": "recap", "text": "Your monthly premium would be {{premium}}, with {{coverage}} coverage."}, {"type": "objection", "trigger": "too_expensive", "response": "We can adjust the deductible to lower your premium."}, {"type": "close", "text": "Ready to enroll today?"}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "insurance_type", "type": "string", "default": "auto"}, {"name": "premium", "type": "string", "source": "custom"}, {"name": "coverage", "type": "string", "source": "custom"}]',
 1),
('TPL-APPOINTMENT', 'Appointment Setting', 'Schedule appointments with prospects', 'sales',
 '{"blocks": [{"type": "greeting", "text": "Hi {{first_name}}, this is {{agent_name}}. Got a minute?"}, {"type": "intro", "text": "I am reaching out about {{topic}}. We help companies like {{company}} achieve {{benefit}}."}, {"type": "qualify", "text": "Is solving {{pain_point}} a priority for you right now?"}, {"type": "close", "text": "Can we schedule a 15-minute call to explore this further?"}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "company", "type": "string", "source": "lead"}, {"name": "topic", "type": "string", "default": ""}, {"name": "benefit", "type": "string", "default": ""}, {"name": "pain_point", "type": "string", "default": ""}]',
 1),
('TPL-SUPPORT', 'Technical Support', 'Tier 1 technical support triage', 'support',
 '{"blocks": [{"type": "greeting", "text": "Thank you for calling {{company}} support. This is {{agent_name}}."}, {"type": "verify", "text": "Can I get your account email or phone number?"}, {"type": "diagnose", "text": "I am sorry you are experiencing {{issue}}. Let me help troubleshoot."}, {"type": "escalate", "trigger": "complex_issue", "response": "Let me transfer you to a specialist who can better assist."}, {"type": "close", "text": "Is there anything else I can help with today?"}]}',
 '[{"name": "company", "type": "string", "default": ""}, {"name": "agent_name", "type": "string", "default": "Sam"}, {"name": "issue", "type": "string", "source": "call"}]',
 1),
('TPL-DEBT', 'Debt Collection', 'Friendly debt collection outreach', 'finance',
 '{"blocks": [{"type": "greeting", "text": "Hello {{first_name}}, this is {{agent_name}} calling from {{company}} regarding your account."}, {"type": "verify", "text": "Can you confirm your date of birth for security?"}, {"type": "purpose", "text": "You have an outstanding balance of {{balance}} that is now {{days_overdue}} days overdue."}, {"type": "options", "text": "We can offer a payment plan or settlement. Which works better?"}, {"type": "close", "text": "I will send confirmation to your email. Thank you."}]}',
 '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "balance", "type": "string", "source": "custom"}, {"name": "days_overdue", "type": "string", "source": "custom"}]',
 1),
('TPL-EVENT', 'Event Promotion', 'Webinar or event registration', 'marketing',
  '{"blocks": [{"type": "greeting", "text": "Hi {{first_name}}, this is {{agent_name}} from {{company}}."}, {"type": "intro", "text": "We are hosting {{event_name}} on {{event_date}} and thought you would be interested."}, {"type": "pitch", "text": "You will learn {{benefit_1}}, {{benefit_2}}, and {{benefit_3}}."}, {"type": "close", "text": "Can I register you? It is free and only takes a minute."}]}',
  '[{"name": "first_name", "type": "string", "source": "lead"}, {"name": "event_name", "type": "string", "default": ""}, {"name": "event_date", "type": "string", "default": ""}, {"name": "benefit_1", "type": "string", "default": ""}, {"name": "benefit_2", "type": "string", "default": ""}, {"name": "benefit_3", "type": "string", "default": ""}]',
  1);

-- SMS Templates
CREATE TABLE IF NOT EXISTS sms_templates (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sms_templates_tenant ON sms_templates(tenant_id);

-- SMS Log
CREATE TABLE IF NOT EXISTS sms_log (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    to_number TEXT NOT NULL,
    from_number TEXT,
    body TEXT NOT NULL,
    status TEXT DEFAULT 'sent',
    direction TEXT DEFAULT 'outbound',
    sid TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sms_log_tenant ON sms_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sms_log_status ON sms_log(status);

-- Chat Sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    visitor_id TEXT NOT NULL,
    visitor_name TEXT,
    visitor_email TEXT,
    agent_id TEXT REFERENCES agents(id),
    status TEXT DEFAULT 'waiting',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_at TIMESTAMP,
    closed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_tenant ON chat_sessions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_status ON chat_sessions(status);

-- Chat Messages
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    sender_type TEXT NOT NULL,
    sender_name TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);

-- Penetration Test Scans
CREATE TABLE IF NOT EXISTS pen_test_scans (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    target_url TEXT NOT NULL, status TEXT DEFAULT 'running',
    findings_json TEXT DEFAULT '[]', severity TEXT DEFAULT 'medium',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pen_test_tenant ON pen_test_scans(tenant_id);

-- WAF Events
CREATE TABLE IF NOT EXISTS waf_events (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL, action TEXT NOT NULL,
    source_ip TEXT, request_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_waf_events_tenant ON waf_events(tenant_id, created_at DESC);

-- Data Classification
CREATE TABLE IF NOT EXISTS data_classification (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    schema_name TEXT DEFAULT 'public', table_name TEXT NOT NULL,
    column_name TEXT NOT NULL, sensitivity TEXT NOT NULL DEFAULT 'internal',
    description TEXT
);
CREATE INDEX IF NOT EXISTS idx_data_class_tenant ON data_classification(tenant_id);

-- RBAC Audit Results
CREATE TABLE IF NOT EXISTS rbac_audit_results (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role TEXT NOT NULL, resource TEXT NOT NULL, action TEXT NOT NULL,
    expected INTEGER NOT NULL, actual INTEGER NOT NULL, passed INTEGER NOT NULL,
    tested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rbac_audit_tenant ON rbac_audit_results(tenant_id);

-- DR Tests
CREATE TABLE IF NOT EXISTS dr_tests (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    test_type TEXT NOT NULL, status TEXT DEFAULT 'running',
    result_json TEXT DEFAULT '{}', duration_seconds REAL DEFAULT 0,
    tested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dr_tests_tenant ON dr_tests(tenant_id);

-- Rate Limit Configs
CREATE TABLE IF NOT EXISTS rate_limit_configs (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    route_key TEXT NOT NULL, max_requests INTEGER NOT NULL DEFAULT 100,
    window_seconds INTEGER NOT NULL DEFAULT 60,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rl_config_tenant ON rate_limit_configs(tenant_id);

-- Circuit Breaker Events
CREATE TABLE IF NOT EXISTS circuit_breaker_events (
    id TEXT PRIMARY KEY, breaker_name TEXT NOT NULL,
    from_state TEXT NOT NULL, to_state TEXT NOT NULL,
    failure_count INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tenant Branding (White-Label)
CREATE TABLE IF NOT EXISTS tenant_branding (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
    company_name TEXT,
    logo_url TEXT,
    primary_color TEXT DEFAULT '#2563eb',
    secondary_color TEXT DEFAULT '#7c3aed',
    favicon_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tb_tenant ON tenant_branding(tenant_id);

-- Custom Domains
CREATE TABLE IF NOT EXISTS custom_domains (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    domain TEXT NOT NULL UNIQUE,
    ssl_status TEXT DEFAULT 'pending',
    verified INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cd_tenant ON custom_domains(tenant_id);

-- Onboarding Progress
CREATE TABLE IF NOT EXISTS onboarding_progress (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    steps_completed_json TEXT DEFAULT '[]',
    current_step TEXT DEFAULT 'welcome',
    completed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_op_tenant ON onboarding_progress(tenant_id);

-- Tenant Config (key-value for self-serve provisioning)
CREATE TABLE IF NOT EXISTS tenant_config (
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (tenant_id, key)
);

-- API Keys
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    scopes_json TEXT DEFAULT '["all"]',
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ak_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_ak_tenant ON api_keys(tenant_id);

-- Webhook Configs
CREATE TABLE IF NOT EXISTS webhook_configs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    events_json TEXT DEFAULT '[]',
    secret TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Webhook Delivery Logs
CREATE TABLE IF NOT EXISTS webhook_delivery_logs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    webhook_id TEXT NOT NULL REFERENCES webhook_configs(id),
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    request_body TEXT,
    response_status INTEGER,
    response_body TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Customer Profiles (CDP)
CREATE TABLE IF NOT EXISTS customer_profiles (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_id TEXT,
    phone TEXT,
    email TEXT,
    name TEXT,
    tags_json TEXT DEFAULT '[]',
    metadata_json TEXT DEFAULT '{}',
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cp_tenant_phone ON customer_profiles(tenant_id, phone);
CREATE INDEX IF NOT EXISTS idx_cp_tenant_email ON customer_profiles(tenant_id, email);

-- Customer Segments (CDP)
CREATE TABLE IF NOT EXISTS customer_segments (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    criteria_json TEXT NOT NULL DEFAULT '{}',
    member_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Vertical Deployments
CREATE TABLE IF NOT EXISTS vertical_deployments (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vertical_id TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    config_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AI Platform: Models
CREATE TABLE IF NOT EXISTS ai_models (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    model_type TEXT NOT NULL DEFAULT 'intent',
    config_json TEXT DEFAULT '{}',
    metrics_json TEXT DEFAULT '{}',
    status TEXT DEFAULT 'staging',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, name, version)
);
CREATE INDEX IF NOT EXISTS idx_ai_models_tenant ON ai_models(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_models_type ON ai_models(tenant_id, model_type);

-- AI Platform: Training Jobs
CREATE TABLE IF NOT EXISTS training_jobs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    model_base TEXT NOT NULL,
    hyperparams_json TEXT DEFAULT '{}',
    status TEXT DEFAULT 'pending',
    progress REAL DEFAULT 0.0,
    example_count INTEGER DEFAULT 0,
    result_json TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_training_jobs_tenant ON training_jobs(tenant_id);

-- AI Platform: Voice Profiles
CREATE TABLE IF NOT EXISTS voice_profiles (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    speaker_name TEXT NOT NULL,
    features_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_voice_profiles_tenant ON voice_profiles(tenant_id);

-- AI Platform: Emotion Logs
CREATE TABLE IF NOT EXISTS emotion_logs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id TEXT,
    speaker TEXT,
    emotion TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    timestamp_ms INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_emotion_logs_tenant ON emotion_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_emotion_logs_call ON emotion_logs(tenant_id, call_id);

-- Datasets (versioned training data)
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0.0',
    recipe_type TEXT NOT NULL DEFAULT 'dialogue',
    recipe_version TEXT NOT NULL DEFAULT '1.0',
    source_start_date TEXT,
    source_end_date TEXT,
    total_examples INTEGER DEFAULT 0,
    total_turns INTEGER DEFAULT 0,
    quality_score REAL DEFAULT 0.0,
    stats_json TEXT DEFAULT '{}',
    status TEXT DEFAULT 'building',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, name, version)
);
CREATE INDEX IF NOT EXISTS idx_datasets_tenant ON datasets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_datasets_recipe ON datasets(recipe_type);

-- Turns (individual conversational turns with speaker labels)
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id TEXT,
    dataset_id TEXT,
    speaker TEXT NOT NULL DEFAULT 'customer',
    text TEXT NOT NULL,
    turn_index INTEGER DEFAULT 0,
    start_ms INTEGER DEFAULT 0,
    end_ms INTEGER DEFAULT 0,
    asr_confidence REAL DEFAULT 0.0,
    sentiment TEXT DEFAULT 'neutral',
    emotion TEXT DEFAULT 'neutral',
    intent TEXT,
    is_low_quality INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_turns_dataset ON turns(dataset_id);
CREATE INDEX IF NOT EXISTS idx_turns_call ON turns(call_id);

-- Labels (human QA labels for training data)
CREATE TABLE IF NOT EXISTS labels (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    turn_id TEXT REFERENCES turns(id) ON DELETE CASCADE,
    labeler_id TEXT,
    label_type TEXT NOT NULL DEFAULT 'intent',
    label_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_labels_turn ON labels(turn_id);
CREATE INDEX IF NOT EXISTS idx_labels_type ON labels(label_type);

-- External Training Jobs
CREATE TABLE IF NOT EXISTS external_jobs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    external_job_id TEXT NOT NULL,
    external_provider TEXT NOT NULL DEFAULT 'modal',
    status TEXT DEFAULT 'submitted',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ext_jobs_tenant ON external_jobs(tenant_id, model_id);

-- Model Audit Log
CREATE TABLE IF NOT EXISTS model_audit_log (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_state TEXT,
    new_state TEXT,
    actor TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_model_audit ON model_audit_log(tenant_id, model_id);

-- Evaluation Metrics
CREATE TABLE IF NOT EXISTS eval_metrics (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    metrics_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_eval_metrics ON eval_metrics(tenant_id, model_id, model_version);
"""

async def init_pg_schema(pool: asyncpg.Pool):
    """Initialize PostgreSQL schema using Alembic migrations.

    Falls back to raw SQL if Alembic fails (e.g., first-run migration
    hasn't been created yet).
    """
    from api.services.db_migrations import run_alembic_migrations
    try:
        ok = await run_alembic_migrations()
        if ok:
            return
    except Exception as e:
        logger.warning("Alembic migration failed, falling back to raw SQL", error=str(e))

    async with pool.acquire() as conn:
        try:
            await conn.execute(SCHEMA_SQL)
            logger.info("PostgreSQL schema initialized via raw SQL (fallback)")
        except Exception as e:
            logger.error("PostgreSQL schema initialization failed", error=str(e))
            raise e


def init_sqlite_schema():
    """Initialize SQLite schema using Alembic migrations.

    Falls back to raw SQL if Alembic fails.
    """
    import asyncio

    from api.services.db_migrations import run_alembic_migrations
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(run_alembic_migrations())
            logger.info("Delegated SQLite schema migration to running event loop")
            return
        else:
            ok = loop.run_until_complete(run_alembic_migrations())
            if ok:
                return
    except Exception as e:
        logger.warning("Alembic migration failed, falling back to raw SQL", error=str(e))

    from api.services.db_pool import _get_sqlite_conn
    from api.services.db_sqlite_transform import postgres_to_sqlite

    # The legacy SQLITE_SCHEMA_SQL constant in this module accumulated
    # Postgres-only types (UUID, JSONB, TIMESTAMPTZ, etc.) over time
    # and fails on a fresh SQLite database. We now derive the SQLite
    # schema at runtime from SCHEMA_SQL (the canonical Postgres schema)
    # via a deterministic type translation. This guarantees SQLite and
    # Postgres stay structurally in sync going forward.
    conn = _get_sqlite_conn()
    sqlite_sql = postgres_to_sqlite(SCHEMA_SQL)
    conn.executescript(sqlite_sql)
    conn.commit()
    conn.close()
    logger.info("SQLite schema initialized from translated SCHEMA_SQL (fallback)")


