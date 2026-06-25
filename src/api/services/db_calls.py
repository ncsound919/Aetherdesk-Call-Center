import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


# --- Call Sessions ---

async def create_call_session(tenant_id, agent_id, caller_number, caller_name=None, called_number=None,
                              call_direction="inbound", intent_detected=None, sip_call_id=None):
    call_id = str(uuid.uuid4())
    status = "ringing" if agent_id else "initiated"
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO call_sessions (id, tenant_id, agent_id, caller_number, caller_name, called_number,
                    call_direction, call_status, sip_call_id, intent_detected, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW())
            """, call_id, tenant_id, agent_id, caller_number, caller_name, called_number or caller_number,
                call_direction, status, sip_call_id, intent_detected)
            return await pool.fetchrow("SELECT * FROM call_sessions WHERE id = $1", call_id)
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO call_sessions (id, tenant_id, agent_id, caller_number, caller_name, called_number,
                    call_direction, call_status, sip_call_id, intent_detected, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (call_id, tenant_id, agent_id, caller_number, caller_name, called_number or caller_number,
                  call_direction, status, sip_call_id, intent_detected, now, now))
            conn.commit()
            row = conn.execute("SELECT * FROM call_sessions WHERE id = ?", (call_id,)).fetchone()
            return row
        finally:
            conn.close()


async def get_call_session(call_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow("SELECT * FROM call_sessions WHERE id = $1", call_id)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT * FROM call_sessions WHERE id = ?", (call_id,)).fetchone()
        conn.close()
        return row


async def update_call_status(call_id, status):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("UPDATE call_sessions SET call_status = $1, updated_at = NOW() WHERE id = $2", status, call_id)
            return await pool.fetchrow("SELECT * FROM call_sessions WHERE id = $1", call_id)
    else:
        conn = _get_sqlite_conn()
        now = datetime.now(UTC).isoformat()
        conn.execute("UPDATE call_sessions SET call_status = ?, updated_at = ? WHERE id = ?",
                     (status, now, call_id))
        conn.commit()
        row = conn.execute("SELECT * FROM call_sessions WHERE id = ?", (call_id,)).fetchone()
        conn.close()
        return row


async def list_calls(tenant_id, status=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if status:
                return await pool.fetch("SELECT * FROM call_sessions WHERE tenant_id = $1 AND call_status = $2 ORDER BY created_at DESC", tenant_id, status)
            return await pool.fetch("SELECT * FROM call_sessions WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
    else:
        conn = _get_sqlite_conn()
        if status:
            rows = conn.execute("SELECT * FROM call_sessions WHERE tenant_id = ? AND call_status = ? ORDER BY created_at DESC", (tenant_id, status)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM call_sessions WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
        conn.close()
        return rows


# --- Call Queue ---

async def enqueue_call(tenant_id, caller_number, intent=None, skills_required=None):
    position = 1
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            max_pos = await pool.fetchval("SELECT COALESCE(MAX(position), 0) + 1 FROM call_queue WHERE tenant_id = $1 AND status = 'waiting'", tenant_id)
            position = max_pos or 1
            queue_id = str(uuid.uuid4())
            await pool.execute("""
                INSERT INTO call_queue (id, tenant_id, caller_number, position, intent, status, skills_required)
                VALUES ($1, $2, $3, $4, $5, 'waiting', $6)
            """, queue_id, tenant_id, caller_number, position, intent, json.dumps(skills_required or []))
            return await pool.fetchrow("SELECT * FROM call_queue WHERE id = $1", queue_id)
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 AS max_pos FROM call_queue WHERE tenant_id = ? AND status = 'waiting'", (tenant_id,)).fetchone()
        position = row["max_pos"] if row and row["max_pos"] else 1
        queue_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO call_queue (id, tenant_id, caller_number, position, intent, status, skills_required)
            VALUES (?, ?, ?, ?, ?, 'waiting', ?)
        """, (queue_id, tenant_id, caller_number, position, intent, json.dumps(skills_required or [])))
        conn.commit()
        row = conn.execute("SELECT * FROM call_queue WHERE id = ?", (queue_id,)).fetchone()
        conn.close()
        return row


async def dequeue_call(tenant_id, agent_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        "SELECT * FROM call_queue WHERE tenant_id = $1 AND status = 'waiting' ORDER BY position LIMIT 1",
                        tenant_id
                    )
                    if row:
                        await conn.execute("UPDATE call_queue SET status = 'assigned', assigned_at = NOW() WHERE id = $1", row['id'])
                        return dict(row)
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            row = conn.execute("SELECT * FROM call_queue WHERE tenant_id = ? AND status = 'waiting' ORDER BY position LIMIT 1", (tenant_id,)).fetchone()
            if row:
                conn.execute("UPDATE call_queue SET status = 'assigned', assigned_at = ? WHERE id = ?", (now, row['id']))
                conn.commit()
                return dict(row)
        finally:
            conn.close()
    return None


