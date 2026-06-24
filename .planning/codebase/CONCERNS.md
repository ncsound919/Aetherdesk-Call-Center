# Codebase Concerns

**Analysis Date:** 2026-06-23

## 1. Frontend Architecture Conflict (CRITICAL)

**Duplicate App Entry Points — Two Complete Apps Coexist:**

| File | Lines | Routes | Used? |
|------|-------|--------|-------|
| `agent-ui/src/main.jsx` → `agent-ui/src/App.jsx` | 49 | `/` Dashboard, `/agents`, `/calls`, `/settings`, `/voice-cloning`, `/login` | **YES** (index.html loads `main.jsx`) |
| `agent-ui/src/main.tsx` → `agent-ui/src/App.tsx` | 48 | `/` LandingPage, `/login` mock, `/dashboard` SaaSDashboard | **NO** (dead code) |

- Issue: `agent-ui/index.html` line 11 loads `<script type="module" src="/src/main.jsx">`. The TSX variant is completely dead.
- Files: `agent-ui/src/main.tsx`, `agent-ui/src/App.tsx`

**Duplicate Vite Configs:**
- `agent-ui/vite.config.js` — port 3001 (ACTIVE, used by `main.jsx`)
- `agent-ui/vite.config.ts` — port 5173 (DEAD, never loaded)
- Different ports and proxy targets (`127.0.0.1:8000` vs `localhost:8000`)

**Duplicate API Clients:**
- `agent-ui/src/services/api.js` (74 lines, Axios) — used by JSX app (`Dashboard.jsx`, `AgentManagement.jsx`, etc.)
- `agent-ui/src/lib/api.ts` (376 lines, Fetch-based `ApiClient` class) — used by TSX pages (`BillingPage.tsx`, `SignupPage.tsx`, `LeadsPage.tsx`, etc.)
- Token key mismatch: `api.js` reads `localStorage.getItem('token')`, `api.ts` reads `localStorage.getItem('access_token')`
- Default base URL mismatch: `api.js` defaults to `http://localhost:3000`, `api.ts` defaults to `http://localhost:8000`

**Duplicate Dashboard Components:**
- `agent-ui/src/components/Dashboard.tsx` (24 lines) — imports `AuthContext` from `../App` which does NOT export it. **THIS FILE IS BROKEN AND WILL CRASH AT RUNTIME.**
- `agent-ui/src/pages/Dashboard.jsx` (161 lines) — the actual working dashboard

**Broken Import in Dashboard.tsx:**
- File: `agent-ui/src/components/Dashboard.tsx:2`
- Code: `import { AuthContext } from '../App';`
- Problem: `App.tsx` does not export `AuthContext`. This component will throw `SyntaxError: The requested module does not provide an export named 'AuthContext'`.

**Unreachable Pages (10 pages with no route in either App):**

| Page | File | Status |
|------|------|--------|
| BillingPage | `agent-ui/src/pages/BillingPage.tsx` | No route in App.jsx or App.tsx |
| ForgotPasswordPage | `agent-ui/src/pages/ForgotPasswordPage.tsx` | No route |
| ResetPasswordPage | `agent-ui/src/pages/ResetPasswordPage.tsx` | No route |
| VerifyEmailPage | `agent-ui/src/pages/VerifyEmailPage.tsx` | No route |
| SignupPage | `agent-ui/src/pages/SignupPage.tsx` | No route |
| LeadsPage | `agent-ui/src/pages/LeadsPage.tsx` | No route |
| ScriptsPage | `agent-ui/src/pages/ScriptsPage.tsx` | No route |
| ScriptEditorPage | `agent-ui/src/pages/ScriptEditorPage.tsx` | No route |
| LeadImportPage | `agent-ui/src/pages/LeadImportPage.tsx` | No route |
| VoiceCloning | `agent-ui/src/pages/VoiceCloning.jsx` | Has route but uses JSX API client, not TSX |

