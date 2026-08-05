# AetherDesk — Deployment Readiness Assessment

**Date:** 2026-08-05
**Assessment type:** Codebase + CI/CD verification (self-assessed against the existing Enterprise Readiness Benchmark, with fresh verification of the code, tests, builds, and pipeline).

---

## Readiness Score: **72% — "Almost Deployable"**

The product is feature-complete and the code builds and runs locally, but **not yet production-ready end-to-end** because the CI/CD pipeline is inconsistent with the actual code layout, the full test suite fails its own coverage gate, and no real infrastructure has been stood up.

### What the existing benchmark says vs. what is real

| Source | Score | Notes |
|--------|-------|-------|
| `ENTERPRISE_READINESS_BENCHMARK.md` (self-assessed) | 31/40 = **77.5%** | Aspirational; self-assessed, not independently validated |
| **This assessment (fresh verification)** | **~72%** | Penalized for verified pipeline/test/build blockers |

The 77.5% self-assessment is **plausible as a feature-maturity score but overstated as a deployment-readiness score.** The difference (≈5-8 pts) is the gap between "we built the features" and "a production system is actually running."

---

## What I verified (not just read)

| Check | Result |
|-------|--------|
| Backend app imports | ⚠️ Imports but requires `JWT_SECRET` + `INTERNAL_API_KEY` in env (config guard — expected, not a bug) |
| Frontend production build (`npm run build`) | ✅ Builds successfully (12s, chunk-size warning only) |
| Backend lint (`ruff check src/`) | ⚠️ Has import-organization warnings (not failures) |
| Full backend test suite (`pytest tests/`) | ❌ **Fails**: coverage 26% vs 65% gate; **1 collection error** in `tests/unit/test_llm_client.py` when run in aggregate |
| `tests/unit/test_llm_client.py` alone | ✅ 9 tests pass in isolation |
| CI/CD workflow (`apps/api/` paths) | ❌ **Broken**: workflow references `apps/api/Dockerfile`, `apps/api/main.py`, `bandit -r apps/` — but the code lives in `src/api/` and the Dockerfile uses `src.api.main`. The build/deploy jobs would fail. |
| docker-compose (production services) | ✅ Uses `Dockerfile.optimized` with project-root context (consistent with `src/` layout) |
| K8s manifests, deploy.sh, GKE workflow | ✅ Present (staging + production namespaces, rollout waits) |
| `.env` present locally with required keys | ✅ Present (not committed — verified `.env` is gitignored) |

---

## Readiness by category

### ✅ Strong (deployable-ish)
- **Feature completeness** — multi-tenant call center, AI agents, voice (Twilio + FreeSWITCH), SMS, live chat, billing (Stripe), analytics (ClickHouse/Metabase/PostHog), monitoring (Prometheus/Grafana/Sentry/Langfuse)
- **Local run** — `make setup` + `make dev` work; frontend builds; backend serves with env configured
- **Security controls implemented** — encryption at rest/in transit, JWT + RBAC, audit logging, MFA, secrets scanning, Helmet/CORS/rate-limit hardening on the Node server
- **Deployment assets exist** — Dockerfiles, docker-compose, K8s manifests, GKE CI/CD, deploy.sh, Procfile

### ⚠️ Blocking for production
1. **CI/CD path mismatch** — `.github/workflows/ci-cd.yml` references `apps/api/*` but code is in `src/api/*`. The `build`, `test`, `bandit`, and image-push steps would fail. **This must be fixed before any automated deploy.**
2. **Test gate fails** — full suite is 26% coverage (gate is 65%) and has 1 collection error in aggregate. Either fix the collection error + raise coverage, or lower/remove the gate for initial launch (not recommended).
3. **Coverage gap** — many service modules are untested (ticketing, training, voice_biometrics, webhook_engine, vendor_health at 0-30%).

### 🟡 For a confident launch
- Formal SOC 2 / HIPAA certification (controls exist; no audit)
- Third-party penetration test (only scripted scans today)
- Real load-test results (k6 scripts exist but no recorded baseline)
- Actual uptime/SLA history (code tracks it, nothing has run in prod)
- Real telephony verification (Twilio numbers, FreeSWITCH in production, not local)