# --- Usage / Analytics ---

async def get_usage_stats(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            total_agents = await pool.fetchval("SELECT COUNT(*) FROM agents WHERE tenant_id = $1", tenant_id)
            active_agents = await pool.fetchval("SELECT COUNT(*) FROM agents WHERE tenant_id = $1 AND status IN ('available','busy','on_call')", tenant_id)
            total_calls = await pool.fetchval("SELECT COUNT(*) FROM call_sessions WHERE tenant_id = $1", tenant_id)
            active_calls = await pool.fetchval("SELECT COUNT(*) FROM call_sessions WHERE tenant_id = $1 AND call_status = 'active'", tenant_id)
            total_minutes = await pool.fetchval("SELECT COALESCE(SUM(duration_seconds)/60.0, 0) FROM call_sessions WHERE tenant_id = $1", tenant_id)
            return {
                "total_agents": total_agents, "active_agents": active_agents or 0,
                "total_calls": total_calls, "active_calls": active_calls or 0,
                "total_minutes": float(total_minutes or 0), "queue_depth": 0
            }
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM agents WHERE tenant_id = ?", (tenant_id,)).fetchone()
            total_agents = row["cnt"] if row else 0
            row = conn.execute("SELECT COUNT(*) as cnt FROM agents WHERE tenant_id = ? AND status IN ('available','busy','on_call')", (tenant_id,)).fetchone()
            active_agents = row["cnt"] if row else 0
            row = conn.execute("SELECT COUNT(*) as cnt FROM call_sessions WHERE tenant_id = ?", (tenant_id,)).fetchone()
            total_calls = row["cnt"] if row else 0
            row = conn.execute("SELECT COUNT(*) as cnt FROM call_sessions WHERE tenant_id = ? AND call_status = 'active'", (tenant_id,)).fetchone()
            active_calls = row["cnt"] if row else 0
            row = conn.execute("SELECT COALESCE(SUM(duration_seconds)/60.0, 0) as val FROM call_sessions WHERE tenant_id = ?", (tenant_id,)).fetchone()
            total_minutes = row["val"] if row else 0
        finally:
            conn.close()
        return {
            "total_agents": total_agents, "active_agents": active_agents or 0,
            "total_calls": total_calls or 0, "active_calls": active_calls or 0,
            "total_minutes": float(total_minutes or 0), "queue_depth": 0
        }


async def get_billing_summary(tenant_id, period_start, period_end):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            total_calls = await pool.fetchval("SELECT COUNT(*) FROM call_sessions WHERE tenant_id = $1 AND created_at BETWEEN $2 AND $3", tenant_id, period_start, period_end)
            total_minutes = await pool.fetchval("SELECT COALESCE(SUM(duration_seconds)/60.0, 0) FROM call_sessions WHERE tenant_id = $1 AND created_at BETWEEN $2 AND $3", tenant_id, period_start, period_end)
            return {"total_calls": total_calls, "total_minutes": float(total_minutes or 0), "total_cost": float(total_minutes or 0) * 0.015, "currency": "USD"}
    else:
        conn = _get_sqlite_conn()
        try:
            total_calls = (conn.execute("SELECT COUNT(*) AS cnt FROM call_sessions WHERE tenant_id = ? AND created_at BETWEEN ? AND ?", (tenant_id, period_start, period_end)).fetchone() or {}).get("cnt", 0)
            total_minutes = (conn.execute("SELECT COALESCE(SUM(duration_seconds)/60.0, 0) AS mins FROM call_sessions WHERE tenant_id = ? AND created_at BETWEEN ? AND ?", (tenant_id, period_start, period_end)).fetchone() or {}).get("mins", 0)
        finally:
            conn.close()
        return {"total_calls": total_calls or 0, "total_minutes": float(total_minutes or 0), "total_cost": float(total_minutes or 0) * 0.015, "currency": "USD"}


# --- Audit Logging ---

async def log_audit_event(tenant_id, user_id, action, resource_type, resource_id, old_values=None, new_values=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO audit_log (tenant_id, user_id, action, resource_type, resource_id, old_values, new_values, ip_address)
                VALUES ($1, $2, $3, $4, $5, $6, $7, '127.0.0.1')
            """, tenant_id, user_id, action, resource_type, resource_id, json.dumps(old_values or {}), json.dumps(new_values or {}))
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                INSERT INTO audit_log (tenant_id, user_id, action, resource_type, resource_id, old_values, new_values, ip_address)
                VALUES (?, ?, ?, ?, ?, ?, ?, '127.0.0.1')
            """, (tenant_id, user_id, action, resource_type, resource_id, json.dumps(old_values or {}), json.dumps(new_values or {})))
            conn.commit()
        finally:
            conn.close()


# --- SaaS Dashboard & Operations Helpers ---

async def get_saas_dashboard_db(tenant_id: str) -> dict:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rentals_rows = await pool.fetch("SELECT * FROM rentals WHERE tenant_id = $1", tenant_id)
            profiles_rows = await pool.fetch("SELECT * FROM agent_profiles WHERE tenant_id = $1", tenant_id)
            return {
                "rentals": [dict(r) for r in rentals_rows],
                "profiles": [dict(p) for p in profiles_rows]
            }
    else:
        conn = _get_sqlite_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rentals WHERE tenant_id = ?", (tenant_id,))
            rentals = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT * FROM agent_profiles WHERE tenant_id = ?", (tenant_id,))
            profiles = [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
        return {
            "rentals": rentals,
            "profiles": profiles
        }
    return {"rentals": [], "profiles": []}


async def rent_agent_db(rental_id, tenant_id, profile_id, duration_type, end_time):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "INSERT INTO rentals (id, tenant_id, profile_id, duration_type, end_time) VALUES ($1, $2, $3, $4, $5)",
                rental_id, tenant_id, profile_id, duration_type, end_time
            )
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute(
                "INSERT INTO rentals (id, tenant_id, profile_id, duration_type, end_time) VALUES (?, ?, ?, ?, ?)",
                (rental_id, tenant_id, profile_id, duration_type, end_time.strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
        finally:
            conn.close()


async def get_session_recordings_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM session_recordings WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM session_recordings WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]
    return []


async def get_pending_approvals_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM action_approvals WHERE status = 'pending' AND tenant_id = $1", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM action_approvals WHERE status = 'pending' AND tenant_id = ?", (tenant_id,)).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]
    return []


