import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


# ── Failover Tests ─────────────────────────────────────────────────

async def create_failover_test_db(tenant_id, test_type, primary_provider, secondary_provider,
                                  failover_success, failover_time_ms, fallback_success):
    test_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO failover_tests (id, tenant_id, test_type, primary_provider, secondary_provider, failover_success, failover_time_ms, fallback_success, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            """, test_id, tenant_id, test_type, primary_provider, secondary_provider, failover_success, failover_time_ms, fallback_success)
            return test_id
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO failover_tests (id, tenant_id, test_type, primary_provider, secondary_provider, failover_success, failover_time_ms, fallback_success, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (test_id, tenant_id, test_type, primary_provider, secondary_provider, failover_success, failover_time_ms, fallback_success, now))
            conn.commit()
            return test_id
        finally:
            conn.close()
    return None


async def list_failover_tests_db(tenant_id, limit=50):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM failover_tests WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2", tenant_id, limit)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM failover_tests WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?", (tenant_id, limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Conversation Quality Scores ────────────────────────────────────

async def create_conversation_quality_score_db(tenant_id, agent_id, call_id, transcript_hash,
                                              rubric_name, total_score, criteria_scores):
    score_id = str(uuid.uuid4())
    criteria_json = json.dumps(criteria_scores) if isinstance(criteria_scores, dict) else json.dumps({})
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO conversation_quality_scores (id, tenant_id, agent_id, call_id, transcript_hash, rubric_name, total_score, criteria_json, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW())
            """, score_id, tenant_id, agent_id, call_id, transcript_hash, rubric_name, total_score, criteria_json)
            return score_id
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO conversation_quality_scores (id, tenant_id, agent_id, call_id, transcript_hash, rubric_name, total_score, criteria_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (score_id, tenant_id, agent_id, call_id, transcript_hash, rubric_name, total_score, criteria_json, now))
            conn.commit()
            return score_id
        finally:
            conn.close()
    return None


async def list_conversation_quality_scores_db(tenant_id, agent_id=None, limit=100):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if agent_id:
                rows = await pool.fetch("SELECT * FROM conversation_quality_scores WHERE tenant_id = $1 AND agent_id = $2 ORDER BY created_at DESC LIMIT $3", tenant_id, agent_id, limit)
            else:
                rows = await pool.fetch("SELECT * FROM conversation_quality_scores WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2", tenant_id, limit)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            if agent_id:
                rows = conn.execute("SELECT * FROM conversation_quality_scores WHERE tenant_id = ? AND agent_id = ? ORDER BY created_at DESC LIMIT ?", (tenant_id, agent_id, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM conversation_quality_scores WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?", (tenant_id, limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── API Versions ───────────────────────────────────────────────────

async def create_api_version_db(version, status, release_date, sunset_date=None, changelog=None, migration_notes=None):
    version_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO api_versions (id, version, status, release_date, sunset_date, changelog, migration_notes)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, version_id, version, status, release_date, sunset_date, changelog, migration_notes)
            return version_id
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                INSERT INTO api_versions (id, version, status, release_date, sunset_date, changelog, migration_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (version_id, version, status, release_date, sunset_date, changelog, migration_notes))
            conn.commit()
            return version_id
        finally:
            conn.close()
    return None


async def get_api_versions_db():
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM api_versions ORDER BY release_date DESC")
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM api_versions ORDER BY release_date DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def update_api_version_status_db(version, status, sunset_date=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if sunset_date:
                await pool.execute("UPDATE api_versions SET status = $1, sunset_date = $2 WHERE version = $3", status, sunset_date, version)
            else:
                await pool.execute("UPDATE api_versions SET status = $1 WHERE version = $2", status, version)
            return True
    else:
        conn = _get_sqlite_conn()
        try:
            if sunset_date:
                conn.execute("UPDATE api_versions SET status = ?, sunset_date = ? WHERE version = ?", (status, sunset_date, version))
            else:
                conn.execute("UPDATE api_versions SET status = ? WHERE version = ?", (status, version))
            conn.commit()
            return True
        finally:
            conn.close()
    return False


# ── Customer Portal Sessions ───────────────────────────────────────

async def create_customer_portal_session_db(tenant_id, customer_id, session_data):
    session_id = str(uuid.uuid4())
    session_json = json.dumps(session_data) if isinstance(session_data, dict) else json.dumps({})
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO customer_portal_sessions (id, tenant_id, customer_id, session_data_json, created_at)
                VALUES ($1, $2, $3, $4::jsonb, NOW())
            """, session_id, tenant_id, customer_id, session_json)
            return session_id
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO customer_portal_sessions (id, tenant_id, customer_id, session_data_json, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, tenant_id, customer_id, session_json, now))
            conn.commit()
            return session_id
        finally:
            conn.close()
    return None


async def get_customer_portal_session_db(session_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM customer_portal_sessions WHERE id = $1", session_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM customer_portal_sessions WHERE id = ?", (session_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
