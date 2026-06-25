import json

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_api_key_db(tenant_id, name, key_prefix, key_hash, scopes, expires_at):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("""
                INSERT INTO api_keys (tenant_id, name, key_prefix, key_hash, scopes_json, expires_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                RETURNING id, tenant_id, name, key_prefix, scopes_json, expires_at, last_used_at, is_active, created_at
            """, tenant_id, name, key_prefix, key_hash, json.dumps(scopes), expires_at)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            cur = conn.execute("""
                INSERT INTO api_keys (tenant_id, name, key_prefix, key_hash, scopes_json, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (tenant_id, name, key_prefix, key_hash, json.dumps(scopes), expires_at))
            conn.commit()
            row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (cur.lastrowid,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_api_key_by_prefix_db(key_prefix):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM api_keys WHERE key_prefix = $1", key_prefix)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM api_keys WHERE key_prefix = ?", (key_prefix,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def revoke_api_key_db(tenant_id, key_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.execute("UPDATE api_keys SET is_active = FALSE WHERE id = $1 AND tenant_id = $2", key_id, tenant_id)
            return "UPDATE" in result
    else:
        conn = _get_sqlite_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE api_keys SET is_active = 0 WHERE id = ? AND tenant_id = ?", (key_id, tenant_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    return False


async def list_api_keys_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM api_keys WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM api_keys WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def update_api_key_last_used_db(key_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("UPDATE api_keys SET last_used_at = NOW() WHERE id = $1", key_id)
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (key_id,))
            conn.commit()
        finally:
            conn.close()


async def get_api_key_by_id_db(tenant_id, key_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM api_keys WHERE id = $1 AND tenant_id = $2", key_id, tenant_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM api_keys WHERE id = ? AND tenant_id = ?", (key_id, tenant_id)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def register_webhook_db(tenant_id, url, events, secret):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("""
                INSERT INTO webhook_configs (tenant_id, url, events_json, secret)
                VALUES ($1, $2, $3::jsonb, $4)
                RETURNING id, tenant_id, url, events_json, secret, is_active, created_at
            """, tenant_id, url, json.dumps(events), secret)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            cur = conn.execute("""
                INSERT INTO webhook_configs (tenant_id, url, events_json, secret)
                VALUES (?, ?, ?, ?)
            """, (tenant_id, url, json.dumps(events), secret))
            conn.commit()
            row = conn.execute("SELECT * FROM webhook_configs WHERE id = ?", (cur.lastrowid,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def unregister_webhook_db(tenant_id, webhook_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.execute("DELETE FROM webhook_configs WHERE id = $1 AND tenant_id = $2", webhook_id, tenant_id)
            return "DELETE" in result
    else:
        conn = _get_sqlite_conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM webhook_configs WHERE id = ? AND tenant_id = ?", (webhook_id, tenant_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    return False


async def list_webhooks_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM webhook_configs WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM webhook_configs WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_webhook_by_id_db(tenant_id, webhook_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM webhook_configs WHERE id = $1 AND tenant_id = $2", webhook_id, tenant_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM webhook_configs WHERE id = ? AND tenant_id = ?", (webhook_id, tenant_id)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_active_webhooks_for_event_db(tenant_id, event_type):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT * FROM webhook_configs
                WHERE tenant_id = $1 AND is_active = TRUE AND events_json::jsonb ? $2
            """, tenant_id, event_type)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM webhook_configs
                WHERE tenant_id = ? AND is_active = 1 AND events_json LIKE ?
            """, (tenant_id, f'%"{event_type}"%')).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def create_webhook_delivery_log_db(tenant_id, webhook_id, event_type, request_body):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("""
                INSERT INTO webhook_delivery_logs (tenant_id, webhook_id, event_type, request_body)
                VALUES ($1, $2, $3, $4)
                RETURNING id, tenant_id, webhook_id, event_type, status, request_body, response_status, error_message, retry_count, created_at
            """, tenant_id, webhook_id, event_type, request_body)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            cur = conn.execute("""
                INSERT INTO webhook_delivery_logs (tenant_id, webhook_id, event_type, request_body)
                VALUES (?, ?, ?, ?)
            """, (tenant_id, webhook_id, event_type, request_body))
            conn.commit()
            row = conn.execute("SELECT * FROM webhook_delivery_logs WHERE id = ?", (cur.lastrowid,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def update_webhook_delivery_log_db(log_id, status, response_status=None, response_body=None, error_message=None, retry_count=None):
    updates = {"status": status}
    if response_status is not None:
        updates["response_status"] = response_status
    if response_body is not None:
        updates["response_body"] = response_body
    if error_message is not None:
        updates["error_message"] = error_message
    if retry_count is not None:
        updates["retry_count"] = retry_count

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            set_parts = []
            params = []
            idx = 1
            for k, v in updates.items():
                set_parts.append(f"{k} = ${idx}")
                params.append(v)
                idx += 1
            params.append(log_id)
            await pool.execute(f"UPDATE webhook_delivery_logs SET {', '.join(set_parts)} WHERE id = ${idx}", *params)
    else:
        conn = _get_sqlite_conn()
        try:
            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                params.append(v)
            params.append(log_id)
            conn.execute(f"UPDATE webhook_delivery_logs SET {', '.join(set_parts)} WHERE id = ?", params)
            conn.commit()
        finally:
            conn.close()


async def get_webhook_delivery_logs_db(tenant_id, webhook_id, limit=50):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch(
                "SELECT * FROM webhook_delivery_logs WHERE tenant_id = $1 AND webhook_id = $2 ORDER BY created_at DESC LIMIT $3",
                tenant_id, webhook_id, limit
            )
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM webhook_delivery_logs WHERE tenant_id = ? AND webhook_id = ? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, webhook_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_webhook_delivery_log_by_id_db(log_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM webhook_delivery_logs WHERE id = $1", log_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM webhook_delivery_logs WHERE id = ?", (log_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
