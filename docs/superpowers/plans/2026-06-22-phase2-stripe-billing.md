# Phase 2: Stripe Billing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Stripe-based subscription billing for tenants. Users can upgrade to Starter ($49/mo), Pro ($149/mo), or Enterprise ($499/mo) plans via Stripe Checkout, manage billing via Stripe Customer Portal, and have plan limits enforced (max_concurrent_calls, max_agents).

**Architecture:** Add Stripe SDK to dependencies. Create `stripe_service.py` for SDK wrapper (lazy-loaded for dev). Add `/api/v1/billing/*` router with checkout/portal/webhook/subscription/usage endpoints. Update seed plan prices to match spec. Add plan enforcement helper for middleware use.

**Tech Stack:** FastAPI, Stripe Python SDK (`stripe>=7.0.0`), Pydantic, structlog

**Note:** Stripe is mocked gracefully when `STRIPE_SECRET_KEY` is not set. Tests work without live credentials.

---

## File Structure

### Backend (New/Modified)

| File | Action | Purpose |
|------|--------|---------|
| `pyproject.toml` | Modify | Add `stripe>=7.0.0` dependency |
| `.env.example` | Modify | Add Stripe env vars |
| `apps/api/services/stripe_service.py` | Create | Stripe SDK wrapper (lazy, mockable) |
| `apps/api/services/db_schema.py` | Modify | Update plan seed prices |
| `apps/api/services/db_tenants.py` | Modify | Add `update_tenant_subscription_db`, `get_tenant_subscription_db`, `record_usage_db` |
| `apps/api/routers/billing.py` | Create | Stripe checkout/portal/webhook endpoints |
| `apps/api/main.py` | Modify | Register billing router |
| `tests/unit/test_billing.py` | Create | Tests for billing endpoints |
| `tests/unit/test_plan_enforcement.py` | Create | Tests for plan limit checks |

### Frontend (New/Modified)

| File | Action | Purpose |
|------|--------|---------|
| `agent-ui/src/lib/api.ts` | Modify | Add billing methods |
| `agent-ui/src/pages/BillingPage.tsx` | Create | Subscription status + upgrade/portal |
| `agent-ui/src/App.tsx` | Modify | Add `/billing` route |

---

## Task 1: Add Stripe to dependencies + .env.example

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Add `stripe>=7.0.0` to dependencies**

In `pyproject.toml`, add `"stripe>=7.0.0"` to the dependencies list. Insert after `"httpx>=0.25.0",`:

```toml
    "httpx>=0.25.0",
    "stripe>=7.0.0",
    "langchain>=0.1.0",
```

- [ ] **Step 2: Add Stripe env vars to `.env.example`**

Append the following block at the end of `.env.example`:

```bash
# ── Stripe (Phase 2 Billing) ─────────────────────────────────────
# Leave STRIPE_SECRET_KEY empty to run in MOCK mode (dev only)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_STARTER=price_starter_monthly
STRIPE_PRICE_PRO=price_pro_monthly
STRIPE_PRICE_ENTERPRISE=price_enterprise_monthly
STRIPE_SUCCESS_URL=http://localhost:5173/billing?success=true
STRIPE_CANCEL_URL=http://localhost:5173/billing?canceled=true
```

- [ ] **Step 3: Install stripe and verify**

Run: `python -m pip install "stripe>=7.0.0"`
Expected: Installation succeeds; `python -c "import stripe; print(stripe.__version__)"` prints a version like `7.x.x`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml .env.example
git commit -m "feat: add stripe SDK dependency + env vars"
```

---

## Task 2: Create Stripe service (lazy-loaded, mockable)

**Files:**
- Create: `apps/api/services/stripe_service.py`

- [ ] **Step 1: Create the service module**

Create `apps/api/services/stripe_service.py`:

```python
"""Stripe SDK wrapper.

When STRIPE_SECRET_KEY is unset, all functions return mock data so dev/test
environments work without network calls. In production, set STRIPE_SECRET_KEY
in the environment.
"""
import os
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_STRIPE_ENABLED = bool(os.getenv("STRIPE_SECRET_KEY", "").strip())

if _STRIPE_ENABLED:
    try:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        _stripe = stripe
    except ImportError:
        logger.warning("stripe package not installed; running in mock mode")
        _stripe = None
        _STRIPE_ENABLED = False
else:
    _stripe = None


def is_stripe_enabled() -> bool:
    """Return True if Stripe SDK is configured."""
    return _STRIPE_ENABLED and _stripe is not None


def get_price_id(plan: str) -> Optional[str]:
    """Map plan name → Stripe price_id from env."""
    return os.getenv(f"STRIPE_PRICE_{plan.upper()}")


