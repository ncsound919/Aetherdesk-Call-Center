import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_sms_template_db(tenant_id, name, body):
    template_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO sms_templates (id, tenant_id, name, body, created_at)
                VALUES ($1, $2, $3, $4, NOW())
            """, template_id, tenant_id, name, body)
            row = await pool.fetchrow("SELECT * FROM sms_templates WHERE id = $1", template_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO sms_templates (id, tenant_id, name, body, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (template_id, tenant_id, name, body, now))
            conn.commit()
            row = conn.execute("SELECT * FROM sms_templates WHERE id = ?", (template_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_sms_templates_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM sms_templates WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM sms_templates WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def log_sms_db(tenant_id, to_number, body, from_number=None, status="sent", direction="outbound", sid=None):
    log_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO sms_log (id, tenant_id, to_number, from_number, body, status, direction, sid, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            """, log_id, tenant_id, to_number, from_number, body, status, direction, sid)
            row = await pool.fetchrow("SELECT * FROM sms_log WHERE id = $1", log_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO sms_log (id, tenant_id, to_number, from_number, body, status, direction, sid, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, tenant_id, to_number, from_number, body, status, direction, sid, now))
            conn.commit()
            row = conn.execute("SELECT * FROM sms_log WHERE id = ?", (log_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_sms_log_db(tenant_id, limit=100, offset=0):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT * FROM sms_log WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3"
            rows = await pool.fetch(query, tenant_id, limit, offset)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM sms_log WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (tenant_id, limit, offset)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def create_chat_session_db(tenant_id, visitor_id, visitor_name=None, visitor_email=None):
    session_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO chat_sessions (id, tenant_id, visitor_id, visitor_name, visitor_email, status, created_at)
                VALUES ($1, $2, $3, $4, $5, 'waiting', NOW())
            """, session_id, tenant_id, visitor_id, visitor_name, visitor_email)
            row = await pool.fetchrow("SELECT * FROM chat_sessions WHERE id = $1", session_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO chat_sessions (id, tenant_id, visitor_id, visitor_name, visitor_email, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'waiting', ?)
            """, (session_id, tenant_id, visitor_id, visitor_name, visitor_email, now))
            conn.commit()
            row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_chat_session_db(session_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM chat_sessions WHERE id = $1", session_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_waiting_sessions_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch(
                "SELECT cs.*, COUNT(cm.id) as message_count FROM chat_sessions cs "
                "LEFT JOIN chat_messages cm ON cm.session_id = cs.id "
                "WHERE cs.tenant_id = $1 AND cs.status = 'waiting' "
                "GROUP BY cs.id ORDER BY cs.created_at ASC",
                tenant_id
            )
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT cs.*, COUNT(cm.id) as message_count FROM chat_sessions cs
                LEFT JOIN chat_messages cm ON cm.session_id = cs.id
                WHERE cs.tenant_id = ? AND cs.status = 'waiting'
                GROUP BY cs.id ORDER BY cs.created_at ASC
            """, (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def add_chat_message_db(session_id, sender_type, content, sender_name=None):
    msg_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO chat_messages (id, session_id, sender_type, sender_name, content, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
            """, msg_id, session_id, sender_type, sender_name, content)
            row = await pool.fetchrow("SELECT * FROM chat_messages WHERE id = $1", msg_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO chat_messages (id, session_id, sender_type, sender_name, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (msg_id, session_id, sender_type, sender_name, content, now))
            conn.commit()
            row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (msg_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_chat_messages_db(session_id, after_id=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if after_id:
                rows = await pool.fetch(
                    "SELECT * FROM chat_messages WHERE session_id = $1 AND id > $2 ORDER BY created_at ASC",
                    session_id, after_id
                )
            else:
                rows = await pool.fetch(
                    "SELECT * FROM chat_messages WHERE session_id = $1 ORDER BY created_at ASC",
                    session_id
                )
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            if after_id:
                rows = conn.execute(
                    "SELECT * FROM chat_messages WHERE session_id = ? AND id > ? ORDER BY created_at ASC",
                    (session_id, after_id)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
                    (session_id,)
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def update_chat_session_db(session_id, **kwargs):
    allowed = {"agent_id", "status", "assigned_at", "closed_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return None
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
            params.append(session_id)
            await pool.execute(
                f"UPDATE chat_sessions SET {', '.join(set_parts)} WHERE id = ${idx}",
                *params
            )
            row = await pool.fetchrow("SELECT * FROM chat_sessions WHERE id = $1", session_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                params.append(v)
            params.append(session_id)
            conn.execute(
                f"UPDATE chat_sessions SET {', '.join(set_parts)} WHERE id = ?",
                params
            )
            conn.commit()
            row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
