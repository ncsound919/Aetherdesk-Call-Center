# Rental Pricing, Prepaid Minutes & Stripe Checkout — Design

**Date:** 2026-08-06
**Status:** Approved (phase-split)
**Scope:** Phase 1 = revenue flow (pricing catalog, rental/top-up checkout, billing contract fix, Pricing + Billing pages). Phase 2 = voice options + easy/power modes.

---

## 1. Business model

AetherDesk is positioned as a **low-cost AI call center you rent by the hour**. Customers rent *concurrent AI agents* for flexible durations. Capacity (concurrent agents × time) is the time-limited resource; call minutes are a consumable that comes with the rental and can be topped up.

Two AI modes per rental:

- **DeepSeek (managed):** the platform runs the DeepSeek brain. Zero setup for the customer.
- **BYOK:** the customer plugs in their own LLM API keys; the platform still provides STT/TTS, telephony, and the agent runtime.

All payments are **prepaid and one-time** via Stripe Checkout (`mode="payment"`). No subscriptions, no post-paid risk.

### Voice options (Phase 2)

Three ways to give an agent a voice:

1. **Generic voices** — built-in open-source/edge TTS voices (already supported via `edge`/`chatterbox`/`qwen3` engines in `tts.py`). Free, included.
2. **Record your own** — browser media recorder (exists in `VoiceCloning.jsx`) → `POST /voice/clone` → open-source Chatterbox cloning. Included.
3. **ElevenLabs import** *(new)* — customer supplies their own ElevenLabs API key + voice ID; `tts.py` gains an `elevenlabs` engine that uses the customer's key. **Pass-through** — the customer pays ElevenLabs directly; no platform cost, no markup.

### Easy mode / Power mode (Phase 2)

- **Easy mode:** a guided 5-step wizard (extends existing `SelfServeSetup.jsx`) that gets a non-technical user live in minutes: business info → rent agents → pick voice → pick a script template *or describe use case in plain English* (auto-generates a simple protocol) → pay → live. Advanced config hidden.
- **Power mode:** the full existing dashboard set (custom protocols/engine, BYOK keys, deep analytics, integrations, voice studio, WFM, QA). A mode toggle in the UI switches between the two; easy mode hides advanced nav, power mode reveals it.

---

## 2. Pricing catalog (single source of truth)

`src/api/services/pricing.py` defines the canonical catalog, served publicly by `GET /billing/plans`.

### Rental periods (per concurrent agent)

| key | Period | Price | Eff./hr | Included min |
|---|---|---|---|---|
| `hour` | 1 hour | $2.00 | $2.00 | 40 |
| `four_hour` | 4 hours | $7.20 | $1.80 | 160 |
| `day` | 8 hours | $13.30 | $1.66 | 320 |
| `week` | 5×8h | $64.00 | $1.60 | 1,600 |
| `month` | 22×8h | $239.00 | $1.36 | 7,040 |
| `quarter` | 3 months | $644.00 | $1.22 | 21,120 |
| `half_year` | 6 months | $1,204.00 | $1.14 | 42,240 |
| `year` | 12 months | $2,239.00 | $1.06 | 84,480 |

Included minutes scale at **40 min per agent-hour**. Rental prices are fixed (no per-period rounding changes).

### Per-minute rates

- **BYOK:** $0.03/min
- **DeepSeek (managed):** $0.05/min

### Top-up packs (price = pack size × per-minute rate)

| Pack (min) | BYOK | DeepSeek |
|---|---|---|
| 100 | $3 | $5 |
| 500 | $15 | $25 |
| 1,000 | $30 | $50 |
| 5,000 | $150 | $250 |

### Example (customer-facing)

Rent 5 agents × 8-hour day on DeepSeek: **$66.50** capacity = **1,600 included minutes**. A 1,000-min top-up adds $50 → 2,600 min for **$116.50**.

---

## 3. Account / data model

Per tenant, add to the existing `tenants` record (schema migration in `db_schema.py` + alembic):

- `ai_mode` — `deepseek` | `byok`
- `rental_period` — catalog key or `NULL`
- `rental_start`, `rental_end` — active rental window (NULL when none)
- `minute_balance` — prepaid minutes, **rolls over** (does not expire with the rental)
- `stripe_session_id`, `stripe_customer_id` (already present), `stripe_payment_intent_id`
- `byok_keys` — encrypted JSON of customer LLM keys (e.g. `{openai, deepseek, groq}`)
- `elevenlabs_api_key`, `elevenlabs_voice_id` (Phase 2)

**Minute balance rules:** rental activation credits `included_minutes` to `minute_balance`. Usage (`record_usage_db`, existing) decrements it. Top-ups credit more. Calls are blocked when `minute_balance <= 0` and no active rental (capacity) — enforced at call start. Unused balance persists.

---

## 4. Stripe integration

All Checkout sessions are **one-time** (`mode="payment"`). No subscriptions.

### Stripe Prices (configured via env, mapped in `pricing.py`)

- 8 rental Prices: `STRIPE_PRICE_RENTAL_<KEY>` (e.g. `STRIPE_PRICE_RENTAL_HOUR`)
- Top-up Prices per pack × mode: `STRIPE_PRICE_TOPUP_<PACK>_<MODE>` (e.g. `STRIPE_PRICE_TOPUP_1000_DEEPSEEK`)
- Fallback to mock mode when `STRIPE_SECRET_KEY` unset (existing `stripe_service.py` behavior preserved).

### Checkout

`POST /billing/checkout` body `{type: "rental"|"topup", period?: key, pack?: int, mode?: "byok"|"deepseek", quantity?: int}`:

1. Auth required (`verify_access_token`).
2. Validate against `pricing.py` catalog (400 on invalid).
3. Create Stripe Checkout session with metadata `{tenant_id, type, period, pack, mode, quantity}`.
4. Return `{checkout_url, session_id}`; frontend redirects.

`quantity` = number of agents for a rental (e.g. 5 agents × day) or pack quantity for top-up. Line item quantity multiplies the unit price.

### Webhooks (`POST /billing/webhooks/stripe`, existing route extended)

- `checkout.session.completed` → metadata-driven:
  - `type=rental` → set `ai_mode`, open rental window (`rental_start=now`, `rental_end=now+duration`), credit `included_minutes × quantity` to balance.
  - `type=topup` → credit `pack × quantity` minutes to balance.
- `checkout.session.expired` / payment failures → no activation (idempotent, safe).
- `customer.subscription.deleted` → no-op (kept for backward compat).

### Billing API contract fix

`GET /billing` currently returns `{total_calls, total_minutes, total_cost, currency, breakdown}` but `BillingPage.jsx` reads `plan`, `status`, `balance`, `estimated_cost`, `calls_this_month`, `calls_limit`, `minutes_used`, `minutes_limit`. **Fix:** the endpoint returns a unified payload:

```
{
  plan: rental_period or "free",
  mode: ai_mode,
  status: active_rental | no_rental,
  rental_start, rental_end,
  calls_this_month, minutes_used,
  minute_balance, calls_limit (derived from active rental), minutes_limit,
  total_cost, currency, breakdown,
  price_per_min: <mode rate>,
}
```

Frontend `BillingPage.jsx` is updated to consume this.

---

## 5. BYOK / DeepSeek key resolution

- `PUT /billing/byok` (auth) stores encrypted customer LLM keys; returns masked confirmation.
- `llm_client` gains a tenant-aware resolution: when a tenant has `byok_keys` and `ai_mode=byok`, use the tenant's key/provider; otherwise fall back to the platform DeepSeek config.
- Existing orchestrator (`orchestrator.py`) passes `tenant_id` through to `llm_client` where the key is resolved (minimal change — the call site already has tenant context).

---

## 6. Frontend

### Phase 1

- **`PricingPage.jsx`** (new, public — no auth): mode toggle (BYOK/DeepSeek), rental duration table with per-agent price + included minutes, top-up pack table, "Rent now" / "Buy minutes". Logged-in → calls checkout directly. Anonymous → routes to signup, then checkout. Registered at `/pricing`.
- **`BillingPage.jsx`** (fix): consume the corrected `/billing` payload; show rental window, minute balance, minutes used, mode; wire **Upgrade Plan → /pricing**, **Buy minutes → checkout (top-up)**, **View Invoices → Stripe portal** (`POST /billing/portal`).
- **`App.jsx`**: add `/pricing` route, wire Billing handlers, add Pricing to nav.

### Phase 2

- **Voice picker** component used in the wizard and the VoiceCloning studio: three tabs — Generic / Record / ElevenLabs.
- **`GET /voice/options`** returns generic voices + any tenant clones + ElevenLabs voices (if key set).
- **Easy-mode wizard** (extend `SelfServeSetup.jsx`): ① business info → ② rent agents (count × duration × mode) → ③ voice → ④ script template or free-text use case → auto-generate protocol → ⑤ checkout → live.
- **Mode toggle** in the app shell; easy mode hides advanced nav.

---

## 7. Backend endpoints summary (new/changed)

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/billing/plans` | GET | none | Public pricing catalog |
| `/billing/checkout` | POST | token | Create rental/top-up Checkout session |
| `/billing/webhooks/stripe` | POST | sig | Activate rental / credit minutes |
| `/billing` | GET | tenant | Unified billing payload (fixed) |
| `/billing/portal` | POST | token | Stripe customer portal (existing) |
| `/billing/byok` | PUT | token | Store encrypted BYOK keys |
| `/voice/options` | GET | api key | Generic voices + clones + ElevenLabs (P2) |
| `/voice/elevenlabs` | POST | api key | Save ElevenLabs key + voice id (P2) |
| `/voice/clone`, `/voice/clones*` | — | api key | Existing (reused) |

---

## 8. Testing

- **Unit:** `pricing.py` catalog validation; checkout request validation; webhook handling (rental activate, top-up credit, expired, idempotency); BYOK key encrypt/decrypt + resolution; billing contract shape; `llm_client` tenant-key fallback.
- **Phase 2:** `voice/options` aggregation; ElevenLabs engine (mock) + fallback to generic when key invalid; wizard protocol auto-generation from free-text.
- **Frontend (vitest + testing-library):** `PricingPage`, `BillingPage` (fixed contract), wizard steps, voice picker.
- All Python tests under `tests/unit/`, keeping the ≥95% coverage gate green.

---

## 9. Out of scope (this build)

- Stripe metered subscriptions (deliberately replaced by prepaid minutes + top-ups).
- Post-paid invoicing.
- Free-trial / coupon application to rentals (coupons exist for other flows; rental coupon support deferred).
- Multi-currency billing (USD only for now).
- Real-time balance alerts / email notifications (toast in UI only).

---

## 10. Phase plan

**Phase 1 — revenue flow:**
`pricing.py` catalog + `/billing/plans` → tenant rental-state migration → `/billing/checkout` + webhook handling → `/billing` contract fix → `PUT /billing/byok` + `llm_client` resolution → `PricingPage.jsx` → `BillingPage.jsx` fix + `App.jsx` wiring → backend + frontend tests.

**Phase 2 — voices + modes:**
`/voice/options` + `/voice/elevenlabs` + `tts.py` elevenlabs engine → voice picker component → easy-mode wizard (script-template→protocol generation) → mode toggle + nav split → tests.