def create_checkout_session(customer_id: str, price_id: str, success_url: str, cancel_url: str, metadata: Optional[dict] = None) -> dict:
    """Create a Stripe Checkout session for subscription upgrade."""
    if not is_stripe_enabled():
        # Mock response for dev/test
        return {
            "id": f"cs_mock_{price_id}",
            "url": f"{success_url}?mock=true",
            "mock": True,
        }
    session = _stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata or {},
    )
    return {"id": session.id, "url": session.url, "mock": False}


def create_portal_session(customer_id: str, return_url: str) -> dict:
    """Create a Stripe Customer Portal session."""
    if not is_stripe_enabled():
        return {
            "id": f"portal_mock_{customer_id}",
            "url": f"{return_url}?mock=true",
            "mock": True,
        }
    portal = _stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return {"id": portal.id, "url": portal.url, "mock": False}


def get_customer(customer_id: str) -> dict:
    """Retrieve Stripe customer details."""
    if not is_stripe_enabled():
        return {"id": customer_id, "email": "mock@example.com", "mock": True}
    return _stripe.Customer.retrieve(customer_id).to_dict()


def create_customer(email: str, name: Optional[str] = None, metadata: Optional[dict] = None) -> dict:
    """Create a new Stripe customer."""
    if not is_stripe_enabled():
        return {
            "id": f"cus_mock_{email.replace('@', '_').replace('.', '_')}",
            "email": email,
            "mock": True,
        }
    customer = _stripe.Customer.create(email=email, name=name, metadata=metadata or {})
    return customer.to_dict()


def report_usage(subscription_item_id: str, quantity: int, timestamp: Optional[int] = None) -> dict:
    """Report metered usage to Stripe."""
    if not is_stripe_enabled():
        return {"id": f"mbur_mock_{subscription_item_id}", "quantity": quantity, "mock": True}
    usage = _stripe.SubscriptionItem.create_usage_record(
        subscription_item_id,
        quantity=quantity,
        timestamp=timestamp,
    )
    return usage.to_dict()


def verify_webhook_signature(payload: bytes, sig_header: str, secret: str) -> Optional[Any]:
    """Verify and parse Stripe webhook signature."""
    if not is_stripe_enabled():
        # In mock mode, try to parse JSON directly
        import json
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
    try:
        return _stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception as e:
        logger.error("stripe_webhook_verify_failed", error=str(e))
        return None
```

- [ ] **Step 2: Verify imports**

Run: `python -c "from apps.api.services.stripe_service import is_stripe_enabled, get_price_id; print('Mock mode:', is_stripe_enabled()); print('Starter price:', get_price_id('starter'))"`
Expected: prints `Mock mode: False` (or True if env set) and `Starter price: price_starter_monthly`

- [ ] **Step 3: Commit**

```bash
git add apps/api/services/stripe_service.py
git commit -m "feat: add Stripe service wrapper with mock-mode fallback"
```

---

## Task 3: Update seed plan prices to match spec

**Files:**
- Modify: `apps/api/services/db_schema.py`

- [ ] **Step 1: Update PostgreSQL plan seed**

In `apps/api/services/db_schema.py`, find the seed block in `SCHEMA_SQL` (around lines 447-451). Replace with the new tier prices from the spec:

```sql
INSERT INTO plans (name, description, price_per_hour, price_per_day, price_per_week, price_per_month, max_concurrent_calls, max_agents, max_recordings_mb, features) VALUES
('Starter', 'Entry plan — small teams', 8.00, 30.00, 100.00, 49.00, 2, 2, 500, '["basic_scripts","csv_import","email_support"]'),
('Pro', 'Growing teams', 20.00, 70.00, 250.00, 149.00, 10, 10, 2000, '["templates","ab_testing","analytics","priority_support"]'),
('Enterprise', 'Large scale operations', 60.00, 200.00, 700.00, 499.00, 50, 50, 10000, '["custom_scripts","api_access","dedicated_support","sla"]')
ON CONFLICT (name) DO NOTHING;
```

- [ ] **Step 2: Update SQLite plan seed**

Find the SQLite seed block (around lines 654-657). Replace with:

```sql
INSERT OR IGNORE INTO plans (id, name, description, price_per_hour, price_per_day, price_per_week, price_per_month, max_concurrent_calls, max_agents, max_recordings_mb, features) VALUES
('PLAN-STARTER', 'Starter', 'Entry plan — small teams', 8.00, 30.00, 100.00, 49.00, 2, 2, 500, '["basic_scripts","csv_import","email_support"]'),
('PLAN-PRO', 'Pro', 'Growing teams', 20.00, 70.00, 250.00, 149.00, 10, 10, 2000, '["templates","ab_testing","analytics","priority_support"]'),
('PLAN-ENTERPRISE', 'Enterprise', 'Large scale operations', 60.00, 200.00, 700.00, 499.00, 50, 50, 10000, '["custom_scripts","api_access","dedicated_support","sla"]');
```

- [ ] **Step 3: Verify schema still loads**

Run: `python -c "from apps.api.services.db_schema import SCHEMA_SQL, SQLITE_SCHEMA_SQL; print('OK')"`
Expected: prints `OK`

- [ ] **Step 4: Commit**

```bash
git add apps/api/services/db_schema.py
git commit -m "feat: update plan prices to $49/$149/$499 per spec"
```

---

## Task 4: Add subscription DB helpers

**Files:**
- Modify: `apps/api/services/db_tenants.py`

- [ ] **Step 1: Add helper functions at end of file**

Append to `apps/api/services/db_tenants.py`:

```python
async def update_tenant_subscription_db(tenant_id: str, stripe_customer_id: str = None, stripe_subscription_id: str = None, plan_id: str = None, plan_ends_at: str = None):
    """Update tenant Stripe subscription fields."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE tenants SET
                   stripe_customer_id = COALESCE($1, stripe_customer_id),
                   stripe_subscription_id = COALESCE($2, stripe_subscription_id),
                   plan_id = COALESCE($3, plan_id),
                   plan_ends_at = COALESCE($4, plan_ends_at),
                   updated_at = NOW()
                   WHERE id = $5""",
                stripe_customer_id, stripe_subscription_id, plan_id, plan_ends_at, tenant_id
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE tenants SET
               stripe_customer_id = COALESCE(?, stripe_customer_id),
               stripe_subscription_id = COALESCE(?, stripe_subscription_id),
               plan_id = COALESCE(?, plan_id),
               plan_ends_at = COALESCE(?, plan_ends_at),
               updated_at = datetime('now')
               WHERE id = ?""",
            (stripe_customer_id, stripe_subscription_id, plan_id, plan_ends_at, tenant_id)
        )
        conn.commit()
        conn.close()


async def get_tenant_by_stripe_customer_db(stripe_customer_id: str):
    """Look up tenant by Stripe customer ID."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow("SELECT id, plan_id FROM tenants WHERE stripe_customer_id = $1", stripe_customer_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, plan_id FROM tenants WHERE stripe_customer_id = ?", (stripe_customer_id,))
        row = cursor.fetchone()
        conn.close()
        return row


