import json
import secrets
import uuid
from datetime import timezone, datetime
from typing import Optional

import structlog

from apps.api.services.db_config import USE_POSTGRES
from apps.api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


# ── Database Operations ─────────────────────────────────────────

# --- Tenants ---

async def create_tenant(name, email, slug, phone=None, plan_id=None, settings=None, gdpr_consent=False):
    tenant_id = str(uuid.uuid4())
    api_key = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO tenants (id, name, slug, email, phone, plan_id, settings, gdpr_consent, gdpr_consented_at, api_key, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW())
            """, tenant_id, name, slug, email, phone, plan_id, json.dumps(settings or {}), gdpr_consent, gdpr_consent, api_key)
            return await pool.fetchrow("SELECT * FROM tenants WHERE id = $1", tenant_id)
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                INSERT INTO tenants (id, name, slug, email, phone, plan_id, settings, gdpr_consent, gdpr_consented_at, api_key, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tenant_id, name, slug, email, phone, plan_id, json.dumps(settings or {}),
                  gdpr_consent, now.isoformat() if gdpr_consent else None, api_key, now.isoformat(), now.isoformat()))
            conn.commit()
            row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
            return row
        finally:
            conn.close()


async def get_tenant_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT * FROM tenants WHERE id = $1", tenant_id)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        conn.close()
        return row


async def list_tenants_db():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetch("SELECT * FROM tenants WHERE is_active = true ORDER BY created_at DESC")
    else:
        conn = _get_sqlite_conn()
        rows = conn.execute("SELECT * FROM tenants WHERE is_active = 1 ORDER BY created_at DESC").fetchall()
        conn.close()
        return rows


async def get_tenant_by_api_key(api_key):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT id, name FROM tenants WHERE api_key = $1", api_key)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT id, name FROM tenants WHERE api_key = ?", (api_key,)).fetchone()
        conn.close()
        return row
    return None


async def verify_tenant_api_key(tenant_id: str, api_key: str) -> bool:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT 1 FROM tenants WHERE id = $1 AND api_key = $2", tenant_id, api_key)
            return row is not None
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT 1 FROM tenants WHERE id = ? AND api_key = ?", (tenant_id, api_key)).fetchone()
        conn.close()
        return row is not None
    return False


# --- Agents ---

async def create_agent(tenant_id, name, display_name, agent_type="ai", skills=None, config=None, phone=None, email=None):
    agent_id = str(uuid.uuid4())
    sip_extension = f"3{agent_id[:6]}"
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO agents (id, tenant_id, name, display_name, agent_type, skills, config, phone, email, sip_extension, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'offline', NOW(), NOW())
            """, agent_id, tenant_id, name, display_name or name, agent_type, json.dumps(skills or []), json.dumps(config or {}), phone, email, sip_extension)
            return await pool.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                INSERT INTO agents (id, tenant_id, name, display_name, agent_type, skills, config, phone, email, sip_extension, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'offline', ?, ?)
            """, (agent_id, tenant_id, name, display_name or name, agent_type, json.dumps(skills or []), json.dumps(config or {}), phone, email, sip_extension, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
            conn.commit()
            row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            return row
        finally:
            conn.close()


async def get_agent_db(agent_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        conn.close()
        return row


async def list_agents(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetch("SELECT * FROM agents WHERE tenant_id = $1 ORDER BY name", tenant_id)
    else:
        conn = _get_sqlite_conn()
        rows = conn.execute("SELECT * FROM agents WHERE tenant_id = ? ORDER BY name", (tenant_id,)).fetchall()
        conn.close()
        return rows


async def update_agent_status(agent_id, status, session_ref=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.fetchval("""
                SELECT * FROM update_agent_status($1, $2, $3)
            """, agent_id, status, session_ref)
            return json.loads(result) if result else {"success": False, "error": "function returned null"}
    else:
        conn = _get_sqlite_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE agents SET status = ?, last_seen_at = ?, updated_at = ? WHERE id = ?",
                     (status, now, now, agent_id))
        agent_row = conn.execute("SELECT tenant_id, status FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if agent_row:
            conn.execute("""
                INSERT INTO agent_activity (agent_id, tenant_id, activity_type, status_before, status_after, session_ref, created_at)
                VALUES (?, ?, 'status_change', ?, ?, ?, ?)
            """, (agent_id, agent_row['tenant_id'], agent_row['status'], status, session_ref, now))
        conn.commit()
        conn.close()
        return {"success": True, "agent_id": agent_id, "new_status": status}


async def update_agent_db(agent_id, tenant_id, name=None, display_name=None, agent_type=None, skills=None, config=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            fields = []
            values = []
            idx = 1
            if name is not None:
                fields.append(f"name = ${idx}"); values.append(name); idx += 1
            if display_name is not None:
                fields.append(f"display_name = ${idx}"); values.append(display_name); idx += 1
            if agent_type is not None:
                fields.append(f"agent_type = ${idx}"); values.append(agent_type); idx += 1
            if skills is not None:
                fields.append(f"skills = ${idx}"); values.append(json.dumps(skills)); idx += 1
            if config is not None:
                fields.append(f"config = ${idx}"); values.append(json.dumps(config)); idx += 1
            if fields:
                fields.append("updated_at = NOW()")
                values.extend([agent_id, tenant_id])
                query = f"UPDATE agents SET {', '.join(fields)} WHERE id = ${idx} AND tenant_id = ${idx+1}"  # nosec B608 — field names are code constants
                await pool.execute(query, *values)
            return await pool.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
    else:
        conn = _get_sqlite_conn()
        fields = []
        values = []
        if name is not None:
            fields.append("name = ?"); values.append(name)
        if display_name is not None:
            fields.append("display_name = ?"); values.append(display_name)
        if agent_type is not None:
            fields.append("agent_type = ?"); values.append(agent_type)
        if skills is not None:
            fields.append("skills = ?"); values.append(json.dumps(skills))
        if config is not None:
            fields.append("config = ?"); values.append(json.dumps(config))
        if fields:
            fields.append("updated_at = ?"); values.append(datetime.now(timezone.utc).isoformat())
            values.extend([agent_id, tenant_id])
            conn.execute(f"UPDATE agents SET {', '.join(fields)} WHERE id = ? AND tenant_id = ?", values)  # nosec B608 — field names are code constants
            conn.commit()
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        conn.close()
        return row


async def delete_agent_db(agent_id, tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.execute("DELETE FROM agents WHERE id = $1 AND tenant_id = $2", agent_id, tenant_id)
            return result != "DELETE 0"
    else:
        conn = _get_sqlite_conn()
        conn.execute("DELETE FROM agents WHERE id = ? AND tenant_id = ?", (agent_id, tenant_id))
        affected = conn.total_changes
        conn.commit()
        conn.close()
        return affected > 0


def _parse_skills(skills_value) -> list:
    if skills_value is None:
        return []
    if isinstance(skills_value, list):
        return skills_value
    if isinstance(skills_value, str):
        try:
            parsed = json.loads(skills_value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


async def get_available_agents(tenant_id, skills=None):
    skills_filter = skills or []
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if skills_filter:
                return await pool.fetch("""
                    SELECT * FROM agents WHERE tenant_id = $1 AND status = 'available'
                    AND skills @> $2 ORDER BY total_calls ASC
                """, tenant_id, json.dumps(skills_filter))
            return await pool.fetch("""
                SELECT * FROM agents WHERE tenant_id = $1 AND status = 'available' ORDER BY total_calls ASC
            """, tenant_id)
    else:
        conn = _get_sqlite_conn()
        rows = conn.execute("SELECT * FROM agents WHERE tenant_id = ? AND status = 'available' ORDER BY total_calls ASC", (tenant_id,)).fetchall()
        conn.close()
        if skills_filter:
            return [r for r in rows if any(s in _parse_skills(r.get('skills')) for s in skills_filter)]
        return rows


# --- Agent Profiles ---

async def create_agent_profile_db(profile_id, tenant_id, name, prompt, parameters):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "INSERT INTO agent_profiles (id, tenant_id, name, prompt, parameters) VALUES ($1, $2, $3, $4, $5)",
                profile_id, tenant_id, name, prompt, json.dumps(parameters)
            )
    else:
        conn = _get_sqlite_conn()
        conn.execute(
            "INSERT INTO agent_profiles (id, tenant_id, name, prompt, parameters) VALUES (?, ?, ?, ?, ?)",
            (profile_id, tenant_id, name, prompt, json.dumps(parameters))
        )
        conn.commit()
        conn.close()


# --- Tenant Settings ---

async def get_tenant_settings_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT * FROM tenant_settings WHERE tenant_id = $1", tenant_id)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT * FROM tenant_settings WHERE tenant_id = ?", (tenant_id,)).fetchone()
        conn.close()
        return row
    return None


async def update_tenant_settings_db(tenant_id, settings):
    api_feeds = json.dumps(settings.get("api_feeds"))
    auto_mode_enabled = int(settings.get("auto_mode_enabled", 0))
    redact_pii = int(settings.get("redact_pii", 1))
    require_consent = int(settings.get("require_consent", 1))
    sync_dnc = int(settings.get("sync_dnc", 0))
    mcp_servers = json.dumps(settings.get("mcp_servers", "{}"))

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                """INSERT INTO tenant_settings (tenant_id, api_feeds, auto_mode_enabled, redact_pii, require_consent, sync_dnc, mcp_servers)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)
                   ON CONFLICT(tenant_id) DO UPDATE SET
                   api_feeds=EXCLUDED.api_feeds,
                   auto_mode_enabled=EXCLUDED.auto_mode_enabled,
                   redact_pii=EXCLUDED.redact_pii,
                   require_consent=EXCLUDED.require_consent,
                   sync_dnc=EXCLUDED.sync_dnc,
                   mcp_servers=EXCLUDED.mcp_servers""",
                tenant_id, api_feeds, auto_mode_enabled, redact_pii, require_consent, sync_dnc, mcp_servers
            )
    else:
        conn = _get_sqlite_conn()
        conn.execute(
            """INSERT INTO tenant_settings (tenant_id, api_feeds, auto_mode_enabled, redact_pii, require_consent, sync_dnc, mcp_servers)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tenant_id) DO UPDATE SET
               api_feeds=excluded.api_feeds,
               auto_mode_enabled=excluded.auto_mode_enabled,
               redact_pii=excluded.redact_pii,
               require_consent=excluded.require_consent,
               sync_dnc=excluded.sync_dnc,
               mcp_servers=excluded.mcp_servers""",
            (tenant_id, api_feeds, auto_mode_enabled, redact_pii, require_consent, sync_dnc, mcp_servers)
        )
        conn.commit()
        conn.close()


# --- User Helpers ---

async def get_user_by_email_db(email):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT id, tenant_id, email, password_hash, role, full_name FROM users WHERE email = $1", email)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute(
            "SELECT id, tenant_id, email, password_hash, role, full_name FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()
        return row
    return None


async def create_user_db(email: str, password_hash: str, full_name: str, tenant_id: str = None, role: str = "owner"):
    """Create a new user account."""
    user_id = str(uuid.uuid4())
    verification_token = secrets.token_urlsafe(32)

    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO users (id, email, password_hash, full_name, tenant_id, role, verification_token)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                user_id, email, password_hash, full_name, tenant_id, role, verification_token
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO users (id, email, password_hash, full_name, tenant_id, role, verification_token)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, email, password_hash, full_name, tenant_id, role, verification_token)
        )
        conn.commit()

    return {"id": user_id, "email": email, "verification_token": verification_token}


async def get_user_by_id_db(user_id: str):
    """Get user by ID."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, email, full_name, email_verified, tenant_id, role, onboarding_completed, onboarding_step, created_at FROM users WHERE id = $1",
                user_id
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, email, full_name, email_verified, tenant_id, role, onboarding_completed, onboarding_step, created_at FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()

    if not row:
        return None
    return dict(row) if USE_POSTGRES else {k: row[k] for k in row.keys()}


