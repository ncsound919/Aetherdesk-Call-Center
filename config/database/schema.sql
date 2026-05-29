-- AetherDesk Call Center Platform - Database Schema
-- HIPAA/GDPR Compliant, Multi-Tenant Architecture
-- PostgreSQL 15+

-- ============================================
-- EXTENSIONS
-- ============================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";

-- ============================================
-- TENANTS (Businesses that rent agents)
-- ============================================
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20),
    plan_id UUID REFERENCES plans(id),
    plan_started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    plan_ends_at TIMESTAMP WITH TIME ZONE,
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    gdpr_consent BOOLEAN DEFAULT FALSE,
    gdpr_consented_at TIMESTAMP WITH TIME ZONE,
    data_processing_agreement BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE -- Soft delete
);

-- ============================================
-- PLANS (Subscription tiers)
-- ============================================
CREATE TABLE plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL, -- "Starter", "Pro", "Enterprise"
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- AGENTS (AI/Human agents rented by tenants)
-- ============================================
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(20),
    agent_type VARCHAR(20) NOT NULL DEFAULT 'ai', -- 'ai', 'human', 'hybrid'
    status VARCHAR(20) NOT NULL DEFAULT 'offline', -- 'offline', 'online', 'available', 'busy', 'on_call', 'paused'
    skills JSONB DEFAULT '[]', -- ["sales", "support", "technical", "billing"]
    config JSONB DEFAULT '{}', -- AI model settings, voice settings, etc.
    sip_extension VARCHAR(20) UNIQUE, -- SIP extension in FreeSWITCH
    sip_password VARCHAR(128), -- Encrypted SIP password
    encryption_key VARCHAR(256), -- Per-agent encryption key for HIPAA
    total_calls INT DEFAULT 0,
    total_talk_time_seconds INT DEFAULT 0,
    avg_rating DECIMAL(3, 2) DEFAULT 0.0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE
);

-- ============================================
-- CALL SESSIONS (Individual call records)
-- ============================================
CREATE TABLE call_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
    caller_number VARCHAR(20) NOT NULL,
    caller_name VARCHAR(255),
    called_number VARCHAR(20) NOT NULL,
    call_direction VARCHAR(10) NOT NULL, -- 'inbound', 'outbound'
    call_status VARCHAR(20) NOT NULL DEFAULT 'initiated', -- 'initiated', 'ringing', 'active', 'hold', 'completed', 'failed', 'missed', 'voicemail'
    call_type VARCHAR(20) DEFAULT 'voice', -- 'voice', 'video', 'conference'
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
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
    transcription_id UUID, -- References transcription
    recording_id UUID, -- References recording
    sentiment_score DECIMAL(5, 4), -- AI sentiment analysis (-1.0 to 1.0)
    intent_detected VARCHAR(100), -- Detected caller intent
    ai_summary TEXT, -- AI-generated call summary
    pii_redacted BOOLEAN DEFAULT FALSE, -- HIPAA: PII redaction status
    encryption_key VARCHAR(256), -- Per-call encryption key
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- CALL QUEUE (Real-time queue management)
-- ============================================
CREATE TABLE call_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id UUID REFERENCES call_sessions(id) ON DELETE CASCADE,
    caller_number VARCHAR(20) NOT NULL,
    position INT NOT NULL,
    priority INT DEFAULT 5, -- 1-10, 10 = highest
    estimated_wait_seconds INT,
    status VARCHAR(20) DEFAULT 'waiting', -- 'waiting', 'assigned', 'abandoned', 'timeout'
    intent VARCHAR(100),
    skills_required JSONB DEFAULT '[]',
    enqueued_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assigned_at TIMESTAMP WITH TIME ZONE,
    abandoned_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- AGENT ACTIVITY LOG (Time tracking for billing)
