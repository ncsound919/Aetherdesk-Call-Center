# AetherDesk 87% → 90%+ Readiness Plan

**Goal:** Raise production readiness from 87.0% to 90%+ by boosting Python coverage to ~50%, fixing 2 pre-existing WebSocket test failures, and closing auth test gaps.

**Current baseline:**
- Python tests: 363 pass, 2 fail (pre-existing WS mock assertion issues)
- Frontend tests: 85 pass
- Coverage: 37.86% (2,319 / 6,126 lines covered)
- Readiness score: 87.0%

**Target:**
- Python tests: 365 pass, 0 fail
- Coverage: ≥50% (≥3,063 lines covered)
- Readiness score: ≥90.0%

---

## Step 1: Fix 2 Pre-existing WebSocket Test Failures

**Files:** `apps/api/routers/agent.py`, `tests/unit/test_agent.py`

**Context:** The `ws_agent` function (line 150) has a reconnection loop (lines 169-176) that calls `websocket.accept()` and `hub.connect()` on a disconnected socket. This is dead code — a server cannot re-accept a disconnected WebSocket; only the client can reconnect with a fresh socket. The tests correctly assert single calls, but the code calls them twice.

**Tasks:**
- [ ] Remove the reconnection loop (lines 169-176) from `ws_agent` in `apps/api/routers/agent.py` — keep only `hub.disconnect()` and the logger
- [ ] Verify: `python -m pytest tests/unit/test_agent.py::TestWebSocket -v --tb=short 2>&1 | tail -10`
- [ ] Verify: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add apps/api/routers/agent.py && git commit -m "fix: remove dead reconnection loop in ws_agent (server cannot re-accept disconnected WS)"`

---

## Step 2: Add health.py Tests

**Files:** `tests/unit/test_health.py` (new), `apps/api/routers/health.py`

**Context:** `health.py` has 3 simple endpoints (health check, readiness, liveness) at 0% coverage. These are perfect for TestClient tests — no auth dependencies, no DB side effects.

**Tasks:**
- [ ] Read `apps/api/routers/health.py` to understand endpoints
- [ ] Create `tests/unit/test_health.py` with TestClient tests:
  - `GET /health` returns 200 with `{"status": "healthy"}`
  - `GET /api/v1/health` returns 200 with fonster + db status
  - `GET /api/v1/health/ready` returns 200
  - `GET /api/v1/health/live` returns 200
- [ ] Run: `python -m pytest tests/unit/test_health.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify full suite: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_health.py && git commit -m "test: add health endpoint TestClient tests"`

---

## Step 3: Add usage.py Tests

**Files:** `tests/unit/test_usage.py` (new), `apps/api/routers/usage.py`

**Context:** `usage.py` has ~21 lines with simple usage-tracking endpoints at 0% coverage. Small, quick wins.

**Tasks:**
- [ ] Read `apps/api/routers/usage.py` to understand endpoints
- [ ] Create `tests/unit/test_usage.py` with TestClient tests for usage routes
- [ ] Run: `python -m pytest tests/unit/test_usage.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_usage.py && git commit -m "test: add usage router tests"`

---

## Step 4: Add security.py Middleware Tests

**Files:** `tests/unit/test_security_middleware.py` (new), `apps/api/middleware/security.py`

**Context:** `security.py` is 14 lines of middleware at 0% coverage. Can be tested by instantiating directly.

**Tasks:**
- [ ] Read `apps/api/middleware/security.py` to understand the middleware
- [ ] Create `tests/unit/test_security_middleware.py` with direct instantiation tests
- [ ] Run: `python -m pytest tests/unit/test_security_middleware.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_security_middleware.py && git commit -m "test: add security middleware unit tests"`

---

## Step 5: Add webhooks_twilio.py Tests

**Files:** `tests/unit/test_webhooks_twilio.py` (new), `apps/api/routers/webhooks_twilio.py`

**Context:** `webhooks_twilio.py` is 64 lines at 0% coverage. Tests Twilio callback handling.

**Tasks:**
- [ ] Read `apps/api/routers/webhooks_twilio.py` to understand the endpoint
- [ ] Create `tests/unit/test_webhooks_twilio.py` with tests for the webhook handler
- [ ] Run: `python -m pytest tests/unit/test_webhooks_twilio.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_webhooks_twilio.py && git commit -m "test: add Twilio webhook handler tests"`

---

## Step 6: Add calls.py Tests

**Files:** `tests/unit/test_calls_router.py` (new), `apps/api/routers/calls.py`

**Context:** `calls.py` is 85 lines at 0% coverage. Call management routes. Uses `Depends()` so needs TestClient.

**Tasks:**
- [ ] Read `apps/api/routers/calls.py` to understand routes
- [ ] Create `tests/unit/test_calls_router.py` with TestClient tests
- [ ] Run: `python -m pytest tests/unit/test_calls_router.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_calls_router.py && git commit -m "test: add calls router tests"`

---

## Step 7: Boost agent.py Router to 100%

**Files:** `tests/unit/test_agent.py`, `apps/api/routers/agent.py`

**Context:** agent.py router is at 88% coverage (17 lines missed). The AgentCache class methods are partially tested. Also add tests for `update_agent_status`, `delete_agent`.

**Tasks:**
- [ ] Read existing `tests/unit/test_agent.py` to identify coverage gaps
- [ ] Add tests for: AgentCache.invalidate_prefix, AgentCache.cleanup, AgentCache edge cases
- [ ] Add tests for: `update_agent_status` route, `delete_agent` route
- [ ] Run: `python -m pytest tests/unit/test_agent.py -v --tb=short 2>&1 | tail -15`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_agent.py && git commit -m "test: boost agent.py router coverage to 100%"`

