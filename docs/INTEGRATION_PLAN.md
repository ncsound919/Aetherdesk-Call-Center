# AetherDesk Integration Plan — Critical & High Priority Tools

## Overview

This plan integrates production-grade open-source tools to replace custom infrastructure and add enterprise capabilities. Each integration is designed to be backward-compatible (graceful degradation when not configured) and follows the existing `sys.path` bridge pattern.

---

## Phase 1: Observability Stack (Week 1)

### 1.1 Langfuse — AI Call Monitoring

**What it replaces**: Custom `observability.py` CallLogger/MetricsCollector, manual LLM cost tracking

**Why**: Tracks every AI agent conversation — LLM costs, prompt quality, intent classification accuracy, token usage per call. Without this you're flying blind on AI agent performance.

**Files to create/modify**:
- `src/api/services/langfuse_client.py` — New: Langfuse initialization and helpers
- `src/api/services/observability.py` — Modify: add Langfuse decorators to CallLogger
- `src/api/services/orchestrator.py` — Modify: wrap LLM calls with `@observe(as_type="generation")`
- `src/api/services/intent_classifier.py` — Modify: trace intent classification
- `src/api/main.py` — Modify: initialize Langfuse on startup, flush on shutdown
- `requirements.txt` — Add: `langfuse>=2.0.0`

**Integration pattern**:
```python
# src/api/services/langfuse_client.py
import os
from langfuse import Langfuse

_langfuse = None

def get_langfuse() -> Langfuse | None:
    global _langfuse
    if _langfuse is None:
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        if public_key and secret_key:
            _langfuse = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
    return _langfuse

def observe_call(func):
    """Decorator that traces call-handling functions to Langfuse."""
    from langfuse import observe
    @observe(as_type="generation")
    async def wrapper(*args, **kwargs):
        lf = get_langfuse()
        if lf:
            return await func(*args, **kwargs)
        return await func(*args, **kwargs)
    return wrapper
```

```python
# In orchestrator.py — wrap the main LLM call
from api.services.langfuse_client import get_langfuse

@observe(as_type="generation")
def classify_intent(user_message: str, tenant_id: str) -> dict:
    lf = get_langfuse()
    # ... existing intent classification logic ...
    if lf:
        lf.score(name="intent_confidence", value=confidence)
    return result
```

**Env vars needed**:
```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com  # or self-hosted
```

**Verification**: Call an agent, check Langfuse dashboard for traces showing intent classification, LLM calls, and costs.

---

### 1.2 Sentry — Error Tracking & Performance

**What it replaces**: Custom error logging in `observability.py`, partial Sentry config in `main.py`

**Why**: Already partially configured but not properly wired. Needs FastAPI integration, performance tracing, and release tracking.

**Files to modify**:
- `src/api/main.py` — Modify: proper Sentry init with FastAPI integration
- `src/api/middleware/audit.py` — Modify: report audit failures to Sentry
- `requirements.txt` — Add: `sentry-sdk[fastapi]>=2.0.0`

**Integration pattern**:
```python
# In main.py — replace existing Sentry init (lines ~504-511)
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0.1,  # 10% of requests traced
        profiles_sample_rate=0.1,
        integrations=[
            FastApiIntegration(
                app=app,
                failed_request_status_codes={400, 401, 403, 404, 500},
            ),
            LoggingIntegration(level="error"),
        ],
        environment=os.getenv("APP_ENV", "development"),
        release=f"aetherdesk@{os.getenv('APP_VERSION', '1.0.0')}",
    )
```

**Env vars needed**:
```
SENTRY_DSN=https://...@o1.ingest.sentry.io/...
APP_VERSION=1.0.0
```

**Verification**: Trigger a 500 error, confirm it appears in Sentry dashboard with stack trace and request context.

---

## Phase 2: Billing & Auth (Week 2)

### 2.1 Lago — Usage-Based Billing

**What it replaces**: Custom `stripe_service.py` (partially), manual usage tracking in `usage.py`

**Why**: Tracks per-minute call usage, subscription tiers, invoicing. Handles metering, plan limits, and Stripe integration out of the box.

**Files to create/modify**:
- `src/api/services/billing_engine.py` — New: Lago client and metering
- `src/api/services/stripe_service.py` — Modify: delegate to Lago for metering
- `src/api/routers/usage.py` — Modify: query Lago for usage data
- `src/api/main.py` — Modify: initialize Lago client on startup
- `requirements.txt` — Add: `lago-python-client>=1.0.0`

