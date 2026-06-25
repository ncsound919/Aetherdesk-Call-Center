# Phase 1 Implementation Plan — Enterprise Readiness

**Status:** ✅ COMPLETE — All 4 phases executed. Score: 17/40 → 26/40 (+9)
**Goal:** Move from 17/40 → 22/40 in 4 weeks by closing the 5 critical gaps.
**Strategy:** Focus on the lowest-scoring categories first (WFM 1/5, Business Continuity 1/5) then Security (3/5→4/5) and Reliability (2/5→3/5).
**Result:** Exceeded target — 26/40 (65%) vs planned 22/40 (55%)

---

## File Inventory — What We're Touching

### New Files to Create (9)

| # | File | Purpose | Part of |
|---|------|---------|---------|
| 1 | `src/api/routers/wfm.py` | WFM router — shifts, schedules, forecasts, QA scores | WFM |
| 2 | `src/api/services/wfm.py` | WFM business logic — scheduling engine, forecasting, QA scoring engine | WFM |
| 3 | `src/api/services/forecasting.py` | Demand forecasting — Holt-Winters / ARIMA on historical call volume | WFM |
| 4 | `src/api/services/qa_scoring.py` | QA evaluation engine — rubric-based call scoring | WFM |
| 5 | `src/api/services/mfa.py` | MFA logic — TOTP generation, verification, backup codes | Security |
| 6 | `src/api/services/runbooks.py` | Runbook definitions and incident escalation engine | BC |
| 7 | `src/api/services/vendor_health.py` | Vendor health monitoring — Twilio, Deepgram, Groq status checks | BC |
| 8 | `agent-ui/src/pages/WFMDashboard.jsx` | WFM dashboard — schedules, adherence, QA scores, forecasts | WFM |
| 9 | `agent-ui/src/pages/QADashboard.jsx` | QA scoring dashboard — call review, rubrics, agent scores | WFM |

### Existing Files to Modify (24)

| # | File | Change | Part of |
|---|------|--------|---------|
| 1 | `src/api/main.py` | Register WFM router, add MFA routes, add metrics middleware, add Prometheus endpoint | All |
| 2 | `src/api/routers/auth.py` | Add MFA endpoints (setup, verify, backup codes, disable) | Security |
| 3 | `src/api/services/auth.py` | Add TOTP validation, MFA token requirements in JWT | Security |
| 4 | `src/api/routers/agents.py` | Add QA scores to agent responses, add schedule assignment | WFM |
| 5 | `src/api/services/database.py` | Re-export new DB functions from wfm_db, forecasting_db | WFM |
| 6 | `src/api/services/db_tenants.py` | Add agent schedule, shift, QA score DB operations | WFM |
| 7 | `src/api/services/db_calls.py` | Add call QA status, add call scoring fields | WFM |
| 8 | `src/api/models/dto.py` | Add ShiftCreate, ShiftResponse, ScheduleCreate, QAScoreCreate, QAScoreResponse, RunbookResponse, RunbookTrigger | WFM/Security |
| 9 | `src/api/middleware/metrics.py` | Add uptime counter, add per-tenant call metrics gauge, add DB connection gauge | Reliability |
| 10 | `src/api/services/observability.py` | Add uptime tracking, add SLA metric aggregation | Reliability |
| 11 | `src/api/services/rate_limit.py` | Add per-tenant rate limiting (read tenant_id from JWT) | Security |
| 12 | `src/api/services/celery_tasks.py` | Add WFM tasks (daily forecast computation, schedule adherence check, QA auto-scoring) | WFM |
| 13 | `agent-ui/src/App.jsx` | Add routes for /wfm, /qa-dashboard | WFM |
| 14 | `agent-ui/src/pages/Dashboard.jsx` | Add WFM summary section, add QA score card | WFM |
| 15 | `agent-ui/src/pages/Settings.jsx` | Add MFA setup section in Security tab, add scheduling settings in General | Security/WFM |
| 16 | `agent-ui/src/components/Sidebar.jsx` | Add WFM, QA nav items | WFM |
| 17 | `agent-ui/src/services/api.js` | Add WFM, QA API modules | WFM |
| 18 | `docker-compose.yml` | Add Prometheus + Grafana services | Reliability |
| 19 | `kubernetes/deployment.yml` | Add Prometheus annotations, add HPA resource metrics | Reliability |
| 20 | `config/database/schema.sql` | Add wfm_shifts, wfm_schedules, qa_scores, qa_rubrics tables | WFM |
| 21 | `config/postgresql.conf` | Add pg_stat_statements extension | Reliability |
| 22 | `src/api/services/db_schema.py` | Add WFM + QA table creation in SCHEMA_SQL | WFM |
| 23 | `src/api/services/connection_pool.py` | Add connection pool metrics reporting | Reliability |
| 24 | `Makefile` | Add metrics targets (prom-up, grafana-up, view-metrics) | Reliability |