async def verify_user_email_db(verification_token: str):
    """Verify user email by token. Returns user_id or None."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM users WHERE verification_token = $1",
                verification_token
            )
            if row:
                await conn.execute(
                    "UPDATE users SET email_verified = TRUE, verification_token = NULL, updated_at = NOW() WHERE id = $1",
                    row["id"]
                )
                return row["id"]
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE verification_token = ?", (verification_token,))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE users SET email_verified = 1, verification_token = NULL, updated_at = datetime('now') WHERE id = ?", (row[0],))
            conn.commit()
            return row[0]
    return None


async def set_password_reset_token_db(email: str):
    """Generate password reset token. Returns (user_id, token) or (None, None)."""
    token = secrets.token_urlsafe(32)

    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM users WHERE email = $1", email)
            if row:
                await conn.execute(
                    "UPDATE users SET reset_token = $1, reset_token_expires = NOW() + INTERVAL '1 hour' WHERE id = $2",
                    token, row["id"]
                )
                return row["id"], token
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            from datetime import timedelta
            expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            cursor.execute("UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE id = ?", (token, expires, row[0]))
            conn.commit()
            return row[0], token
    return None, None


async def reset_password_db(reset_token: str, new_password_hash: str):
    """Reset password using token. Returns user_id or None."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM users WHERE reset_token = $1 AND reset_token_expires > NOW()",
                reset_token
            )
            if row:
                await conn.execute(
                    "UPDATE users SET password_hash = $1, reset_token = NULL, reset_token_expires = NULL, updated_at = NOW() WHERE id = $2",
                    new_password_hash, row["id"]
                )
                return row["id"]
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "SELECT id FROM users WHERE reset_token = ? AND reset_token_expires > ?",
            (reset_token, now)
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expires = NULL, updated_at = datetime('now') WHERE id = ?",
                (new_password_hash, row[0])
            )
            conn.commit()
            return row[0]
    return None