---

## Step 8: Boost billing.py to 100%

**Files:** `tests/unit/test_billing.py`, `apps/api/routers/billing.py`

**Context:** billing.py is at 88% coverage (11 lines missed). Close the remaining gaps.

**Tasks:**
- [ ] Read `tests/unit/test_billing.py` to see existing tests
- [ ] Read `apps/api/routers/billing.py` to identify uncovered lines
- [ ] Add tests covering the missing 11 lines
- [ ] Run: `python -m pytest tests/unit/test_billing.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_billing.py && git commit -m "test: boost billing.py coverage to 100%"`

---

## Step 9: Boost stripe_service.py to 85%

**Files:** `tests/unit/test_stripe_service.py`, `apps/api/services/stripe_service.py`

**Context:** stripe_service.py is at 56% coverage (24 missed lines). Missing lines are in `create_customer`, `report_usage`, webhook signature verification errors.

**Tasks:**
- [ ] Read `tests/unit/test_stripe_service.py` and `apps/api/services/stripe_service.py`
- [ ] Add tests for uncovered code paths (error handling, edge cases)
- [ ] Run: `python -m pytest tests/unit/test_stripe_service.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_stripe_service.py && git commit -m "test: boost stripe_service.py coverage to 85%"`

---

## Step 10: Boost rate_limit.py to 65%

**Files:** `tests/unit/test_rate_limiter.py`, `apps/api/services/rate_limit.py`

**Context:** rate_limit.py is at 33% coverage (79 missed lines). The `dispatch` method and Redis integration paths are uncovered.

**Tasks:**
- [ ] Read `tests/unit/test_rate_limiter.py` and `apps/api/services/rate_limit.py`
- [ ] Add tests for: `dispatch()` with in-memory fallback, rate limit exceeded, Redis connection failure
- [ ] Run: `python -m pytest tests/unit/test_rate_limiter.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_rate_limiter.py && git commit -m "test: boost rate_limit.py coverage to 65%"`

---

## Step 11: Boost auth.py Service to 65%