async def record_usage_db(tenant_id: str, metric: str, quantity: float, period_start: str, period_end: str):
    """Record metered usage (e.g., agent minutes) for a tenant billing period."""
    from datetime import UTC, datetime
    record_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO billing_records (id, tenant_id, period_start, period_end, total_minutes, total_agent_hours, status, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, 0, $5, 'pending', NOW(), NOW())""",
                record_id, tenant_id, period_start, period_end, quantity
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO billing_records (id, tenant_id, period_start, period_end, total_agent_hours, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (record_id, tenant_id, period_start, period_end, quantity, now, now)
        )
        conn.commit()
        conn.close()


async def get_tenant_plan_db(tenant_id: str):
    """Get tenant's plan with limits. Returns (plan_name, max_concurrent_calls, max_agents) or None."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                """SELECT p.name AS plan_name, p.max_concurrent_calls, p.max_agents
                   FROM tenants t LEFT JOIN plans p ON t.plan_id = p.id
                   WHERE t.id = $1""",
                tenant_id
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT p.name AS plan_name, p.max_concurrent_calls, p.max_agents
               FROM tenants t LEFT JOIN plans p ON t.plan_id = p.id
               WHERE t.id = ?""",
            (tenant_id,)
        )
        return cursor.fetchone()


async def count_active_agents_db(tenant_id: str) -> int:
    """Count active agents for tenant (for plan enforcement)."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM agents WHERE tenant_id = $1 AND is_active = TRUE",
                tenant_id
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM agents WHERE tenant_id = ? AND is_active = 1", (tenant_id,))
        return cursor.fetchone()[0]


async def count_active_calls_db(tenant_id: str) -> int:
    """Count active calls for tenant (for plan enforcement)."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM call_sessions WHERE tenant_id = $1 AND call_status IN ('ringing','in_progress','active')",
                tenant_id
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM call_sessions WHERE tenant_id = ? AND call_status IN ('ringing','in_progress','active')",
            (tenant_id,)
        )
        return cursor.fetchone()[0]
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "from apps.api.services.db_tenants import update_tenant_subscription_db, get_tenant_by_stripe_customer_db, record_usage_db, get_tenant_plan_db, count_active_agents_db, count_active_calls_db; print('OK')"`
Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
git add apps/api/services/db_tenants.py
git commit -m "feat: add subscription/usage/plan-enforcement DB helpers"
```

---

## Task 5: Create billing router

**Files:**
- Create: `apps/api/routers/billing.py`

- [ ] **Step 1: Create the router**

Create `apps/api/routers/billing.py`:

```python
import os
import json
import structlog
from fastapi import APIRouter, HTTPException, Depends, Request, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from apps.api.services import stripe_service

logger = structlog.get_logger()
router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan: str  # 'starter' | 'pro' | 'enterprise'


class UsageRequest(BaseModel):
    metric: str
    quantity: float


@router.post("/checkout")
async def create_checkout(
    req: CheckoutRequest,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
):
    """Create Stripe Checkout session for plan upgrade."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    from apps.api.services.auth import verify_access_token
    from apps.api.services.db_tenants import get_tenant_db, update_tenant_subscription_db

    payload = await verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    tenant_id = payload.get("tenant_id")
    email = payload.get("email")

    price_id = stripe_service.get_price_id(req.plan)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {req.plan}")

    tenant = await get_tenant_db(tenant_id)
    customer_id = tenant.get("stripe_customer_id") if tenant else None
    if not customer_id:
        customer = stripe_service.create_customer(email=email, metadata={"tenant_id": tenant_id})
        customer_id = customer["id"]
        await update_tenant_subscription_db(tenant_id, stripe_customer_id=customer_id)

    success_url = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:5173/billing?success=true")
    cancel_url = os.getenv("STRIPE_CANCEL_URL", "http://localhost:5173/billing?canceled=true")

    session = stripe_service.create_checkout_session(
        customer_id=customer_id,
        price_id=price_id,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"tenant_id": tenant_id, "plan": req.plan},
    )

    logger.info("billing_checkout_created", tenant_id=tenant_id, plan=req.plan, mock=session.get("mock"))
    return {"checkout_url": session["url"], "session_id": session["id"], "mock": session.get("mock", False)}


@router.post("/portal")
async def create_portal(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
):
    """Create Stripe Customer Portal session."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    from apps.api.services.auth import verify_access_token
    from apps.api.services.db_tenants import get_tenant_db

    payload = await verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    tenant_id = payload.get("tenant_id")

    tenant = await get_tenant_db(tenant_id)
    customer_id = tenant.get("stripe_customer_id") if tenant else None
    if not customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer — subscribe first")

    return_url = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:5173/billing")
    portal = stripe_service.create_portal_session(customer_id=customer_id, return_url=return_url)

    logger.info("billing_portal_created", tenant_id=tenant_id, mock=portal.get("mock"))
    return {"portal_url": portal["url"], "mock": portal.get("mock", False)}


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(default="")):
    """Handle Stripe webhook events."""
    from apps.api.services.db_tenants import (
        update_tenant_subscription_db,
        get_tenant_by_stripe_customer_db,
    )

    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    payload = await request.body()

    event = stripe_service.verify_webhook_signature(payload, stripe_signature, secret)
    if not event:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
    data = event.get("data", {}) if isinstance(event, dict) else (event.data.object if hasattr(event, "data") else {})

    logger.info("stripe_webhook_received", event_type=event_type)

    if event_type == "checkout.session.completed":
        session = data.get("object", data) if isinstance(data, dict) else data
        customer_id = session.get("customer") if isinstance(session, dict) else getattr(session, "customer", None)
        subscription_id = session.get("subscription") if isinstance(session, dict) else getattr(session, "subscription", None)
        tenant_row = await get_tenant_by_stripe_customer_db(customer_id) if customer_id else None
        if tenant_row:
            tenant_id = tenant_row["id"] if isinstance(tenant_row, dict) else tenant_row[0]
            await update_tenant_subscription_db(
                tenant_id,
                stripe_subscription_id=subscription_id,
            )

    elif event_type == "customer.subscription.deleted":
        sub = data.get("object", data) if isinstance(data, dict) else data
        customer_id = sub.get("customer") if isinstance(sub, dict) else getattr(sub, "customer", None)
        tenant_row = await get_tenant_by_stripe_customer_db(customer_id) if customer_id else None
        if tenant_row:
            tenant_id = tenant_row["id"] if isinstance(tenant_row, dict) else tenant_row[0]
            await update_tenant_subscription_db(
                tenant_id,
                stripe_subscription_id=None,
            )

    return {"received": True, "event_type": event_type}


@router.get("/subscription")
async def get_subscription(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))):
    """Get current subscription status."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    from apps.api.services.auth import verify_access_token
    from apps.api.services.db_tenants import get_tenant_db, get_tenant_plan_db

    payload = await verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    tenant_id = payload.get("tenant_id")

    tenant = await get_tenant_db(tenant_id)
    plan = await get_tenant_plan_db(tenant_id)

    has_subscription = bool(tenant and tenant.get("stripe_subscription_id")) if tenant else False

    return {
        "plan_name": (plan.get("plan_name") if plan else None) or "free",
        "max_concurrent_calls": (plan.get("max_concurrent_calls") if plan else None) or 1,
        "max_agents": (plan.get("max_agents") if plan else None) or 1,
        "active": has_subscription,
        "stripe_customer_id": tenant.get("stripe_customer_id") if tenant else None,
        "stripe_subscription_id": tenant.get("stripe_subscription_id") if tenant else None,
        "plan_ends_at": str(tenant.get("plan_ends_at")) if tenant and tenant.get("plan_ends_at") else None,
    }


@router.post("/usage")
async def report_usage(req: UsageRequest, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))):
    """Report metered usage (agent minutes, etc.)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    from apps.api.services.auth import verify_access_token
    from apps.api.services.db_tenants import record_usage_db
    from datetime import datetime, UTC

    payload = await verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    tenant_id = payload.get("tenant_id")

    now = datetime.now(UTC)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    next_month = now.replace(day=28)  # safe lower bound
    if next_month.month == 12:
        period_end = next_month.replace(year=next_month.year + 1, month=1).isoformat()
    else:
        period_end = next_month.replace(month=next_month.month + 1).isoformat()

    await record_usage_db(tenant_id, req.metric, req.quantity, period_start, period_end)
    logger.info("usage_reported", tenant_id=tenant_id, metric=req.metric, quantity=req.quantity)
    return {"recorded": True, "metric": req.metric, "quantity": req.quantity}
```