**Unreachable Components:**
- `agent-ui/src/components/LandingPage.tsx` — only imported by dead `App.tsx`
- `agent-ui/src/components/SaaSDashboard.tsx` — only imported by dead `App.tsx`
- `agent-ui/src/components/CallDetail.tsx` — only imported by dead `SaaSDashboard.tsx`
- `agent-ui/src/components/Inbox.tsx` — not imported by any routed component
- `agent-ui/src/components/OnboardingWizard.tsx` — not imported by any routed component
- `agent-ui/src/components/onboarding/Step*.tsx` (5 files) — only used by OnboardingWizard
- `agent-ui/src/components/Dashboard.tsx` — broken, imports non-existent export

**Missing Dependency: `framer-motion`:**
- File: `agent-ui/src/components/LandingPage.tsx:2` — `import { motion } from 'framer-motion';`
- Problem: `framer-motion` is NOT listed in `agent-ui/package.json`. Build will fail if this file is ever imported.

---

## 2. Frontend Test Coverage Gaps (HIGH)

**Current test files (4 files, ~16 test cases):**
- `tests/unit/frontend/components/ConfirmationModal.test.js` — 5 tests
- `tests/unit/frontend/components/ErrorModal.test.js` — 4 tests
- `tests/unit/frontend/components/ToastNotification.test.js` — 6 tests
- `tests/unit/frontend/components/ui_components.test.js` — 1 test

**Untested frontend source files (44 total, 40 untested = 91% untested):**

| Category | Files | Tested? |
|----------|-------|---------|
| Pages (13) | `Dashboard.jsx`, `Login.jsx`, `Settings.jsx`, `AgentManagement.jsx`, `CallLogs.jsx`, `VoiceCloning.jsx`, `BillingPage.tsx`, `SignupPage.tsx`, `ForgotPasswordPage.tsx`, `ResetPasswordPage.tsx`, `VerifyEmailPage.tsx`, `LeadsPage.tsx`, `ScriptsPage.tsx`, `ScriptEditorPage.tsx`, `LeadImportPage.tsx` | **NONE** |
| Components (16) | `StatCard.jsx`, `AgentStatusChart.jsx`, `CallVolumeChart.jsx`, `RecentCalls.jsx`, `Sidebar.jsx`, `DeleteButton.jsx`, `ErrorDisplay.jsx`, `LandingPage.tsx`, `SaaSDashboard.tsx`, `CallDetail.tsx`, `Inbox.tsx`, `OnboardingWizard.tsx`, `Dashboard.tsx`, plus 5 onboarding steps | **NONE** |
| Context (2) | `AuthContext.jsx`, `SocketContext.jsx` | **NONE** |
| API Clients (2) | `services/api.js`, `lib/api.ts` | **NONE** |
| Entry Points (2) | `main.jsx`, `main.tsx` | **NONE** |

**Critical untested paths:**
- **Auth flow**: Login → token storage → protected routes → logout (zero tests)
- **API client**: Both `api.js` (Axios) and `api.ts` (Fetch) — no unit tests for request/response handling, error interception, token refresh
- **Routing**: No tests verify which pages are reachable from which routes
- **Real-time**: SocketContext WebSocket connection management (zero tests)

---

## 3. main.py Monolith (HIGH)

**File:** `apps/api/main.py` — 1,205 lines

**22 routes defined directly in main.py** (in addition to 14 included routers):

| Route Group | Lines | Routes | Overlaps With Router? |
|-------------|-------|--------|-----------------------|
| Health Check | 614-651 | `GET /api/v1/health`, `GET /health` | No |
| Tenant Management | 657-723 | `POST /api/v1/tenants`, `GET /api/v1/tenants/{id}` | Partial (auth.py) |
| Agent Management | 749-938 | `POST/GET/PUT/DELETE /api/v1/tenants/{id}/agents/*`, `PATCH /api/v1/agents/{id}/status` | YES — overlaps with `routers/agent.py` |
| Call Management | 944-1131 | `POST /api/v1/calls`, `POST /api/v1/calls/{id}/action`, `GET /api/v1/calls/{id}`, `GET /api/v1/calls` | YES — overlaps with `routers/engine.py` |
| Fonster Webhook | 1137-1195 | `POST /api/v1/webhooks/fonster` | YES — overlaps with `routers/webhooks_twilio.py` |
| Usage Analytics | 1200-1246 | `GET /api/v1/usage` | Partial |
| Billing | 1252-1281 | `GET /api/v1/billing` | YES — overlaps with `routers/billing.py` |
| WebSockets | 1287-1354 | `WS /ws/calls/{id}`, `WS /ws/agent/{id}` | YES — overlaps with `routers/realtime.py` |
| Health Probes | 1371-1387 | `GET /api/v1/health/ready`, `GET /api/v1/health/live`, `GET /metrics` | No |

