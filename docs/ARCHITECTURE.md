# AetherDesk Call Center — Architecture Overview

## System Architecture

AetherDesk is a multi-tenant, privacy-focused digital call center SaaS platform built
with **FastAPI** (Python) and **React** (JavaScript), backed by **PostgreSQL**,
**Redis**, and **Celery** for async task processing. Voice routing is handled
by **Fonoster** and **FreeSWITCH**, with a **Twilio** fallback for dev/staging.

```
Browser ──→ [React SPA :3001] ──→ HTTP/REST ──→ [FastAPI Backend :8000] ──→ SQL ──→ [PostgreSQL / SQLite]
                                         │
                                    WebSocket ──→ Real-time call events
                                         │
                                    Redis pub/sub ──→ Cross-process event bus
                                         │
                              [Fonoster / FreeSWITCH] ──→ Voice calls (SIP/RTP)
```

## Project Structure

```
aetherdesk_scaffold/
├── apps/
│   ├── api/                        # FastAPI backend
│   │   ├── main.py                 # App factory, middleware stack, router includes
│   │   ├── routers/                # 21 route handler files
│   │   ├── services/               # 43 business logic & infrastructure modules
│   │   ├── middleware/             # 3 middleware modules (audit, security, metrics)
│   │   ├── models/
│   │   │   └── dto.py              # Pydantic request/response schemas
│   │   ├── fonoster_client.py      # Fonoster HTTP client (voice API)
│   │   ├── twilio_client.py        # Twilio fallback voice client
│   │   ├── mock_voice_client.py    # Mock client for local dev / demo
│   │   ├── websocket_server.py     # Standalone WebSocket server
│   │   └── Dockerfile              # Container image definition
│   └── voice/                      # Fonoster voice application (Node.js)
│       └── server.js
├── agent-ui/                       # React frontend (Vite)
│   ├── src/
│   │   ├── App.jsx                 # Entry point, auth-gated routing
│   │   ├── pages/                  # 15 page components
│   │   ├── components/             # 10 reusable UI components
│   │   ├── context/                # AuthContext, SocketContext
│   │   ├── services/
│   │   │   └── api.js              # Axios-based API client
│   │   └── main.jsx                # ReactDOM entry
│   └── package.json
├── config/
│   ├── database/
│   │   └── schema.sql              # PostgreSQL schema (540 lines)
│   ├── freeswitch/                 # FreeSWITCH SIP profiles
│   └── protocols/                  # Call protocol definitions
├── kubernetes/                     # GKE deployment manifests
├── scripts/                        # Deployment & utility scripts
├── tests/
│   ├── unit/                       # Python unit tests (pytest)
│   └── e2e/                        # End-to-end tests
├── docker-compose.yml              # Local dev orchestration
└── .env.example                    # Environment variable template
```

---

## Backend: `apps/api/` (FastAPI)

### `main.py` — Application Factory

The FastAPI application is constructed in `main.py` (~431 lines). It:

1. Loads environment variables via `dotenv`
2. Configures middleware stack (order matters):
   - `CORSMiddleware` — CORS headers for SPA
   - `SecurityHeadersMiddleware` — CSP, HSTS, X-Frame-Options
   - `AuditMiddleware` — HIPAA audit logging for PHI paths
   - `MetricsMiddleware` — Prometheus HTTP metrics
   - `RateLimitMiddleware` — Per-IP rate limiting (Redis-backed)
3. Includes all routers under versioned prefixes
4. Sets up Redis connection pool and voice client on startup
5. Tears down connections on shutdown

### Routers (`routers/` — 21 files)

All route handlers use FastAPI's `@router` decorator pattern with `Depends()`
for dependency injection (auth, database connections).