- [ ] **Step 2: Verify compiles**

Run: `python -c "import py_compile; py_compile.compile('apps/api/routers/billing.py', doraise=True); print('OK')"`
Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
git add apps/api/routers/billing.py
git commit -m "feat: add billing router (checkout/portal/webhook/subscription/usage)"
```

---

## Task 6: Register billing router in main.py

**Files:**
- Modify: `apps/api/main.py`

- [ ] **Step 1: Add import + registration**

In `apps/api/main.py`, add `billing` to the router imports list and include the router:

```python
from apps.api.routers import (
    agent,
    auth,
    billing,    # NEW
    campaign,
    engine,
    onboarding,
    protocols,
    realtime,
    saas,
    voice,
    voice_cloning,
    webhooks_twilio,
)
```

Then add `app.include_router(billing.router, prefix="/api/v1")` after the auth router line:

```python
app.include_router(auth.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")    # NEW
app.include_router(onboarding.router, prefix="/api/v1")
app.include_router(webhooks_twilio.router)
```

- [ ] **Step 2: Verify compiles**

Run: `python -c "import py_compile; py_compile.compile('apps/api/main.py', doraise=True); print('OK')"`
Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
git add apps/api/main.py
git commit -m "feat: register billing router"
```

---

## Task 7: Plan enforcement helper

**Files:**
- Create: `apps/api/services/plan_enforcement.py`

- [ ] **Step 1: Create the helper module**

Create `apps/api/services/plan_enforcement.py`:

```python
"""Plan enforcement helpers.

Used by middleware/endpoints to check if a tenant has reached its plan
limit before allowing an action (creating an agent, starting a call, etc.).
"""
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


class PlanLimitExceeded(Exception):
    def __init__(self, message: str, current: int, limit: int, plan: str):
        super().__init__(message)
        self.message = message
        self.current = current
        self.limit = limit
        self.plan = plan


async def check_agent_limit(tenant_id: str) -> Tuple[bool, dict]:
    """Check whether tenant can create a new agent."""
    from apps.api.services.db_tenants import get_tenant_plan_db, count_active_agents_db

    plan = await get_tenant_plan_db(tenant_id)
    max_agents = (plan.get("max_agents") if plan else None) or 1
    current = await count_active_agents_db(tenant_id)

    if current >= max_agents:
        plan_name = (plan.get("plan_name") if plan else None) or "free"
        return False, {
            "error": "plan_limit_reached",
            "resource": "agents",
            "current": current,
            "limit": max_agents,
            "plan": plan_name,
            "message": f"Agent limit reached for {plan_name} plan ({current}/{max_agents}). Upgrade to add more.",
        }
    return True, {"current": current, "limit": max_agents}


async def check_call_limit(tenant_id: str) -> Tuple[bool, dict]:
    """Check whether tenant can start a new call."""
    from apps.api.services.db_tenants import get_tenant_plan_db, count_active_calls_db

    plan = await get_tenant_plan_db(tenant_id)
    max_calls = (plan.get("max_concurrent_calls") if plan else None) or 1
    current = await count_active_calls_db(tenant_id)

    if current >= max_calls:
        plan_name = (plan.get("plan_name") if plan else None) or "free"
        return False, {
            "error": "plan_limit_reached",
            "resource": "concurrent_calls",
            "current": current,
            "limit": max_calls,
            "plan": plan_name,
            "message": f"Concurrent call limit reached for {plan_name} plan ({current}/{max_calls}). Upgrade to add more.",
        }
    return True, {"current": current, "limit": max_calls}
```

- [ ] **Step 2: Verify compiles**

Run: `python -c "from apps.api.services.plan_enforcement import check_agent_limit, check_call_limit; print('OK')"`
Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
git add apps/api/services/plan_enforcement.py
git commit -m "feat: add plan enforcement helpers for agent/call limits"
```

---

## Task 8: Create billing tests

**Files:**
- Create: `tests/unit/test_billing.py`

- [ ] **Step 1: Write tests**

Create `tests/unit/test_billing.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def auth_bearer():
    """Mock HTTPBearer credentials."""
    cred = MagicMock()
    cred.credentials = "valid_test_token"
    return cred


class TestCheckout:
    @pytest.mark.asyncio
    async def test_checkout_creates_session(self, auth_bearer):
        from apps.api.routers.billing import create_checkout, CheckoutRequest

        with patch("apps.api.services.stripe_service.get_price_id", return_value="price_test"), \
             patch("apps.api.services.stripe_service.create_checkout_session") as mock_session, \
             patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_db", new_callable=AsyncMock) as mock_get_tenant, \
             patch("apps.api.services.db_tenants.update_tenant_subscription_db", new_callable=AsyncMock):

            mock_verify.return_value = {"tenant_id": "tenant-1", "email": "user@test.com"}
            mock_get_tenant.return_value = {}
            mock_session.return_value = {"id": "cs_test", "url": "https://checkout.stripe.com/test", "mock": True}

            result = await create_checkout(CheckoutRequest(plan="pro"), credentials=auth_bearer)
            assert result["checkout_url"] == "https://checkout.stripe.com/test"
            assert result["mock"] is True
            mock_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_checkout_rejects_unknown_plan(self, auth_bearer):
        from apps.api.routers.billing import create_checkout, CheckoutRequest
        from fastapi import HTTPException

        with patch("apps.api.services.stripe_service.get_price_id", return_value=None), \
             patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"tenant_id": "tenant-1", "email": "user@test.com"}

            with pytest.raises(HTTPException) as exc:
                await create_checkout(CheckoutRequest(plan="enterprise"), credentials=auth_bearer)
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_checkout_requires_auth(self):
        from apps.api.routers.billing import create_checkout, CheckoutRequest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await create_checkout(CheckoutRequest(plan="pro"), credentials=None)
        assert exc.value.status_code == 401