**Integration pattern**:
```python
# src/api/services/billing_engine.py
import os
from lago_python_client import LagoClient

_client = None

def get_lago() -> LagoClient | None:
    global _client
    if _client is None:
        api_key = os.getenv("LAGO_API_KEY")
        if api_key:
            _client = LagoClient(api_key=api_key)
            if os.getenv("LAGO_API_URL"):
                _client.base_url = os.getenv("LAGO_API_URL")
    return _client

def track_call_usage(tenant_id: str, call_sid: str, duration_seconds: int, call_type: str):
    """Meter a completed call for billing."""
    lago = get_lago()
    if not lago:
        return  # Mock mode — no billing
    lago.events().create({
        "event_code": "call_completed",
        "customer_id": tenant_id,
        "properties": {
            "call_sid": call_sid,
            "duration_seconds": duration_seconds,
            "call_type": call_type,  # inbound/outbound
        }
    })

def get_usage_summary(tenant_id: str, period_start: str, period_end: str) -> dict:
    """Get billing summary for a tenant in a period."""
    lago = get_lago()
    if not lago:
        return {"mock": True, "calls": 0, "minutes": 0, "cost": 0}
    # Query Lago API for usage
    ...
```

**Env vars needed**:
```
LAGO_API_KEY=...
LAGO_API_URL=http://localhost:8001  # self-hosted Lago
STRIPE_SECRET_KEY=...  # for payment processing
```

**Verification**: Place a call, confirm usage event appears in Lago dashboard, confirm invoice generation.

---

### 2.2 Casbin — Multi-Tenant RBAC

**What it replaces**: Custom role checks scattered across routers, hardcoded permission logic

**Why**: Centralizes authorization — agent, supervisor, admin, tenant-owner roles with policy-based access control. Currently auth is just JWT validation with no role enforcement.

**Files to create/modify**:
- `src/api/services/authorization.py` — New: Casbin enforcer and middleware
- `src/api/middleware/rbac.py` — New: RBAC middleware
- `src/api/main.py` — Modify: add RBAC middleware
- `src/api/routers/*.py` — Modify: replace manual role checks with `@require_role("admin")`
- `requirements.txt` — Add: `casbin>=1.36.0`, `casbin-sqlalchemy-adapter>=1.0.0`

**Integration pattern**:
```python
# src/api/services/authorization.py
import os
import casbin
from pathlib import Path

_enforcer = None

def get_enforcer() -> casbin.Enforcer:
    global _enforcer
    if _enforcer is None:
        model_path = Path(__file__).parent.parent / "config" / "casbin_model.conf"
        policy_path = Path(__file__).parent.parent / "config" / "casbin_policy.csv"
        _enforcer = casbin.Enforcer(str(model_path), str(policy_path))
    return _enforcer

def check_permission(user_role: str, resource: str, action: str) -> bool:
    """Check if role has permission on resource for given action."""
    e = get_enforcer()
    return e.enforce(user_role, resource, action)
```

```python
# src/api/middleware/rbac.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip auth for public endpoints
        if request.url.path in ("/health", "/api/v1/auth/login", "/docs"):
            return await call_next(request)

        # Extract role from JWT (set by auth middleware)
        user_role = getattr(request.state, "user_role", None)
        if not user_role:
            return await call_next(request)  # Let auth middleware handle

        # Check permission
        from api.services.authorization import check_permission
        method = request.method.lower()
        resource = request.url.path.split("/")[3] if len(request.url.path.split("/")) > 3 else "root"

        if not check_permission(user_role, resource, method):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        return await call_next(request)
```

**Casbin model** (`config/casbin_model.conf`):
```
[request_definition]
r = sub, obj, act

[policy_definition]
p = sub, obj, act

[role_definition]
g = _, _

[policy_effect]
e = some(where (p.eft == allow))

[matchers]
m = g(r.sub, p.sub) && r.obj == p.obj && r.act == p.act
```

**Casbin policy** (`config/casbin_policy.csv`):
```
p, admin, *, *
p, supervisor, agents, read
p, supervisor, agents, write
p, supervisor, calls, read
p, supervisor, calls, write
p, agent, calls, read
p, agent, calls, transfer
p, tenant_owner, *, *
g, admin, tenant_owner
```

**Verification**: Attempt admin-only action as agent role → 403. Attempt read action as agent → 200.

---

## Phase 3: Analytics (Week 3)

### 3.1 ClickHouse — Call Analytics Database

**What it replaces**: SQLite/Postgres for high-volume call logs, CDR analysis, real-time metrics

**Why**: SQLite can't handle millions of call records with sub-second queries. ClickHouse is purpose-built for analytical workloads — call duration distributions, agent utilization, SLA tracking.

**Files to create/modify**:
- `src/api/services/analytics_db.py` — New: ClickHouse connection and queries
- `src/api/routers/usage.py` — Modify: query ClickHouse for analytics
- `src/api/services/observability.py` — Modify: write call events to ClickHouse
- `src/api/main.py` — Modify: initialize ClickHouse on startup
- `requirements.txt` — Add: `clickhouse-connect>=0.7.0`