async def update_user_onboarding_db(user_id: str, step: int, completed: bool = False):
    """Update onboarding progress."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET onboarding_step = $1, onboarding_completed = $2, updated_at = NOW() WHERE id = $3",
                step, completed, user_id
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET onboarding_step = ?, onboarding_completed = ?, updated_at = datetime('now') WHERE id = ?",
            (step, 1 if completed else 0, user_id)
        )
        conn.commit()


# --- Billing / Plan helpers ---

async def update_tenant_subscription_db(tenant_id: str, stripe_customer_id: str = None, stripe_subscription_id: str = None, plan_id: str = None, plan_ends_at: str = None):
    """Update tenant Stripe subscription fields."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE tenants SET
                   stripe_customer_id = COALESCE($1, stripe_customer_id),
                   stripe_subscription_id = COALESCE($2, stripe_subscription_id),
                   plan_id = COALESCE($3, plan_id),
                   plan_ends_at = COALESCE($4, plan_ends_at),
                   updated_at = NOW()
                   WHERE id = $5""",
                stripe_customer_id, stripe_subscription_id, plan_id, plan_ends_at, tenant_id
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE tenants SET
               stripe_customer_id = COALESCE(?, stripe_customer_id),
               stripe_subscription_id = COALESCE(?, stripe_subscription_id),
               plan_id = COALESCE(?, plan_id),
               plan_ends_at = COALESCE(?, plan_ends_at),
               updated_at = datetime('now')
               WHERE id = ?""",
            (stripe_customer_id, stripe_subscription_id, plan_id, plan_ends_at, tenant_id)
        )
        conn.commit()
        conn.close()


