# AetherDesk Call Center — Supabase Setup Guide

**Project URL**: https://mpcbgtntllzixuadhkay.supabase.co

This guide walks you through the complete Supabase configuration for AetherDesk, including database schema, Row-Level Security policies, Realtime configuration, and Storage buckets.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Variables](#environment-variables)
3. [Database Schema](#database-schema)
4. [Row-Level Security (RLS) Policies](#row-level-security-rls-policies)
5. [Realtime Configuration](#realtime-configuration)
6. [Storage Buckets](#storage-buckets)
7. [Testing the Integration](#testing-the-integration)
8. [Deployment Checklist](#deployment-checklist)

---

## 1. Prerequisites

- **Supabase Account**: https://supabase.com
- **Project Created**: `https://mpcbgtntllzixuadhkay.supabase.co`
- **Node.js 18+** installed
- **PostgreSQL client** (optional, for local testing)

---

## 2. Environment Variables

Create `agent-ui/.env` with the following:

```bash
# Supabase Configuration
VITE_SUPABASE_URL=https://mpcbgtntllzixuadhkay.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key-here

# (Optional) Legacy API Base URL - can be removed once fully migrated
VITE_API_URL=http://localhost:8000/api/v1
```

### Where to Find Your Keys:

1. Go to [Supabase Dashboard](https://app.supabase.com/project/mpcbgtntllzixuadhkay/settings/api)
2. Copy:
   - **Project URL** → `VITE_SUPABASE_URL`
   - **anon public** key → `VITE_SUPABASE_ANON_KEY`

> ⚠️ **Never commit your `.env` file**. Use `.env.example` as a template.

---

## 3. Database Schema

Run the following SQL in the Supabase SQL Editor:

### Core Tables

```sql
-- ============================================================================
-- AetherDesk Call Center - Supabase Schema
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ────────────────────────────────────────────────────────────────────────────
-- 1. Tenants
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name       TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tenants_name ON tenants(name);

-- ────────────────────────────────────────────────────────────────────────────
-- 2. Agents
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id   UUID REFERENCES tenants(id) ON DELETE CASCADE NOT NULL,
  name        TEXT NOT NULL,
  agent_type  TEXT CHECK (agent_type IN ('ai', 'human', 'hybrid')) NOT NULL,
  status      TEXT CHECK (status IN ('available', 'busy', 'offline', 'on_call', 'paused')) DEFAULT 'offline',
  skills      TEXT[] DEFAULT '{}',
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agents_tenant ON agents(tenant_id);
CREATE INDEX idx_agents_status ON agents(status);

-- ────────────────────────────────────────────────────────────────────────────
-- 3. Calls
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS calls (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id        UUID REFERENCES tenants(id) ON DELETE CASCADE NOT NULL,
  agent_id         UUID REFERENCES agents(id) ON DELETE SET NULL,
  caller_number    TEXT,
  direction        TEXT CHECK (direction IN ('inbound', 'outbound')) NOT NULL,
  status           TEXT CHECK (status IN ('queued', 'ringing', 'active', 'completed', 'failed', 'missed')) DEFAULT 'queued',
  duration_seconds INT DEFAULT 0,
  intent           TEXT,
  recording_url    TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_calls_tenant ON calls(tenant_id);
CREATE INDEX idx_calls_agent ON calls(agent_id);
CREATE INDEX idx_calls_status ON calls(status);
CREATE INDEX idx_calls_created ON calls(created_at DESC);

-- ────────────────────────────────────────────────────────────────────────────
-- 4. Leads
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id   UUID REFERENCES tenants(id) ON DELETE CASCADE NOT NULL,
  name        TEXT,
  phone       TEXT NOT NULL,
  email       TEXT,
  status      TEXT CHECK (status IN ('new', 'contacted', 'qualified', 'converted', 'lost')) DEFAULT 'new',
  source      TEXT,
  notes       TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_leads_tenant ON leads(tenant_id);
CREATE INDEX idx_leads_status ON leads(status);

-- ────────────────────────────────────────────────────────────────────────────
-- 5. Scripts
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scripts (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id   UUID REFERENCES tenants(id) ON DELETE CASCADE NOT NULL,
  name        TEXT NOT NULL,
  content     JSONB NOT NULL,
  tags        TEXT[] DEFAULT '{}',
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scripts_tenant ON scripts(tenant_id);

-- ────────────────────────────────────────────────────────────────────────────
-- 6. Chat Sessions
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id      UUID REFERENCES tenants(id) ON DELETE CASCADE NOT NULL,
  visitor_id     TEXT NOT NULL,
  visitor_name   TEXT,
  visitor_email  TEXT,
  agent_id       UUID REFERENCES agents(id) ON DELETE SET NULL,
  status         TEXT CHECK (status IN ('waiting', 'active', 'closed')) DEFAULT 'waiting',
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  closed_at      TIMESTAMPTZ
);

CREATE INDEX idx_chat_sessions_tenant ON chat_sessions(tenant_id);
CREATE INDEX idx_chat_sessions_status ON chat_sessions(status);

-- ────────────────────────────────────────────────────────────────────────────
-- 7. Chat Messages
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_messages (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id  UUID REFERENCES chat_sessions(id) ON DELETE CASCADE NOT NULL,
  sender_type TEXT CHECK (sender_type IN ('visitor', 'agent', 'system')) NOT NULL,
  sender_name TEXT,
  content     TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chat_messages_session ON chat_messages(session_id, created_at);

-- ────────────────────────────────────────────────────────────────────────────
-- 8. Billing
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS billing (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id         UUID REFERENCES tenants(id) ON DELETE CASCADE NOT NULL UNIQUE,
  plan              TEXT DEFAULT 'free',
  balance           NUMERIC(10,2) DEFAULT 0.00,
  currency          TEXT DEFAULT 'USD',
  status            TEXT CHECK (status IN ('active', 'trialing', 'past_due', 'cancelled', 'paused')) DEFAULT 'active',
  calls_this_month  INT DEFAULT 0,
  minutes_used      INT DEFAULT 0,
  estimated_cost    NUMERIC(10,2) DEFAULT 0.00,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_billing_tenant ON billing(tenant_id);

-- ────────────────────────────────────────────────────────────────────────────
-- 9. API Keys (for Developer dashboard)
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id   UUID REFERENCES tenants(id) ON DELETE CASCADE NOT NULL,
  name        TEXT NOT NULL,
  key_hash    TEXT NOT NULL UNIQUE,
  last_used   TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  revoked_at  TIMESTAMPTZ
);

CREATE INDEX idx_api_keys_tenant ON api_keys(tenant_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);

-- ────────────────────────────────────────────────────────────────────────────
-- 10. Webhooks
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS webhooks (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id   UUID REFERENCES tenants(id) ON DELETE CASCADE NOT NULL,
  url         TEXT NOT NULL,
  events      TEXT[] NOT NULL,
  secret      TEXT NOT NULL,
  active      BOOLEAN DEFAULT TRUE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_webhooks_tenant ON webhooks(tenant_id);

-- ────────────────────────────────────────────────────────────────────────────
-- 11. Audit Log
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id   UUID REFERENCES tenants(id) ON DELETE CASCADE NOT NULL,
  user_id     UUID,
  action      TEXT NOT NULL,
  resource    TEXT NOT NULL,
  details     JSONB,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_tenant ON audit_log(tenant_id, created_at DESC);
```

---

## 4. Row-Level Security (RLS) Policies

Enable RLS and create tenant-scoped policies:

```sql
-- Enable RLS on all tables
ALTER TABLE tenants        ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents         ENABLE ROW LEVEL SECURITY;
ALTER TABLE calls          ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads          ENABLE ROW LEVEL SECURITY;
ALTER TABLE scripts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages  ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing        ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys       ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhooks       ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log      ENABLE ROW LEVEL SECURITY;

-- Helper function to get current user's tenant_id from auth.users metadata
CREATE OR REPLACE FUNCTION auth.user_tenant_id()
RETURNS UUID AS $$
  SELECT (auth.jwt() -> 'user_metadata' ->> 'tenant_id')::UUID;
$$ LANGUAGE SQL STABLE;

-- Tenants: users can only see their own tenant
CREATE POLICY tenant_isolation_policy ON tenants
  FOR ALL USING (id = auth.user_tenant_id());

-- Agents: tenant-scoped
CREATE POLICY agents_tenant_policy ON agents
  FOR ALL USING (tenant_id = auth.user_tenant_id());

-- Calls: tenant-scoped
CREATE POLICY calls_tenant_policy ON calls
  FOR ALL USING (tenant_id = auth.user_tenant_id());

-- Leads: tenant-scoped
CREATE POLICY leads_tenant_policy ON leads
  FOR ALL USING (tenant_id = auth.user_tenant_id());

-- Scripts: tenant-scoped
CREATE POLICY scripts_tenant_policy ON scripts
  FOR ALL USING (tenant_id = auth.user_tenant_id());

-- Chat sessions: tenant-scoped
CREATE POLICY chat_sessions_tenant_policy ON chat_sessions
  FOR ALL USING (tenant_id = auth.user_tenant_id());

-- Chat messages: via session tenant_id
CREATE POLICY chat_messages_tenant_policy ON chat_messages
  FOR ALL USING (
    session_id IN (
      SELECT id FROM chat_sessions WHERE tenant_id = auth.user_tenant_id()
    )
  );

-- Billing: tenant-scoped
CREATE POLICY billing_tenant_policy ON billing
  FOR ALL USING (tenant_id = auth.user_tenant_id());

-- API Keys: tenant-scoped
CREATE POLICY api_keys_tenant_policy ON api_keys
  FOR ALL USING (tenant_id = auth.user_tenant_id());

-- Webhooks: tenant-scoped
CREATE POLICY webhooks_tenant_policy ON webhooks
  FOR ALL USING (tenant_id = auth.user_tenant_id());

-- Audit log: tenant-scoped (read-only for users)
CREATE POLICY audit_tenant_policy ON audit_log
  FOR SELECT USING (tenant_id = auth.user_tenant_id());
```

---

## 5. Realtime Configuration

Enable Realtime for the following tables:

1. Go to **Database** → **Replication** in Supabase Dashboard
2. Enable replication for:
   - `calls`
   - `agents`
   - `chat_messages`
   - `chat_sessions`

---

## 6. Storage Buckets

Create the following Storage buckets:

```sql
-- Run in Supabase SQL Editor
INSERT INTO storage.buckets (id, name, public) VALUES
  ('call-recordings', 'call-recordings', false),
  ('avatars', 'avatars', true),
  ('lead-imports', 'lead-imports', false);
```

### Storage Policies

```sql
-- Call recordings: tenant-scoped
CREATE POLICY call_recordings_policy ON storage.objects
  FOR ALL USING (
    bucket_id = 'call-recordings' AND
    (storage.foldername(name))[1] = auth.user_tenant_id()::TEXT
  );

-- Avatars: public read, tenant write
CREATE POLICY avatars_read_policy ON storage.objects
  FOR SELECT USING (bucket_id = 'avatars');

CREATE POLICY avatars_write_policy ON storage.objects
  FOR INSERT WITH CHECK (
    bucket_id = 'avatars' AND
    (storage.foldername(name))[1] = auth.user_tenant_id()::TEXT
  );

-- Lead imports: tenant-scoped
CREATE POLICY lead_imports_policy ON storage.objects
  FOR ALL USING (
    bucket_id = 'lead-imports' AND
    (storage.foldername(name))[1] = auth.user_tenant_id()::TEXT
  );
```

---

## 7. Testing the Integration

### 1. Install Dependencies

```bash
cd agent-ui
npm install @supabase/supabase-js zod
```

### 2. Start the Dev Server

```bash
npm run dev
```

### 3. Test Auth Flow

1. Navigate to `/signup`
2. Create an account (will create a tenant automatically)
3. Check email for verification link (if email confirmation is enabled)
4. Log in via `/login`

### 4. Test Realtime

1. Open two browser windows side-by-side
2. Log in with the same account in both
3. In one window, update an agent's status
4. The other window should receive the realtime update

---

## 8. Deployment Checklist

- [ ] All SQL schemas applied
- [ ] RLS policies enabled on all tables
- [ ] Realtime replication enabled for `calls`, `agents`, `chat_messages`
- [ ] Storage buckets created with correct policies
- [ ] Environment variables set in production
- [ ] Email templates configured in Supabase Auth settings
- [ ] Email sender verified (for production)
- [ ] API rate limits configured
- [ ] Database backups scheduled
- [ ] Monitoring and alerts set up

---

## Troubleshooting

### Issue: "Missing or malformed Authorization header"

- Ensure you're logged in and the session is valid
- Check browser DevTools → Application → Local Storage → `sb-session`

### Issue: "Row violates row-level security policy"

- Verify the user's `user_metadata.tenant_id` matches the resource's `tenant_id`
- Check that RLS policies are correctly applied

### Issue: Realtime not working

- Ensure replication is enabled for the table
- Check that the channel filter matches your tenant_id
- Verify websocket connection in DevTools → Network → WS

---

## Next Steps

1. **Migrate existing data** from the Python FastAPI backend to Supabase
2. **Update `api.js`** to use Supabase client directly instead of Axios
3. **Remove legacy localStorage auth** logic
4. **Deploy to production** with proper environment variables

For questions or issues, open a GitHub issue or contact the team.