**Integration pattern**:
```python
# src/api/services/analytics_db.py
import os
import clickhouse_connect

_client = None

def get_clickhouse():
    global _client
    if _client is None:
        host = os.getenv("CLICKHOUSE_HOST")
        if host:
            _client = clickhouse_connect.get_client(
                host=host,
                port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
                username=os.getenv("CLICKHOUSE_USER", "default"),
                password=os.getenv("CLICKHOUSE_PASSWORD", ""),
                database=os.getenv("CLICKHOUSE_DB", "aetherdesk"),
            )
            _init_schema(_client)
    return _client

def _init_schema(client):
    client.command("""
        CREATE TABLE IF NOT EXISTS call_events (
            call_id String,
            tenant_id String,
            agent_id String,
            direction Enum8('inbound' = 1, 'outbound' = 2),
            caller String,
            called String,
            started_at DateTime64(3),
            ended_at Nullable(DateTime64(3)),
            duration_seconds Float64,
            intent LowCardinality(String),
            status LowCardinality(String),
            satisfaction_score Nullable(Float64),
            tokens_used UInt32,
            cost_cents UInt32,
            INDEX idx_tenant tenant_id TYPE bloom_filter GRANULARITY 4,
            INDEX idx_agent agent_id TYPE bloom_filter GRANULARITY 4,
            INDEX idx_intent intent TYPE set(100) GRANULARITY 4
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(started_at)
        ORDER BY (tenant_id, started_at)
    """)

def record_call_event(event: dict):
    """Insert a call event into ClickHouse."""
    ch = get_clickhouse()
    if not ch:
        return  # Fallback to SQLite/Postgres
    ch.insert("call_events", [event], column_names=list(event.keys()))
```

**Env vars needed**:
```
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DB=aetherdesk
```

**Verification**: Place 100 calls, query ClickHouse for call distribution by intent, confirm sub-second response.

---

### 3.2 Metabase — Embeddable Dashboards

**What it replaces**: Custom analytics pages, manual report generation

**Why**: Tenants get self-serve analytics dashboards — call volume, agent performance, CSAT scores, revenue. Zero code needed for dashboard creation.

**Files to create/modify**:
- `docker-compose.yml` — Add: Metabase service
- `config/metabase/` — New: Metabase environment config
- `src/api/routers/metabase.py` — New: iframe embed endpoints for tenant dashboards
- `agent-ui/src/pages/Analytics.jsx` — Modify: embed Metabase iframe for advanced analytics

**Docker Compose addition**:
```yaml
  metabase:
    image: metabase/metabase:latest
    container_name: aetherdesk-metabase
    restart: unless-stopped
    environment:
      MB_DB_TYPE: postgres
      MB_DB_DBNAME: metabase
      MB_DB_PORT: 5432
      MB_DB_USER: ${DB_USER}
      MB_DB_PASS: ${DB_PASSWORD}
      MB_DB_HOST: db
      MB_EMBEDDING_APP_ORIGIN: http://localhost:3001
    ports:
      - "3002:3000"
    networks:
      - aetherdesk-net
    depends_on:
      db:
        condition: service_healthy
```

**Verification**: Open Metabase at `localhost:3002`, connect to ClickHouse/Postgres, create a "Calls per Day" dashboard, confirm it loads.

---

## Phase 4: Product Analytics (Week 4)

### 4.1 PostHog — Product Analytics & Feature Flags

**What it replaces**: None — new capability for A/B testing and feature rollout

**Why**: Track how tenants use the UI, A/B test call routing algorithms, feature-flag new capabilities (voice cloning, AI scripts) for gradual rollout.

**Files to create/modify**:
- `src/api/services/analytics_client.py` — New: PostHog client wrapper
- `src/api/main.py` — Modify: initialize PostHog on startup
- `agent-ui/src/services/posthog.js` — New: PostHog JS SDK init
- `agent-ui/src/App.jsx` — Modify: wrap with PostHog provider
- `requirements.txt` — Add: `posthog>=3.0.0`

**Integration pattern**:
```python
# src/api/services/analytics_client.py
import os
from posthog import Posthog

_client = None

def get_posthog() -> Posthog | None:
    global _client
    if _client is None:
        api_key = os.getenv("POSTHOG_API_KEY")
        if api_key:
            _client = Posthog(
                api_key=api_key,
                host=os.getenv("POSTHOG_HOST", "https://us.i.posthog.com"),
            )
    return _client

def track_event(distinct_id: str, event: str, properties: dict = None):
    """Track a product analytics event."""
    ph = get_posthog()
    if ph:
        ph.capture(distinct_id=distinct_id, event=event, properties=properties or {})

def is_feature_enabled(flag_key: str, distinct_id: str) -> bool:
    """Check if a feature flag is enabled for a user."""
    ph = get_posthog()
    if not ph:
        return True  # Default to enabled when PostHog not configured
    return ph.feature_enabled(key=flag_key, distinct_id=distinct_id)
```

