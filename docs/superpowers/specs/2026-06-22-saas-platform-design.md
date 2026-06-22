# AetherDesk SaaS Platform — Full MVP Design Spec

**Date:** 2026-06-22
**Status:** Draft
**Scope:** Full MVP — Signup, Onboarding, Billing, Call Lists, Scripts, Parallel Dialer, Live Dashboard

---

## 1. Executive Summary

AetherDesk is a privacy-focused multi-tenant call center SaaS platform. Users sign up, rent AI agents by the hour or month, import call lists, write/generate scripts with variables and branching, and launch parallel outbound campaigns. Supervisors monitor campaigns in real-time via a live dashboard.

This spec covers the complete SaaS product: from signup through campaign launch and monitoring.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (React/Vite)                 │
│  Landing → Signup → Onboarding Wizard → Dashboard       │
│  ├── Campaign Manager (live dashboard)                  │
│  ├── Call List Manager (CSV upload, lead pipeline)      │
│  ├── Script Editor (variables, branching, templates)    │
│  ├── Billing (Stripe Checkout + Portal)                 │
│  └── Settings (tenant config, agent management)         │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API + WebSocket
┌──────────────────────┴──────────────────────────────────┐
│                    BACKEND (FastAPI)                      │
│  ├── Auth (JWT + email verification + password reset)   │
│  ├── Onboarding (wizard state machine)                  │
│  ├── Billing (Stripe webhooks, usage metering)          │
│  ├── Campaigns (parallel dialer, scheduling)            │
│  ├── Leads (CSV import, column mapping, scoring)        │
│  ├── Scripts (templates, variables, branching)          │
│  ├── Real-time (WebSocket dashboard, agent presence)    │
│  └── Voice (STT/TTS, Fonoster/Twilio SIP)              │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│              DATA LAYER                                  │
│  ├── PostgreSQL (primary, with RLS)                     │
│  ├── SQLite (dev fallback)                              │
│  ├── Redis (queues, pub/sub, caching)                   │
│  └── Object Storage (recordings, CSV uploads)           │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Feature Specifications

### 3.1 User Registration & Authentication

#### 3.1.1 Database: `users` Table

**CRITICAL:** This table is referenced by `get_user_by_email_db()` but never defined. Must be created.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    verification_token VARCHAR(255),
    reset_token VARCHAR(255),
    reset_token_expires TIMESTAMP,
    tenant_id UUID REFERENCES tenants(id),
    role VARCHAR(50) DEFAULT 'owner',  -- owner, admin, agent
    avatar_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### 3.1.2 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `POST /api/v1/auth/register` | POST | Create account, send verification email |
| `POST /api/v1/auth/verify-email` | POST | Verify email with token |
| `POST /api/v1/auth/forgot-password` | POST | Send password reset email |
| `POST /api/v1/auth/reset-password` | POST | Reset password with token |
| `POST /api/v1/auth/login` | POST | Login (existing) |
| `POST /api/v1/auth/logout` | POST | Logout (existing) |
| `GET /api/v1/auth/me` | GET | Get current user (existing) |

#### 3.1.3 Registration Flow

1. User enters email + password + full name on `/signup`
2. Backend creates user record with `email_verified=False`
3. Backend generates verification token, sends email (or logs it in dev)
4. User clicks link → `POST /api/v1/auth/verify-email` with token
5. User is redirected to onboarding wizard

#### 3.1.4 Frontend Pages

- `/signup` — Registration form with email, password, full name, company name
- `/verify-email` — "Check your email" confirmation page
- `/forgot-password` — Password reset request form
- `/reset-password` — New password form (token from email link)

---

### 3.2 Onboarding Wizard

**Style:** Linear 5-step wizard, cannot be skipped. State persisted in `users.onboarding_completed` flag.

#### Step 1: Business Info

**Form fields:**
- Company name (required)
- Industry (dropdown: Sales, Support, Healthcare, Real Estate, Insurance, Other)
- Timezone (dropdown, auto-detected from browser)
- Phone number for outbound calls (E.164 format)

**Backend:** `POST /api/v1/onboarding/business-info`
- Creates or updates `tenants` record
- Sets `tenant_settings` defaults

#### Step 2: Import Call List