---

## Steps to Deployment

### Step 0 — Fix the pipeline (required, ~0.5 day)
Edit `.github/workflows/ci-cd.yml` so all `apps/...` paths point at the real layout:
- `apps/api/Dockerfile` → the repo's root `Dockerfile` (or `src/`-based path)
- `bandit -r apps/` → `bandit -r src/`
- Verify `docker/build-push-action` contexts and the two images (`api`, `agent-ui`) match what the K8s deployments expect.
- **Test the workflow** by pushing to a `develop` branch and confirming lint→test→build→deploy-staging runs green.

### Step 1 — Get the test suite green (required, ~1-2 days)
- Fix the `tests/unit/test_llm_client.py` collection error in aggregate (likely a module/fixture name collision).
- Either add meaningful tests to raise coverage toward 65%, or set `--cov-fail-under` to a realistic floor (e.g., 50%) for launch, then raise it after.

### Step 2 — Choose a deployment target
| Option | Effort | Best for |
|--------|--------|----------|
| **A. Docker Compose (VPS)** | Low | Fastest path: single server, `make prod`, reverse-proxy + TLS. Good for a real launch. |
| **B. GKE (existing CI/CD)** | High | Full enterprise scaling once the workflow path bug is fixed and a GCP project + SA key exist. |
| **C. Render / Railway / Fly** | Low | The repo has a Procfile (`api` + `ui`); Render/Railway can run it with a Postgres + Redis add-on. |
| **D. Vercel (agent-ui only)** | Low | Frontend-only; the `DEPLOYMENT.md` Supabase path applies if you want Supabase-backed auth/db instead of the FastAPI backend. |

> **Recommendation for a real, near-term launch: Option A (Docker Compose on a VPS) or Option C (Render/Railway).** GKE is overkill until you have real traffic.

### Step 3 — Provision infrastructure & secrets
- A Postgres instance + Redis (Docker Compose includes both; Render/Railway offer managed ones).
- Create the DB schema (`make db-init` / Alembic migrations).
- Set all required env vars in the platform (not just `.env`): `TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER`, `ENCRYPTION_KEY`, `JWT_SECRET`, `INTERNAL_API_KEY`, `STRIPE_*`, `DEEPGRAM_API_KEY`, `GROQ_API_KEY` (or DeepSeek fallback), `SENTRY_DSN`, etc.

### Step 4 — Stand up telephony (the highest-risk external dependency)
- Provision a **Twilio** number and verify inbound/outbound calls + webhooks work from the deployed host (not localhost).
- Or stand up **FreeSWITCH/Fonoster** if self-hosting SIP.
- Verify audio (STT/TTS) round-trips on a real call.

### Step 5 — Smoke-test the full flow against the deployed instance
- Register a tenant, create an AI agent, run a scripted call, confirm call recording + analytics land in ClickHouse.
- Verify billing (Stripe checkout + webhook) and real-time dashboard updates.

### Step 6 — Go-live checks
- TLS/HTTPS enforced; CORS whitelist set to your real domain.
- `.env` never committed; secrets only in the platform secret store.
- A backup/restore test of Postgres.
- Set up uptime monitoring (UptimeRobot / Grafana) + alerts.

### Step 7 — Post-launch hardening (the remaining benchmark gaps)
- Record real load-test results (k6) and an uptime history.
- Schedule a third-party pen test and accessibility audit.
- Decide on SOC 2 / HIPAA roadmap if enterprise customers require it.

---

## Bottom line

**Feature-ready (~72% deployment readiness).** The fastest path to a real, running deployment:
1. Fix the CI/CD `apps/` → `src/` path bug.
2. Fix the test collection error + set a realistic coverage floor.
3. Deploy via Docker Compose on a VPS (or Render/Railway) with a real Twilio number.
4. Smoke-test one real call end-to-end.

The remaining ~28% is **certification, real-traffic validation, and hardening** — not feature work. Nothing is blocking you from a functional launch today except the pipeline path bug and the test gate.