| Router | Prefix | Description |
|--------|--------|-------------|
| `auth.py` | `/auth` | Login, registration, password reset |
| `agents.py` | `/tenants/{id}/agents` | Agent CRUD + status management |
| `agent.py` | `/agent` | Agent queue, session management |
| `calls.py` | `/calls` | Call lifecycle (create, action, get, list) |
| `billing.py` | `/billing` | Stripe checkout, portal, subscriptions |
| `leads.py` | `/leads` | Lead CRUD, CSV import |
| `campaign.py` | `/campaign` | Campaign management, phone validation |
| `scripts.py` | `/scripts` | Script CRUD + templates |
| `voice.py` | `/voice` | Voice session management |
| `voice_cloning.py` | `/voice-cloning` | ElevenLabs voice cloning |
| `realtime.py` | `/realtime` | WebSocket connections for live call events |
| `health.py` | `/health` | Health check, readiness, liveness probes |
| `webhooks_twilio.py` | `/webhooks/twilio` | Twilio status callbacks |
| `webhooks_fonster.py` | `/webhooks/fonster` | Fonoster voice events |
| `saas.py` | `/saas` | Multi-tenant plan management |
| `protocols.py` | `/protocols` | Upload/manage call protocols |
| `onboarding.py` | `/onboarding` | New tenant onboarding flow |
| `engine.py` | `/engine` | SMS/call routing engine |
| `tenants.py` | `/tenants` | Tenant CRUD |
| `usage.py` | `/usage` | Usage analytics |
| `agent_management.py` | — | Agent queue, session management |

### Services (`services/` — 43 modules)

Business logic is organized into focused service modules:

**Database Layer:**
- `database.py` — Re-exports from focused sub-modules
- `db_pool.py` — Connection pool management (SQLite / PostgreSQL)
- `db_tenants.py` — Tenant/user database operations
- `db_calls.py` — Call session operations
- `db_config.py` — Database configuration constants
- `db_schema.py` — Schema migration helpers
- `db_errors.py` — Database error types
- `db_migrations.py` — Migration runner

**Authentication:**
- `auth.py` — JWT verification, tenant access, API key checks
- `jwt_utils.py` — JWT encode/decode helpers
- `validators.py` — Input validation utilities

**Voice & Communication:**
- `orchestrator.py` — Call routing, agent assignment
- `engine.py` — Routing engine logic
- `queue.py` — Queue manager
- `call_session.py` — Call session state management
- `asr.py` — Automatic speech recognition
- `tts.py` — Text-to-speech
- `transcript_store.py` — Call transcription storage
- `agent.py` — Agent state management

**Billing:**
- `stripe_service.py` — Stripe SDK wrapper (mock mode for dev)
- `plan_enforcement.py` — Plan limit enforcement

**Infrastructure:**
- `rate_limit.py` — Rate limiter middleware (Redis + in-memory)
- `connection_pool.py` — HTTP connection pool
- `celery_app.py` — Celery app with Redis broker
- `celery_tasks.py` — Async task definitions
- `task_queue.py` — Task queue utilities
- `worker.py` — Celery worker entry point

**AI/ML:**
- `rag.py` — Retrieval-augmented generation
- `intent_classifier.py` — Caller intent detection
- `mcp_client.py` — Model Context Protocol client
- `security_guard.py` — Security guardrails for AI

**Observability:**
- `observability.py` — Logging and tracing setup
- `retry.py` — Retry utilities
- `sanitizer.py` — PII redaction, input sanitization
- `memory_service.py` — Conversation memory management
- `memory.py` — Memory storage backend
- `voice_profile_store.py` — Voice profile persistence
- `loader.py` — Module loader utilities
- `config.py` — Configuration management
- `router.py` — SMS/call routing
- `actions.py` — Call actions

### Middleware (`middleware/` — 3 files)

| Middleware | Class | Responsibility |
|-----------|-------|----------------|
| `audit.py` | `AuditMiddleware` | HIPAA-compliant audit logging for PHI paths |
| `security.py` | `SecurityHeadersMiddleware` | CSP, HSTS, X-Frame-Options headers |
| `metrics.py` | `MetricsMiddleware` | Prometheus request count/latency metrics |

### Data Models (`models/dto.py`)

All Pydantic request/response schemas are in a single file:
- `TenantCreate`, `TenantResponse`
- `AgentCreate`, `AgentResponse`
- `CallCreate`, `CallAction`, `CallResponse`
- `LeadCreate`, `LeadResponse`
- `CampaignCreate`, `CampaignResponse`
- `ScriptCreate`, `ScriptResponse`
- Billing and subscription schemas

### Voice Clients

The platform supports three voice backends with automatic fallback:

1. **Fonoster** (`fonoster_client.py`) — Production voice API
2. **Twilio** (`twilio_client.py`) — Dev/staging fallback
3. **MockVoiceClient** (`mock_voice_client.py`) — Local dev without network

Selection logic in `main.py::get_voice_client()` checks environment variables
in order: `FONOSTER_API_KEY` → `TWILIO_ACCOUNT_SID` → fall through to mock.

