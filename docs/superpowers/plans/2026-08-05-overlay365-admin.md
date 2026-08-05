# Overlay365 Admin Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Overlay365 operator admin (SEO, CRM, Coupons, Flyer maker) into Aetherdesk's existing FastAPI backend + `agent-ui` React app.

**Architecture:** One new FastAPI router (`admin_ops.py`) + DB layer (`db_admin_ops.py`) with 6 new tables; four new lazy React pages wired into the existing `App.jsx` shell + nav. Admin routes use existing JWT auth; one public route group serves SEO content to the Overlay365 static site. Flyers export to PNG client-side via `html2canvas`; optional AI copy uses the existing `llm_client` (DeepSeek). Coupons mirror the mock/real Stripe pattern from `signup_overlay365.py`.

**Tech Stack:** FastAPI, SQLite + Postgres (`db_pool`), React 18 + Vite (`agent-ui`), axios, `html2canvas`, existing `llm_client` (DeepSeek), pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-08-05-overlay365-admin-design.md`

---

## File Structure

**Backend (Aetherdesk repo root `C:\Users\User\Downloads\Uplift\Aetherdesk-Call-Center`):**
- Create `src/api/services/db_admin_ops.py` — all DB CRUD for the 6 admin tables
- Create `src/api/routers/admin_ops.py` — admin + public API routes
- Modify `src/api/services/db_schema.py` — add 6 `CREATE TABLE IF NOT EXISTS` blocks
- Modify `src/api/main.py` — import + `include_router` for admin_ops
- Test: `tests/unit/test_admin_ops_router.py`

**Frontend (Aetherdesk repo root `...\agent-ui`):**
- Create `src/pages/admin/FlyersPage.jsx`, `SEOContentPage.jsx`, `CRMPage.jsx`, `CouponsPage.jsx`
- Create `src/pages/admin/flyers/` — flyer template components + `html2canvas` export helper
- Modify `src/services/api.js` — add `adminApi`
- Modify `src/App.jsx` — add 4 lazy routes + "Overlay365 Admin" nav group
- Test: `src/test/FlyerTemplate.test.jsx`, `src/test/CouponsForm.test.jsx`

---

## PART A — BACKEND

### Task 1: Add admin tables to db_schema.py

**Files:**
- Modify: `src/api/services/db_schema.py` (append near the end, after the last `CREATE TABLE`)

- [ ] **Step 1: Append the 6 admin tables**

Append to the end of `db_schema.py`:

```sql
-- ── Overlay365 Admin Suite ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS seo_content (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    meta_title TEXT,
    meta_description TEXT,
    og_title TEXT,
    og_description TEXT,
    og_image TEXT,
    keywords TEXT,
    body TEXT,
    status TEXT DEFAULT 'draft',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS donors (
    id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    phone TEXT,
    amount REAL DEFAULT 0.0,
    currency TEXT DEFAULT 'USD',
    tier TEXT,
    notes TEXT,
    donation_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS coupons (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    type TEXT DEFAULT 'percent',
    value REAL DEFAULT 0.0,
    min_amount REAL,
    max_uses INTEGER,
    starts_at TIMESTAMP,
    ends_at TIMESTAMP,
    stripe_coupon_id TEXT,
    status TEXT DEFAULT 'local_only',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_notes (
    id TEXT PRIMARY KEY,
    source TEXT,
    contact_id TEXT,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS flyer_saves (
    id TEXT PRIMARY KEY,
    template_id TEXT,
    title TEXT,
    subtitle TEXT,
    cta_text TEXT,
    cta_url TEXT,
    theme TEXT,
    logo_url TEXT,
    config_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS flyer_templates (
    id TEXT PRIMARY KEY,
    category TEXT,
    name TEXT,
    preset_json TEXT DEFAULT '{}'
);
```

- [ ] **Step 2: Verify schema loads**

Run: `python -c "from api.services import db_schema; print('ok')"`
Expected: prints `ok` (module imports and executes the schema SQL without error).

- [ ] **Step 3: Commit**

```bash
git add src/api/services/db_schema.py
git commit -m "feat(admin): add Overlay365 admin tables to schema"
```

### Task 2: Create the admin DB layer

**Files:**
- Create: `src/api/services/db_admin_ops.py`
- Test: `tests/unit/test_db_admin_ops.py` (covered implicitly via router tests in Task 4)

- [ ] **Step 1: Write the DB layer**

Create `src/api/services/db_admin_ops.py`:

```python
"""DB operations for the Overlay365 admin suite."""
import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()

def _now():
    return datetime.now(UTC).isoformat()

def _row_to_dict(row, keys):
    return dict(zip(keys, row)) if row else None


# ── SEO content ──────────────────────────────────────────────────────

SEO_KEYS = ("id", "slug", "meta_title", "meta_description", "og_title",
            "og_description", "og_image", "keywords", "body", "status",
            "updated_at", "created_at")

async def list_seo_content_db(status=None):
    rows = []
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if status:
                recs = await pool.fetch("SELECT * FROM seo_content WHERE status = $1 ORDER BY created_at DESC", status)
            else:
                recs = await pool.fetch("SELECT * FROM seo_content ORDER BY created_at DESC")
            return [dict(r) for r in recs]
    conn = _get_sqlite_conn()
    if status:
        cur = conn.execute("SELECT * FROM seo_content WHERE status = ? ORDER BY created_at DESC", (status,))
    else:
        cur = conn.execute("SELECT * FROM seo_content ORDER BY created_at DESC")
    return [_row_to_dict(r, SEO_KEYS) for r in cur.fetchall()]

async def get_seo_content_db(slug):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            r = await pool.fetchrow("SELECT * FROM seo_content WHERE slug = $1", slug)
            return dict(r) if r else None
    conn = _get_sqlite_conn()
    return _row_to_dict(conn.execute("SELECT * FROM seo_content WHERE slug = ?", (slug,)).fetchone(), SEO_KEYS)

async def upsert_seo_content_db(slug, data):
    now = _now()
    cid = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            r = await pool.fetchrow("""
                INSERT INTO seo_content (id, slug, meta_title, meta_description, og_title, og_description, og_image, keywords, body, status, updated_at, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$11)
                ON CONFLICT (slug) DO UPDATE SET
                  meta_title=EXCLUDED.meta_title, meta_description=EXCLUDED.meta_description,
                  og_title=EXCLUDED.og_title, og_description=EXCLUDED.og_description,
                  og_image=EXCLUDED.og_image, keywords=EXCLUDED.keywords,
                  body=EXCLUDED.body, status=EXCLUDED.status, updated_at=EXCLUDED.updated_at
                RETURNING *
            """, cid, slug, data.get("meta_title"), data.get("meta_description"),
                data.get("og_title"), data.get("og_description"), data.get("og_image"),
                data.get("keywords"), data.get("body"), data.get("status", "draft"), now)
            return dict(r) if r else None
    conn = _get_sqlite_conn()
    existing = conn.execute("SELECT id FROM seo_content WHERE slug = ?", (slug,)).fetchone()
    if existing:
        conn.execute("""
            UPDATE seo_content SET meta_title=?, meta_description=?, og_title=?, og_description=?,
              og_image=?, keywords=?, body=?, status=?, updated_at=? WHERE slug=?
        """, (data.get("meta_title"), data.get("meta_description"), data.get("og_title"),
              data.get("og_description"), data.get("og_image"), data.get("keywords"),
              data.get("body"), data.get("status", "draft"), now, slug))
        conn.commit()
        return get_seo_content_db(slug)
    conn.execute("""
        INSERT INTO seo_content (id, slug, meta_title, meta_description, og_title, og_description, og_image, keywords, body, status, updated_at, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (cid, slug, data.get("meta_title"), data.get("meta_description"), data.get("og_title"),
          data.get("og_description"), data.get("og_image"), data.get("keywords"),
          data.get("body"), data.get("status", "draft"), now, now))
    conn.commit()
    return get_seo_content_db(slug)


# ── Donors ───────────────────────────────────────────────────────────

DONOR_KEYS = ("id", "name", "email", "phone", "amount", "currency", "tier",
              "notes", "donation_date", "created_at")

async def list_donors_db():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return [dict(r) for r in await pool.fetch("SELECT * FROM donors ORDER BY donation_date DESC")]
    conn = _get_sqlite_conn()
    return [_row_to_dict(r, DONOR_KEYS) for r in conn.execute("SELECT * FROM donors ORDER BY donation_date DESC").fetchall()]

async def create_donor_db(name, email, phone, amount, currency, tier, notes, donation_date):
    did = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "INSERT INTO donors (id,name,email,phone,amount,currency,tier,notes,donation_date) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                did, name, email, phone, amount, currency, tier, notes, donation_date)
            r = await pool.fetchrow("SELECT * FROM donors WHERE id=$1", did)
            return dict(r)
    conn = _get_sqlite_conn()
    conn.execute(
        "INSERT INTO donors (id,name,email,phone,amount,currency,tier,notes,donation_date) VALUES (?,?,?,?,?,?,?,?,?)",
        (did, name, email, phone, amount, currency, tier, notes, donation_date))
    conn.commit()
    return _row_to_dict(conn.execute("SELECT * FROM donors WHERE id=?", (did,)).fetchone(), DONOR_KEYS)


# ── Coupons ──────────────────────────────────────────────────────────

COUPON_KEYS = ("id", "code", "type", "value", "min_amount", "max_uses",
               "starts_at", "ends_at", "stripe_coupon_id", "status", "created_at")

async def list_coupons_db():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return [dict(r) for r in await pool.fetch("SELECT * FROM coupons ORDER BY created_at DESC")]
    conn = _get_sqlite_conn()
    return [_row_to_dict(r, COUPON_KEYS) for r in conn.execute("SELECT * FROM coupons ORDER BY created_at DESC").fetchall()]

async def create_coupon_db(code, ctype, value, min_amount, max_uses, starts_at, ends_at, stripe_coupon_id, status):
    cid = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "INSERT INTO coupons (id,code,type,value,min_amount,max_uses,starts_at,ends_at,stripe_coupon_id,status) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                cid, code, ctype, value, min_amount, max_uses, starts_at, ends_at, stripe_coupon_id, status)
            r = await pool.fetchrow("SELECT * FROM coupons WHERE id=$1", cid)
            return dict(r)
    conn = _get_sqlite_conn()
    conn.execute(
        "INSERT INTO coupons (id,code,type,value,min_amount,max_uses,starts_at,ends_at,stripe_coupon_id,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cid, code, ctype, value, min_amount, max_uses, starts_at, ends_at, stripe_coupon_id, status))
    conn.commit()
    return _row_to_dict(conn.execute("SELECT * FROM coupons WHERE id=?", (cid,)).fetchone(), COUPON_KEYS)

async def set_coupon_status_db(coupon_id, status):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("UPDATE coupons SET status=$2 WHERE id=$1", coupon_id, status)
            return
    conn = _get_sqlite_conn()
    conn.execute("UPDATE coupons SET status=? WHERE id=?", (status, coupon_id))
    conn.commit()


# ── Contact notes ────────────────────────────────────────────────────

NOTE_KEYS = ("id", "source", "contact_id", "note", "created_at")

async def add_contact_note_db(source, contact_id, note):
    nid = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "INSERT INTO contact_notes (id,source,contact_id,note) VALUES ($1,$2,$3,$4)",
                nid, source, contact_id, note)
            return
    conn = _get_sqlite_conn()
    conn.execute("INSERT INTO contact_notes (id,source,contact_id,note) VALUES (?,?,?,?)",
                 (nid, source, contact_id, note))
    conn.commit()

async def list_contact_notes_db(source, contact_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return [dict(r) for r in await pool.fetch(
                "SELECT * FROM contact_notes WHERE source=$1 AND contact_id=$2 ORDER BY created_at DESC",
                source, contact_id)]
    conn = _get_sqlite_conn()
    return [_row_to_dict(r, NOTE_KEYS) for r in conn.execute(
        "SELECT * FROM contact_notes WHERE source=? AND contact_id=? ORDER BY created_at DESC",
        (source, contact_id)).fetchall()]


# ── Flyer saves ──────────────────────────────────────────────────────

FLYER_KEYS = ("id", "template_id", "title", "subtitle", "cta_text", "cta_url",
              "theme", "logo_url", "config_json", "created_at")

async def list_flyer_saves_db():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return [dict(r) for r in await pool.fetch("SELECT * FROM flyer_saves ORDER BY created_at DESC")]
    conn = _get_sqlite_conn()
    rows = [_row_to_dict(r, FLYER_KEYS) for r in conn.execute("SELECT * FROM flyer_saves ORDER BY created_at DESC").fetchall()]
    for r in rows:
        if isinstance(r.get("config_json"), str):
            try:
                r["config_json"] = json.loads(r["config_json"])
            except json.JSONDecodeError:
                r["config_json"] = {}
    return rows

async def create_flyer_save_db(template_id, title, subtitle, cta_text, cta_url, theme, logo_url, config):
    fid = str(uuid.uuid4())
    config_json = json.dumps(config or {})
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "INSERT INTO flyer_saves (id,template_id,title,subtitle,cta_text,cta_url,theme,logo_url,config_json) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                fid, template_id, title, subtitle, cta_text, cta_url, theme, logo_url, config_json)
            r = await pool.fetchrow("SELECT * FROM flyer_saves WHERE id=$1", fid)
            return dict(r)
    conn = _get_sqlite_conn()
    conn.execute(
        "INSERT INTO flyer_saves (id,template_id,title,subtitle,cta_text,cta_url,theme,logo_url,config_json) VALUES (?,?,?,?,?,?,?,?,?)",
        (fid, template_id, title, subtitle, cta_text, cta_url, theme, logo_url, config_json))
    conn.commit()
    return _row_to_dict(conn.execute("SELECT * FROM flyer_saves WHERE id=?", (fid,)).fetchone(), FLYER_KEYS)
```

- [ ] **Step 2: Verify module imports**

Run: `python -c "from api.services.db_admin_ops import list_coupons_db; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/api/services/db_admin_ops.py
git commit -m "feat(admin): add DB layer for Overlay365 admin suite"
```

### Task 3: Add the admin API router

**Files:**
- Create: `src/api/routers/admin_ops.py`
- Test: `tests/unit/test_admin_ops_router.py`

- [ ] **Step 1: Write the router**

Create `src/api/routers/admin_ops.py`:

```python
"""Overlay365 operator admin: SEO, CRM, coupons, flyers."""
import os
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from api.services.db_admin_ops import (
    add_contact_note_db,
    create_coupon_db,
    create_donor_db,
    create_flyer_save_db,
    get_seo_content_db,
    list_contact_notes_db,
    list_coupons_db,
    list_donors_db,
    list_flyer_saves_db,
    list_seo_content_db,
    set_coupon_status_db,
    upsert_seo_content_db,
)
from api.services.db_config import USE_POSTGRES
from api.services.db_pool import get_pg_pool
from api.services.llm_client import llm_client

logger = structlog.get_logger()

admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
public_router = APIRouter(prefix="/api/v1/public", tags=["public"])

bearer_scheme = HTTPBearer(auto_error=False)


async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Verify the operator JWT. Returns the payload."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    from api.services.auth import verify_access_token
    payload = await verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


# ── SEO content ──────────────────────────────────────────────────────

class SEOContent(BaseModel):
    slug: str = Field(..., min_length=1, max_length=200)
    meta_title: str | None = None
    meta_description: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    og_image: str | None = None
    keywords: str | None = None
    body: str | None = None
    status: str = "draft"


@admin_router.get("/seo/content")
async def admin_list_seo(payload: dict = Depends(require_admin)):
    return await list_seo_content_db()


@admin_router.put("/seo/content/{slug}")
async def admin_upsert_seo(slug: str, data: SEOContent, payload: dict = Depends(require_admin)):
    return await upsert_seo_content_db(slug, data.model_dump())


@admin_router.post("/seo/generate")
async def admin_generate_seo(body: dict, payload: dict = Depends(require_admin)):
    topic = body.get("topic", "Overlay365")
    audience = body.get("audience", "the Black community")
    prompt = (
        f"Write SEO metadata for a page about '{topic}' aimed at {audience}. "
        "Return a JSON object with exactly these keys: meta_title (under 60 chars), "
        "meta_description (under 160 chars), og_title, og_description, keywords (comma separated)."
    )
    try:
        result = await llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.4, json_mode=True,
        )
        from api.services.llm_client import parse_json_content
        return parse_json_content(result.text)
    except Exception as e:
        logger.warning("seo_generate_failed", error=str(e))
        return {
            "meta_title": topic,
            "meta_description": f"Learn about {topic} with Overlay365.",
            "og_title": topic,
            "og_description": f"Learn about {topic} with Overlay365.",
            "keywords": "overlay365, community",
        }


# ── CRM ──────────────────────────────────────────────────────────────

@admin_router.get("/crm/contacts")
async def admin_crm_contacts(payload: dict = Depends(require_admin)):
    """Unified contacts: leads + donors + signups."""
    from api.services.db_tenants import list_leads_db
    leads = await list_leads_db("TENANT-001", limit=500, offset=0)
    donors = await list_donors_db()

    # Signups: existing users (name/email). Works on both SQLite and Postgres.
    signups = []
    try:
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                for row in await pool.fetch("SELECT id, email, full_name FROM users LIMIT 500"):
                    signups.append({"id": row["id"], "email": row["email"], "name": row["full_name"]})
        else:
            from api.services.db_pool import _get_sqlite_conn
            conn = _get_sqlite_conn()
            for row in conn.execute("SELECT id, email, full_name FROM users LIMIT 500").fetchall():
                signups.append({"id": row[0], "email": row[1], "name": row[2]})
    except Exception as e:
        logger.warning("signup_load_failed", error=str(e))

    contacts = []
    for lead in leads or []:
        if isinstance(lead, dict):
            contacts.append({
                "source": "lead", "id": lead.get("id"),
                "name": lead.get("contact_name") or lead.get("first_name") or lead.get("company_name"),
                "email": lead.get("email"), "phone": lead.get("phone"),
                "segment": "business" if lead.get("company_name") else "lead",
            })
    for donor in donors:
        if isinstance(donor, dict):
            contacts.append({
                "source": "donor", "id": donor.get("id"),
                "name": donor.get("name"), "email": donor.get("email"),
                "phone": donor.get("phone"), "segment": "donor",
                "amount": donor.get("amount"),
            })
    for user in signups:
        if isinstance(user, dict):
            contacts.append({
                "source": "signup", "id": user.get("id"),
                "name": user.get("name"), "email": user.get("email"),
                "phone": None, "segment": "signup",
            })
    return contacts


@admin_router.get("/crm/contacts/{source}/{contact_id}/notes")
async def admin_contact_notes(source: str, contact_id: str, payload: dict = Depends(require_admin)):
    return await list_contact_notes_db(source, contact_id)


@admin_router.post("/crm/contacts/{source}/{contact_id}/notes")
async def admin_add_note(source: str, contact_id: str, body: dict, payload: dict = Depends(require_admin)):
    note = (body.get("note") or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="note is required")
    await add_contact_note_db(source, contact_id, note)
    return {"ok": True}


@admin_router.post("/crm/donors")
async def admin_create_donor(body: dict, payload: dict = Depends(require_admin)):
    return await create_donor_db(
        name=body.get("name"), email=body.get("email"), phone=body.get("phone"),
        amount=float(body.get("amount", 0) or 0), currency=body.get("currency", "USD"),
        tier=body.get("tier"), notes=body.get("notes"),
        donation_date=body.get("donation_date"),
    )


# ── Coupons ──────────────────────────────────────────────────────────

class CouponCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    type: str = "percent"
    value: float = Field(..., gt=0)
    min_amount: float | None = None
    max_uses: int | None = None
    starts_at: str | None = None
    ends_at: str | None = None


@admin_router.get("/coupons")
async def admin_list_coupons(payload: dict = Depends(require_admin)):
    return await list_coupons_db()


@admin_router.post("/coupons")
async def admin_create_coupon(data: CouponCreate, payload: dict = Depends(require_admin)):
    # Best-effort Stripe coupon creation (mirrors signup_overlay365 pattern).
    stripe_coupon_id = None
    status = "local_only"
    stripe_secret = os.getenv("STRIPE_SECRET_KEY")
    if stripe_secret:
        try:
            import stripe
            stripe.api_key = stripe_secret
            coupon_kwargs = {}
            if data.type == "percent":
                coupon_kwargs["percent_off"] = data.value
            else:
                coupon_kwargs["amount_off"] = int(data.value * 100)
            if data.max_uses:
                coupon_kwargs["max_redemptions"] = data.max_uses
            coupon = stripe.Coupon.create(
                id=data.code,
                duration="forever",
                currency="usd",
                **coupon_kwargs,
            )
            stripe_coupon_id = coupon.id
            status = "active"
        except Exception as e:
            logger.warning("stripe_coupon_create_failed", code=data.code, error=str(e))

    return await create_coupon_db(
        code=data.code.upper(), ctype=data.type, value=data.value,
        min_amount=data.min_amount, max_uses=data.max_uses,
        starts_at=data.starts_at, ends_at=data.ends_at,
        stripe_coupon_id=stripe_coupon_id, status=status,
    )


@admin_router.post("/coupons/{coupon_id}/disable")
async def admin_disable_coupon(coupon_id: str, payload: dict = Depends(require_admin)):
    await set_coupon_status_db(coupon_id, "disabled")
    return {"ok": True}


# ── Flyers ───────────────────────────────────────────────────────────

@admin_router.get("/flyers")
async def admin_list_flyers(payload: dict = Depends(require_admin)):
    return await list_flyer_saves_db()


@admin_router.post("/flyers")
async def admin_save_flyer(body: dict, payload: dict = Depends(require_admin)):
    return await create_flyer_save_db(
        template_id=body.get("template_id"), title=body.get("title"),
        subtitle=body.get("subtitle"), cta_text=body.get("cta_text"),
        cta_url=body.get("cta_url"), theme=body.get("theme"),
        logo_url=body.get("logo_url"), config=body.get("config"),
    )


@admin_router.post("/flyers/generate-copy")
async def admin_generate_flyer_copy(body: dict, payload: dict = Depends(require_admin)):
    topic = body.get("topic", "Overlay365 community event")
    audience = body.get("audience", "the Black community")
    cta = body.get("cta", "Join us")
    prompt = (
        f"Write flyer copy for a {topic} aimed at {audience}. "
        f"The call to action is '{cta}'. Return a JSON object with keys: "
        "title (short, punchy), subtitle (one sentence), cta_text (2-4 words)."
    )
    try:
        result = await llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.7, json_mode=True,
        )
        from api.services.llm_client import parse_json_content
        return parse_json_content(result.text)
    except Exception as e:
        logger.warning("flyer_copy_failed", error=str(e))
        return {"title": topic, "subtitle": "Join Overlay365 in building stronger futures.", "cta_text": cta}


# ── Public SEO content (for overlay365.com build) ───────────────────

@public_router.get("/seo/content")
async def public_list_seo():
    return await list_seo_content_db(status="published")
```

- [ ] **Step 2: Register the routers in main.py**

Modify `src/api/main.py` — add imports near the other `from api.routers import (...)` block and include the routers after the existing includes:

```python
# after `from api.routers.signup_overlay365 import router as signup_overlay365_router`
from api.routers.admin_ops import admin_router, public_router
```

At the end of the router includes (after the `signup_overlay365_router` / `blocklabor_overlay365_router` includes):

```python
app.include_router(admin_router)
app.include_router(public_router)
```

- [ ] **Step 3: Verify app imports**

Run: `python -c "from api.main import app; print('ok')"` (set env vars first: `APP_ENV=development`, `JWT_SECRET=x`, `INTERNAL_API_KEY=x`, `ENCRYPTION_KEY=<a valid 44-char Fernet key>`)
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add src/api/routers/admin_ops.py src/api/main.py
git commit -m "feat(admin): add Overlay365 admin + public SEO routers"
```

### Task 4: Backend tests for the admin router

**Files:**
- Create: `tests/unit/test_admin_ops_router.py`

- [ ] **Step 1: Write router tests**

Create `tests/unit/test_admin_ops_router.py`:

```python
"""Tests for the Overlay365 admin router."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.admin_ops import admin_router, public_router
from api.routers.admin_ops import require_admin


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(admin_router)
    application.include_router(public_router)

    async def _override_admin():
        return {"sub": "admin-1", "tenant_id": "TENANT-001"}

    application.dependency_overrides[require_admin] = _override_admin
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestSEOContent:
    def test_list_seo(self, client):
        with patch(
            "api.routers.admin_ops.list_seo_content_db",
            new_callable=AsyncMock,
            return_value=[{"slug": "home", "status": "published"}],
        ):
            resp = client.get("/api/v1/admin/seo/content")
        assert resp.status_code == 200
        assert resp.json()[0]["slug"] == "home"

    def test_upsert_seo(self, client):
        with patch(
            "api.routers.admin_ops.upsert_seo_content_db",
            new_callable=AsyncMock,
            return_value={"slug": "home", "status": "published"},
        ) as mock_upsert:
            resp = client.put(
                "/api/v1/admin/seo/content/home",
                json={"slug": "home", "meta_title": "T", "status": "published"},
            )
        assert resp.status_code == 200
        assert mock_upsert.call_args.args[0] == "home"

    def test_generate_seo_returns_content(self, client):
        with patch(
            "api.routers.admin_ops.llm_client.chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.return_value = type("R", (), {
                "text": '{"meta_title": "T", "meta_description": "D", "og_title": "T", "og_description": "D", "keywords": "a,b"}',
            })()
            resp = client.post("/api/v1/admin/seo/generate", json={"topic": "health"})
        assert resp.status_code == 200
        assert resp.json()["meta_title"] == "T"

    def test_generate_seo_fallback(self, client):
        with patch(
            "api.routers.admin_ops.llm_client.chat",
            new_callable=AsyncMock,
            side_effect=Exception("down"),
        ):
            resp = client.post("/api/v1/admin/seo/generate", json={"topic": "health"})
        assert resp.status_code == 200
        assert "meta_title" in resp.json()


class TestCRM:
    def test_unified_contacts(self, client):
        with patch(
            "api.routers.admin_ops.list_leads_db",
            new_callable=AsyncMock,
            return_value=[
                {"id": "L1", "contact_name": "Alice", "email": "a@b.com", "phone": "555", "company_name": "Acme"}
            ],
        ), patch(
            "api.routers.admin_ops.list_donors_db",
            new_callable=AsyncMock,
            return_value=[{"id": "D1", "name": "Bob", "email": "b@c.com", "amount": 100}],
        ):
            resp = client.get("/api/v1/admin/crm/contacts")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_add_note_requires_note(self, client):
        resp = client.post(
            "/api/v1/admin/crm/contacts/lead/L1/notes",
            json={},
        )
        assert resp.status_code == 400


class TestCoupons:
    def test_list_coupons(self, client):
        with patch(
            "api.routers.admin_ops.list_coupons_db",
            new_callable=AsyncMock,
            return_value=[{"code": "WELCOME20", "status": "local_only"}],
        ):
            resp = client.get("/api/v1/admin/coupons")
        assert resp.status_code == 200

    def test_create_coupon_local_only_without_stripe(self, client):
        with patch.dict("os.environ", {}, clear=True), patch(
            "api.routers.admin_ops.create_coupon_db",
            new_callable=AsyncMock,
            return_value={"code": "TEST10", "status": "local_only"},
        ) as mock_create:
            resp = client.post(
                "/api/v1/admin/coupons",
                json={"code": "test10", "type": "percent", "value": 10},
            )
        assert resp.status_code == 200
        assert mock_create.call_args.kwargs["status"] == "local_only"

    def test_create_coupon_with_stripe(self, client):
        mock_coupon = type("C", (), {"id": "TEST10"})()
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_live_123"}, clear=True), \
             patch("stripe.Coupon.create", return_value=mock_coupon), patch(
            "api.routers.admin_ops.create_coupon_db",
            new_callable=AsyncMock,
            return_value={"code": "TEST10", "status": "active", "stripe_coupon_id": "TEST10"},
        ) as mock_create:
            resp = client.post(
                "/api/v1/admin/coupons",
                json={"code": "TEST10", "type": "percent", "value": 10},
            )
        assert resp.status_code == 200
        assert mock_create.call_args.kwargs["status"] == "active"

    def test_disable_coupon(self, client):
        with patch(
            "api.routers.admin_ops.set_coupon_status_db",
            new_callable=AsyncMock,
        ) as mock_set:
            resp = client.post("/api/v1/admin/coupons/c1/disable")
        assert resp.status_code == 200
        assert mock_set.call_args.args[1] == "disabled"


class TestFlyers:
    def test_list_flyers(self, client):
        with patch(
            "api.routers.admin_ops.list_flyer_saves_db",
            new_callable=AsyncMock,
            return_value=[{"template_id": "t1"}],
        ):
            resp = client.get("/api/v1/admin/flyers")
        assert resp.status_code == 200

    def test_save_flyer(self, client):
        with patch(
            "api.routers.admin_ops.create_flyer_save_db",
            new_callable=AsyncMock,
            return_value={"id": "f1", "template_id": "t1"},
        ) as mock_save:
            resp = client.post(
                "/api/v1/admin/flyers",
                json={"template_id": "t1", "title": "Health Fair"},
            )
        assert resp.status_code == 200
        assert mock_save.call_args.kwargs["template_id"] == "t1"

    def test_generate_flyer_copy(self, client):
        with patch(
            "api.routers.admin_ops.llm_client.chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.return_value = type("R", (), {
                "text": '{"title": "Health Fair", "subtitle": "Free screenings", "cta_text": "Register Now"}',
            })()
            resp = client.post(
                "/api/v1/admin/flyers/generate-copy",
                json={"topic": "health fair", "cta": "Register"},
            )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Health Fair"


class TestPublicSEO:
    def test_public_only_published(self, client):
        with patch(
            "api.routers.admin_ops.list_seo_content_db",
            new_callable=AsyncMock,
            return_value=[{"slug": "home", "status": "published"}],
        ) as mock_list:
            resp = client.get("/api/v1/public/seo/content")
        assert resp.status_code == 200
        assert mock_list.call_args.kwargs["status"] == "published"
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/unit/test_admin_ops_router.py -q --no-cov -p no:cacheprovider`
Expected: all pass (17 tests).

- [ ] **Step 3: Fix the users table column name if needed**

The CRM signups query in the router uses `full_name`; if the `users` table uses a different column (check `db_schema.py` `CREATE TABLE IF NOT EXISTS users`), update the query column accordingly and re-run.

- [ ] **Step 4: Run the full unit suite to confirm no regressions**

Run: `python -m pytest tests/unit -q --no-cov -p no:cacheprovider`
Expected: all prior tests still pass.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_admin_ops_router.py
git commit -m "test(admin): add router tests for Overlay365 admin suite"
```

---

## PART B — FRONTEND

### Task 5: Add adminApi to the frontend client

**Files:**
- Modify: `agent-ui/src/services/api.js`

- [ ] **Step 1: Add adminApi export**

Append to `agent-ui/src/services/api.js` (before `export default api`):

```javascript
export const adminApi = {
  // SEO
  listSEO: () => api.get('/admin/seo/content'),
  upsertSEO: (slug, data) => api.put(`/admin/seo/content/${slug}`, data),
  generateSEO: (data) => api.post('/admin/seo/generate', data),
  // CRM
  listContacts: () => api.get('/admin/crm/contacts'),
  listNotes: (source, contactId) => api.get(`/admin/crm/contacts/${source}/${contactId}/notes`),
  addNote: (source, contactId, note) => api.post(`/admin/crm/contacts/${source}/${contactId}/notes`, { note }),
  createDonor: (data) => api.post('/admin/crm/donors', data),
  // Coupons
  listCoupons: () => api.get('/admin/coupons'),
  createCoupon: (data) => api.post('/admin/coupons', data),
  disableCoupon: (couponId) => api.post(`/admin/coupons/${couponId}/disable`),
  // Flyers
  listFlyers: () => api.get('/admin/flyers'),
  saveFlyer: (data) => api.post('/admin/flyers', data),
  generateFlyerCopy: (data) => api.post('/admin/flyers/generate-copy', data),
}
```

- [ ] **Step 2: Run frontend tests to confirm nothing broke**

Run: `cd agent-ui && npm test`
Expected: existing tests pass.

- [ ] **Step 3: Commit**

```bash
cd agent-ui
git add src/services/api.js
git commit -m "feat(admin): add adminApi client"
```

### Task 6: Install html2canvas

**Files:**
- Modify: `agent-ui/package.json`

- [ ] **Step 1: Install the dependency**

Run: `cd agent-ui && npm install html2canvas`

- [ ] **Step 2: Verify build**

Run: `cd agent-ui && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
cd agent-ui
git add package.json package-lock.json
git commit -m "chore(admin): add html2canvas for flyer export"
```

### Task 7: Flyer template components + export helper

**Files:**
- Create: `agent-ui/src/pages/admin/flyers/exportFlyer.js`
- Create: `agent-ui/src/pages/admin/flyers/templates.jsx`
- Create: `agent-ui/src/pages/admin/flyers/FlyerPreview.jsx`

- [ ] **Step 1: Write the export helper**

Create `agent-ui/src/pages/admin/flyers/exportFlyer.js`:

```javascript
import html2canvas from 'html2canvas'

export async function exportFlyerToPng(element, filename = 'flyer.png') {
  if (!element) throw new Error('Flyer element not found')
  const canvas = await html2canvas(element, {
    backgroundColor: null,
    scale: 2,
    useCORS: true,
    logging: false,
  })
  const link = document.createElement('a')
  link.download = filename
  link.href = canvas.toDataURL('image/png')
  link.click()
  return canvas.toDataURL('image/png')
}
```

- [ ] **Step 2: Write the template registry**

Create `agent-ui/src/pages/admin/flyers/templates.jsx`:

```jsx
import React from 'react'

// 10+ fixed templates across 3 categories, each with 4 themes.
// Each template is a pure component receiving the editable fields.

const THEMES = {
  midnight: { bg: 'linear-gradient(135deg,#05060a 0%,#10182e 100%)', accent: '#22d3ee', text: '#ffffff', sub: '#a5b4fc' },
  teal:    { bg: 'linear-gradient(135deg,#0f766e 0%,#134e4a 100%)', accent: '#2dd4bf', text: '#ffffff', sub: '#99f6e4' },
  gold:    { bg: 'linear-gradient(135deg,#78350f 0%,#451a03 100%)', accent: '#fbbf24', text: '#ffffff', sub: '#fde68a' },
  cyan:    { bg: 'linear-gradient(135deg,#164e63 0%,#083344 100%)', accent: '#38bdf8', text: '#ffffff', sub: '#bae6fd' },
}

function Banner({ theme, title, subtitle, ctaText }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 400, background: t.bg, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 64px', fontFamily: 'Arial, sans-serif' }}>
      <div style={{ fontSize: 16, color: t.accent, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 16 }}>Overlay365</div>
      <div style={{ fontSize: 52, color: t.text, fontWeight: 900, lineHeight: 1.1, marginBottom: 12 }}>{title}</div>
      <div style={{ fontSize: 22, color: t.sub, marginBottom: 32 }}>{subtitle}</div>
      <div style={{ alignSelf: 'flex-start', background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 32px', borderRadius: 999, fontSize: 18 }}>{ctaText}</div>
    </div>
  )
}

function SquareCard({ theme, title, subtitle, ctaText }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 600, height: 600, background: t.bg, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', padding: 48, fontFamily: 'Arial, sans-serif' }}>
      <div style={{ width: 80, height: 80, borderRadius: '50%', background: t.accent, marginBottom: 32 }} />
      <div style={{ fontSize: 44, color: t.text, fontWeight: 900, marginBottom: 12 }}>{title}</div>
      <div style={{ fontSize: 20, color: t.sub, marginBottom: 36, maxWidth: 420 }}>{subtitle}</div>
      <div style={{ background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 40px', borderRadius: 999, fontSize: 18 }}>{ctaText}</div>
    </div>
  )
}

function SplitLayout({ theme, title, subtitle, ctaText }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 500, display: 'flex', fontFamily: 'Arial, sans-serif' }}>
      <div style={{ width: '45%', background: t.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 96 }}>✦</div>
      <div style={{ width: '55%', background: t.bg, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: 40 }}>
        <div style={{ fontSize: 14, color: t.accent, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 12 }}>Overlay365</div>
        <div style={{ fontSize: 38, color: t.text, fontWeight: 900, marginBottom: 10 }}>{title}</div>
        <div style={{ fontSize: 18, color: t.sub, marginBottom: 24 }}>{subtitle}</div>
        <div style={{ border: `2px solid ${t.accent}`, color: t.accent, alignSelf: 'flex-start', fontWeight: 800, padding: '12px 28px', borderRadius: 999, fontSize: 16 }}>{ctaText}</div>
      </div>
    </div>
  )
}

function RibbonTop({ theme, title, subtitle, ctaText }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 500, background: t.bg, fontFamily: 'Arial, sans-serif', display: 'flex', flexDirection: 'column' }}>
      <div style={{ background: t.accent, color: '#05060a', fontWeight: 800, textAlign: 'center', padding: 12, fontSize: 14, letterSpacing: 2, textTransform: 'uppercase' }}>Overlay365 · One Platform</div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', padding: 40 }}>
        <div style={{ fontSize: 46, color: t.text, fontWeight: 900, marginBottom: 12 }}>{title}</div>
        <div style={{ fontSize: 20, color: t.sub, marginBottom: 32, maxWidth: 520 }}>{subtitle}</div>
        <div style={{ background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 36px', borderRadius: 999, fontSize: 18 }}>{ctaText}</div>
      </div>
    </div>
  )
}

// Template registry — each entry: id, category, name, component, default theme
export const FLYER_TEMPLATES = [
  // Event / Community
  { id: 'event-banner', category: 'event', name: 'Event Banner', component: Banner, theme: 'midnight' },
  { id: 'event-card', category: 'event', name: 'Community Card', component: SquareCard, theme: 'teal' },
  { id: 'event-split', category: 'event', name: 'Split Promo', component: SplitLayout, theme: 'gold' },
  { id: 'event-ribbon', category: 'event', name: 'Ribbon Top', component: RibbonTop, theme: 'cyan' },
  // Donation Drive
  { id: 'donate-banner', category: 'donation', name: 'Donation Banner', component: Banner, theme: 'gold' },
  { id: 'donate-card', category: 'donation', name: 'Giving Card', component: SquareCard, theme: 'midnight' },
  { id: 'donate-split', category: 'donation', name: 'Impact Split', component: SplitLayout, theme: 'teal' },
  { id: 'donate-ribbon', category: 'donation', name: 'Giving Ribbon', component: RibbonTop, theme: 'cyan' },
  // Business Promo
  { id: 'biz-banner', category: 'business', name: 'Business Banner', component: Banner, theme: 'teal' },
  { id: 'biz-card', category: 'business', name: 'Business Card', component: SquareCard, theme: 'midnight' },
  { id: 'biz-split', category: 'business', name: 'Offer Split', component: SplitLayout, theme: 'cyan' },
  { id: 'biz-ribbon', category: 'business', name: 'Offer Ribbon', component: RibbonTop, theme: 'gold' },
]

export const FLYER_THEMES = Object.keys(THEMES)
```

- [ ] **Step 3: Write the preview wrapper**

Create `agent-ui/src/pages/admin/flyers/FlyerPreview.jsx`:

```jsx
import React, { forwardRef } from 'react'
import { FLYER_TEMPLATES } from './templates'

const FlyerPreview = forwardRef(function FlyerPreview({ templateId, theme, title, subtitle, ctaText }, ref) {
  const tpl = FLYER_TEMPLATES.find((t) => t.id === templateId) || FLYER_TEMPLATES[0]
  const C = tpl.component
  return (
    <div ref={ref} style={{ borderRadius: 12, overflow: 'hidden', boxShadow: '0 20px 60px rgba(0,0,0,.4)' }}>
      <C theme={theme || tpl.theme} title={title || 'Your Headline Here'} subtitle={subtitle || 'Your supporting message goes here.'} ctaText={ctaText || 'Get Started'} />
    </div>
  )
})

export default FlyerPreview
```

- [ ] **Step 4: Run build to verify**

Run: `cd agent-ui && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
cd agent-ui
git add src/pages/admin/flyers/
git commit -m "feat(admin): add flyer templates and html2canvas export helper"
```

### Task 8: Flyers page

**Files:**
- Create: `agent-ui/src/pages/admin/FlyersPage.jsx`

- [ ] **Step 1: Write the page**

Create `agent-ui/src/pages/admin/FlyersPage.jsx`:

```jsx
import React, { useState, useRef, useCallback } from 'react'
import { toast } from 'sonner'
import { Wand2, Download, Save, Search } from 'lucide-react'
import { adminApi } from '../../services/api'
import FlyerPreview from './flyers/FlyerPreview'
import { FLYER_TEMPLATES, FLYER_THEMES } from './flyers/templates'
import { exportFlyerToPng } from './flyers/exportFlyer'

const CATEGORIES = [
  { id: 'event', label: 'Event / Community' },
  { id: 'donation', label: 'Donation Drive' },
  { id: 'business', label: 'Business Promo' },
]

export default function FlyersPage() {
  const [category, setCategory] = useState('event')
  const [templateId, setTemplateId] = useState(FLYER_TEMPLATES[0].id)
  const [theme, setTheme] = useState(FLYER_TEMPLATES[0].theme)
  const [title, setTitle] = useState('')
  const [subtitle, setSubtitle] = useState('')
  const [ctaText, setCtaText] = useState('')
  const [topic, setTopic] = useState('')
  const [audience, setAudience] = useState('the Black community')
  const [saved, setSaved] = useState([])
  const previewRef = useRef(null)

  const templates = FLYER_TEMPLATES.filter((t) => t.category === category)

  const pickTemplate = useCallback((tpl) => {
    setTemplateId(tpl.id)
    setTheme(tpl.theme)
  }, [])

  const handleGenerate = useCallback(async () => {
    try {
      const { data } = await adminApi.generateFlyerCopy({ topic: topic || 'Overlay365 community event', audience, cta: ctaText || 'Join us' })
      setTitle(data.title || '')
      setSubtitle(data.subtitle || '')
      setCtaText(data.cta_text || '')
      toast.success('AI copy generated — review and edit before exporting')
    } catch {
      toast.error('AI copy generation failed')
    }
  }, [topic, audience, ctaText])

  const handleExport = useCallback(async () => {
    try {
      await exportFlyerToPng(previewRef.current, 'overlay365-flyer.png')
      toast.success('Flyer exported as PNG')
    } catch (e) {
      toast.error(e.message || 'Export failed')
    }
  }, [])

  const handleSave = useCallback(async () => {
    try {
      await adminApi.saveFlyer({ template_id: templateId, title, subtitle, cta_text: ctaText, theme })
      toast.success('Flyer saved')
      loadSaved()
    } catch {
      toast.error('Save failed')
    }
  }, [templateId, title, subtitle, ctaText, theme])

  async function loadSaved() {
    try {
      const { data } = await adminApi.listFlyers()
      setSaved(data || [])
    } catch {
      setSaved([])
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-slate-900">Flyer Studio</h1>
        <p className="text-sm text-slate-500 mt-1">Pick a template, customize, and export a print-ready PNG.</p>
      </div>

      {/* AI assist */}
      <div className="bg-gradient-to-r from-violet-50 to-fuchsia-50 rounded-2xl border border-violet-100 p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <Wand2 className="h-4 w-4 text-violet-500" />
          <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Topic, e.g. community health fair" className="flex-1 min-w-40 px-3 py-2 rounded-xl border border-violet-200 text-sm" />
          <input value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="Audience" className="w-48 px-3 py-2 rounded-xl border border-violet-200 text-sm" />
          <button type="button" onClick={handleGenerate} className="px-4 py-2 text-sm font-bold bg-violet-600 text-white rounded-xl hover:bg-violet-700">Generate Copy</button>
        </div>
      </div>

      {/* Template gallery */}
      <div className="flex gap-2 flex-wrap">
        {CATEGORIES.map((c) => (
          <button key={c.id} type="button" onClick={() => { setCategory(c.id); setTemplateId(FLYER_TEMPLATES.find((t) => t.category === c.id).id) }} className={`px-3 py-1.5 rounded-xl text-xs font-bold ${category === c.id ? 'bg-slate-900 text-white' : 'bg-white text-slate-600 border border-slate-200'}`}>{c.label}</button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: templates + fields */}
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-2">
            <p className="text-xs font-black uppercase tracking-widest text-slate-400">Templates</p>
            <div className="grid grid-cols-2 gap-2">
              {templates.map((t) => (
                <button key={t.id} type="button" onClick={() => pickTemplate(t)} className={`text-left px-3 py-3 rounded-xl border text-xs font-bold ${templateId === t.id ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-700 hover:border-slate-400'}`}>{t.name}</button>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-3">
            <p className="text-xs font-black uppercase tracking-widest text-slate-400">Customize</p>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Headline" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <textarea value={subtitle} onChange={(e) => setSubtitle(e.target.value)} placeholder="Subtitle / message" rows={3} className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <input value={ctaText} onChange={(e) => setCtaText(e.target.value)} placeholder="CTA button text" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-500">Theme:</span>
              {FLYER_THEMES.map((th) => (
                <button key={th} type="button" onClick={() => setTheme(th)} className={`h-7 w-7 rounded-full border-2 ${theme === th ? 'border-slate-900' : 'border-transparent'}`} style={{ background: th === 'midnight' ? '#05060a' : th === 'teal' ? '#0f766e' : th === 'gold' ? '#b45309' : '#0e7490' }} title={th} />
              ))}
            </div>
          </div>

          <div className="flex gap-2">
            <button type="button" onClick={handleExport} className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-bold bg-slate-900 text-white rounded-xl"><Download className="h-4 w-4" /> Export PNG</button>
            <button type="button" onClick={handleSave} className="flex items-center gap-2 px-4 py-2.5 text-sm font-bold bg-white border border-slate-200 rounded-xl text-slate-700"><Save className="h-4 w-4" /> Save</button>
          </div>
        </div>

        {/* Right: live preview */}
        <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-200 p-6 flex items-center justify-center">
          <FlyerPreview ref={previewRef} templateId={templateId} theme={theme} title={title} subtitle={subtitle} ctaText={ctaText} />
        </div>
      </div>

      {/* Saved flyers */}
      {saved.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-4">
          <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">Saved Flyers</p>
          <div className="flex gap-2 flex-wrap">
            {saved.map((f) => (
              <button key={f.id} type="button" onClick={() => { setTemplateId(f.template_id); setTitle(f.title || ''); setSubtitle(f.subtitle || ''); setCtaText(f.cta_text || ''); setTheme(f.theme || 'midnight') }} className="px-3 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-700 hover:border-slate-400">{f.title || f.template_id}</button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Run build**

Run: `cd agent-ui && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
cd agent-ui
git add src/pages/admin/FlyersPage.jsx
git commit -m "feat(admin): add Flyer Studio page"
```

### Task 9: SEO, CRM, and Coupons pages

**Files:**
- Create: `agent-ui/src/pages/admin/SEOContentPage.jsx`
- Create: `agent-ui/src/pages/admin/CRMPage.jsx`
- Create: `agent-ui/src/pages/admin/CouponsPage.jsx`

- [ ] **Step 1: Write the SEO page**

Create `agent-ui/src/pages/admin/SEOContentPage.jsx`:

```jsx
import React, { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { Wand2, Plus, Save } from 'lucide-react'
import { adminApi } from '../../services/api'

export default function SEOContentPage() {
  const [records, setRecords] = useState([])
  const [selected, setSelected] = useState(null)
  const [topic, setTopic] = useState('')
  const [form, setForm] = useState({ slug: '', meta_title: '', meta_description: '', og_title: '', og_description: '', keywords: '', body: '', status: 'draft' })

  const load = useCallback(async () => {
    try {
      const { data } = await adminApi.listSEO()
      setRecords(data || [])
    } catch { setRecords([]) }
  }, [])

  useEffect(() => { load() }, [load])

  function openRecord(rec) {
    setSelected(rec)
    setForm({
      slug: rec.slug, meta_title: rec.meta_title || '', meta_description: rec.meta_description || '',
      og_title: rec.og_title || '', og_description: rec.og_description || '',
      keywords: rec.keywords || '', body: rec.body || '', status: rec.status || 'draft',
    })
  }

  async function handleGenerate() {
    if (!topic) return toast.error('Enter a topic first')
    try {
      const { data } = await adminApi.generateSEO({ topic, audience: 'the Black community' })
      setForm((f) => ({ ...f, meta_title: data.meta_title || f.meta_title, meta_description: data.meta_description || f.meta_description, og_title: data.og_title || f.og_title, og_description: data.og_description || f.og_description, keywords: data.keywords || f.keywords }))
      toast.success('AI drafted SEO fields — review before saving')
    } catch { toast.error('Generation failed') }
  }

  async function handleSave() {
    if (!form.slug) return toast.error('Slug is required')
    try {
      await adminApi.upsertSEO(form.slug, form)
      toast.success('Saved')
      load()
    } catch { toast.error('Save failed') }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-slate-900">SEO Content</h1>
        <p className="text-sm text-slate-500 mt-1">Manage metadata for overlay365.com pages. Published records are served to the site at build time.</p>
      </div>

      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-2xl border border-blue-100 p-4 flex items-center gap-3 flex-wrap">
        <Wand2 className="h-4 w-4 text-blue-500" />
        <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Topic for AI metadata, e.g. financial wellness" className="flex-1 min-w-40 px-3 py-2 rounded-xl border border-blue-200 text-sm" />
        <button type="button" onClick={handleGenerate} className="px-4 py-2 text-sm font-bold bg-blue-600 text-white rounded-xl">Generate</button>
        <button type="button" onClick={() => { setSelected(null); setForm({ slug: '', meta_title: '', meta_description: '', og_title: '', og_description: '', keywords: '', body: '', status: 'draft' }) }} className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl"><Plus className="h-4 w-4" /> New</button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-4">
          <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">Pages</p>
          <div className="space-y-1">
            {records.map((r) => (
              <button key={r.slug} type="button" onClick={() => openRecord(r)} className={`w-full text-left px-3 py-2.5 rounded-xl text-sm font-semibold ${selected?.slug === r.slug ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-50'}`}>
                <span>{r.slug}</span>
                <span className={`ml-2 text-[10px] font-bold uppercase ${r.status === 'published' ? 'text-green-500' : 'text-amber-500'}`}>{r.status}</span>
              </button>
            ))}
            {records.length === 0 && <p className="text-sm text-slate-400 px-3 py-4">No content records yet. Create one with "New".</p>}
          </div>
        </div>

        <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-200 p-5 space-y-3">
          <p className="text-xs font-black uppercase tracking-widest text-slate-400">Edit</p>
          <input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="slug (e.g. home, health)" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          <input value={form.meta_title} onChange={(e) => setForm({ ...form, meta_title: e.target.value })} placeholder="Meta title (under 60 chars)" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          <textarea value={form.meta_description} onChange={(e) => setForm({ ...form, meta_description: e.target.value })} placeholder="Meta description (under 160 chars)" rows={2} className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          <div className="grid grid-cols-2 gap-3">
            <input value={form.og_title} onChange={(e) => setForm({ ...form, og_title: e.target.value })} placeholder="OG title" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <input value={form.og_description} onChange={(e) => setForm({ ...form, og_description: e.target.value })} placeholder="OG description" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          </div>
          <input value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} placeholder="Keywords (comma separated)" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          <textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} placeholder="Page body content" rows={6} className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          <div className="flex items-center gap-3">
            <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className="px-3 py-2 rounded-xl border border-slate-200 text-sm">
              <option value="draft">Draft</option>
              <option value="published">Published</option>
            </select>
            <button type="button" onClick={handleSave} className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl"><Save className="h-4 w-4" /> Save</button>
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Write the CRM page**

Create `agent-ui/src/pages/admin/CRMPage.jsx`:

```jsx
import React, { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { Search, Plus } from 'lucide-react'
import { adminApi } from '../../services/api'

export default function CRMPage() {
  const [contacts, setContacts] = useState([])
  const [search, setSearch] = useState('')
  const [source, setSource] = useState('all')
  const [selected, setSelected] = useState(null)
  const [notes, setNotes] = useState([])
  const [noteText, setNoteText] = useState('')
  const [showDonor, setShowDonor] = useState(false)
  const [donor, setDonor] = useState({ name: '', email: '', phone: '', amount: '', tier: '' })

  const load = useCallback(async () => {
    try {
      const { data } = await adminApi.listContacts()
      setContacts(data || [])
    } catch { setContacts([]) }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = contacts.filter((c) => {
    const q = search.toLowerCase()
    const matchesQ = !q || `${c.name || ''} ${c.email || ''} ${c.phone || ''}`.toLowerCase().includes(q)
    const matchesSource = source === 'all' || c.source === source
    return matchesQ && matchesSource
  })

  async function openContact(c) {
    setSelected(c)
    try {
      const { data } = await adminApi.listNotes(c.source, c.id)
      setNotes(data || [])
    } catch { setNotes([]) }
  }

  async function addNote() {
    if (!noteText.trim()) return
    try {
      await adminApi.addNote(selected.source, selected.id, noteText.trim())
      setNoteText('')
      const { data } = await adminApi.listNotes(selected.source, selected.id)
      setNotes(data || [])
    } catch { toast.error('Failed to add note') }
  }

  async function createDonor() {
    try {
      await adminApi.createDonor({ ...donor, amount: Number(donor.amount || 0) })
      toast.success('Donor added')
      setShowDonor(false)
      setDonor({ name: '', email: '', phone: '', amount: '', tier: '' })
      load()
    } catch { toast.error('Failed to create donor') }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black text-slate-900">CRM</h1>
          <p className="text-sm text-slate-500 mt-1">Unified contacts — leads, donors, and signups.</p>
        </div>
        <button type="button" onClick={() => setShowDonor(true)} className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl"><Plus className="h-4 w-4" /> Add Donor</button>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center flex-1 min-w-52 bg-white border border-slate-200 rounded-2xl px-3 py-2">
          <Search className="h-4 w-4 text-slate-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, email, phone" className="bg-transparent border-none text-sm ml-2 w-full focus:outline-none" />
        </div>
        <select value={source} onChange={(e) => setSource(e.target.value)} className="px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white">
          <option value="all">All sources</option>
          <option value="lead">Leads</option>
          <option value="donor">Donors</option>
          <option value="signup">Signups</option>
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-widest text-slate-400">
              <th className="px-4 py-3">Name</th><th className="px-4 py-3">Email</th><th className="px-4 py-3">Phone</th><th className="px-4 py-3">Source</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-50">
              {filtered.map((c) => (
                <tr key={`${c.source}-${c.id}`} onClick={() => openContact(c)} className="cursor-pointer hover:bg-slate-50">
                  <td className="px-4 py-3 font-semibold text-slate-900">{c.name || '—'}</td>
                  <td className="px-4 py-3 text-slate-500">{c.email || '—'}</td>
                  <td className="px-4 py-3 text-slate-500">{c.phone || '—'}</td>
                  <td className="px-4 py-3"><span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-slate-100 text-slate-600">{c.source}</span></td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan="4" className="px-4 py-8 text-center text-slate-400 text-sm">No contacts found.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-5">
          {selected ? (
            <>
              <p className="text-sm font-black text-slate-900">{selected.name || 'Contact'}</p>
              <p className="text-xs text-slate-500 mb-2">{selected.email} · {selected.phone || 'no phone'}</p>
              {selected.amount != null && <p className="text-sm font-bold text-green-600 mb-3">Donated: ${selected.amount}</p>}
              <div className="border-t border-slate-100 pt-3">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">Notes</p>
                <div className="space-y-2 mb-3">
                  {notes.map((n) => <p key={n.id} className="text-xs text-slate-600 bg-slate-50 rounded-lg px-3 py-2">{n.note}</p>)}
                  {notes.length === 0 && <p className="text-xs text-slate-400">No notes yet.</p>}
                </div>
                <div className="flex gap-2">
                  <input value={noteText} onChange={(e) => setNoteText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addNote()} placeholder="Add a note..." className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-sm" />
                  <button type="button" onClick={addNote} className="px-3 py-2 text-xs font-bold bg-slate-900 text-white rounded-xl">Add</button>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-400 text-center py-10">Select a contact to view details and notes.</p>
          )}
        </div>
      </div>

      {showDonor && (
        <div className="fixed inset-0 bg-slate-900/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md space-y-3">
            <p className="text-sm font-black text-slate-900">Add Donor</p>
            {['name', 'email', 'phone', 'amount', 'tier'].map((k) => (
              <input key={k} value={donor[k]} onChange={(e) => setDonor({ ...donor, [k]: e.target.value })} placeholder={k} className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            ))}
            <div className="flex gap-2">
              <button type="button" onClick={createDonor} className="flex-1 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl">Save</button>
              <button type="button" onClick={() => setShowDonor(false)} className="px-4 py-2 text-sm font-bold bg-slate-100 text-slate-700 rounded-xl">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Write the Coupons page**

Create `agent-ui/src/pages/admin/CouponsPage.jsx`:

```jsx
import React, { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'
import { adminApi } from '../../services/api'

const EMPTY = { code: '', type: 'percent', value: '', min_amount: '', max_uses: '', starts_at: '', ends_at: '' }

export default function CouponsPage() {
  const [coupons, setCoupons] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY)

  const load = useCallback(async () => {
    try {
      const { data } = await adminApi.listCoupons()
      setCoupons(data || [])
    } catch { setCoupons([]) }
  }, [])

  useEffect(() => { load() }, [load])

  async function createCoupon() {
    if (!form.code || !form.value) return toast.error('Code and value are required')
    try {
      await adminApi.createCoupon({
        code: form.code, type: form.type, value: Number(form.value),
        min_amount: form.min_amount ? Number(form.min_amount) : null,
        max_uses: form.max_uses ? Number(form.max_uses) : null,
        starts_at: form.starts_at || null, ends_at: form.ends_at || null,
      })
      toast.success('Coupon created')
      setShowForm(false)
      setForm(EMPTY)
      load()
    } catch { toast.error('Failed to create coupon') }
  }

  async function disable(couponId) {
    try {
      await adminApi.disableCoupon(couponId)
      load()
    } catch { toast.error('Failed to disable') }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black text-slate-900">Coupons</h1>
          <p className="text-sm text-slate-500 mt-1">Discount codes for subscriptions. Created as Stripe coupons when configured.</p>
        </div>
        <button type="button" onClick={() => setShowForm(true)} className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl"><Plus className="h-4 w-4" /> New Coupon</button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-widest text-slate-400">
            <th className="px-4 py-3">Code</th><th className="px-4 py-3">Type</th><th className="px-4 py-3">Value</th><th className="px-4 py-3">Max Uses</th><th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Action</th>
          </tr></thead>
          <tbody className="divide-y divide-slate-50">
            {coupons.map((c) => (
              <tr key={c.id}>
                <td className="px-4 py-3 font-mono font-bold text-slate-900">{c.code}</td>
                <td className="px-4 py-3 text-slate-500">{c.type}</td>
                <td className="px-4 py-3 text-slate-500">{c.type === 'percent' ? `${c.value}%` : `$${c.value}`}</td>
                <td className="px-4 py-3 text-slate-500">{c.max_uses ?? '∞'}</td>
                <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${c.status === 'active' ? 'bg-green-100 text-green-700' : c.status === 'disabled' ? 'bg-slate-100 text-slate-500' : 'bg-amber-100 text-amber-700'}`}>{c.status}</span></td>
                <td className="px-4 py-3 text-right">{c.status !== 'disabled' && <button type="button" onClick={() => disable(c.id)} className="text-xs font-bold text-rose-600 hover:underline">Disable</button>}</td>
              </tr>
            ))}
            {coupons.length === 0 && <tr><td colSpan="6" className="px-4 py-8 text-center text-slate-400">No coupons yet.</td></tr>}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-slate-900/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md space-y-3">
            <p className="text-sm font-black text-slate-900">New Coupon</p>
            <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="Code (e.g. WELCOME20)" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <div className="flex gap-3">
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white">
                <option value="percent">Percent</option>
                <option value="amount">Amount</option>
              </select>
              <input value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} placeholder="Value" type="number" className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <input value={form.min_amount} onChange={(e) => setForm({ ...form, min_amount: e.target.value })} placeholder="Min amount" type="number" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
              <input value={form.max_uses} onChange={(e) => setForm({ ...form, max_uses: e.target.value })} placeholder="Max uses" type="number" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            </div>
            <input value={form.ends_at} onChange={(e) => setForm({ ...form, ends_at: e.target.value })} placeholder="Ends at (optional)" type="datetime-local" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <div className="flex gap-2">
              <button type="button" onClick={createCoupon} className="flex-1 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl">Create</button>
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm font-bold bg-slate-100 text-slate-700 rounded-xl">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run build**

Run: `cd agent-ui && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
cd agent-ui
git add src/pages/admin/
git commit -m "feat(admin): add SEO, CRM, and Coupons pages"
```

### Task 10: Wire routes + nav in App.jsx

**Files:**
- Modify: `agent-ui/src/App.jsx`

- [ ] **Step 1: Add lazy imports**

After the existing lazy imports in `App.jsx` (around line 90), add:

```javascript
const FlyersPage     = lazy(() => import('./pages/admin/FlyersPage'))
const SEOContentPage = lazy(() => import('./pages/admin/SEOContentPage'))
const CRMPage        = lazy(() => import('./pages/admin/CRMPage'))
const CouponsPage    = lazy(() => import('./pages/admin/CouponsPage'))
```

- [ ] **Step 2: Add the nav group**

In `NAV_GROUPS`, after the "Management" group (closing `},` at line ~157), add a new group:

```javascript
  {
    label: 'Overlay365 Admin',
    items: [
      { name: 'Flyers',      icon: LayoutDashboard, path: '/admin/flyers' },
      { name: 'SEO Content', icon: Globe,           path: '/admin/seo' },
      { name: 'CRM',         icon: Users,           path: '/admin/crm' },
      { name: 'Coupons',     icon: Zap,             path: '/admin/coupons' },
    ],
  },
```

- [ ] **Step 3: Add the routes**

In the authenticated `<Routes>` block (after the "Management" routes, before the fallback), add:

```jsx
                      {/* Overlay365 Admin */}
                      <Route path="/admin/flyers"  element={<FlyersPage />} />
                      <Route path="/admin/seo"     element={<SEOContentPage />} />
                      <Route path="/admin/crm"     element={<CRMPage />} />
                      <Route path="/admin/coupons" element={<CouponsPage />} />
```

- [ ] **Step 4: Run build + tests**

Run: `cd agent-ui && npm run build && npm test`
Expected: build succeeds and existing tests pass.

- [ ] **Step 5: Commit**

```bash
cd agent-ui
git add src/App.jsx
git commit -m "feat(admin): wire Overlay365 admin pages into navigation"
```

### Task 11: Frontend tests for flyer templates + coupons form

**Files:**
- Create: `agent-ui/src/test/FlyerTemplate.test.jsx`
- Create: `agent-ui/src/test/CouponsForm.test.jsx`

- [ ] **Step 1: Write flyer template test**

Create `agent-ui/src/test/FlyerTemplate.test.jsx`:

```jsx
import { describe, it, expect } from 'vitest'
import React from 'react'
import { render } from '@testing-library/react'
import FlyerPreview from '../pages/admin/flyers/FlyerPreview'
import { FLYER_TEMPLATES } from '../pages/admin/flyers/templates'

describe('Flyer templates', () => {
  it('registers 10+ templates across 3 categories', () => {
    expect(FLYER_TEMPLATES.length).toBeGreaterThanOrEqual(10)
    const cats = new Set(FLYER_TEMPLATES.map((t) => t.category))
    expect(cats).toEqual(new Set(['event', 'donation', 'business']))
  })

  it('renders the title, subtitle, and CTA for every template', () => {
    for (const tpl of FLYER_TEMPLATES) {
      const { container } = render(
        <FlyerPreview templateId={tpl.id} theme={tpl.theme} title="Health Fair" subtitle="Free screenings" ctaText="Register" />
      )
      expect(container.textContent).toContain('Health Fair')
      expect(container.textContent).toContain('Free screenings')
      expect(container.textContent).toContain('Register')
    }
  })
})
```

- [ ] **Step 2: Write the coupons form test**

Create `agent-ui/src/test/CouponsForm.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import CouponsPage from '../pages/admin/CouponsPage'

const mockList = vi.fn()
const mockCreate = vi.fn()
const mockDisable = vi.fn()

vi.mock('../services/api', () => ({
  default: {
    listCoupons: (...a) => mockList(...a),
    createCoupon: (...a) => mockCreate(...a),
    disableCoupon: (...a) => mockDisable(...a),
  },
}))

describe('CouponsPage', () => {
  beforeEach(() => {
    mockList.mockResolvedValue({ data: [{ id: '1', code: 'WELCOME20', type: 'percent', value: 20, max_uses: null, status: 'local_only' }] })
  })

  it('renders existing coupons', async () => {
    render(<CouponsPage />)
    expect(await screen.findByText('WELCOME20')).toBeTruthy()
  })

  it('opens the form and creates a coupon', async () => {
    mockCreate.mockResolvedValue({ data: { id: '2' } })
    render(<CouponsPage />)
    fireEvent.click(await screen.findByText('New Coupon'))
    fireEvent.change(screen.getByPlaceholderText('Code (e.g. WELCOME20)'), { target: { value: 'TEST10' } })
    fireEvent.change(screen.getByPlaceholderText('Value'), { target: { value: '10' } })
    fireEvent.click(screen.getByText('Create'))
    await waitFor(() => expect(mockCreate).toHaveBeenCalled())
  })
})
```

- [ ] **Step 3: Run frontend tests**

Run: `cd agent-ui && npm test`
Expected: all pass (existing + new).

- [ ] **Step 4: Fix jsdom globals if needed**

If `@testing-library/react` / `jsdom` are not installed as devDependencies, add them:
Run: `cd agent-ui && npm install -D @testing-library/react @testing-library/jest-dom jsdom`
Then add `import '@testing-library/jest-dom'` to `src/test/setup.js`.

- [ ] **Step 5: Commit**

```bash
cd agent-ui
git add src/test/
git commit -m "test(admin): add flyer template and coupons form tests"
```

### Task 12: End-to-end verification + docs

**Files:**
- Modify: `docs/ARCHITECTURE.md` (optional)

- [ ] **Step 1: Run backend suite**

Run: `python -m pytest tests/unit -q --no-cov -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 2: Run frontend suite + build**

Run: `cd agent-ui && npm test && npm run build`
Expected: tests pass, build succeeds.

- [ ] **Step 3: Manual smoke — start backend + frontend**

Run backend: `uvicorn api.main:app --port 8000` (with dev env vars set)
Run frontend: `cd agent-ui && npm run dev`
Verify in browser: login → "Overlay365 Admin" group → each of Flyers / SEO / CRM / Coupons loads; a flyer exports to PNG; a coupon creates.

- [ ] **Step 4: Push**

```bash
git push origin main
```

- [ ] **Step 5: Commit any doc updates**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: document Overlay365 admin suite"  # if changed
```