---

## Week-by-Week Breakdown

### Week 1 — Workforce Management Foundation (WFM: 1/5 → 3/5)

#### Database Layer
- **`config/database/schema.sql`** — Add tables:
  - `wfm_shifts` (id, tenant_id, agent_id, start_time, end_time, shift_type, status, created_at)
  - `wfm_schedules` (id, tenant_id, date, forecasted_volume, forecasted_agents, actual_volume, actual_agents, adherence_pct, created_at)
  - `qa_scores` (id, tenant_id, call_id, agent_id, reviewer_id, rubric_id, total_score, max_score, scores_per_criterion JSONB, notes, reviewed_at)
  - `qa_rubrics` (id, tenant_id, name, criteria JSONB, created_at)
- **`src/api/services/db_schema.py`** — Add WFM tables to SCHEMA_SQL and SQLITE_SCHEMA_SQL
- **`src/api/services/db_tenants.py`** — Add:
  - `create_shift_db()`, `list_shifts_db()`, `update_shift_db()`, `delete_shift_db()`
  - `create_schedule_db()`, `get_schedule_db()`, `update_schedule_adherence_db()`
  - `create_qa_score_db()`, `list_qa_scores_db()`, `get_agent_qa_scores_db()`
  - `create_qa_rubric_db()`, `list_qa_rubrics_db()`

#### Backend Services
- **`src/api/services/forecasting.py`** (new):
  - `compute_forecast(tenant_id, days_ahead)` — uses Holt-Winters on historical `call_sessions` to predict volume
  - `get_forecasted_staffing(tenant_id, date)` — calculates required agents from forecast
- **`src/api/services/wfm.py`** (new):
  - `assign_shifts(schedule_id, agents, shift_config)` — auto-assigns agents to shifts
  - `check_adherence(tenant_id, date)` — measures schedule vs actual login
  - `compute_adherence_pct(agent_id, date)` — individual adherence score
- **`src/api/services/qa_scoring.py`** (new):
  - `score_call(call_id, rubric_id, scores_per_criterion)` — evaluates a call
  - `get_agent_qa_summary(agent_id)` — aggregates QA scores by agent
  - `get_tenant_qa_stats(tenant_id)` — tenant-wide QA metrics
- **`src/api/services/celery_tasks.py`** — Add:
  - `compute_daily_forecast()` — runs forecasting nightly
  - `check_schedule_adherence()` — runs adherence check every hour
  - `auto_assign_shifts()` — runs weekly for schedule generation