async def process_approval_db(approval_id, status, tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.execute("UPDATE action_approvals SET status = $1 WHERE id = $2 AND tenant_id = $3", status, approval_id, tenant_id)
            try:
                rows_updated = int(result.split()[-1])
                return rows_updated > 0
            except (ValueError, IndexError, AttributeError):
                return False
    else:
        conn = _get_sqlite_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE action_approvals SET status = ? WHERE id = ? AND tenant_id = ?", (status, approval_id, tenant_id))
            rows_updated = cursor.rowcount
            conn.commit()
        finally:
            conn.close()
        return rows_updated > 0
    return False


# --- Actions & Integration Helpers ---

async def get_webhook_url_db(tenant_id):
    try:
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                row = await pool.fetchrow("SELECT settings->>'webhook_url' as webhook_url FROM tenants WHERE id = $1", tenant_id)
                if row and row.get("webhook_url"):
                    return row["webhook_url"]
                row_settings = await pool.fetchrow("SELECT webhook_url FROM tenant_settings WHERE tenant_id = $1", tenant_id)
                if row_settings:
                    return row_settings["webhook_url"]
        else:
            conn = _get_sqlite_conn()
            try:
                row = conn.execute("SELECT webhook_url FROM tenant_settings WHERE tenant_id = ?", (tenant_id,)).fetchone()
            finally:
                conn.close()
            if row:
                return row.get("webhook_url")
    except Exception as e:
        logger.warning("get_webhook_url_db failed", error=str(e))
    return None


async def lookup_invoice_db(invoice_id):
    try:
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                row = await pool.fetchrow("SELECT amount, status, due_date FROM invoices WHERE id = $1", invoice_id)
                return dict(row) if row else None
        else:
            conn = _get_sqlite_conn()
            row = conn.execute("SELECT amount, status, due_date FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            conn.close()
            return dict(row) if row else None
    except Exception as e:
        logger.warning("lookup_invoice_db failed", error=str(e))
    return None


async def get_order_status_db(order_id):
    try:
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                row = await pool.fetchrow("SELECT status, expected_delivery FROM orders WHERE id = $1", order_id)
                return dict(row) if row else None
        else:
            conn = _get_sqlite_conn()
            row = conn.execute("SELECT status, expected_delivery FROM orders WHERE id = ?", (order_id,)).fetchone()
            conn.close()
            return dict(row) if row else None
    except Exception as e:
        logger.warning("get_order_status_db failed", error=str(e))
    return None