**Files:** `tests/unit/test_auth_service.py`, `apps/api/services/auth.py`

**Context:** auth.py service is at 37% coverage (101 missed lines). The `__init__` module setup, `get_tenant_db` generator, tenant resolution functions are uncovered.

**Tasks:**
- [ ] Read `tests/unit/test_auth_service.py` and `apps/api/services/auth.py`
- [ ] Add tests for: `get_tenant_db` context manager, `resolve_tenant` with various inputs, API key validation edge cases
- [ ] Run: `python -m pytest tests/unit/test_auth_service.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_auth_service.py && git commit -m "test: boost auth.py service coverage to 65%"`

---

## Step 12: Boost db_pool.py to 100%

**Files:** `tests/unit/test_db_pool.py`, `apps/api/services/db_pool.py`

**Context:** db_pool.py is at 87% coverage (12 missed lines). Close the gap.

**Tasks:**
- [ ] Read `tests/unit/test_db_pool.py` and `apps/api/services/db_pool.py`
- [ ] Add tests covering remaining 12 missed lines
- [ ] Run: `python -m pytest tests/unit/test_db_pool.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_db_pool.py && git commit -m "test: boost db_pool.py coverage to 100%"`

---

## Step 13: Boost Small Near-100 Modules

**Files:** Multiple test files

**Context:** Several modules are near 100% but not quite: saas.py (97%, 2 lines), protocols.py (98%, 1 line), plan_enforcement.py (82%, 5 lines), queue.py (90%, 12 lines), sanitizer.py (93%, 5 lines), transcript_store.py (80%, 7 lines), db_config.py (91%, 1 line), loader.py (67%, 5 lines).

**Tasks:**
- [ ] For each module, identify the uncovered lines and add targeted tests
- [ ] Run full suite: `python -m pytest tests/unit/ -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add -A && git commit -m "test: boost coverage for 8 near-100 modules to 100%"`

---

## Step 14: Add voice.py Tests

**Files:** `tests/unit/test_voice_router.py` (new), `apps/api/routers/voice.py`

**Context:** voice.py is at 19% coverage (130 missed lines). Voice routing is a core feature. Adding TestClient tests for basic call flow will boost coverage significantly.

**Tasks:**
- [ ] Read `apps/api/routers/voice.py` to understand routes
- [ ] Create `tests/unit/test_voice_router.py` with TestClient tests for:
  - Voice connect/disconnect endpoints
  - Call status webhook
  - Voice configuration endpoints
- [ ] Run: `python -m pytest tests/unit/test_voice_router.py -v --tb=short 2>&1 | tail -10`
- [ ] Verify no regression: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5`
- [ ] Commit: `git add tests/unit/test_voice_router.py && git commit -m "test: add voice router tests"`

---

## Step 15: Final Verification & Gate Update

**Files:** `pyproject.toml`, `.github/workflows/ci-cd.yml`

**Context:** After all steps, re-evaluate coverage and update the gate.

**Tasks:**
- [ ] Run full suite with coverage: `python -m pytest tests/unit/ -q --cov=apps.api --cov-report=term-missing 2>&1 | Select-String "^TOTAL"`
- [ ] If coverage ≥50%, update `pyproject.toml` fail_under to 50 and `.github/workflows/ci-cd.yml` --cov-fail-under to 50
- [ ] Run: `python -m pytest tests/unit/ -q --cov-fail-under=50 2>&1 | Select-String -Pattern "coverage|FAIL" | Select-Object -Last 3`
- [ ] Run frontend: `npx jest --config jest.config.js 2>&1 | Select-Object -Last 5`
- [ ] Commit: `git add pyproject.toml .github/workflows/ci-cd.yml && git commit -m "chore: set coverage gate to 50% (reached after targeted testing)"`

---

## Rollback

If any step causes test failures or coverage regression:
1. `git checkout -- <file>` to revert changes
2. If committed: `git revert <commit-hash>`
3. Report the failure and skip to next step
