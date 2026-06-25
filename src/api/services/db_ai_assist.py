import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_knowledge_snippet_db(tenant_id, title, content, tags=None, category="general"):
    snippet_id = str(uuid.uuid4())
    tags_json = json.dumps(tags or [])
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO knowledge_snippets (id, tenant_id, title, content, tags, category, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, NOW(), NOW())
            """, snippet_id, tenant_id, title, content, tags_json, category)
            row = await pool.fetchrow("SELECT * FROM knowledge_snippets WHERE id = $1", snippet_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO knowledge_snippets (id, tenant_id, title, content, tags, category, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (snippet_id, tenant_id, title, content, tags_json, category, now, now))
            conn.commit()
            row = conn.execute("SELECT * FROM knowledge_snippets WHERE id = ?", (snippet_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def search_knowledge_snippets_db(tenant_id, query, limit=5):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT * FROM knowledge_snippets
                WHERE tenant_id = $1 AND (title ILIKE $2 OR content ILIKE $2)
                ORDER BY created_at DESC LIMIT $3
            """, tenant_id, f"%{query}%", limit)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM knowledge_snippets
                WHERE tenant_id = ? AND (title LIKE ? OR content LIKE ?)
                ORDER BY created_at DESC LIMIT ?
            """, (tenant_id, f"%{query}%", f"%{query}%", limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


async def list_knowledge_snippets_db(tenant_id, category=None, limit=50, offset=0):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if category:
                rows = await pool.fetch("""
                    SELECT * FROM knowledge_snippets
                    WHERE tenant_id = $1 AND category = $2
                    ORDER BY created_at DESC LIMIT $3 OFFSET $4
                """, tenant_id, category, limit, offset)
            else:
                rows = await pool.fetch("""
                    SELECT * FROM knowledge_snippets
                    WHERE tenant_id = $1
                    ORDER BY created_at DESC LIMIT $2 OFFSET $3
                """, tenant_id, limit, offset)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            if category:
                rows = conn.execute("""
                    SELECT * FROM knowledge_snippets
                    WHERE tenant_id = ? AND category = ?
                    ORDER BY created_at DESC LIMIT ? OFFSET ?
                """, (tenant_id, category, limit, offset)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM knowledge_snippets
                    WHERE tenant_id = ?
                    ORDER BY created_at DESC LIMIT ? OFFSET ?
                """, (tenant_id, limit, offset)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


async def delete_knowledge_snippet_db(tenant_id, snippet_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.execute(
                "DELETE FROM knowledge_snippets WHERE id = $1 AND tenant_id = $2",
                snippet_id, tenant_id,
            )
            return "DELETE" in result
    else:
        conn = _get_sqlite_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM knowledge_snippets WHERE id = ? AND tenant_id = ?", (snippet_id, tenant_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    return False
