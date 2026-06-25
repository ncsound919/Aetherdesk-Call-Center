import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def upsert_customer_profile_db(tenant_id, customer_id, **kwargs):
    allowed = {"external_id", "phone", "email", "name", "tags_json", "metadata_json", "last_seen_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return await get_customer_profile_db(customer_id)

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
            set_parts.append("updated_at = NOW()")
            params.append(customer_id)
            await pool.execute(
                f"UPDATE customer_profiles SET {', '.join(set_parts)} WHERE id = ${idx}",
                *params
            )
            row = await pool.fetchrow("SELECT * FROM customer_profiles WHERE id = $1", customer_id)
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
            params.append(customer_id)
            conn.execute(
                f"UPDATE customer_profiles SET {', '.join(set_parts)} WHERE id = ?",
                params
            )
            conn.commit()
            row = conn.execute("SELECT * FROM customer_profiles WHERE id = ?", (customer_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def create_customer_profile_db(tenant_id, **kwargs):
    customer_id = str(uuid.uuid4())
    name = kwargs.get("name")
    phone = kwargs.get("phone")
    email = kwargs.get("email")
    external_id = kwargs.get("external_id")
    tags_json = json.dumps(kwargs.get("tags", []))
    metadata_json = json.dumps(kwargs.get("metadata", {}))
    now = datetime.now(UTC).isoformat()

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO customer_profiles (id, tenant_id, external_id, phone, email, name, tags_json, metadata_json, first_seen_at, last_seen_at, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10, NOW(), NOW())
            """, customer_id, tenant_id, external_id, phone, email, name, tags_json, metadata_json, now, now)
            row = await pool.fetchrow("SELECT * FROM customer_profiles WHERE id = $1", customer_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                INSERT INTO customer_profiles (id, tenant_id, external_id, phone, email, name, tags_json, metadata_json, first_seen_at, last_seen_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (customer_id, tenant_id, external_id, phone, email, name, tags_json, metadata_json, now, now, now, now))
            conn.commit()
            row = conn.execute("SELECT * FROM customer_profiles WHERE id = ?", (customer_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_customer_profile_db(customer_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM customer_profiles WHERE id = $1", customer_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM customer_profiles WHERE id = ?", (customer_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def find_customers_by_identifier_db(tenant_id, identifiers):
    results = []
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            conditions = []
            params = [tenant_id]
            idx = 2
            for key, val in identifiers.items():
                if val:
                    conditions.append(f"{key} = ${idx}")
                    params.append(val)
                    idx += 1
            if not conditions:
                return []
            query = f"SELECT * FROM customer_profiles WHERE tenant_id = $1 AND ({' OR '.join(conditions)})"
            rows = await pool.fetch(query, *params)
            results = [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            conditions = []
            params = [tenant_id]
            for key, val in identifiers.items():
                if val:
                    conditions.append(f"{key} = ?")
                    params.append(val)
            if conditions:
                query = f"SELECT * FROM customer_profiles WHERE tenant_id = ? AND ({' OR '.join(conditions)})"
                rows = conn.execute(query, params).fetchall()
                results = [dict(r) for r in rows]
        finally:
            conn.close()
    return results


async def search_customers_db(tenant_id, query_text):
    results = []
    like_val = f"%{query_text}%"
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT * FROM customer_profiles
                WHERE tenant_id = $1
                  AND (name ILIKE $2 OR phone ILIKE $2 OR email ILIKE $2)
                ORDER BY last_seen_at DESC NULLS LAST
                LIMIT 50
            """, tenant_id, like_val)
            results = [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM customer_profiles
                WHERE tenant_id = ?
                  AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)
                ORDER BY last_seen_at DESC
                LIMIT 50
            """, (tenant_id, like_val, like_val, like_val)).fetchall()
            results = [dict(r) for r in rows]
        finally:
            conn.close()
    return results


async def update_customer_tags_db(customer_id, tags):
    tags_json = json.dumps(tags)
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("UPDATE customer_profiles SET tags_json = $1::jsonb, updated_at = NOW() WHERE id = $2", tags_json, customer_id)
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("UPDATE customer_profiles SET tags_json = ?, updated_at = ? WHERE id = ?", (tags_json, now, customer_id))
            conn.commit()
        finally:
            conn.close()


async def get_customer_tags_db(customer_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchval("SELECT tags_json FROM customer_profiles WHERE id = $1", customer_id)
            if row:
                return json.loads(row) if isinstance(row, str) else row
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT tags_json FROM customer_profiles WHERE id = ?", (customer_id,)).fetchone()
            if row:
                return json.loads(row["tags_json"])
        finally:
            conn.close()
    return []


async def list_customer_interactions_db(tenant_id, customer_id, limit=100):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT * FROM customer_interactions
                WHERE tenant_id = $1 AND customer_id = $2
                ORDER BY created_at DESC LIMIT $3
            """, tenant_id, customer_id, limit)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM customer_interactions
                WHERE tenant_id = ? AND customer_id = ?
                ORDER BY created_at DESC LIMIT ?
            """, (tenant_id, customer_id, limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def list_csat_surveys_for_customer_db(tenant_id, customer_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT * FROM csat_surveys
                WHERE tenant_id = $1 AND customer_id = $2
                ORDER BY created_at DESC LIMIT 50
            """, tenant_id, customer_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM csat_surveys
                WHERE tenant_id = ? AND customer_id = ?
                ORDER BY created_at DESC LIMIT 50
            """, (tenant_id, customer_id)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def create_customer_interaction_db(tenant_id, customer_id, interaction_type, channel="voice", call_id=None, agent_id=None, sentiment="neutral", summary=None, duration_seconds=0):
    import uuid
    interaction_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO customer_interactions (id, tenant_id, customer_id, interaction_type, channel, call_id, agent_id, sentiment, summary, duration_seconds, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            """, interaction_id, tenant_id, customer_id, interaction_type, channel, call_id, agent_id, sentiment, summary, duration_seconds)
            row = await pool.fetchrow("SELECT * FROM customer_interactions WHERE id = $1", interaction_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                INSERT INTO customer_interactions (id, tenant_id, customer_id, interaction_type, channel, call_id, agent_id, sentiment, summary, duration_seconds, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (interaction_id, tenant_id, customer_id, interaction_type, channel, call_id, agent_id, sentiment, summary, duration_seconds, now))
            conn.commit()
            row = conn.execute("SELECT * FROM customer_interactions WHERE id = ?", (interaction_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


# ── Segments ──────────────────────────────────────────────────────

async def create_segment_db(tenant_id, name, criteria_json):
    segment_id = str(uuid.uuid4())
    criteria_str = json.dumps(criteria_json) if isinstance(criteria_json, dict) else criteria_json
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO customer_segments (id, tenant_id, name, criteria_json, created_at)
                VALUES ($1, $2, $3, $4::jsonb, NOW())
            """, segment_id, tenant_id, name, criteria_str)
            row = await pool.fetchrow("SELECT * FROM customer_segments WHERE id = $1", segment_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO customer_segments (id, tenant_id, name, criteria_json, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (segment_id, tenant_id, name, criteria_str, now))
            conn.commit()
            row = conn.execute("SELECT * FROM customer_segments WHERE id = ?", (segment_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_segments_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM customer_segments WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM customer_segments WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_segment_db(segment_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM customer_segments WHERE id = $1", segment_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM customer_segments WHERE id = ?", (segment_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def update_segment_member_count_db(segment_id, count):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("UPDATE customer_segments SET member_count = $1 WHERE id = $2", count, segment_id)
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("UPDATE customer_segments SET member_count = ? WHERE id = ?", (count, segment_id))
            conn.commit()
        finally:
            conn.close()