**Upload flow:**
1. User uploads CSV or Excel file
2. Backend parses columns, shows preview (first 5 rows)
3. User maps columns to lead fields: `first_name`, `last_name`, `company`, `phone`, `email`, `industry`, `notes`
4. Backend validates all rows (phone E.164, required fields)
5. Shows validation errors with row numbers
6. User confirms import → leads created in `leads` table

**Supported formats:** CSV, XLSX, XLS
**Max file size:** 10MB
**Max rows:** 10,000 per import
**Column detection:** Auto-match columns by name similarity (e.g., "Company Name" → `company`)

**Backend endpoints:**
| Endpoint | Method | Description |
|---|---|---|
| `POST /api/v1/leads/upload` | POST | Upload CSV/Excel, returns parsed preview |
| `POST /api/v1/leads/map-columns` | POST | Map columns to lead fields |
| `POST /api/v1/leads/import` | POST | Import validated leads |

**Frontend:** `/onboarding/import` — Upload zone, column mapping UI, validation preview table

#### Step 3: Write/Generate Script

**Options:**
1. **AI Generate** — Enter objective → Ollama generates script with variables
2. **Template Gallery** — Pick from pre-built templates (DB-backed, not hardcoded)
3. **Blank Editor** — Write from scratch with variable picker

**Script syntax:**
```
Hello {{first_name}} from {{company}}! I'm calling about our AI platform.

{{#if industry == "tech"}}
I noticed you're in the tech space — our platform handles technical support automation.
{{else if industry == "healthcare"}}
For healthcare, we offer HIPAA-compliant call handling.
{{else}}
We help businesses like yours automate their call center operations.
{{/if}}

Would you have 5 minutes to hear how we can help?
```

**Variables available:** All lead fields (first_name, last_name, company, phone, email, industry, notes) + custom fields.

**Backend endpoints:**
| Endpoint | Method | Description |
|---|---|---|
| `POST /api/v1/scripts/generate` | POST | AI-generate script from objective |
| `POST /api/v1/scripts` | POST | Save script to database |
| `GET /api/v1/scripts` | GET | List saved scripts |
| `GET /api/v1/scripts/templates` | GET | List marketplace templates |