-- ============================================
CREATE TABLE agent_activity (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    activity_type VARCHAR(20) NOT NULL, -- 'login', 'logout', 'call_start', 'call_end', 'pause', 'resume', 'break', 'lunch'
    status_before VARCHAR(20),
    status_after VARCHAR(20),
    call_id UUID REFERENCES call_sessions(id),
    session_ref VARCHAR(255), -- Fonoster session reference
    duration_seconds INT DEFAULT 0,
    ip_address INET,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- RECORDINGS (HIPAA-compliant encrypted storage)
-- ============================================
CREATE TABLE recordings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id UUID REFERENCES call_sessions(id),
    agent_id UUID REFERENCES agents(id),
    file_path VARCHAR(500) NOT NULL, -- Encrypted file path in object storage
    file_size_bytes BIGINT,
    duration_seconds INT,
    format VARCHAR(10) DEFAULT 'wav',
    encryption_algorithm VARCHAR(20) DEFAULT 'AES-256-GCM',
    encryption_key_id VARCHAR(255), -- KMS key reference
    checksum VARCHAR(255), -- SHA-256 integrity check
    transcription TEXT, -- Full transcript
    pii_redacted BOOLEAN DEFAULT FALSE,
    access_policy JSONB DEFAULT '{}', -- HIPAA access control
    retention_until TIMESTAMP WITH TIME ZONE, -- GDPR retention policy
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE
);

-- ============================================
-- TRANSCRIPTIONS (AI-generated transcripts)
-- ============================================
CREATE TABLE transcriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id UUID REFERENCES call_sessions(id),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stt_engine VARCHAR(50) DEFAULT 'deepgram',
    language_code VARCHAR(10) DEFAULT 'en-US',
    confidence_score DECIMAL(5, 4),
    full_text TEXT,
    segments JSONB DEFAULT '[]', -- Word-level timestamps
    speaker_diarization JSONB DEFAULT '[]', -- Speaker identification
    pii_redacted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- BILLING & USAGE (Cost tracking per tenant)
-- ============================================
CREATE TABLE billing_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
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
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'invoiced', 'paid', 'refunded', 'disputed'
    stripe_invoice_id VARCHAR(255),
    stripe_payment_id VARCHAR(255),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- AUDIT LOG (HIPAA/GDPR compliance trail)
-- ============================================
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id),
    user_id UUID,
    action VARCHAR(100) NOT NULL, -- 'create_agent', 'delete_call', 'access_recording', etc.
    resource_type VARCHAR(50), -- 'agent', 'call', 'recording', 'tenant', 'config'
    resource_id UUID,
    old_values JSONB,
    new_values JSONB,
    ip_address INET,
    user_agent VARCHAR(500),
    reason TEXT, -- Business justification for the action
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- INDEXES (Performance optimization)
-- ============================================
CREATE INDEX idx_calls_tenant ON call_sessions(tenant_id);
CREATE INDEX idx_calls_agent ON call_sessions(agent_id);
CREATE INDEX idx_calls_status ON call_sessions(call_status);
CREATE INDEX idx_calls_start_time ON call_sessions(start_time DESC);
CREATE INDEX idx_agents_tenant ON agents(tenant_id);
CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_queue_waiting ON call_queue(status) WHERE status = 'waiting';
CREATE INDEX idx_activity_agent ON agent_activity(agent_id, created_at DESC);
CREATE INDEX idx_activity_tenant ON agent_activity(tenant_id, created_at DESC);
CREATE INDEX idx_recordings_call ON recordings(call_id);
CREATE INDEX idx_billing_tenant ON billing_records(tenant_id, period_start DESC);
CREATE INDEX idx_audit_tenant ON audit_log(tenant_id, created_at DESC);

-- ============================================
-- ROW LEVEL SECURITY (PostgreSQL RLS)
-- HIPAA/GDPR: Each tenant can ONLY access their own data
-- ============================================

-- Enable RLS on all tenant-scoped tables
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE recordings ENABLE ROW LEVEL SECURITY;
ALTER TABLE transcriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Tenant isolation policies
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

-- ============================================
-- ENCRYPTION FUNCTIONS (HIPAA compliance)
-- ============================================