async def get_tenant_by_stripe_customer_db(stripe_customer_id: str):
    """Look up tenant by Stripe customer ID."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow("SELECT id, plan_id FROM tenants WHERE stripe_customer_id = $1", stripe_customer_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, plan_id FROM tenants WHERE stripe_customer_id = ?", (stripe_customer_id,))
        row = cursor.fetchone()
        conn.close()
        return row


async def record_usage_db(tenant_id: str, metric: str, quantity: float, period_start: str, period_end: str):
    """Record metered usage (e.g., agent minutes) for a tenant billing period."""
    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO billing_records (id, tenant_id, period_start, period_end, total_minutes, total_agent_hours, status, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, 0, $5, 'pending', NOW(), NOW())""",
                record_id, tenant_id, period_start, period_end, quantity
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO billing_records (id, tenant_id, period_start, period_end, total_agent_hours, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (record_id, tenant_id, period_start, period_end, quantity, now, now)
        )
        conn.commit()
        conn.close()


async def get_tenant_plan_db(tenant_id: str):
    """Get tenant's plan with limits. Returns (plan_name, max_concurrent_calls, max_agents) or None."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                """SELECT p.name AS plan_name, p.max_concurrent_calls, p.max_agents
                   FROM tenants t LEFT JOIN plans p ON t.plan_id = p.id
                   WHERE t.id = $1""",
                tenant_id
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT p.name AS plan_name, p.max_concurrent_calls, p.max_agents
               FROM tenants t LEFT JOIN plans p ON t.plan_id = p.id
               WHERE t.id = ?""",
            (tenant_id,)
        )
        return cursor.fetchone()