**Database: `script_templates` table**
```sql
CREATE TABLE script_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),  -- NULL for platform templates
    name VARCHAR(255) NOT NULL,
    description TEXT,
    industry VARCHAR(100),
    script_content TEXT NOT NULL,  -- JSON with variables, branches
    variables JSONB DEFAULT '[]',
    avg_qa_score FLOAT DEFAULT 0.0,
    usage_count INT DEFAULT 0,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Frontend:** `/onboarding/script` — Script editor with live preview, variable picker dropdown, template gallery sidebar

#### Step 4: Test Agent

**Sandbox test:**
1. User clicks "Test Call" button
2. Backend creates temporary agent with the script
3. User's browser connects via WebSocket (or Twilio for phone test)
4. User has a 2-minute test conversation with the AI agent
5. After test: shows transcript, QA score, suggestions

**Backend:** Reuses existing `POST /api/v1/voice/test-call` endpoint
**Frontend:** `/onboarding/test` — Call simulation UI with live transcript, end-test button, score display

#### Step 5: Launch

**Summary page:**
- Business info summary
- Call list stats (X leads imported)
- Script preview
- Test results
- "Launch First Campaign" button

**Backend:** `POST /api/v1/onboarding/complete` — Sets `users.onboarding_completed = True`
**Frontend:** `/onboarding/launch` — Summary cards, launch button

---

### 3.3 Subscription & Billing (Stripe)

#### 3.3.1 Plan Structure

| Plan | Price | Concurrent Calls | Max Agents | Features |
|---|---|---|---|---|
| Starter | $49/mo or $8/hr | 2 | 2 | Basic scripts, CSV import |
| Pro | $149/mo or $20/hr | 10 | 10 | Templates, A/B testing, analytics |
| Enterprise | $499/mo or $60/hr | 50 | 50 | Custom scripts, API access, priority support |

**Database:** Existing `plans` table (already seeded with 3 tiers, prices need updating)

#### 3.3.2 Stripe Integration

**Backend endpoints:**
| Endpoint | Method | Description |
|---|---|---|
| `POST /api/v1/billing/checkout` | POST | Create Stripe Checkout session |
| `POST /api/v1/billing/portal` | POST | Create Stripe Customer Portal session |
| `POST /api/v1/billing/webhook` | POST | Handle Stripe webhooks |
| `GET /api/v1/billing/subscription` | GET | Get current subscription status |
| `POST /api/v1/billing/usage` | POST | Report usage (per-minute metering) |

**Stripe Checkout flow:**
1. User clicks "Upgrade" → `POST /api/v1/billing/checkout`
2. Backend creates Stripe Checkout Session with price_id
3. User redirected to Stripe Checkout
4. On success → Stripe webhook → Backend creates subscription
5. Tenant updated with `stripe_customer_id`, `stripe_subscription_id`, `plan_id`

**Stripe Webhooks to handle:**
- `checkout.session.completed` — Activate subscription
- `invoice.paid` — Record payment
- `invoice.payment_failed` — Dunning notification
- `customer.subscription.updated` — Plan changes
- `customer.subscription.deleted` — Cancel subscription

**Usage metering:**
- Track agent minutes per billing period
- Report to Stripe via `POST /v1/subscription_items/{id}/usage_records`
- Enforce plan limits: `max_concurrent_calls`, `max_agents`

#### 3.3.3 Plan Enforcement

**Middleware checks on every call/campaign start:**
1. Query `tenants.plan_id` → `plans.max_concurrent_calls`
2. Count active calls for tenant
3. If at limit → reject with 402 status, show upgrade prompt
4. Same for `max_agents` on agent creation

#### 3.3.4 Frontend Pages

- `/billing` — Subscription status, current plan, usage this period, upgrade/downgrade buttons
- `/billing/checkout` — Stripe Checkout redirect
- `/billing/portal` — Stripe Customer Portal redirect (manage payment method, cancel)

---

### 3.4 Call List Management

#### 3.4.1 CSV/Excel Import

**Upload endpoint:** `POST /api/v1/leads/upload`
- Accepts `multipart/form-data` with file
- Parses CSV (with auto-detect delimiter) or Excel
- Returns: column headers, row count, preview (first 5 rows), detected column types

**Column mapping endpoint:** `POST /api/v1/leads/map-columns`
- Input: file_id + column mapping (e.g., `{"Company Name": "company", "Phone": "phone"}`)
- Auto-maps by name similarity
- Returns: validation results (errors per row)

**Import endpoint:** `POST /api/v1/leads/import`
- Input: file_id + confirmed mapping
- Creates leads in batches of 500
- Returns: total imported, total errors, error details

**Database: Expand `leads` table**
```sql
ALTER TABLE leads ADD COLUMN IF NOT EXISTS first_name VARCHAR(100);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_name VARCHAR(100);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS custom_fields JSONB DEFAULT '{}';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS score FLOAT DEFAULT 0.0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS source VARCHAR(100);  -- csv, api, manual
ALTER TABLE leads ADD COLUMN IF NOT EXISTS imported_at TIMESTAMP;
```

#### 3.4.2 Lead Management

**API endpoints:**
| Endpoint | Method | Description |
|---|---|---|
| `GET /api/v1/leads` | GET | List leads with filters (status, score, industry) |
| `POST /api/v1/leads` | POST | Create single lead |
| `PATCH /api/v1/leads/{id}` | PATCH | Update lead |
| `DELETE /api/v1/leads/{id}` | DELETE | Delete lead |
| `POST /api/v1/leads/bulk-update` | POST | Bulk status change |
| `POST /api/v1/leads/bulk-delete` | POST | Bulk delete |

**Lead statuses:** `new`, `queued`, `calling`, `answered`, `voicemail`, `no_answer`, `interested`, `follow_up`, `converted`, `declined`, `do_not_call`

**Lead scoring:** Manual priority (1-10) + auto-scoring based on:
- Industry match to script relevance
- Previous call outcomes (if re-imported)
- Time since last contact

#### 3.4.3 Frontend Pages

- `/onboarding/import` — Step 2 of wizard (upload + mapping + validation)
- `/leads` — Lead manager (table with filters, bulk actions, import button)
- `/leads/import` — Standalone import page (for re-importing after onboarding)

---

### 3.5 Script & Template System

#### 3.5.1 Script Data Model

**Database: `scripts` table**
```sql
CREATE TABLE scripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    name VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,  -- JSON: {blocks: [...], variables: [...], branches: [...]}
    variables JSONB DEFAULT '[]',  -- [{name, type, default, source}]
    is_active BOOLEAN DEFAULT FALSE,
    version INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Script content format (JSON):**
