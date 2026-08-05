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