async def count_active_agents_db(tenant_id: str) -> int:
    """Count active agents for tenant (for plan enforcement)."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM agents WHERE tenant_id = $1 AND is_active = TRUE",
                tenant_id
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM agents WHERE tenant_id = ? AND is_active = 1", (tenant_id,))
        return cursor.fetchone()[0]


async def count_active_calls_db(tenant_id: str) -> int:
    """Count active calls for tenant (for plan enforcement)."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM call_sessions WHERE tenant_id = $1 AND call_status IN ('ringing','in_progress','active')",
                tenant_id
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM call_sessions WHERE tenant_id = ? AND call_status IN ('ringing','in_progress','active')",
            (tenant_id,)
        )
        return cursor.fetchone()[0]


# --- Leads ---

async def create_lead_db(tenant_id: str, phone: str, company_name: str = None, contact_name: str = None, first_name: str = None, last_name: str = None, email: str = None, industry: str = None, notes: str = None, priority: int = 5, status: str = "new", score: float = 0.0, source: str = "manual", custom_fields: dict = None):
    """Create a new lead."""
    lead_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO leads (
                   id, tenant_id, company_name, contact_name, first_name, last_name, phone, email, industry, notes, priority, status, score, source, imported_at, custom_fields, created_at, updated_at
                   ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW(), $15, NOW(), NOW())""",
                lead_id, tenant_id, company_name, contact_name, first_name, last_name, phone, email, industry, notes, priority, status, score, source, json.dumps(custom_fields or {})
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO leads (
               id, tenant_id, company_name, contact_name, first_name, last_name, phone, email, industry, notes, priority, status, score, source, imported_at, custom_fields, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lead_id, tenant_id, company_name, contact_name, first_name, last_name, phone, email, industry, notes, priority, status, score, source, now, json.dumps(custom_fields or {}), now, now)
        )
        conn.commit()
        conn.close()
    return {"id": lead_id}


async def get_lead_db(lead_id: str, tenant_id: str):
    """Get a single lead by ID."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM leads WHERE id = $1 AND tenant_id = $2", lead_id, tenant_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id))
        row = cursor.fetchone()
        conn.close()
        return row