```json
{
  "blocks": [
    {"type": "greeting", "text": "Hello {{first_name}}!"},
    {"type": "pitch", "text": "I'm calling from AetherDesk..."},
    {"type": "branch", "condition": "industry == 'tech'", "true_block": "tech_pitch", "false_block": "generic_pitch"},
    {"type": "objection", "trigger": "not_interested", "response": "I understand..."},
    {"type": "close", "text": "Would you like to schedule a demo?"}
  ],
  "variables": [
    {"name": "first_name", "type": "string", "source": "lead"},
    {"name": "company", "type": "string", "source": "lead"},
    {"name": "industry", "type": "string", "source": "lead"}
  ]
}
```

#### 3.5.2 Template Marketplace

**Database: `script_templates` table** (defined in section 3.2)

**Seed data:** 8-10 templates across industries:
- B2B SaaS Sales
- Healthcare Outreach
- Real Estate Follow-up
- Insurance Quotes
- Financial Services
- E-commerce Upsell
- Technical Support
- Appointment Setting

**API endpoints:**
| Endpoint | Method | Description |
|---|---|---|
| `GET /api/v1/scripts/templates` | GET | List public templates (filterable by industry) |
| `POST /api/v1/scripts/templates/{id}/clone` | POST | Clone template to user's scripts |
| `POST /api/v1/scripts/templates/publish` | POST | Publish user's script as template |

#### 3.5.3 Script Editor UI

**Features:**
- Visual block-based editor (greeting, pitch, branch, objection, close)
- Variable picker dropdown (inserts `{{variable}}` syntax)
- Branch builder (condition + true/false blocks)
- Live preview with sample data
- Save/load versions
- Template gallery sidebar

**Frontend:** `/scripts` — Script list page, `/scripts/editor/{id}` — Editor page

---

### 3.6 Parallel Dialer & Campaigns

#### 3.6.1 Campaign Data Model

**Database: `campaigns` table**
```sql
CREATE TABLE campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    name VARCHAR(255) NOT NULL,
    script_id UUID REFERENCES scripts(id),
    status VARCHAR(50) DEFAULT 'draft',  -- draft, scheduled, running, paused, completed, cancelled
    max_concurrent INT DEFAULT 3,
    dialer_speed VARCHAR(50) DEFAULT 'normal',  -- slow, normal, fast, aggressive
    schedule_start TIMESTAMP,
    schedule_end TIMESTAMP,
    schedule_timezone VARCHAR(50),
    schedule_hours JSONB,  -- {mon: {start: "09:00", end: "17:00"}, ...}
    total_leads INT DEFAULT 0,
    leads_contacted INT DEFAULT 0,
    leads_interested INT DEFAULT 0,
    leads_converted INT DEFAULT 0,
    total_calls INT DEFAULT 0,
    total_minutes FLOAT DEFAULT 0,
    total_cost FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Database: `campaign_agents` junction table**
```sql
CREATE TABLE campaign_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    calls_made INT DEFAULT 0,
    avg_duration FLOAT DEFAULT 0,
    UNIQUE(campaign_id, agent_id)
);
```

#### 3.6.2 Campaign Lifecycle

```
draft → scheduled → running → paused → running → completed
                    ↘ cancelled