**Pydantic models in main.py** (lines 452-586) instead of `apps/api/models/dto.py`:
- `TenantCreate`, `TenantResponse`, `AgentCreate`, `AgentResponse`, `AgentStatusUpdate`, `CallCreate`, `CallAction`, `CallResponse`, `UsageResponse`, `HealthCheck`, `WebhookConfig`

**What needs to be done:**
- Extract all route handlers from main.py into appropriate router files
- Move Pydantic models to `apps/api/models/dto.py`
- Resolve route overlaps (main.py routes vs router files)
- main.py should ONLY contain: app setup, middleware, lifespan, CORS config

---

## 4. Database/Alembic Issues (MEDIUM)

**Duplicate Schema Definitions:**
- `apps/api/services/db_schema.py` (870 lines) contains BOTH:
  - PostgreSQL schema as raw SQL (`SCHEMA_SQL`, lines 9-536)
  - SQLite schema as raw SQL (`SQLITE_SCHEMA_SQL`, lines 541-819)
- This DUPLICATES the Alembic migration in `alembic/versions/33be689273d2_initial_schema.py` (689 lines)
- The raw SQL fallback in `db_schema.py` will drift from Alembic migrations over time

**PostgreSQL Schema SQL Order Issue:**
- File: `apps/api/services/db_schema.py:42`
- `users` table references `tenants(id)` via FK, but `tenants` table isn't created until line 54
- This will cause a PostgreSQL error on first run if `init_pg_schema()` executes raw SQL

**SQLite Schema Duplicate Table:**
- File: `apps/api/services/db_schema.py`
- `script_templates` CREATE TABLE appears twice: lines 584-590 AND lines 674-680
- Second definition uses `CREATE TABLE IF NOT EXISTS` so no runtime error, but indicates copy-paste debt

**Config Directory Typo:**
- `config/fonoster/config.json` (correct spelling)
- `config/fonster/config.json` (typo — missing 'o')
- Both directories exist, unclear which is actually used

---

## 5. CI/CD Gaps (HIGH)

**File:** `.github/workflows/ci-cd.yml`

| Check | Present? | Details |
|-------|----------|---------|
| Python linting (Ruff) | YES | Lines 23-38 |
| Python tests (pytest) | YES | Lines 66-110 |
| Security scan (Bandit) | YES | Lines 108-110 |
| Dependency scan (safety) | YES | Lines 43-61 |
| HTTP load test | YES | Lines 115-153 |
| Docker build | YES | Lines 158-192 |
| Deploy to GKE | YES | Lines 197-271 |
| **Frontend linting (ESLint)** | **NO** | Not configured |
| **Frontend tests (vitest/jest)** | **NO** | Not configured |
| **Frontend build check** | **NO** | No `npm run build` step |
| **TypeScript type check** | **NO** | No `tsc --noEmit` step |
| **Frontend format check (Prettier)** | **NO** | Not configured |

**Impact:** A PR could merge that breaks the frontend build, introduces TypeScript errors, or has lint violations — CI would pass green.

---

## 6. Code Quality Issues

**logger Used Before Definition:**
- File: `apps/api/main.py:162`
- Code: `logger.warning("database_url_not_set_using_sqlite")`
- `logger` is defined at line 209 (`logger = logging.getLogger(__name__)`)
- This will raise `NameError: name 'logger' is not defined` if `DATABASE_URL` is not set

**print() in Production Code:**
- `apps/api/services/db_config.py:11` — `print("DATABASE_URL not set. Running with SQLite fallback.")`
  - Should use `logging.warning()` instead
- `apps/api/mock_voice_client.py:56-58` — 3 print statements (acceptable for mock/demo client)