#### API Layer
- **`src/api/routers/wfm.py`** (new):
  - `GET /wfm/shifts?tenant_id=` — list shifts
  - `POST /wfm/shifts` — create shift assignment
  - `PUT /wfm/shifts/{id}` — update shift
  - `DELETE /wfm/shifts/{id}` — remove shift
  - `GET /wfm/schedules?tenant_id=&date=` — get daily schedule
  - `POST /wfm/schedules/forecast` — compute forecast
  - `GET /wfm/adherence?tenant_id=&date=` — get adherence metrics
  - `GET /wfm/qa/scores?tenant_id=&agent_id=` — list QA scores
  - `POST /wfm/qa/scores` — submit QA score
  - `GET /wfm/qa/rubrics` — list scoring rubrics
  - `POST /wfm/qa/rubrics` — create rubric
  - `GET /wfm/qa/agent-summary/{agent_id}` — agent QA summary
- **`src/api/routers/agents.py`** — Add QA scores to agent response payload
- **`src/api/services/database.py`** — Re-export new WFM DB functions
- **`src/api/models/dto.py`** — Add DTOs for shifts, schedules, QA scores, rubrics
- **`src/api/main.py`** — Register `wfm.router`

#### Frontend
- **`agent-ui/src/components/Sidebar.jsx`** — Add WFM nav item (icon: `CalendarClock`), QA nav item (icon: `ClipboardCheck`)
- **`agent-ui/src/services/api.js`** — Add `wfmApi` module (shifts, schedules, adherence, forecast) and `qaApi` module (scores, rubrics, agent-summary)
- **`agent-ui/src/pages/WFMDashboard.jsx`** (new):
  - Schedule view: daily/weekly agent schedule calendar
  - Adherence gauge: % schedule adherence, per-agent breakdown
  - Forecast chart: projected vs actual call volume (line chart)
  - Staffing table: shift assignments with agent names and times
- **`agent-ui/src/pages/QADashboard.jsx`** (new):
  - Score overview: tenant-wide average, recent evaluations list
  - Rubric builder: create/edit evaluation criteria
  - Agent scorecards: per-agent QA trends over time
  - Call review modal: load call data + scoring form
- **`agent-ui/src/App.jsx`** — Add routes: `/wfm` → WFMDashboard, `/qa` → QADashboard
- **`agent-ui/src/pages/Dashboard.jsx`** — Add WFM summary card (scheduled vs available agents, adherence %, pending QA reviews)

---

### Week 2 — Business Continuity & MFA (BC: 1/5 → 3/5, Security: 3/5 → 4/5)

#### Business Continuity Backend
- **`src/api/services/runbooks.py`** (new):
  - `Runbook` model — contains steps, escalation paths, contacts
  - `trigger_runbook(incident_type, context)` — initiates runbook
  - `escalate_incident(incident_id, level)` — escalates based on severity
  - `get_active_incidents(tenant_id)` — returns open incidents
  - `load_runbook(runbook_id)` — loads runbook definition
  - Predefined runbooks: `telephony_outage`, `database_failure`, `llm_degradation`, `security_incident`, `provider_degradation`
- **`src/api/services/vendor_health.py`** (new):
  - `check_vendor_health()` — pings Twilio API status, Deepgram health, Groq endpoint
  - `get_vendor_status_summary()` — returns all vendor health states
  - `report_vendor_outage(vendor)` — triggers telephony runbook if critical
- **`src/api/services/celery_tasks.py`** — Add:
  - `check_vendor_health_task()` — runs every 60s
  - `daily_runbook_review_task()` — reviews recent incidents

#### MFA Backend
- **`src/api/services/mfa.py`** (new):
  - `generate_totp_secret()` — creates TOTP secret (pyotp)
  - `verify_totp(secret, code)` — validates 6-digit code
  - `generate_backup_codes()` — creates 8 single-use backup codes
  - `validate_backup_code(user_id, code)` — validates and consumes
  - `get_mfa_status(user_id)` — returns enrolled/not-enrolled
- **`src/api/routers/auth.py`** — Add:
  - `POST /auth/mfa/setup` — initiate MFA enrollment (returns secret + QR URI)
  - `POST /auth/mfa/verify` — verify TOTP code to complete enrollment
  - `POST /auth/mfa/disable` — disable (requires password re-auth)
  - `POST /auth/mfa/login` — login step 2 (after password auth, requires TOTP)
  - `POST /auth/mfa/backup-code` — login with backup code
  - `GET /auth/mfa/status` — check enrollment status
