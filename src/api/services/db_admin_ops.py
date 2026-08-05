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
    # db_pool's SQLite connections use _dict_factory, so rows are already
    # dicts. Pass dicts through untouched; zip only for tuple rows (defensive).
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return dict(zip(keys, row, strict=False))


# ── SEO content ──────────────────────────────────────────────────────

SEO_KEYS = (
    "id",
    "slug",
    "meta_title",
    "meta_description",
    "og_title",
    "og_description",
    "og_image",
    "keywords",
    "body",
    "status",
    "updated_at",
    "created_at",
)


async def list_seo_content_db(status=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if status:
                recs = await pool.fetch(
                    "SELECT * FROM seo_content WHERE status = $1 ORDER BY created_at DESC",
                    status,
                )
            else:
                recs = await pool.fetch(
                    "SELECT * FROM seo_content ORDER BY created_at DESC"
                )
            return [dict(r) for r in recs]
    conn = _get_sqlite_conn()
    if status:
        cur = conn.execute(
            "SELECT * FROM seo_content WHERE status = ? ORDER BY created_at DESC",
            (status,),
        )
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
    return _row_to_dict(
        conn.execute("SELECT * FROM seo_content WHERE slug = ?", (slug,)).fetchone(),
        SEO_KEYS,
    )


async def upsert_seo_content_db(slug, data):
    now = _now()
    cid = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            r = await pool.fetchrow(
                """
                INSERT INTO seo_content (id, slug, meta_title, meta_description, og_title, og_description, og_image, keywords, body, status, updated_at, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$11)
                ON CONFLICT (slug) DO UPDATE SET
                  meta_title=EXCLUDED.meta_title, meta_description=EXCLUDED.meta_description,
                  og_title=EXCLUDED.og_title, og_description=EXCLUDED.og_description,
                  og_image=EXCLUDED.og_image, keywords=EXCLUDED.keywords,
                  body=EXCLUDED.body, status=EXCLUDED.status, updated_at=EXCLUDED.updated_at
                RETURNING *
            """,
                cid,
                slug,
                data.get("meta_title"),
                data.get("meta_description"),
                data.get("og_title"),
                data.get("og_description"),
                data.get("og_image"),
                data.get("keywords"),
                data.get("body"),
                data.get("status", "draft"),
                now,
            )
            return dict(r) if r else None
    conn = _get_sqlite_conn()
    existing = conn.execute(
        "SELECT id FROM seo_content WHERE slug = ?", (slug,)
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE seo_content SET meta_title=?, meta_description=?, og_title=?, og_description=?,
              og_image=?, keywords=?, body=?, status=?, updated_at=? WHERE slug=?
        """,
            (
                data.get("meta_title"),
                data.get("meta_description"),
                data.get("og_title"),
                data.get("og_description"),
                data.get("og_image"),
                data.get("keywords"),
                data.get("body"),
                data.get("status", "draft"),
                now,
                slug,
            ),
        )
        conn.commit()
        return await get_seo_content_db(slug)
    conn.execute(
        """
        INSERT INTO seo_content (id, slug, meta_title, meta_description, og_title, og_description, og_image, keywords, body, status, updated_at, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """,
        (
            cid,
            slug,
            data.get("meta_title"),
            data.get("meta_description"),
            data.get("og_title"),
            data.get("og_description"),
            data.get("og_image"),
            data.get("keywords"),
            data.get("body"),
            data.get("status", "draft"),
            now,
            now,
        ),
    )
    conn.commit()
    return await get_seo_content_db(slug)


# ── Donors ───────────────────────────────────────────────────────────

DONOR_KEYS = (
    "id",
    "name",
    "email",
    "phone",
    "amount",
    "currency",
    "tier",
    "notes",
    "donation_date",
    "created_at",
)


async def list_donors_db():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return [
                dict(r)
                for r in await pool.fetch(
                    "SELECT * FROM donors ORDER BY donation_date DESC"
                )
            ]
    conn = _get_sqlite_conn()
    return [
        _row_to_dict(r, DONOR_KEYS)
        for r in conn.execute(
            "SELECT * FROM donors ORDER BY donation_date DESC"
        ).fetchall()
    ]


async def create_donor_db(
    name, email, phone, amount, currency, tier, notes, donation_date
):
    did = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "INSERT INTO donors (id,name,email,phone,amount,currency,tier,notes,donation_date) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                did,
                name,
                email,
                phone,
                amount,
                currency,
                tier,
                notes,
                donation_date,
            )
            r = await pool.fetchrow("SELECT * FROM donors WHERE id=$1", did)
            return dict(r)
    conn = _get_sqlite_conn()
    conn.execute(
        "INSERT INTO donors (id,name,email,phone,amount,currency,tier,notes,donation_date) VALUES (?,?,?,?,?,?,?,?,?)",
        (did, name, email, phone, amount, currency, tier, notes, donation_date),
    )
    conn.commit()
    return _row_to_dict(
        conn.execute("SELECT * FROM donors WHERE id=?", (did,)).fetchone(), DONOR_KEYS
    )


# ── Coupons ──────────────────────────────────────────────────────────

COUPON_KEYS = (
    "id",
    "code",
    "type",
    "value",
    "min_amount",
    "max_uses",
    "starts_at",
    "ends_at",
    "stripe_coupon_id",
    "status",
    "created_at",
)


async def list_coupons_db():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return [
                dict(r)
                for r in await pool.fetch(
                    "SELECT * FROM coupons ORDER BY created_at DESC"
                )
            ]
    conn = _get_sqlite_conn()
    return [
        _row_to_dict(r, COUPON_KEYS)
        for r in conn.execute(
            "SELECT * FROM coupons ORDER BY created_at DESC"
        ).fetchall()
    ]


async def create_coupon_db(
    code,
    ctype,
    value,
    min_amount,
    max_uses,
    starts_at,
    ends_at,
    stripe_coupon_id,
    status,
):
    cid = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "INSERT INTO coupons (id,code,type,value,min_amount,max_uses,starts_at,ends_at,stripe_coupon_id,status) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                cid,
                code,
                ctype,
                value,
                min_amount,
                max_uses,
                starts_at,
                ends_at,
                stripe_coupon_id,
                status,
            )
            r = await pool.fetchrow("SELECT * FROM coupons WHERE id=$1", cid)
            return dict(r)
    conn = _get_sqlite_conn()
    conn.execute(
        "INSERT INTO coupons (id,code,type,value,min_amount,max_uses,starts_at,ends_at,stripe_coupon_id,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            cid,
            code,
            ctype,
            value,
            min_amount,
            max_uses,
            starts_at,
            ends_at,
            stripe_coupon_id,
            status,
        ),
    )
    conn.commit()
    return _row_to_dict(
        conn.execute("SELECT * FROM coupons WHERE id=?", (cid,)).fetchone(), COUPON_KEYS
    )


async def set_coupon_status_db(coupon_id, status):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "UPDATE coupons SET status=$2 WHERE id=$1", coupon_id, status
            )
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
                nid,
                source,
                contact_id,
                note,
            )
            return
    conn = _get_sqlite_conn()
    conn.execute(
        "INSERT INTO contact_notes (id,source,contact_id,note) VALUES (?,?,?,?)",
        (nid, source, contact_id, note),
    )
    conn.commit()


async def list_contact_notes_db(source, contact_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return [
                dict(r)
                for r in await pool.fetch(
                    "SELECT * FROM contact_notes WHERE source=$1 AND contact_id=$2 ORDER BY created_at DESC",
                    source,
                    contact_id,
                )
            ]
    conn = _get_sqlite_conn()
    return [
        _row_to_dict(r, NOTE_KEYS)
        for r in conn.execute(
            "SELECT * FROM contact_notes WHERE source=? AND contact_id=? ORDER BY created_at DESC",
            (source, contact_id),
        ).fetchall()
    ]


# ── Flyer saves ──────────────────────────────────────────────────────

FLYER_KEYS = (
    "id",
    "template_id",
    "title",
    "subtitle",
    "cta_text",
    "cta_url",
    "theme",
    "logo_url",
    "config_json",
    "created_at",
)


async def list_flyer_saves_db():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return [
                dict(r)
                for r in await pool.fetch(
                    "SELECT * FROM flyer_saves ORDER BY created_at DESC"
                )
            ]
    conn = _get_sqlite_conn()
    rows = [
        _row_to_dict(r, FLYER_KEYS)
        for r in conn.execute(
            "SELECT * FROM flyer_saves ORDER BY created_at DESC"
        ).fetchall()
    ]
    for r in rows:
        if isinstance(r.get("config_json"), str):
            try:
                r["config_json"] = json.loads(r["config_json"])
            except json.JSONDecodeError:
                r["config_json"] = {}
    return rows


async def create_flyer_save_db(
    template_id, title, subtitle, cta_text, cta_url, theme, logo_url, config
):
    fid = str(uuid.uuid4())
    config_json = json.dumps(config or {})
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "INSERT INTO flyer_saves (id,template_id,title,subtitle,cta_text,cta_url,theme,logo_url,config_json) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                fid,
                template_id,
                title,
                subtitle,
                cta_text,
                cta_url,
                theme,
                logo_url,
                config_json,
            )
            r = await pool.fetchrow("SELECT * FROM flyer_saves WHERE id=$1", fid)
            return dict(r)
    conn = _get_sqlite_conn()
    conn.execute(
        "INSERT INTO flyer_saves (id,template_id,title,subtitle,cta_text,cta_url,theme,logo_url,config_json) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            fid,
            template_id,
            title,
            subtitle,
            cta_text,
            cta_url,
            theme,
            logo_url,
            config_json,
        ),
    )
    conn.commit()
    return _row_to_dict(
        conn.execute("SELECT * FROM flyer_saves WHERE id=?", (fid,)).fetchone(),
        FLYER_KEYS,
    )
