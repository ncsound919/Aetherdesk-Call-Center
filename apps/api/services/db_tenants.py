import json
import secrets
import uuid
from datetime import UTC, datetime

import structlog

from apps.api.services.db_config import USE_POSTGRES
from apps.api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


# ── Database Operations ─────────────────────────────────────────

# --- Tenants ---

async def create_tenant(name, email, slug, phone=None, plan_id=None, settings=None, gdpr_consent=False):
    tenant_id = str(uuid.uuid4())
    api_key = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
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
            """, (agent_id, tenant_id, name, display_name or name, agent_type, json.dumps(skills or []), json.dumps(config or {}), phone, email, sip_extension, datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()))
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
        now = datetime.now(UTC).isoformat()
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
                query = f"UPDATE agents SET {', '.join(fields)} WHERE id = ${idx} AND tenant_id = ${idx+1}"
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
            fields.append("updated_at = ?"); values.append(datetime.now(UTC).isoformat())
            values.extend([agent_id, tenant_id])
            conn.execute(f"UPDATE agents SET {', '.join(fields)} WHERE id = ? AND tenant_id = ?", values)
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
            return await pool.fetchrow("SELECT id, tenant_id, email, password_hash, role, display_name FROM users WHERE email = $1", email)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute(
            "SELECT id, tenant_id, email, password_hash, role, display_name FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()
        return row
    return None