- **`src/api/services/auth.py`** — Add:
  - `require_mfa(payload)` — middleware check for MFA-required users
  - `mfa_required_roles` — configurable set of roles that must have MFA
  - JWT claim `mfa_verified` for MFA-authenticated sessions
- **`src/api/models/dto.py`** — Add MFASetupResponse, MFAVerifyRequest, MFALoginRequest

#### Frontend MFA
- **`agent-ui/src/pages/Settings.jsx`** — Add MFA section under Security tab:
  - QR code display for TOTP enrollment
  - Code verification input
  - Backup codes display (one-time)
  - Disable MFA button
- **`agent-ui/src/pages/Login.jsx`** — Add MFA step after password:
  - If MFA required, show TOTP code input or backup code option
  - Visual indicator of which step (password → MFA)

---

### Week 3 — Monitoring & Observability (Reliability: 2/5 → 3/5)

#### Infrastructure
- **`docker-compose.yml`** — Add:
  - `prometheus` service — config with scrape targets for API (port 8000 `/metrics`), Redis, PostgreSQL
  - `grafana` service — pre-provisioned dashboards, Prometheus datasource
  - Prometheus config mounted via volume for automatic service discovery
- **`kubernetes/deployment.yml`** — Add:
  - Prometheus annotations (`prometheus.io/scrape: "true"`, `prometheus.io/port: "8000"`)
  - Resource requests/limits for HPA metrics
  - HorizontalPodAutoscaler manifest (CPU-based, min=2, max=10)

#### Backend Monitoring
- **`src/api/middleware/metrics.py`** — Expand with:
  - `uptime_seconds` Gauge — tracks app uptime
  - `db_connection_pool_size` Gauge — tracks DB pool utilization
  - `active_voice_channels` Gauge — count active call legs
  - `per_tenant_call_count` CounterVec — calls by tenant (label: tenant_id)
  - `queue_depth` Gauge — current call queue depth
  - `db_query_latency` Histogram — DB query duration
  - `cache_hit_ratio` Gauge — Redis cache efficiency
  - Add `/metrics` route registration in main.py
- **`src/api/services/observability.py`** — Add:
  - `UptimeTracker` — records app start time, exposes `uptime_seconds` metric
  - `SLAMetrics` — computes availability % over sliding windows (24h, 7d, 30d)
  - `track_db_query(duration_ms, query_name)` — records query latency
- **`src/api/services/connection_pool.py`** — Add:
  - `get_pool_stats()` — returns pool size, available, used connections
  - Update gauge metrics on pool operations
- **`src/api/main.py`** — Add:
  - Prometheus middleware registration (or direct injection before routes)
  - `/metrics` endpoint that returns `generate_latest()`
  - Startup metric initialization (zero all counters, set start time)
- **`config/postgresql.conf`** — Enable `pg_stat_statements` for query performance tracking

#### SLA Measurement
- **`src/api/services/observability.py`** — Add:
  - SLA dashboard data: uptime %, error rate %, p50/p95/p99 latency
  - Service-level indicators: API availability, call completion rate, STT/TTS latency
- **`src/api/routers/health.py`** — Add:
  - `/health/ready` — readiness probe (DB + Redis + voice client)
  - `/health/live` — liveness probe (app process only)
  - `/health/sla` — SLA metrics endpoint (requires internal API key)

---

### Week 4 — Integration, Testing & Hardening

#### Backend Testing
- **`tests/unit/`** — Tests for all new modules:
  - `tests/unit/test_wfm.py` — shift CRUD, adherence computation, forecasting
  - `tests/unit/test_qa_scoring.py` — rubric evaluation, score aggregation
  - `tests/unit/test_mfa.py` — TOTP generation, verification, backup codes
  - `tests/unit/test_runbooks.py` — runbook loading, escalation, incidents
  - `tests/unit/test_vendor_health.py` — health checks, outage detection
  - `tests/unit/test_metrics.py` — metric recording, aggregation
  - `tests/unit/test_forecasting.py` — forecast computation, edge cases