**Frontend**:
```javascript
// agent-ui/src/services/posthog.js
import posthog from 'posthog-js'

const key = import.meta.env.VITE_POSTHOG_KEY
if (key) {
  posthog.init(key, {
    api_host: import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
    capture_pageview: true,
  })
}

export default posthog
```

**Env vars needed**:
```
POSTHOG_API_KEY=phc_...
POSTHOG_HOST=https://us.i.posthog.com
VITE_POSTHOG_KEY=phc_...
VITE_POSTHOG_HOST=https://us.i.posthog.com
```

**Verification**: Navigate dashboard, confirm events appear in PostHog. Create a feature flag, verify it's evaluated correctly.

---

### 4.2 K6 — Load Testing

**What it replaces**: Manual testing, no-load-test coverage

**Why**: Validate WebRTC infrastructure can handle 1000+ concurrent calls, find breaking points before production.

**Files to create**:
- `tests/load/k6_call_flow.js` — New: K6 load test script
- `tests/load/k6_sip_gateway.js` — New: SIP gateway load test
- `Makefile` — Add: `make load-test` target

**K6 script pattern**:
```javascript
// tests/load/k6_call_flow.js
import http from 'k6/http'
import { check, sleep } from 'k6'

export const options = {
  stages: [
    { duration: '1m', target: 50 },   // Ramp up to 50 virtual users
    { duration: '5m', target: 50 },   // Stay at 50 for 5 minutes
    { duration: '1m', target: 200 },  // Spike to 200
    { duration: '5m', target: 200 },  // Sustain
    { duration: '1m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% of requests < 500ms
    http_req_failed: ['rate<0.01'],     // <1% failure rate
  },
}

export default function () {
  // Login
  const loginRes = http.post(`${__ENV.API_URL}/api/v1/auth/login`, JSON.stringify({
    email: 'admin@aetherdesk.com',
    password: 'admin123',
  }), { headers: { 'Content-Type': 'application/json' } })

  check(loginRes, { 'login succeeded': (r) => r.status === 200 })

  const token = loginRes.json('access_token')
  const headers = { Authorization: `Bearer ${token}` }

  // Create a call
  const callRes = http.post(`${__ENV.API_URL}/api/v1/calls`, JSON.stringify({
    to_number: '+19843656059',
    agent_id: 'test-agent',
  }), { headers: { ...headers, 'Content-Type': 'application/json' } })

  check(callRes, { 'call created': (r) => r.status === 200 || r.status === 201 })

  sleep(5) // Simulate call duration
}
```

**Makefile addition**:
```makefile
load-test:
	k6 run tests/load/k6_call_flow.js --env API_URL=http://localhost:8000
```

**Verification**: Run load test, confirm 200 concurrent virtual users complete with <1% failure rate.

---

## Summary: Integration Matrix

| Tool | Phase | Effort | Replaces | Env Vars |
|------|-------|--------|----------|----------|
| Langfuse | 1 | 2h | Custom observability | `LANGFUSE_*` |
| Sentry | 1 | 1h | Custom error logging | `SENTRY_DSN` |
| Lago | 2 | 4h | Custom billing | `LAGO_*` |
| Casbin | 2 | 3h | Manual role checks | None (policy files) |
| ClickHouse | 3 | 4h | SQLite analytics | `CLICKHOUSE_*` |
| Metabase | 3 | 2h | Custom dashboards | None (Docker) |
| PostHog | 4 | 2h | None (new) | `POSTHOG_*` |
| K6 | 4 | 2h | Manual testing | None |

**Total estimated effort**: ~20 hours across 4 weeks

## Dependencies

```
Week 1: Langfuse + Sentry (independent, can parallelize)
Week 2: Lago + Casbin (independent, can parallelize)
Week 3: ClickHouse + Metabase (Metabase depends on ClickHouse)
Week 4: PostHog + K6 (independent, can parallelize)
```

## Rollback Strategy

Each integration is guarded by env vars:
- If `LANGFUSE_PUBLIC_KEY` is not set → Langfuse is a no-op
- If `SENTRY_DSN` is not set → Sentry is disabled
- If `LAGO_API_KEY` is not set → Billing falls back to mock mode
- If `CLICKHOUSE_HOST` is not set → Analytics fall back to SQLite/Postgres
- If `POSTHOG_API_KEY` is not set → PostHog is a no-op

All integrations degrade gracefully — the system works without them, they just add capability when configured.
