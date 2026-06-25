import json
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_integration_config_db(tenant_id, provider, integration_type, config_json, status="active"):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("""
                INSERT INTO integration_configs (tenant_id, provider, integration_type, config_json, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, $5, NOW(), NOW())
                RETURNING *
            """, tenant_id, provider, integration_type, json.dumps(config_json) if isinstance(config_json, dict) else config_json, status)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            config_str = json.dumps(config_json) if isinstance(config_json, dict) else config_json
            conn.execute("""
                INSERT INTO integration_configs (tenant_id, provider, integration_type, config_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (tenant_id, provider, integration_type, config_str, status, now, now))
            conn.commit()
            row = conn.execute("SELECT * FROM integration_configs WHERE tenant_id = ? AND provider = ?", (tenant_id, provider)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_integration_configs_db(tenant_id, integration_type=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if integration_type:
                rows = await pool.fetch("SELECT * FROM integration_configs WHERE tenant_id = $1 AND integration_type = $2", tenant_id, integration_type)
            else:
                rows = await pool.fetch("SELECT * FROM integration_configs WHERE tenant_id = $1", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            if integration_type:
                rows = conn.execute("SELECT * FROM integration_configs WHERE tenant_id = ? AND integration_type = ?", (tenant_id, integration_type)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM integration_configs WHERE tenant_id = ?", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_integration_config_db(tenant_id, provider):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM integration_configs WHERE tenant_id = $1 AND provider = $2", tenant_id, provider)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM integration_configs WHERE tenant_id = ? AND provider = ?", (tenant_id, provider)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def update_integration_config_db(tenant_id, provider, config_json=None, status=None, last_sync_at=None, error_message=None):
    updates = {}
    if config_json is not None:
        updates["config_json"] = json.dumps(config_json) if isinstance(config_json, dict) else config_json
    if status is not None:
        updates["status"] = status
    if last_sync_at is not None:
        updates["last_sync_at"] = last_sync_at
    if error_message is not None:
        updates["error_message"] = error_message
    if not updates:
        return None
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            set_parts = []
            params = []
            idx = 1
            for k, v in updates.items():
                if k == "config_json":
                    set_parts.append(f"{k} = ${idx}::jsonb")
                else:
                    set_parts.append(f"{k} = ${idx}")
                params.append(v)
                idx += 1
            set_parts.append("updated_at = NOW()")
            params.extend([tenant_id, provider])
            await pool.execute(
                f"UPDATE integration_configs SET {', '.join(set_parts)} WHERE tenant_id = ${idx} AND provider = ${idx+1}",
                *params
            )
            row = await pool.fetchrow("SELECT * FROM integration_configs WHERE tenant_id = $1 AND provider = $2", tenant_id, provider)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                params.append(v)
            set_parts.append("updated_at = ?")
            params.append(now)
            params.extend([tenant_id, provider])
            conn.execute(
                f"UPDATE integration_configs SET {', '.join(set_parts)} WHERE tenant_id = ? AND provider = ?",
                params
            )
            conn.commit()
            row = conn.execute("SELECT * FROM integration_configs WHERE tenant_id = ? AND provider = ?", (tenant_id, provider)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def create_ticket_sync_log_db(tenant_id, ticket_id, call_id=None, direction="outbound", status="success", payload_json=None, response_json=None, error_message=None):
    log_id = None
    import uuid
    log_id = str(uuid.uuid4())
    payload_str = json.dumps(payload_json) if payload_json and isinstance(payload_json, dict) else (payload_json or "{}")
    response_str = json.dumps(response_json) if response_json and isinstance(response_json, dict) else (response_json or "{}")
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO ticket_sync_log (id, tenant_id, ticket_id, call_id, direction, status, payload_json, response_json, error_message, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, NOW())
            """, log_id, tenant_id, ticket_id, call_id, direction, status, payload_str, response_str, error_message)
            row = await pool.fetchrow("SELECT * FROM ticket_sync_log WHERE id = $1", log_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO ticket_sync_log (id, tenant_id, ticket_id, call_id, direction, status, payload_json, response_json, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, tenant_id, ticket_id, call_id, direction, status, payload_str, response_str, error_message, now))
            conn.commit()
            row = conn.execute("SELECT * FROM ticket_sync_log WHERE id = ?", (log_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_ticket_sync_logs_db(tenant_id, limit=50, offset=0, status=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if status:
                rows = await pool.fetch("SELECT * FROM ticket_sync_log WHERE tenant_id = $1 AND status = $2 ORDER BY created_at DESC LIMIT $3 OFFSET $4", tenant_id, status, limit, offset)
            else:
                rows = await pool.fetch("SELECT * FROM ticket_sync_log WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3", tenant_id, limit, offset)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            if status:
                rows = conn.execute("SELECT * FROM ticket_sync_log WHERE tenant_id = ? AND status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?", (tenant_id, status, limit, offset)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM ticket_sync_log WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?", (tenant_id, limit, offset)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