class TestPortal:
    @pytest.mark.asyncio
    async def test_portal_creates_session(self, auth_bearer):
        from apps.api.routers.billing import create_portal

        with patch("apps.api.services.stripe_service.create_portal_session") as mock_portal, \
             patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_db", new_callable=AsyncMock) as mock_get_tenant:

            mock_verify.return_value = {"tenant_id": "tenant-1"}
            mock_get_tenant.return_value = {"stripe_customer_id": "cus_test"}
            mock_portal.return_value = {"url": "https://billing.stripe.com/test", "mock": True}

            result = await create_portal(credentials=auth_bearer)
            assert result["portal_url"] == "https://billing.stripe.com/test"
            assert result["mock"] is True


class TestWebhook:
    @pytest.mark.asyncio
    async def test_webhook_handles_checkout_completed(self):
        from apps.api.routers.billing import stripe_webhook

        payload = b'{"type":"checkout.session.completed","data":{"object":{"customer":"cus_test","subscription":"sub_test"}}}'

        with patch("apps.api.services.stripe_service.verify_webhook_signature") as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_by_stripe_customer_db", new_callable=AsyncMock) as mock_lookup, \
             patch("apps.api.services.db_tenants.update_tenant_subscription_db", new_callable=AsyncMock) as mock_update:

            mock_verify.return_value = json.loads(payload) if False else {
                "type": "checkout.session.completed",
                "data": {"object": {"customer": "cus_test", "subscription": "sub_test"}}
            }
            mock_lookup.return_value = {"id": "tenant-1"}

            result = await stripe_webhook(MagicMock(), stripe_signature="t=123,v1=abc")
            assert result["received"] is True
            assert result["event_type"] == "checkout.session.completed"
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_rejects_invalid_signature(self):
        from apps.api.routers.billing import stripe_webhook
        from fastapi import HTTPException

        with patch("apps.api.services.stripe_service.verify_webhook_signature", return_value=None):
            with pytest.raises(HTTPException) as exc:
                await stripe_webhook(MagicMock(), stripe_signature="invalid")
            assert exc.value.status_code == 400


class TestSubscription:
    @pytest.mark.asyncio
    async def test_subscription_returns_plan(self, auth_bearer):
        from apps.api.routers.billing import get_subscription

        with patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_db", new_callable=AsyncMock) as mock_get_tenant, \
             patch("apps.api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_get_plan:

            mock_verify.return_value = {"tenant_id": "tenant-1"}
            mock_get_tenant.return_value = {"stripe_subscription_id": "sub_test"}
            mock_get_plan.return_value = {"plan_name": "pro", "max_concurrent_calls": 10, "max_agents": 10}

            result = await get_subscription(credentials=auth_bearer)
            assert result["plan_name"] == "pro"
            assert result["active"] is True
            assert result["max_agents"] == 10