---

## Frontend: `agent-ui/` (React + Vite)

### Entry Point (`App.jsx`)

Single-page application with:
- `AuthProvider` wrapping the entire component tree
- `Routes` with auth-gated redirects (`Navigate` to `/login`)
- `Sidebar` for navigation when authenticated
- `Toaster` (sonner) for notifications

### Pages (15)

| Page | Route | Description |
|------|-------|-------------|
| `Dashboard.jsx` | `/` | Call metrics, agent status, charts |
| `AgentManagement.jsx` | `/agents` | Agent CRUD, status toggles |
| `CallLogs.jsx` | `/calls` | Call history, filtering |
| `Settings.jsx` | `/settings` | Tenant settings, config |
| `VoiceCloning.jsx` | `/voice-cloning` | ElevenLabs voice clone management |
| `BillingPage.jsx` | `/billing` | Subscription, invoices, usage |
| `LeadsPage.jsx` | `/leads` | Lead management |
| `LeadImportPage.jsx` | `/leads/import` | CSV lead import |
| `ScriptsPage.jsx` | `/scripts` | Script templates |
| `ScriptEditorPage.jsx` | `/scripts/:id` | Script editor |
| `Login.jsx` | `/login` | Authentication |
| `SignupPage.jsx` | `/signup` | Registration |
| `ForgotPasswordPage.jsx` | `/forgot-password` | Password reset request |
| `ResetPasswordPage.jsx` | `/reset-password` | Password reset |
| `VerifyEmailPage.jsx` | `/verify-email` | Email verification |

### Components (10)

| Component | Purpose |
|-----------|---------|
| `Sidebar.jsx` | Navigation sidebar with role-based links |
| `StatCard.jsx` | Metric display card |
| `AgentStatusChart.jsx` | Agent status distribution chart |
| `CallVolumeChart.jsx` | Call volume over time chart |
| `RecentCalls.jsx` | Recent calls table widget |
| `ConfirmationModal.jsx` | Confirmation dialog |
| `ErrorModal.jsx` | Error display dialog |
| `ErrorDisplay.jsx` | Inline error display |
| `DeleteButton.jsx` | Delete action button |
| `ToastNotification.jsx` | Toast notification component |

### Context Providers

| Context | File | Purpose |
|---------|------|---------|
| `AuthContext.jsx` | `context/AuthContext.jsx` | JWT token storage, login/logout, user state |
| `SocketContext.jsx` | `context/SocketContext.jsx` | WebSocket connection management |

### API Client (`services/api.js`)

Axios-based HTTP client with:
- Base URL configuration
- JWT `Authorization` header injection via request interceptor
- Response error handling (401 → redirect to login)

---

## Database Schema

### Development: SQLite
- File-based database created automatically via `db_pool.py`
- Connection pooling via `_get_sqlite_conn()`
- Lightweight, zero-configuration for local development

### Production: PostgreSQL 15+
- Schema defined in `config/database/schema.sql` (540 lines)
- Connection pooling via `psycopg2` pool
- Row-level security for tenant isolation
- Full-text search via `tsvector` columns

### Key Tables

| Table | Purpose | Row count estimate |
|-------|---------|-------------------|
| `plans` | Subscription tiers | 3-5 (Starter, Pro, Enterprise) |
| `tenants` | Business customers | Core table |
| `agents` | AI/human agents per tenant | Scalable |
| `call_sessions` | Individual call records | Core table |
| `call_queue` | Real-time queue management | Ephemeral |
| `agent_activity` | Time tracking / billing | High volume |
| `recordings` | Encrypted call recordings | Configurable retention |
| `transcripts` | Call transcriptions (PII-redacted) | High volume |
| `billing_invoices` | Monthly invoices | Monthly |
| `audit_log` | HIPAA audit trail | Append-only |

### HIPAA/GDPR Features
- **Encryption at rest**: Per-agent and per-call encryption keys
- **PII redaction**: Flagged on `call_sessions.pii_redacted`
- **Soft delete**: `tenants.deleted_at` for GDPR right to deletion
- **Audit logging**: All PHI access logged to `audit_log` table
- **Data residency**: Configurable via deployment region (default: us-east1)

---

## Realtime Architecture

### WebSocket Connections

Two WebSocket paths are available:
- `/ws/calls/{tenant_id}` — Subscribe to call status updates for a tenant
- `/ws/agent/{agent_id}` — Agent-specific call assignments