```

**API endpoints:**
| Endpoint | Method | Description |
|---|---|---|
| `GET /api/v1/campaigns` | GET | List campaigns |
| `POST /api/v1/campaigns` | POST | Create campaign |
| `PATCH /api/v1/campaigns/{id}` | PATCH | Update campaign |
| `POST /api/v1/campaigns/{id}/start` | POST | Start dialer |
| `POST /api/v1/campaigns/{id}/pause` | POST | Pause dialer |
| `POST /api/v1/campaigns/{id}/resume` | POST | Resume dialer |
| `POST /api/v1/campaigns/{id}/stop` | POST | Stop dialer |
| `GET /api/v1/campaigns/{id}/stats` | GET | Real-time campaign stats |

#### 3.6.3 Parallel Dialer Engine

**How it works:**
1. Campaign starts → distributes leads across N agents (N = `max_concurrent`)
2. Each agent gets a batch of leads and dials sequentially
3. When agent finishes a call → gets next lead from batch
4. Campaign tracks: calls made, contacts, interested, converted, cost
5. Respects plan's `max_concurrent_calls` limit
6. Scheduling: only dials during configured hours/days

**Lead distribution:**
- Round-robin across agents
- Each agent gets leads in priority order (score descending)
- Leads marked `do_not_call` are skipped
- Leads already called today are skipped

**Pacing:**
- `slow`: 1 call per 60 seconds
- `normal`: 1 call per 30 seconds
- `fast`: 1 call per 15 seconds
- `aggressive`: 1 call per 5 seconds

#### 3.6.4 Campaign Scheduling

- Time-of-day restrictions (e.g., only call 9am-5pm Eastern)
- Day-of-week restrictions (e.g., no weekends)
- Start/end dates
- Timezone-aware (leads have timezone, calls scheduled per-lead timezone)

#### 3.6.5 Frontend Pages

- `/campaigns` — Campaign list with status badges, stats, actions
- `/campaigns/new` — Create campaign wizard (select script, select leads, configure dialer)
- `/campaigns/{id}` — Campaign detail with live stats, pause/resume, lead pipeline
- `/campaigns/{id}/monitor` — Live call monitoring (supervisor view)

---

### 3.7 Live Real-Time Dashboard

#### 3.7.1 WebSocket Events

**Dashboard WebSocket:** `ws://localhost:8000/ws/dashboard?token=xxx`

**Events pushed to dashboard:**
```json
// Agent status change
{"type": "agent_status", "data": {"agent_id": "xxx", "status": "on_call", "name": "Agent 1"}}

// Campaign stats update
{"type": "campaign_stats", "data": {"campaign_id": "xxx", "contacted": 45, "interested": 12, "calls_in_progress": 3}}

// Call started
{"type": "call_started", "data": {"call_id": "xxx", "agent_id": "xxx", "lead_company": "Acme Corp"}}

// Call completed
{"type": "call_completed", "data": {"call_id": "xxx", "duration": 180, "outcome": "interested", "cost": 0.50}}

// Lead status change
{"type": "lead_update", "data": {"lead_id": "xxx", "old_status": "new", "new_status": "interested"}}
```

#### 3.7.2 Dashboard Widgets

| Widget | Data | Update Frequency |
|---|---|---|
| Agents Online | Count of agents with status != offline | Real-time |
| Calls In Progress | Active call_sessions | Real-time |
| Leads Contacted | Count where status in (answered, voicemail, interested, etc.) | Every 5s |
| Leads Interested | Count where status = 'interested' | Every 5s |
| Conversion Rate | interested / contacted * 100 | Every 5s |
| Cost Today | Sum of call costs today | Every 10s |
| Calls Per Hour | Rolling 1-hour average | Every 30s |
| Live Call Feed | Last 20 calls with status/outcome | Real-time |

#### 3.7.3 Backend Implementation

**Redis pub/sub channels:**
- `campaign:{id}:stats` — Campaign stat updates
- `agent:{id}:status` — Agent status changes
- `call:{id}:event` — Call lifecycle events

**WebSocket manager:** Extend existing `ConnectionManager` in `realtime.py`
- New `dashboard_connections` dict for supervisor dashboard connections
- Broadcast to all dashboard connections on stat changes

#### 3.7.4 Frontend

**Dashboard page:** `/dashboard` (replace current SaaSDashboard)
- Grid layout with stat cards (agents online, calls in progress, cost today)
- Campaign list with live stats
- Live call feed (scrolling list of recent calls)
- Agent status panel (grid of agent cards with status indicators)

---

### 3.8 Multi-Agent Management

#### 3.8.1 Agent Groups