class TestUsage:
    @pytest.mark.asyncio
    async def test_usage_recorded(self, auth_bearer):
        from apps.api.routers.billing import report_usage, UsageRequest

        with patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.services.db_tenants.record_usage_db", new_callable=AsyncMock) as mock_record:

            mock_verify.return_value = {"tenant_id": "tenant-1"}

            result = await report_usage(UsageRequest(metric="agent_minutes", quantity=42.5), credentials=auth_bearer)
            assert result["recorded"] is True
            assert result["quantity"] == 42.5
            mock_record.assert_called_once()


class TestPlanEnforcement:
    @pytest.mark.asyncio
    async def test_agent_limit_exceeded(self):
        from apps.api.services.plan_enforcement import check_agent_limit

        with patch("apps.api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_plan, \
             patch("apps.api.services.db_tenants.count_active_agents_db", new_callable=AsyncMock) as mock_count:

            mock_plan.return_value = {"plan_name": "starter", "max_agents": 2}
            mock_count.return_value = 2

            ok, info = await check_agent_limit("tenant-1")
            assert ok is False
            assert info["limit"] == 2
            assert info["plan"] == "starter"

    @pytest.mark.asyncio
    async def test_agent_limit_ok(self):
        from apps.api.services.plan_enforcement import check_agent_limit

        with patch("apps.api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_plan, \
             patch("apps.api.services.db_tenants.count_active_agents_db", new_callable=AsyncMock) as mock_count:

            mock_plan.return_value = {"plan_name": "pro", "max_agents": 10}
            mock_count.return_value = 5

            ok, info = await check_agent_limit("tenant-1")
            assert ok is True
            assert info["current"] == 5

    @pytest.mark.asyncio
    async def test_call_limit_exceeded(self):
        from apps.api.services.plan_enforcement import check_call_limit

        with patch("apps.api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_plan, \
             patch("apps.api.services.db_tenants.count_active_calls_db", new_callable=AsyncMock) as mock_count:

            mock_plan.return_value = {"plan_name": "starter", "max_concurrent_calls": 2}
            mock_count.return_value = 2

            ok, info = await check_call_limit("tenant-1")
            assert ok is False
            assert info["resource"] == "concurrent_calls"
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/unit/test_billing.py -v -o "addopts=" 2>&1 | tail -30`
Expected: All 9 tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_billing.py
git commit -m "test: add billing endpoint + plan enforcement tests"
```

---

## Task 9: Add billing methods to API client

**Files:**
- Modify: `agent-ui/src/lib/api.ts`

- [ ] **Step 1: Append billing methods**

Add at the end of `ApiClient` class (before `export const api = new ApiClient();`):

```typescript
  // Billing
  async getSubscription() {
    return this.request('/api/v1/billing/subscription');
  }

  async createCheckout(plan: string) {
    return this.request('/api/v1/billing/checkout', {
      method: 'POST',
      body: { plan },
    });
  }

  async createPortal() {
    return this.request('/api/v1/billing/portal', { method: 'POST' });
  }

  async reportUsage(metric: string, quantity: number) {
    return this.request('/api/v1/billing/usage', {
      method: 'POST',
      body: { metric, quantity },
    });
  }
```

- [ ] **Step 2: Commit**

```bash
git add agent-ui/src/lib/api.ts
git commit -m "feat: add billing methods to API client"
```

---

## Task 10: Create BillingPage.tsx

**Files:**
- Create: `agent-ui/src/pages/BillingPage.tsx`

- [ ] **Step 1: Create the page**

Create `agent-ui/src/pages/BillingPage.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { api } from '../lib/api';

interface Subscription {
  plan_name: string;
  max_concurrent_calls: number;
  max_agents: number;
  active: boolean;
  stripe_customer_id?: string;
  stripe_subscription_id?: string;
  plan_ends_at?: string;
}

const PLANS = [
  { id: 'starter', name: 'Starter', price: 49, calls: 2, agents: 2, features: ['Basic scripts', 'CSV import', 'Email support'] },
  { id: 'pro', name: 'Pro', price: 149, calls: 10, agents: 10, features: ['Templates', 'A/B testing', 'Analytics', 'Priority support'] },
  { id: 'enterprise', name: 'Enterprise', price: 499, calls: 50, agents: 50, features: ['Custom scripts', 'API access', 'Dedicated support', 'SLA'] },
];

export default function BillingPage() {
  const [sub, setSub] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionPlan, setActionPlan] = useState<string | null>(null);

  useEffect(() => {
    api.getSubscription()
      .then(setSub)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleUpgrade = async (planId: string) => {
    setActionPlan(planId);
    setError('');
    try {
      const result: any = await api.createCheckout(planId);
      if (result.checkout_url) window.location.href = result.checkout_url;
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionPlan(null);
    }
  };

  const handlePortal = async () => {
    setError('');
    try {
      const result: any = await api.createPortal();
      if (result.portal_url) window.location.href = result.portal_url;
    } catch (err: any) {
      setError(err.message);
    }
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center text-white">Loading billing...</div>;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-6">
      <div className="max-w-5xl mx-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-white">Billing</h1>
          <p className="text-gray-400 mt-2">Manage your subscription and plan.</p>
        </header>

        {error && (
          <div className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300">{error}</div>
        )}

        {sub && (
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 p-6 mb-8">
            <div className="flex justify-between items-center">
              <div>
                <div className="text-sm text-gray-400">Current plan</div>
                <div className="text-2xl font-bold text-white capitalize">{sub.plan_name}</div>
                {sub.plan_ends_at && <div className="text-gray-500 text-sm mt-1">Renews {new Date(sub.plan_ends_at).toLocaleDateString()}</div>}
              </div>
              {sub.active && (
                <button onClick={handlePortal} className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg text-sm">
                  Manage in Stripe Portal
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4 mt-6">
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-sm text-gray-400">Concurrent calls</div>
                <div className="text-xl font-semibold text-white">{sub.max_concurrent_calls}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-sm text-gray-400">Max agents</div>
                <div className="text-xl font-semibold text-white">{sub.max_agents}</div>
              </div>
            </div>
          </div>
        )}

        <h2 className="text-xl font-semibold text-white mb-4">Available plans</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PLANS.map((p) => {
            const isCurrent = sub?.plan_name?.toLowerCase() === p.id;
            return (
              <div key={p.id} className={`bg-white/5 backdrop-blur-lg rounded-2xl border ${isCurrent ? 'border-purple-500' : 'border-white/10'} p-6`}>
                <h3 className="text-lg font-semibold text-white">{p.name}</h3>
                <div className="mt-2 mb-4">
                  <span className="text-3xl font-bold text-white">${p.price}</span>
                  <span className="text-gray-400 text-sm">/month</span>
                </div>
                <ul className="space-y-2 mb-6">
                  <li className="text-gray-300 text-sm">{p.calls} concurrent calls</li>
                  <li className="text-gray-300 text-sm">{p.agents} agents</li>
                  {p.features.map((f) => (
                    <li key={f} className="text-gray-400 text-sm flex items-center gap-2">
                      <span className="text-purple-400">✓</span> {f}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => handleUpgrade(p.id)}
                  disabled={isCurrent || actionPlan === p.id}
                  className={`w-full py-2 rounded-lg font-semibold text-sm ${isCurrent ? 'bg-purple-600/30 text-purple-200 cursor-not-allowed' : 'bg-purple-600 hover:bg-purple-700 text-white'} disabled:opacity-50`}
                >
                  {isCurrent ? 'Current plan' : (actionPlan === p.id ? 'Loading...' : `Upgrade to ${p.name}`)}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add agent-ui/src/pages/BillingPage.tsx
git commit -m "feat: add billing page with subscription status + plan cards"
```

---

## Task 11: Wire /billing route in App.tsx

**Files:**
- Modify: `agent-ui/src/App.tsx`

- [ ] **Step 1: Add import and route**

In `App.tsx`, add the import:

```tsx
import BillingPage from './pages/BillingPage';
```

In the `<Routes>` block, add a protected route:

```tsx
<Route path="/billing" element={<PrivateRoute><BillingPage /></PrivateRoute>} />
```

- [ ] **Step 2: Verify imports compile (manual smoke check)**

Open the file in your editor and ensure no syntax errors. The TypeScript compiler would flag any.

- [ ] **Step 3: Commit**

```bash
git add agent-ui/src/App.tsx
git commit -m "feat: wire /billing route"
```

---

## Task 12: Verify full stack

- [ ] **Step 1: Verify all Python compiles**

Run:
```bash
python -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ['apps/api/services/stripe_service.py','apps/api/services/plan_enforcement.py','apps/api/routers/billing.py','apps/api/services/db_tenants.py','apps/api/services/db_schema.py','apps/api/main.py']]; print('All OK')"
```
Expected: prints `All OK`

- [ ] **Step 2: Run all tests**

Run: `python -m pytest tests/unit/ tests/services/ -o "addopts=" -q`
Expected: All tests pass (existing + new billing tests)

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: Phase 2 complete — Stripe billing with checkout/portal/webhook + plan enforcement

- Stripe SDK wrapper (lazy, mock-mode for dev/test without credentials)
- Updated plan prices to match spec (\$49/\$149/\$499)
- Billing router: /checkout, /portal, /webhook, /subscription, /usage
- Plan enforcement helpers: check_agent_limit, check_call_limit
- Frontend: BillingPage with plan cards + Stripe portal redirect
- API client: getSubscription, createCheckout, createPortal, reportUsage
- /billing route wired in App.tsx
- 9 billing tests + plan enforcement tests passing"
```