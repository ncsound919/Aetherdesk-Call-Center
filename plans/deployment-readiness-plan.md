# Aetherdesk Call Center — Deployment Readiness Implementation Plan

**Generated:** June 21, 2026  
**Last Updated:** June 21, 2026  
**Current Readiness:** ~55% (many Phase 0/1 issues already fixed in `b7da3dc`)  
**Target:** 95% (Production Launch)  
**Estimated Timeline:** 5–7 weeks

---

## Phase 0: Critical Blocker Verification (Week 1) → 55% → 60%

These were already fixed in the deep audit commit. Verify they hold:

| # | Task | Status | Files |
|---|------|--------|-------|
| 0.1 | ~Rotate exposed API keys~ | ✅ .env uses placeholders; K8s uses SealedSecrets | `.env`, `kubernetes/deployment.yml` |
| 0.2 | ~Remove hardcoded DB credentials~ | ✅ `db_config.py` raises RuntimeError in prod, falls back to SQLite in dev | `apps/api/services/db_config.py` |
| 0.3 | ~Fix CORS wildcard~ | ✅ Uses `CORS_ORIGIN` env, restricted methods/headers | `apps/api/main.py:374-380` |
| 0.4 | ~Fix voice clone Chatterbox call~ | ✅ Uses `aiohttp.FormData()` | `apps/api/routers/voice_cloning.py` |
| 0.5 | ~Add rate limiting to auth~ | ✅ `/auth/` paths limited to 10/min (configurable) | `apps/api/services/rate_limit.py:52-54` |
| 0.6 | **Generate SealedSecrets** — 🔴 still placeholders | ❌ `PASTE_ENCRYPTED_VALUE_HERE` | `kubernetes/deployment.yml:99-109` |
| 0.7 | ~Generate fresh JWT/encryption keys~ | ✅ Validated at startup with RuntimeError | `apps/api/main.py:140-147` |
| 0.8 | ~Fix WebSocket token store~ | ✅ Redis-backed with TTL, in-memory fallback | `apps/api/services/auth.py:21-57` |
| 0.9 | **Close http_pool on shutdown** | ❌ `http_pool.close()` missing from lifespan | `apps/api/main.py:296-309` |

**Re-verify:** App starts in prod mode without fallback warnings; auth rate limit responds 429; CORS blocks non-origin; SealedSecrets needed.

---

## Phase 1: Security Hardening (Week 1–2) → 60% → 72%

| # | Task | Status | Files | Effort |
|---|------|--------|-------|--------|
| 1.1 | Webhook signature verification (Fonoster incoming) | ❌ Missing | `apps/api/routers/voice.py` | 2h |
| 1.2 | ~Schema init uses `split(";")`~ | ✅ Fixed — uses `conn.execute()` directly | `apps/api/services/db_schema.py:676` |
| 1.3 | ~SSRF protection~ | ✅ Comprehensive — IPv6, metadata endpoints, DNS rebinding | `apps/api/services/actions.py:50-146` |
| 1.4 | Upgrade JWT to RS256/ES256 | ❌ Still HS256 | `apps/api/services/auth.py:93` | 3h |
| 1.5 | ~PII redaction recursion~ | ✅ Handles nested dicts and lists | `apps/api/middleware/audit.py:49-63` |
| 1.6 | FreeSWITCH seccomp/AppArmor | ❌ hostNetwork still without profiles | `kubernetes/deployment.yml` | 2h |
| 1.7 | Set up Alembic migrations | ❌ No migration tooling | `apps/api/` | 3h |

---

## Phase 2: Testing & CI/CD (Week 2–3) → 72% → 80%

| # | Task | Effort |
|---|------|--------|
| 2.1 | Expand CI test execution — all non-ML tests, 70% coverage gate | 2h |
| 2.2 | Add Playwright E2E to CI — headless Chromium, smoke test core flows | 4h |
| 2.3 | Add ruff-format check to CI | 30m |
| 2.4 | Add staging namespace deploy on develop branch | 3h |
| 2.5 | Add rollback capability (store prev image tags) | 2h |
| 2.6 | Fix Playwright webServer command (points to Python API not npm) | 30m |
| 2.7 | Add bandit + gitleaks to CI security stage | 1h |

---

## Phase 3: Stability & Resource Mgmt (Week 3–4) → 80% → 85%

| # | Task | Status | Effort |
|---|------|--------|--------|
| 3.1 | ~Session removal~ | ✅ Implemented | `call_session.py:138-140` |
| 3.2 | Redis disconnect handling in WebSocket | ⚠️ Basic try/except; could be more graceful | `voice.py:242-249` | 1h |
| 3.3 | ~Close HTTP pool on shutdown~ | ❌ Missing (0.9) | `main.py` | 30m |
| 3.4 | ~TTS failover raises exception~ | ✅ Raises RuntimeError | `tts.py:50` |
| 3.5 | Fix dual-write inconsistency (Redis vs in-memory) | ❌ Still open | `queue.py` | 4h |
| 3.6 | Agent WebSocket reconnection state loss | ❌ Still open | `agent.py` | 2h |
| 3.7 | Campaign race condition | ⚠️ Needs verification | `call_session.py` | 2h |
| 3.8 | DB connection pool size/timeout config | ⚠️ Needs explicit config | `db_pool.py` | 1h |
| 3.9 | Clean up duplicate config dirs (`config/fonster/` vs `config/fonoster/`) | ❌ Both exist | `config/` | 30m |

---

## Phase 4: Load Testing & Observability (Week 4–5) → 85% → 90%

| # | Task | Effort |
|---|------|--------|
| 4.1 | Run load tests at 50/100/500 concurrent calls | 1 week |
| 4.2 | Tune K8s resource limits based on load results | 2d |
| 4.3 | Fix API Dockerfile port mismatch (3000 vs 8000) | 30m |
| 4.4 | Fix sentry_sdk double init (main.py + observability.py) | 30m |
| 4.5 | Set up Prometheus alerting rules | 3h |
| 4.6 | Document incident response runbooks | 4h |

---

## Phase 5: Code Quality (Week 5–6) → 90% → 94%

| # | Task | Effort |
|---|------|--------|
| 5.1 | Eliminate global mutable state (queue.py, realtime.py, agent.py) | 1 week |
| 5.2 | Standardize error response schema | 3d |
| 5.3 | Add full type hints coverage | 3d |
| 5.4 | Split monolithic deployment.yml into per-component files | 2h |
| 5.5 | Fix .gitignore gaps | 15m |
| 5.6 | Add CHANGELOG.md | 1h |

---

## Phase 6: Production Hardening (Week 6–7) → 94% → 97%+

| # | Task | Effort |
|---|------|--------|
| 6.1 | Penetration test | 1 week |
| 6.2 | Disaster recovery test (zone failure, DB corruption) | 1 week |
| 6.3 | Harden FreeSWITCH hostNetwork (CNI or seccomp/AppArmor) | 3d |
| 6.4 | GDPR data export/deletion API endpoints | 3d |
| 6.5 | Performance baseline (P50/P95/P99 latency metrics) | 2d |
| 6.6 | Final readiness sign-off checklist | 1d |

---

## Starting Now

Currently executing **Phase 0 items 0.6, 0.9** then moving to Phase 1.
