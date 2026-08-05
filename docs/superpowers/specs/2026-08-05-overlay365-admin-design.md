# Overlay365 Admin Suite — Design

**Date:** 2026-08-05
**Status:** Approved for implementation planning
**Repo:** `Aetherdesk-Call-Center` (admin lives in the existing `agent-ui` React app)

---

## 1. Goal

Give the single Overlay365 operator (the user) a deep admin panel inside Aetherdesk
covering four modules: **SEO**, **CRM**, **Coupons**, and **Flyer making** — plus a
unified dashboard. The panel is operated centrally for Overlay365, but the code is
multi-tenant-safe so the same codebase ships as the SaaS product. No new hosting, no
CMS service — everything lives in the existing FastAPI backend + React frontend.

## 2. Architecture

- **Backend:** one new router `src/api/routers/admin_ops.py` + a DB layer
  `src/api/services/db_admin_ops.py`, registered in `src/api/main.py` with
  `prefix="/api/v1/admin"`.
- **Auth:** admin routes use the existing JWT bearer (`verify_access_token`).
  One **public** group (`prefix="/api/v1/public"`) serves SEO content to the
  Overlay365 static site at build time.
- **Frontend:** four new lazy pages in `agent-ui/src/pages/`, wired into
  `App.jsx` routes + a new "Overlay365 Admin" nav group in `NAV_GROUPS`, and an
  API client section in `agent-ui/src/services/api.js`.
- **Database:** new tables added via the existing `db_schema.py` `CREATE TABLE IF
  NOT EXISTS` pattern (SQLite + Postgres compatible).

## 3. Modules

### 3.1 Flyer maker (flagship)

- **10+ fixed templates** across three categories:
  1. Event / Community (health fair, workshop, community meet)
  2. Donation Drive
  3. Business Promo (Aetherdesk onboarding / SaaS offer)
- Each template is an HTML/CSS React component with **4 color/gradient theme
  variants** → 40+ visual looks.
- **Export:** `html2canvas` renders the template DOM to a PNG downloaded client-side.
  No image API, works offline, no per-image cost.
- **Customization:** title, subtitle, CTA text + URL, date/venue/location, brand
  color theme, optional logo upload.
- **AI assist (optional):** DeepSeek (via the existing `llm_client`) drafts
  headline / subheadline / CTA from a topic + audience. User edits then exports.
- **Design direction:** Canva/Figma layout principles (bold type, gradient depth,
  strong CTA hierarchy) + Gemini-generated reference images for inspiration only
  (not rendered into flyers).
- Flyer saves persisted to `flyer_saves` so the operator can return and re-export.

### 3.2 SEO content manager

- Content records keyed by page slug: meta title, meta description, OG
  title/description, keywords, canonical URL, body/content, status (draft/published).
- **AI generation (optional):** DeepSeek drafts meta + content from a topic.
- **Public API:** `GET /api/v1/public/seo/content` returns all published records.
  The Overlay365 Next.js site fetches these at build time; `next/og` generates
  OG images server-side from the stored fields.

### 3.3 CRM — unified contacts

- One searchable view merging three sources:
  - **Leads** — existing `leads` table
  - **Donors** — new `donors` table (name, email, phone, amount, date, tier)
  - **Signups** — existing `users` table
- Contact detail with tags + notes (new `contact_notes` table).
- Segments: Black community / businesses / donors (label field).

### 3.4 Coupons

- Create discount codes: type (percent/amount), value, minimum, max uses,
  start/end dates, status.
- Auto-creates a matching **Stripe coupon** when `STRIPE_SECRET_KEY` is set
  (mirrors the mock/real pattern used in `signup_overlay365.py`); stores the
  Stripe coupon ID + status.
- List/disable/delete codes; usage tracking is read from Stripe.

## 4. Data model

All tables created idempotently in `db_schema.py`:

| Table | Columns (key) |
|---|---|
| `seo_content` | slug PK, meta_title, meta_description, og_title, og_description, og_image, keywords, body, status, updated_at |
| `flyer_templates` | id, category, name, preset_json (template config) |
| `flyer_saves` | id, template_id, title, subtitle, cta_text, cta_url, theme, logo_url, config_json, created_at |
| `donors` | id, name, email, phone, amount, currency, tier, donation_date, notes |
| `coupons` | id, code, type, value, min_amount, max_uses, starts_at, ends_at, stripe_coupon_id, status, created_at |
| `contact_notes` | id, source, contact_id, note, created_at |

## 5. Frontend pages

- `/admin/flyers` — template gallery (category filter + theme picker), live
  preview, edit fields, AI copy button, export PNG, saved flyers list.
- `/admin/seo` — list of content records, edit form, AI generate, publish toggle.
- `/admin/crm` — unified contacts table with search + source filter, contact
  detail drawer (notes/tags).
- `/admin/coupons` — coupon list + create form, Stripe status badges.

New nav group "Overlay365 Admin" with items: Flyers, SEO, CRM, Coupons.

## 6. Error handling

- Admin routes follow existing patterns: 401 unauthenticated, 404 not found,
  400 validation, 500 on DB failure (logged via structlog).
- Stripe ops are best-effort: coupon is saved locally; `stripe_coupon_id` is null
  with a `status` of `local_only` when Stripe is unavailable, `active` otherwise.
- Flyer export is fully client-side; template render failures show an inline
  error via the existing `ErrorBoundary` + `sonner` toasts.

## 7. Testing

- Backend: router tests follow the existing minimal-app + dependency-override
  pattern (`test_*_router.py`): SEO CRUD + public API, coupons CRUD + Stripe mock,
  CRM aggregation view, flyer save CRUD.
- Frontend: vitest unit tests for the API client additions; component tests for
  the flyer template renderer (verifies each template renders its fields) and the
  coupon form validation.
- Run: `python -m pytest tests/unit` and `cd agent-ui && npm test`.

## 8. Out of scope (now)

- Drag-and-drop flyer editor (GrapesJS) — possible future add-on.
- AI-generated flyer background images via image APIs — cost/latency tradeoff.
- Per-tenant admin panels for SaaS customers — operator admin only.
- Social media scheduler, loyalty programs, e-commerce/inventory.