**Database: `agent_groups` table**
```sql
CREATE TABLE agent_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    max_agents INT DEFAULT 10,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Database: Add `group_id` to `agents` table**
```sql
ALTER TABLE agents ADD COLUMN IF NOT EXISTS group_id UUID REFERENCES agent_groups(id);
```

#### 3.8.2 Agent Scheduling

**Database: `agent_schedules` table**
```sql
CREATE TABLE agent_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    day_of_week INT NOT NULL,  -- 0=Monday, 6=Sunday
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    timezone VARCHAR(50) DEFAULT 'UTC',
    is_active BOOLEAN DEFAULT TRUE
);
```

**Availability check:** Before assigning a call, check if agent's current time falls within their schedule.

#### 3.8.3 Agent Presence

**Real-time agent grid:**
- Online/offline indicator (green/gray dot)
- Current status (available/busy/on_call/paused)
- Current call duration (if on_call)
- Calls made today
- Average call duration
- Last active timestamp

#### 3.8.4 Frontend

- `/agents` — Agent list with status, group, schedule, performance
- `/agents/groups` — Group management
- `/agents/{id}/schedule` — Weekly schedule editor
- `/agents/invite` — Invite new agent via email

---

## 4. Frontend Architecture

### 4.1 Consolidated App Structure

Remove `App.jsx` (legacy). Use `App.tsx` as single entry point.

```
src/
├── App.tsx                    # Router + Auth provider
├── main.tsx                   # Entry point
├── components/
│   ├── LandingPage.tsx        # Marketing landing (existing)
│   ├── OnboardingWizard.tsx   # 5-step wizard (NEW)
│   │   ├── StepBusinessInfo.tsx
│   │   ├── StepImportLeads.tsx
│   │   ├── StepWriteScript.tsx
│   │   ├── StepTestAgent.tsx
│   │   └── StepLaunch.tsx
│   ├── Dashboard.tsx          # Main dashboard (replaces SaaSDashboard)
│   ├── CampaignManager.tsx    # Campaign list + create
│   ├── CampaignDetail.tsx     # Single campaign live view
│   ├── LeadManager.tsx        # Lead table with filters
│   ├── LeadImport.tsx         # CSV upload + mapping
│   ├── ScriptEditor.tsx       # Visual script editor
│   ├── ScriptTemplates.tsx    # Template marketplace
│   ├── BillingPage.tsx        # Subscription + usage
│   ├── AgentManager.tsx       # Agent CRUD + status
│   ├── AgentGroups.tsx        # Group management
│   └── SettingsPage.tsx       # Tenant settings
├── hooks/
│   ├── useWebSocket.ts        # WebSocket connection hook
│   ├── useDashboard.ts        # Dashboard data hook
│   └── useCampaign.ts         # Campaign state hook
└── lib/
    ├── api.ts                 # API client
    └── auth.ts                # Auth helpers
```

### 4.2 Routing

```tsx
// Public routes
/                          → LandingPage
/signup                    → SignupPage
/login                     → LoginPage
/verify-email              → VerifyEmailPage
/forgot-password           → ForgotPasswordPage
/reset-password            → ResetPasswordPage

