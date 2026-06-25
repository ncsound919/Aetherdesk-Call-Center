import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


# ── Tenant Branding ────────────────────────────────────────────────

async def get_tenant_branding_db(tenant_id: str):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow(
                "SELECT * FROM tenant_branding WHERE tenant_id = $1", tenant_id
            )
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM tenant_branding WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    return None


async def set_tenant_branding_db(tenant_id: str, config: dict):
    now = datetime.now(UTC).isoformat()
    existing = await get_tenant_branding_db(tenant_id)

    if existing:
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                set_parts = []
                params = []
                idx = 1
                for k, v in config.items():
                    if v is not None:
                        set_parts.append(f"{k} = ${idx}")
                        params.append(v)
                        idx += 1
                set_parts.append("updated_at = NOW()")
                params.append(tenant_id)
                await pool.execute(
                    f"UPDATE tenant_branding SET {', '.join(set_parts)} WHERE tenant_id = ${idx}",
                    *params
                )
        else:
            conn = _get_sqlite_conn()
            try:
                set_parts = []
                params = []
                for k, v in config.items():
                    if v is not None:
                        set_parts.append(f"{k} = ?")
                        params.append(v)
                set_parts.append("updated_at = ?")
                params.append(now)
                params.append(tenant_id)
                conn.execute(
                    f"UPDATE tenant_branding SET {', '.join(set_parts)} WHERE tenant_id = ?",
                    params
                )
                conn.commit()
            finally:
                conn.close()
    else:
        brand_id = str(uuid.uuid4())
        company_name = config.get("company_name", "")
        logo_url = config.get("logo_url", "")
        primary_color = config.get("primary_color", "#2563eb")
        secondary_color = config.get("secondary_color", "#7c3aed")
        favicon_url = config.get("favicon_url", "")

        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                await pool.execute("""
                    INSERT INTO tenant_branding (id, tenant_id, company_name, logo_url, primary_color, secondary_color, favicon_url, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
                """, brand_id, tenant_id, company_name, logo_url, primary_color, secondary_color, favicon_url)
        else:
            conn = _get_sqlite_conn()
            try:
                conn.execute("""
                    INSERT INTO tenant_branding (id, tenant_id, company_name, logo_url, primary_color, secondary_color, favicon_url, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (brand_id, tenant_id, company_name, logo_url, primary_color, secondary_color, favicon_url, now, now))
                conn.commit()
            finally:
                conn.close()

    return await get_tenant_branding_db(tenant_id)


async def list_white_label_tenants_db():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT tb.*, t.name as tenant_name, t.email as tenant_email
                FROM tenant_branding tb
                JOIN tenants t ON t.id = tb.tenant_id
                ORDER BY tb.updated_at DESC
            """)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT tb.*, t.name as tenant_name, t.email as tenant_email
                FROM tenant_branding tb
                JOIN tenants t ON t.id = tb.tenant_id
                ORDER BY tb.updated_at DESC
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    return []


# ── Custom Domains ─────────────────────────────────────────────────

async def get_custom_domain_db(tenant_id: str):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow(
                "SELECT * FROM custom_domains WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 1",
                tenant_id
            )
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM custom_domains WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 1",
                (tenant_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    return None


async def set_custom_domain_db(tenant_id: str, domain: str, ssl_status: str = "pending"):
    domain_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO custom_domains (id, tenant_id, domain, ssl_status, verified, created_at)
                VALUES ($1, $2, $3, $4, FALSE, NOW())
            """, domain_id, tenant_id, domain, ssl_status)
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                INSERT INTO custom_domains (id, tenant_id, domain, ssl_status, verified, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
            """, (domain_id, tenant_id, domain, ssl_status, now))
            conn.commit()
        finally:
            conn.close()

    return await get_custom_domain_db(tenant_id)


async def verify_domain_db(domain_id: str):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "UPDATE custom_domains SET verified = TRUE, ssl_status = 'active' WHERE id = $1",
                domain_id
            )
            row = await pool.fetchrow("SELECT * FROM custom_domains WHERE id = $1", domain_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute(
                "UPDATE custom_domains SET verified = 1, ssl_status = 'active' WHERE id = ?",
                (domain_id,)
            )
            conn.commit()
            row = conn.execute("SELECT * FROM custom_domains WHERE id = ?", (domain_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    return None


# ── Onboarding Progress ────────────────────────────────────────────

async def get_onboarding_progress_db(tenant_id: str):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow(
                "SELECT * FROM onboarding_progress WHERE tenant_id = $1", tenant_id
            )
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM onboarding_progress WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    return None


async def create_onboarding_progress_db(tenant_id: str):
    prog_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO onboarding_progress (id, tenant_id, steps_completed_json, current_step, completed, created_at, updated_at)
                VALUES ($1, $2, '[]', 'welcome', FALSE, NOW(), NOW())
            """, prog_id, tenant_id)
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                INSERT INTO onboarding_progress (id, tenant_id, steps_completed_json, current_step, completed, created_at, updated_at)
                VALUES (?, ?, '[]', 'welcome', 0, ?, ?)
            """, (prog_id, tenant_id, now, now))
            conn.commit()
        finally:
            conn.close()

    return await get_onboarding_progress_db(tenant_id)


async def complete_onboarding_step_db(tenant_id: str, step: str):
    existing = await get_onboarding_progress_db(tenant_id)
    if not existing:
        existing = await create_onboarding_progress_db(tenant_id)

    steps = json.loads(existing.get("steps_completed_json", "[]"))
    if step not in steps:
        steps.append(step)

    all_steps = ["welcome", "phone_number", "quickstart", "health_check"]
    completed = len(steps) >= len(all_steps)
    current_step = "done" if completed else all_steps[len(steps)]

    now = datetime.now(UTC).isoformat()

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                UPDATE onboarding_progress
                SET steps_completed_json = $1::jsonb, current_step = $2, completed = $3, updated_at = NOW()
                WHERE tenant_id = $4
            """, json.dumps(steps), current_step, completed, tenant_id)
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                UPDATE onboarding_progress
                SET steps_completed_json = ?, current_step = ?, completed = ?, updated_at = ?
                WHERE tenant_id = ?
            """, (json.dumps(steps), current_step, 1 if completed else 0, now, tenant_id))
            conn.commit()
        finally:
            conn.close()

    return await get_onboarding_progress_db(tenant_id)


# ── Tenant Config (for self-serve provisioning) ────────────────────

async def get_tenant_config_value_db(tenant_id: str, key: str):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow(
                "SELECT value FROM tenant_config WHERE tenant_id = $1 AND key = $2",
                tenant_id, key
            )
            return row["value"] if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT value FROM tenant_config WHERE tenant_id = ? AND key = ?",
                (tenant_id, key)
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()

    return None


async def set_tenant_config_value_db(tenant_id: str, key: str, value: str):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO tenant_config (tenant_id, key, value)
                VALUES ($1, $2, $3)
                ON CONFLICT (tenant_id, key) DO UPDATE SET value = $3
            """, tenant_id, key, value)
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO tenant_config (tenant_id, key, value)
                VALUES (?, ?, ?)
            """, (tenant_id, key, value))
            conn.commit()
        finally:
            conn.close()