### Redis Pub/Sub

The realtime router (`routers/realtime.py`) uses Redis pub/sub channels:

```
Call Created → FastAPI → Redis PUBLISH "calls:{tenant_id}" → WebSocket → Agent UI
                                                                    ↓
                                                            Redis SUBSCRIBE
```

- WebSocket connections subscribe to Redis channels per tenant
- Messages are forwarded from Redis to connected WebSocket clients
- Automatic reconnection with exponential backoff (3 retries)
- Falls back to polling (1s interval) when Redis is unavailable

### Standalone WebSocket Server

`websocket_server.py` provides an alternative standalone WebSocket server using
the `websockets` library, managing connected clients and forwarding messages.

---

## Async Task Processing

### Celery + Redis

Background task processing via Celery (configured in `services/celery_app.py`):

- **Broker/Backend**: Redis (default: `redis://localhost:6379/0`)
- **Serialization**: JSON
- **Task tracking**: `task_track_started=True` for progress monitoring
- **Deadlines**: 5-minute soft limit, 6-minute hard limit

### Scheduled Tasks

Defined in `services/celery_tasks.py`:
- Call transcription processing
- Voice cloning job completion
- Billing invoice generation
- Usage report aggregation
- Cleanup of expired sessions

---

## Key Design Decisions

### 1. Multi-Tenant Isolation via Row-Level Security
Tenants are fully isolated at the database level. All queries include
`tenant_id` filters, enforced by application logic and database constraints.

### 2. Stripe Mock Mode for Development
When `STRIPE_SECRET_KEY` is not set, all Stripe SDK calls return mock responses.
This enables local development without a Stripe account or network access.

### 3. Dual Voice Backend (Fonoster + Twilio + Mock)
The platform auto-selects the best available voice client. This allows:
- Production: Fonoster (self-hosted, cost-efficient)
- Staging: Twilio (cloud API, no Docker needed)
- Dev: MockVoiceClient (no network, logs calls)

### 4. Redis for Both Cache and Pub/Sub
Redis serves dual roles:
- **Cache**: Rate limiter state, session data, temporary storage
- **Message broker**: Celery task queue and WebSocket event broadcasting

### 5. Modular Service Architecture
Business logic is decomposed into focused service modules (43 modules) rather
than a monolithic service layer. Each module has a single responsibility and
can be tested independently.

### 6. HIPAA/GDPR by Design
- Encryption at rest (per-agent/per-call keys)
- Audit logging for all PHI access
- PII redaction pipeline for call transcripts
- Soft delete for GDPR compliance
- Data residency controls via deployment configuration

### 7. Rate Limiting with Redis Backoff
Rate limiting uses Redis when available, falling back to in-memory tracking.
This ensures fair resource usage across tenants without a single point of
failure.

### 8. Prometheus Metrics for Observability
All HTTP requests and voice operations are instrumented with Prometheus
counters, histograms, and gauges for production monitoring and alerting.

---

## Data Flow

```
1. User Authentication
   Browser → POST /auth/login → FastAPI → validate credentials → DB lookup
   ← JWT token (stored in localStorage)

2. Authenticated API Request
   Browser → GET /api/v1/tenants/{id}/agents → FastAPI
   ├── RateLimitMiddleware checks IP (Redis/in-memory)
   ├── SecurityHeadersMiddleware adds CSP, HSTS
   ├── AuthMiddleware verifies JWT → extracts tenant_id
   ├── AuditMiddleware logs PHI access
   └── Route handler → DB query → JSON response

3. Real-time Call Event
   Voice Backend → Webhook → FastAPI → process event
   ├── Persist to DB
   ├── Publish to Redis: "calls:{tenant_id}"
   └── Redis → WebSocket → Browser UI update

4. Background Task
   FastAPI → Celery task → Redis queue → Celery worker
   └── Task result stored in Redis backend
```

## Deployment

### Local Development (Docker Compose)
```
docker-compose up -d
# FastAPI:  http://localhost:8000
# Agent UI: http://localhost:3001
# Redis:    localhost:6379
```

### Production (GKE)
- Kubernetes manifests in `kubernetes/`
- GitHub Actions CI/CD pipeline with lint, test, build, deploy
- Coverage gate: ≥ 45% (`--cov-fail-under=45`)
- Regional deployment: us-east1 (HIPAA eligibility)