// Protected routes (require auth + onboarding completed)
/dashboard                 → Dashboard (main dashboard)
/onboarding                → OnboardingWizard
/campaigns                 → CampaignManager
/campaigns/new             → CreateCampaign
/campaigns/:id             → CampaignDetail
/campaigns/:id/monitor     → LiveMonitor
/leads                     → LeadManager
/leads/import              → LeadImport
/scripts                   → ScriptList
/scripts/editor/:id        → ScriptEditor
/scripts/templates         → ScriptTemplates
/billing                   → BillingPage
/agents                    → AgentManager
/agents/groups             → AgentGroups
/agents/:id/schedule       → AgentSchedule
/settings                  → SettingsPage
```

---

## 5. API Summary

### New Endpoints

| Category | Endpoint | Method | Description |
|---|---|---|---|
| Auth | `/auth/register` | POST | User registration |
| Auth | `/auth/verify-email` | POST | Email verification |
| Auth | `/auth/forgot-password` | POST | Password reset request |
| Auth | `/auth/reset-password` | POST | Password reset |
| Onboarding | `/onboarding/business-info` | POST | Save business info |
| Onboarding | `/onboarding/complete` | POST | Mark onboarding done |
| Leads | `/leads/upload` | POST | Upload CSV/Excel |
| Leads | `/leads/map-columns` | POST | Map columns to fields |
| Leads | `/leads/import` | POST | Import validated leads |
| Leads | `/leads/bulk-update` | POST | Bulk status change |
| Leads | `/leads/bulk-delete` | POST | Bulk delete |
| Scripts | `/scripts` | CRUD | Script management |
| Scripts | `/scripts/generate` | POST | AI script generation |
| Scripts | `/scripts/templates` | GET | List templates |
| Scripts | `/scripts/templates/{id}/clone` | POST | Clone template |
| Campaigns | `/campaigns` | CRUD | Campaign management |
| Campaigns | `/campaigns/{id}/start` | POST | Start dialer |
| Campaigns | `/campaigns/{id}/pause` | POST | Pause dialer |
| Campaigns | `/campaigns/{id}/resume` | POST | Resume dialer |
| Campaigns | `/campaigns/{id}/stop` | POST | Stop dialer |
| Campaigns | `/campaigns/{id}/stats` | GET | Real-time stats |
| Billing | `/billing/checkout` | POST | Stripe checkout |
| Billing | `/billing/portal` | POST | Stripe portal |
| Billing | `/billing/webhook` | POST | Stripe webhook |
| Billing | `/billing/subscription` | GET | Subscription status |
| WebSocket | `ws/dashboard` | WS | Live dashboard events |
| WebSocket | `ws/campaign/{id}` | WS | Campaign live events |

---

## 6. Database Schema Changes

### New Tables

| Table | Purpose |
|---|---|
| `users` | User accounts (CRITICAL — missing) |
| `scripts` | Saved scripts with variables/branches |
| `script_templates` | Marketplace templates |
| `campaigns` | Campaign configurations |
| `campaign_agents` | Campaign-to-agent mapping |
| `agent_groups` | Agent team grouping |
| `agent_schedules` | Agent availability schedules |
| `lead_imports` | Import history and column mappings |

### Modified Tables

| Table | Changes |
|---|---|
| `leads` | Add first_name, last_name, email, custom_fields, score, source, imported_at |
| `tenants` | Add onboarding_completed, onboarding_step |
| `agents` | Add group_id, last_seen_at |
| `plans` | Update prices to match spec |

---

## 7. Implementation Phases

Since this is a full MVP, implementation should be phased for manageability:

### Phase 1: SaaS Foundation (Week 1-2)
- Users table + registration + email verification
- Onboarding wizard (5 steps)
- Onboarding state persistence
- Frontend: Signup, Login (real), Onboarding pages

### Phase 2: Billing (Week 2-3)
- Stripe integration (Checkout, webhooks, portal)
- Plan enforcement middleware
- Usage metering
- Frontend: Billing page

### Phase 3: Call Lists & Scripts (Week 3-4)
- CSV/Excel upload + column mapping
- Lead management CRUD
- Script editor with variables/branches
- Template marketplace (DB-backed)
- Frontend: Lead manager, Script editor, Templates

### Phase 4: Campaigns & Dialer (Week 4-5)
- Campaign CRUD + lifecycle
- Parallel dialer engine
- Campaign scheduling
- Lead distribution
- Frontend: Campaign manager, Create campaign

### Phase 5: Live Dashboard (Week 5-6)
- WebSocket dashboard events
- Redis pub/sub for real-time stats
- Dashboard widgets
- Agent presence
- Frontend: Dashboard, Live monitor

### Phase 6: Multi-Agent (Week 6-7)
- Agent groups
- Agent scheduling
- Agent invitation flow
- Frontend: Agent groups, Schedule editor

---

## 8. Testing Strategy

- **Unit tests** for all new service functions
- **Integration tests** for Stripe webhooks, CSV import, campaign lifecycle
- **E2E tests** for onboarding wizard flow
- **Load tests** for parallel dialer (10+ concurrent agents)

---

## 9. Security Considerations

- All new endpoints require JWT authentication
- CSV uploads validated for file type, size, content
- Stripe webhooks verified with signature
- Rate limiting on registration (prevent abuse)
- Plan enforcement checked before every campaign start
- Lead data encrypted at rest (existing pgcrypto)
- PII redaction for leads (existing Presidio integration)