-- Encrypt sensitive data at rest
CREATE OR REPLACE FUNCTION encrypt_data(plaintext TEXT, key TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN pgp_sym_encrypt(plaintext, key);
END;
$$ LANGUAGE plpgsql;

-- Decrypt sensitive data
CREATE OR REPLACE FUNCTION decrypt_data(ciphertext TEXT, key TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN pgp_sym_decrypt(ciphertext::bytea, key);
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- AGENT AVAILABILITY FUNCTION
-- ============================================
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

    -- Update status
    UPDATE agents
    SET status = p_status,
        last_seen_at = NOW(),
        updated_at = NOW()
    WHERE id = p_agent_id;

    -- Log activity
    INSERT INTO agent_activity (agent_id, tenant_id, activity_type, status_before, status_after, session_ref)
    VALUES (p_agent_id, v_agent.tenant_id, 'status_change', v_agent.status, p_status, p_session_ref);

    RETURN json_build_object('success', true, 'agent_id', p_agent_id, 'new_status', p_status);
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- COST CALCULATION FUNCTION
-- ============================================
CREATE OR REPLACE FUNCTION calculate_call_cost(
    p_duration_seconds INT,
    p_tenant_id UUID
) RETURNS DECIMAL AS $$
DECLARE
    v_plan plans%ROWTYPE;
    v_rate DECIMAL;
BEGIN
    -- Get tenant's current plan rates
    SELECT * INTO v_plan FROM plans WHERE id = (
        SELECT plan_id FROM tenants WHERE id = p_tenant_id
    );

    -- Calculate per-minute rate based on plan
    v_rate := v_plan.price_per_hour / 60;

    RETURN ROUND((p_duration_seconds::DECIMAL / 60) * v_rate, 4);
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- AUTO-ASSIGN AGENT FUNCTION (Smart routing)
-- ============================================
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
    -- Try to find available agent with matching skills
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
    ORDER BY total_calls ASC -- Least calls first (load balancing)
    LIMIT 1;

    IF NOT FOUND THEN
        -- No agent available, add to queue
        SELECT COALESCE(MAX(position), 0) + 1 INTO v_queue_pos
        FROM call_queue WHERE tenant_id = p_tenant_id AND status = 'waiting';

        INSERT INTO call_queue (tenant_id, caller_number, position, intent)
        VALUES (p_tenant_id, p_caller_number, v_queue_pos, p_intent);

        RETURN json_build_object(
            'success', true,
            'queued', true,
            'queue_position', v_queue_pos,
            'message', 'No agents available. Added to queue.'
        );
    END IF;

    -- Create call session
    INSERT INTO call_sessions (tenant_id, agent_id, caller_number, call_direction, call_status)
    VALUES (p_tenant_id, v_agent.id, p_caller_number, 'inbound', 'ringing')
    RETURNING id INTO v_call_id;

    -- Update agent status
    UPDATE agents SET status = 'busy' WHERE id = v_agent.id;

    RETURN json_build_object(
        'success', true,
        'agent_id', v_agent.id,
        'agent_name', v_agent.name,
        'call_id', v_call_id,
        'sip_extension', v_agent.sip_extension
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- GDPR DATA DELETION FUNCTION
-- ============================================
CREATE OR REPLACE FUNCTION gdpr_delete_user_data(
    p_phone_number VARCHAR(20)
) RETURNS JSON AS $$
DECLARE
    v_calls_updated INT;
    v_recordings_updated INT;
BEGIN
    -- Anonymize call sessions
    UPDATE call_sessions
    SET caller_number = 'REDACTED',
        caller_name = NULL,
        pii_redacted = TRUE
    WHERE caller_number = p_phone_number
    RETURNING 1 INTO v_calls_updated;

    -- Mark recordings for deletion
    UPDATE recordings
    SET retention_until = NOW(),
        pii_redacted = TRUE
    WHERE call_id IN (
        SELECT id FROM call_sessions WHERE caller_number = p_phone_number
    )
    RETURNING 1 INTO v_recordings_updated;

    RETURN json_build_object(
        'success', true,
        'calls_anonymized', COALESCE(v_calls_updated, 0),
        'recordings_flagged', COALESCE(v_recordings_updated, 0)
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- VIEW: Agent Performance Dashboard
-- ============================================
CREATE VIEW agent_performance AS
SELECT
    a.id AS agent_id,
    a.name,
    a.tenant_id,
    a.status,
    a.total_calls,
    a.total_talk_time_seconds,
    COALESCE(ROUND(a.total_talk_time_seconds::DECIMAL / NULLIF(a.total_calls, 0), 2), 0) AS avg_call_duration,
    a.avg_rating,
    COUNT(DISTINCT cs.id) FILTER (WHERE cs.call_status = 'active' AND cs.start_time > NOW() - INTERVAL '1 day') AS today_calls,
    COUNT(DISTINCT cs.id) FILTER (WHERE cs.call_status = 'active' AND cs.start_time > NOW() - INTERVAL '1 hour') AS hour_calls,
    t.name AS tenant_name
FROM agents a
LEFT JOIN call_sessions cs ON cs.agent_id = a.id AND cs.start_time > NOW() - INTERVAL '1 day'
LEFT JOIN tenants t ON t.id = a.tenant_id
GROUP BY a.id, a.name, a.tenant_id, a.status, a.total_calls, a.total_talk_time_seconds, a.avg_rating, t.name;

-- ============================================
-- VIEW: Billing Summary
-- ============================================
CREATE VIEW billing_summary AS
SELECT
    t.id AS tenant_id,
    t.name AS tenant_name,
    COUNT(DISTINCT cs.id) AS total_calls,
    SUM(cs.duration_seconds) / 60.0 AS total_minutes,
    SUM(cs.total_cost) AS total_spent,
    p.name AS current_plan,
    t.plan_ends_at AS plan_expires
FROM tenants t
LEFT JOIN call_sessions cs ON cs.tenant_id = t.id
LEFT JOIN plans p ON p.id = t.plan_id
GROUP BY t.id, t.name, p.name, t.plan_ends_at;

-- ============================================
-- DEFAULT PLANS
-- ============================================
INSERT INTO plans (name, description, price_per_hour, price_per_day, price_per_week, price_per_month, max_concurrent_calls, max_agents, max_recordings_mb, features) VALUES
('Starter', 'Small business plan', 2.50, 20.00, 80.00, 299.00, 2, 2, 500, '["basic_ivr", "call_recording", "basic_analytics"]'),
('Pro', 'Growing business plan', 4.00, 35.00, 120.00, 499.00, 5, 5, 2000, '["smart_routing", "ai_assistant", "advanced_analytics", "multi_channel"]'),
('Enterprise', 'Large scale operations', 6.50, 55.00, 200.00, 999.00, 20, 20, 10000, '["custom_ai", "predictive_routing", "real_time_monitoring", "api_access", "dedicated_support"]');

-- ============================================
-- TRIGGERS (Automatic timestamps)
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tenants_updated BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_agents_updated BEFORE UPDATE ON agents FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_calls_updated BEFORE UPDATE ON call_sessions FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_transcriptions_updated BEFORE UPDATE ON transcriptions FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- COMMENT ON TABLES (Documentation)
-- ============================================
COMMENT ON TABLE tenants IS 'Businesses that rent AI/human agents for call center operations. HIPAA/GDPR compliant with data isolation.';
COMMENT ON TABLE agents IS 'AI or human agents rented by tenants. Each agent has SIP credentials for FreeSWITCH integration.';
COMMENT ON TABLE call_sessions IS 'Individual call records with duration, cost, transcription references, and HIPAA encryption keys.';
COMMENT ON TABLE agent_activity IS 'Time tracking for agent billing and usage analytics. Records all status changes.';
COMMENT ON TABLE recordings IS 'Encrypted call recordings with HIPAA-compliant retention policies and PII redaction flags.';
COMMENT ON TABLE billing_records IS 'Monthly billing records with cost breakdowns per tenant and plan.';
COMMENT ON TABLE audit_log IS 'Compliance audit trail for HIPAA/GDPR. Tracks all data access and modifications.';