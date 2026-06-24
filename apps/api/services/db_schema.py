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
('Starter', 'Entry plan — small teams', 8.00, 30.00, 100.00, 49.00, 2, 2, 500, '["basic_scripts","csv_import","email_support"]'),
('Pro', 'Growing teams', 20.00, 70.00, 250.00, 149.00, 10, 10, 2000, '["templates","ab_testing","analytics","priority_support"]'),
('Enterprise', 'Large scale operations', 60.00, 200.00, 700.00, 499.00, 50, 50, 10000, '["custom_scripts","api_access","dedicated_support","sla"]')
ON CONFLICT (name) DO NOTHING;

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
CREATE INDEX IF NOT EXISTS idx_agents_tenant ON agents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_profiles_tenant ON agent_profiles(tenant_id);
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
"""


async def init_pg_schema(pool: asyncpg.Pool):
    """Initialize PostgreSQL schema using Alembic migrations.

    Falls back to raw SQL if Alembic fails (e.g., first-run migration
    hasn't been created yet).
    """
    from apps.api.services.db_migrations import run_alembic_migrations, stamp_db
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
    from apps.api.services.db_migrations import run_alembic_migrations
    import asyncio
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

    from apps.api.services.db_pool import _get_sqlite_conn
    conn = _get_sqlite_conn()
    conn.executescript(SQLITE_SCHEMA_SQL)
    conn.commit()
    conn.close()
    logger.info("SQLite schema initialized via raw SQL (fallback)")