async def list_leads_db(tenant_id: str, status: str = None, industry: str = None, limit: int = 100, offset: int = 0):
    """List leads with optional filters."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = "SELECT * FROM leads WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if status:
                query += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            if industry:
                query += f" AND industry ILIKE ${idx}"
                params.append(f'%{industry}%')
                idx += 1
            query += f" ORDER BY score DESC, created_at DESC LIMIT ${idx} OFFSET ${idx+1}"
            params.extend([limit, offset])
            return await conn.fetch(query, *params)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        query = "SELECT * FROM leads WHERE tenant_id = ?"
        params = [tenant_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if industry:
            query += " AND industry LIKE ?"
            params.append(f'%{industry}%')
        query += " ORDER BY score DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()
        return rows


async def update_lead_db(lead_id: str, tenant_id: str, updates: dict):
    """Update a lead's fields."""
    if not updates:
        return await get_lead_db(lead_id, tenant_id)
    set_clauses = []
    values = []
    idx = 1
    for key, value in updates.items():
        if key == "custom_fields":
            set_clauses.append(f"custom_fields = ${idx}")
            values.append(json.dumps(value))
        else:
            set_clauses.append(f"{key} = ${idx}")
            values.append(value)
        idx += 1
    set_clauses.append("updated_at = NOW()")

    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = f"UPDATE leads SET {', '.join(set_clauses)} WHERE id = ${idx} AND tenant_id = ${idx+1}"
            values.extend([lead_id, tenant_id])
            await conn.execute(query, *values)
            return await get_lead_db(lead_id, tenant_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        set_clauses_sqlite = []
        values_sqlite = []
        for key, value in updates.items():
            if key == "custom_fields":
                existing_row = cursor.execute("SELECT custom_fields FROM leads WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id)).fetchone()
                existing_cf = json.loads(existing_row[0]) if existing_row and existing_row[0] else {}
                merged_cf = {**existing_cf, **value}
                set_clauses_sqlite.append("custom_fields = ?")
                values_sqlite.append(json.dumps(merged_cf))
            else:
                set_clauses_sqlite.append(f"{key} = ?")
                values_sqlite.append(value)
        set_clauses_sqlite.append("updated_at = datetime('now')")

        query = f"UPDATE leads SET {', '.join(set_clauses_sqlite)} WHERE id = ? AND tenant_id = ?"
        values_sqlite.extend([lead_id, tenant_id])
        cursor.execute(query, tuple(values_sqlite))
        conn.commit()
        row = cursor.execute("SELECT * FROM leads WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id)).fetchone()
        conn.close()
        return row


async def delete_lead_db(lead_id: str, tenant_id: str) -> bool:
    """Delete a lead."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM leads WHERE id = $1 AND tenant_id = $2", lead_id, tenant_id)
            return result != "DELETE 0"
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leads WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0


async def bulk_update_leads_db(tenant_id: str, lead_ids: list[str], updates: dict) -> int:
    """Bulk update leads by IDs."""
    if not lead_ids or not updates:
        return 0

    set_clauses = []
    values = []
    idx = 1
    for key, value in updates.items():
        if key == "custom_fields":
            set_clauses.append(f"custom_fields = ${idx}")
            values.append(json.dumps(value))
        else:
            set_clauses.append(f"{key} = ${idx}")
            values.append(value)
        idx += 1
    set_clauses.append("updated_at = NOW()")

    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = f"UPDATE leads SET {', '.join(set_clauses)} WHERE id = ANY(${idx}) AND tenant_id = ${idx+1}"
            values.extend([lead_ids, tenant_id])
            result = await conn.execute(query, *values)
            return int(result.split()[-1])
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        affected_rows = 0
        for lid in lead_ids:
            set_clauses_sqlite = []
            values_sqlite = []
            for key, value in updates.items():
                if key == "custom_fields":
                    existing_row = cursor.execute("SELECT custom_fields FROM leads WHERE id = ? AND tenant_id = ?", (lid, tenant_id)).fetchone()
                    existing_cf = json.loads(existing_row[0]) if existing_row and existing_row[0] else {}
                    merged_cf = {**existing_cf, **value}
                    set_clauses_sqlite.append("custom_fields = ?")
                    values_sqlite.append(json.dumps(merged_cf))
                else:
                    set_clauses_sqlite.append(f"{key} = ?")
                    values_sqlite.append(value)
            set_clauses_sqlite.append("updated_at = datetime('now')")
            query = f"UPDATE leads SET {', '.join(set_clauses_sqlite)} WHERE id = ? AND tenant_id = ?"
            values_sqlite.extend([lid, tenant_id])
            cursor.execute(query, tuple(values_sqlite))
            affected_rows += cursor.rowcount
        conn.commit()
        conn.close()
        return affected_rows


async def bulk_delete_leads_db(tenant_id: str, lead_ids: list[str]) -> int:
    """Bulk delete leads by IDs."""
    if not lead_ids:
        return 0

    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = "DELETE FROM leads WHERE id = ANY($1) AND tenant_id = $2"
            result = await conn.execute(query, lead_ids, tenant_id)
            return int(result.split()[-1])
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        placeholders = ', '.join(['?' for _ in lead_ids])
        query = f"DELETE FROM leads WHERE id IN ({placeholders}) AND tenant_id = ?"
        cursor.execute(query, tuple(lead_ids + [tenant_id]))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected


# --- Scripts ---

async def create_script_db(tenant_id: str, name: str, content: dict, variables: list[dict] = None) -> dict:
    """Create a new script."""
    script_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO scripts (id, tenant_id, name, content, variables, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, NOW(), NOW())""",
                script_id, tenant_id, name, json.dumps(content), json.dumps(variables or [])
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO scripts (id, tenant_id, name, content, variables, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (script_id, tenant_id, name, json.dumps(content), json.dumps(variables or []), now, now)
        )
        conn.commit()
        conn.close()
    return {"id": script_id}


async def get_script_db(script_id: str, tenant_id: str) -> Optional[dict]:
    """Get a script by ID."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM scripts WHERE id = $1 AND tenant_id = $2", script_id, tenant_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scripts WHERE id = ? AND tenant_id = ?", (script_id, tenant_id))
        row = cursor.fetchone()
        conn.close()

    if row and isinstance(row, dict):
        row["content"] = json.loads(row["content"]) if isinstance(row["content"], str) else row["content"]
        row["variables"] = json.loads(row["variables"]) if isinstance(row["variables"], str) else row["variables"]
    elif row and hasattr(row, 'keys'):
        row_dict = {k: row[k] for k in row.keys()}
        row_dict["content"] = json.loads(row_dict["content"]) if isinstance(row_dict["content"], str) else row_dict["content"]
        row_dict["variables"] = json.loads(row_dict["variables"]) if isinstance(row_dict["variables"], str) else row_dict["variables"]
        return row_dict

    return row


async def list_scripts_db(tenant_id: str, is_active: bool = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """List scripts for a tenant."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = "SELECT * FROM scripts WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if is_active is not None:
                query += f" AND is_active = ${idx}"
                params.append(is_active)
                idx += 1
            query += f" ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}"
            params.extend([limit, offset])
            rows = await conn.fetch(query, *params)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        query = "SELECT * FROM scripts WHERE tenant_id = ?"
        params = [tenant_id]
        if is_active is not None:
            query += " AND is_active = ?"
            params.append(1 if is_active else 0)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()

    parsed_rows = []
    for row in rows:
        if isinstance(row, dict):
            row["content"] = json.loads(row["content"]) if isinstance(row["content"], str) else row["content"]
            row["variables"] = json.loads(row["variables"]) if isinstance(row["variables"], str) else row["variables"]
            parsed_rows.append(row)
        elif hasattr(row, 'keys'):
            row_dict = {k: row[k] for k in row.keys()}
            row_dict["content"] = json.loads(row_dict["content"]) if isinstance(row_dict["content"], str) else row_dict["content"]
            row_dict["variables"] = json.loads(row_dict["variables"]) if isinstance(row_dict["variables"], str) else row_dict["variables"]
            parsed_rows.append(row_dict)
    return parsed_rows


async def update_script_db(script_id: str, tenant_id: str, updates: dict) -> Optional[dict]:
    """Update a script's fields."""
    if not updates:
        return await get_script_db(script_id, tenant_id)

    set_clauses = []
    values = []
    idx = 1
    if "content" in updates:
        set_clauses.append(f"content = ${idx}")
        values.append(json.dumps(updates["content"]))
        idx += 1
    if "variables" in updates:
        set_clauses.append(f"variables = ${idx}")
        values.append(json.dumps(updates["variables"]))
        idx += 1
    if "name" in updates:
        set_clauses.append(f"name = ${idx}")
        values.append(updates["name"])
        idx += 1
    if "is_active" in updates:
        set_clauses.append(f"is_active = ${idx}")
        values.append(updates["is_active"])
        idx += 1
    set_clauses.append("version = version + 1")
    set_clauses.append("updated_at = NOW()")

    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = f"UPDATE scripts SET {', '.join(set_clauses)} WHERE id = ${idx} AND tenant_id = ${idx+1}"
            values.extend([script_id, tenant_id])
            await conn.execute(query, *values)
            return await get_script_db(script_id, tenant_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        existing_script = await get_script_db(script_id, tenant_id)
        if not existing_script:
            conn.close()
            return None

        update_values = []
        update_clauses = []
        if "content" in updates:
            existing_content = existing_script.get("content", {})
            if not isinstance(existing_content, dict):
                existing_content = json.loads(existing_content)
            merged_content = {**existing_content, **updates["content"]}
            update_clauses.append("content = ?")
            update_values.append(json.dumps(merged_content))
        if "variables" in updates:
            update_clauses.append("variables = ?")
            update_values.append(json.dumps(updates["variables"]))
        if "name" in updates:
            update_clauses.append("name = ?")
            update_values.append(updates["name"])
        if "is_active" in updates:
            update_clauses.append("is_active = ?")
            update_values.append(1 if updates["is_active"] else 0)
        update_clauses.append("version = version + 1")
        update_clauses.append("updated_at = datetime('now')")

        if update_clauses:
            query = f"UPDATE scripts SET {', '.join(update_clauses)} WHERE id = ? AND tenant_id = ?"
            update_values.extend([script_id, tenant_id])
            cursor.execute(query, tuple(update_values))
            conn.commit()

        row = await get_script_db(script_id, tenant_id)
        conn.close()
        return row


async def delete_script_db(script_id: str, tenant_id: str) -> bool:
    """Delete a script."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM scripts WHERE id = $1 AND tenant_id = $2", script_id, tenant_id)
            return result != "DELETE 0"
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scripts WHERE id = ? AND tenant_id = ?", (script_id, tenant_id))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0


# --- Script Templates ---

async def get_script_template_db(template_id: str) -> Optional[dict]:
    """Get a script template by ID."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM script_templates WHERE id = $1", template_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM script_templates WHERE id = ?", (template_id,))
        row = cursor.fetchone()
        conn.close()

    if row and isinstance(row, dict):
        row["content"] = json.loads(row["content"]) if isinstance(row["content"], str) else row["content"]
        row["variables"] = json.loads(row["variables"]) if isinstance(row["variables"], str) else row["variables"]
    elif row and hasattr(row, 'keys'):
        row_dict = {k: row[k] for k in row.keys()}
        row_dict["content"] = json.loads(row_dict["content"]) if isinstance(row_dict["content"], str) else row_dict["content"]
        row_dict["variables"] = json.loads(row_dict["variables"]) if isinstance(row_dict["variables"], str) else row_dict["variables"]
        return row_dict

    return row


async def list_script_templates_db(industry: str = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """List public script templates."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = "SELECT * FROM script_templates WHERE is_public = TRUE"
            params = []
            idx = 1
            if industry:
                query += f" AND industry ILIKE ${idx}"
                params.append(f'%{industry}%')
                idx += 1
            query += f" ORDER BY name ASC LIMIT ${idx} OFFSET ${idx+1}"
            params.extend([limit, offset])
            rows = await conn.fetch(query, *params)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        query = "SELECT * FROM script_templates WHERE is_public = 1"
        params = []
        if industry:
            query += " AND industry LIKE ?"
            params.append(f'%{industry}%')
        query += " ORDER BY name ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()

    parsed_rows = []
    for row in rows:
        if isinstance(row, dict):
            row["content"] = json.loads(row["content"]) if isinstance(row["content"], str) else row["content"]
            row["variables"] = json.loads(row["variables"]) if isinstance(row["variables"], str) else row["variables"]
            parsed_rows.append(row)
        elif hasattr(row, 'keys'):
            row_dict = {k: row[k] for k in row.keys()}
            row_dict["content"] = json.loads(row_dict["content"]) if isinstance(row_dict["content"], str) else row_dict["content"]
            row_dict["variables"] = json.loads(row_dict["variables"]) if isinstance(row_dict["variables"], str) else row_dict["variables"]
            parsed_rows.append(row_dict)
    return parsed_rows


async def create_script_template_db(name: str, description: str, industry: str, content: dict, variables: list[dict], is_public: bool = True) -> dict:
    """Create a new script template."""
    template_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO script_templates (id, name, description, industry, content, variables, is_public, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())""",
                template_id, name, description, industry, json.dumps(content), json.dumps(variables or []), is_public
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO script_templates (id, name, description, industry, content, variables, is_public, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (template_id, name, description, industry, json.dumps(content), json.dumps(variables or []), 1 if is_public else 0, now, now)
        )
        conn.commit()
        conn.close()
    return {"id": template_id}


async def delete_script_template_db(template_id: str) -> bool:
    """Delete a script template."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM script_templates WHERE id = $1", template_id)
            return result != "DELETE 0"
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM script_templates WHERE id = ?", (template_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0