**console.error/warn in Frontend (20 instances):**
- Most are `console.error` in catch blocks across 7 files
- Acceptable for error reporting but should use a structured logging solution for production
- Files: `SocketContext.jsx`, `SaaSDashboard.tsx`, `AgentManagement.jsx`, `Dashboard.jsx`, `CallLogs.jsx`, `Inbox.tsx`, `CallDetail.tsx`

**TODO in Production Code:**
- `agent-ui/src/pages/Settings.jsx:20` — `// TODO: Update tenant settings via API`
- Settings form submits but does nothing (empty handler)

---

## 7. Repository Hygiene (MEDIUM)

**Files/Directories That Should Not Be Committed:**

| File/Dir | Issue | Risk |
|----------|-------|------|
| `.env` | Environment config with secrets | **SECURITY** — may contain JWT_SECRET, ENCRYPTION_KEY |
| `aetherdesk.db` | SQLite database file | Bloated repo, may contain test data |
| `coverage/`, `htmlcov/` | Generated coverage reports | Repo bloat |
| `agent-ui/dist/` | Built frontend assets | Repo bloat, merge conflicts |
| `logs/app.log`, `server.log`, `agentops.log` | Log files | May contain PHI/PII |
| `*.pyc`, `__pycache__/` | Python bytecode | Already in `.gitignore` but present |
| `bandit_results.json` | Generated scan output | Repo bloat |
| `security_validation_results.json` | Generated scan output | Repo bloat |
| `debug_screenshot.png` | Debug artifact | Repo bloat |

**50+ Debug/Dev Scripts in Project Root:**
- Files like `debug_api.py`, `debug_inline.py`, `check.py`, `check_server.py`, `run.py`, `quick_start.py`, `fresh_start.py`, `launch.py`, `verify.py`, etc.
- Most are duplicates of scripts already in `dev-tools/`
- Should be gitignored or removed from root

**`dev-tools/` Directory Contains 50+ Scripts:**
- Many overlap with root-level scripts
- Multiple scripts do the same thing with slight variations (e.g., `start_api.py`, `start_all.py`, `quick_start.py`, `simple_start.py`)

---

## 8. Security Considerations (HIGH)

**Dev Mode Credentials in Production Code:**
- File: `apps/api/routers/auth.py:19-30`
- Hardcoded dev users: `admin@aetherdesk.com` / `admin123`, `agent@aetherdesk.com` / `agent123`
- These are only active when `APP_ENV=development`, but no runtime check exists in the router itself — relies on caller context

**localStorage Auth Token Handling:**
- `api.js` stores token as `localStorage.getItem('token')`
- `api.ts` stores token as `localStorage.getItem('access_token')`
- Two different token keys means one auth system won't work with the other

**WebSocket Authentication:**
- File: `agent-ui/src/components/Inbox.tsx` — connects to WebSocket without auth token validation
- File: `agent-ui/src/components/CallDetail.tsx` — same issue

---

## 9. Missing Critical Features (MEDIUM)

**No Onboarding Flow Connected:**
- `OnboardingWizard.tsx` + 5 step components exist but no route leads to them
- No UI trigger after signup to start onboarding

**No Password Change API:**
- `Settings.jsx:216-227` renders a password change form with no backend implementation
- No `api.changePassword()` method exists in either API client

**No Email Verification Flow:**
- `SignupPage.tsx` navigates to `/verify-email` but no route exists for `VerifyEmailPage.tsx`
- `ForgotPasswordPage.tsx` and `ResetPasswordPage.tsx` also have no routes

**Settings Form is Non-Functional:**
- `Settings.jsx:18-21` — `handleSubmit` is empty (TODO comment)
- Form appears to save but nothing happens

---

## 10. Performance & Scaling Concerns (LOW)

**main.py Pydantic Model Re-creation:**
- Pydantic models are defined at module level in main.py — re-evaluated on import
- Not a bottleneck but adds to cold start time

**Dual Schema Execution on Startup:**
- `db_schema.py` runs both Alembic migration AND raw SQL fallback on every startup
- This is slow and potentially dangerous if schemas drift

**No Connection Pooling Config for SQLite:**
- SQLite connections are opened/closed per request in `db_pool.py`
- Fine for dev but won't scale

---

*Concerns audit: 2026-06-23*