- **`tests/integration/`** — Integration tests:
  - `test_wfm_api.py` — full WFM API flow end-to-end
  - `test_mfa_auth_flow.py` — login + MFA + session
  - `test_metrics_endpoint.py` — Prometheus endpoint returns valid data
- **`Makefile`** — Add:
  - `make test-wfm` — run WFM tests
  - `make test-security` — run MFA + runbook tests
  - `make test-all` — ensure all pass

#### Hardening
- **`src/api/routers/auth.py`** — Add:
  - Rate limiting on MFA endpoints (5 attempts per IP per minute)
  - Backoff on failed MFA attempts (exponential delay)
- **`src/api/services/rate_limit.py`** — Add:
  - Per-tenant rate limiting using JWT tenant_id
  - Configurable limits per endpoint group
- **`config/database/schema.sql`** — Add indexes:
  - `idx_wfm_shifts_tenant_date` on `wfm_shifts(tenant_id, start_time)`
  - `idx_qa_scores_agent` on `qa_scores(agent_id, reviewed_at)`
- **`src/api/services/db_schema.py`** — Add indexes to SCHEMA_SQL

#### Frontend Integration
- **`agent-ui/src/pages/Dashboard.jsx`** — Wire up real WFM data from API
- **`agent-ui/src/services/api.js`** — Wire up real QA + WFM API calls
- **`agent-ui/src/pages/Settings.jsx`** — Wire up MFA flow with real backend

---

## File Change Details — Critical Files Only

The following are the highest-risk edits that need careful attention:

### `src/api/main.py` — App Bootstrap
```python
# Added imports:
from api.routers import wfm as wfm_router
from api.middleware.metrics import MetricsMiddleware

# In lifespan():
#   Initialize uptime tracker
#   Initialize MFA config
#
# After middleware stack:
app.add_middleware(MetricsMiddleware)
#
# After other routers:
app.include_router(wfm_router)
```

### `src/api/routers/auth.py` — MFA Routes
Add 6 new endpoints (setup, verify, disable, login-step2, backup-code, status). These map to `src/api/services/mfa.py` functions. The login flow changes: after password verification, check if user has MFA enabled → return `mfa_required: true` + temporary session token → client enters TOTP → final JWT issued.

### `src/api/services/forecasting.py` — Core Algorithm
```
Historical call volume by hour →
  Holt-Winters triple exponential smoothing →
  Traffic intensity (Erlang C) →
  Required staff → Schedule recommendations
```

### `agent-ui/src/pages/WFMDashboard.jsx` — New Page
Uses Recharts for forecast chart (line + area), tabular schedule display, adherence gauge (circular SVG). Follows existing design patterns (dark sidebar, card-based layout, Tailwind theme tokens).

---

## Dependency Map

```
MFA (week 2) ──> auth.py, mfa.py, Login.jsx, Settings.jsx
                └─> rate_limit.py (MFA rate limiting)
                └─> jwt_utils.py (MFA claims)

WFM (week 1)  ──> wfm.py, forecasting.py, schema.sql, WFMDashboard.jsx
                └─> celery_tasks.py (nightly forecast)
                └─> agents.py (QA scores in response)

BC (week 2)   ──> runbooks.py, vendor_health.py
                └─> celery_tasks.py (vendor health check)
                └─> health.py (SLA endpoints)

Monitoring    ──> metrics.py, observability.py, connection_pool.py
(week 3)        └─> docker-compose.yml, deployment.yml
                └─> main.py (/metrics endpoint)
```

**No circular dependencies.** Each new service depends only on `database.py` and `models/dto.py`. Frontend pages depend on `services/api.js` and existing components.
