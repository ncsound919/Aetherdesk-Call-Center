import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_dr_test_db(tenant_id, test_type, status, result, duration_seconds):
    test_id = str(uuid.uuid4())
    result_json = json.dumps(result) if isinstance(result, dict) else json.dumps({})
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO dr_tests (id, tenant_id, test_type, status, result_json, duration_seconds, tested_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, NOW())
            """, test_id, tenant_id, test_type, status, result_json, duration_seconds)
            row = await pool.fetchrow("SELECT * FROM dr_tests WHERE id = $1", test_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO dr_tests (id, tenant_id, test_type, status, result_json, duration_seconds, tested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (test_id, tenant_id, test_type, status, result_json, duration_seconds, now))
            conn.commit()
            row = conn.execute("SELECT * FROM dr_tests WHERE id = ?", (test_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_dr_tests_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM dr_tests WHERE tenant_id = $1 ORDER BY tested_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM dr_tests WHERE tenant_id = ? ORDER BY tested_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_dr_test_db(test_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM dr_tests WHERE id = $1", test_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM dr_tests WHERE id = ?", (test_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_rate_limit_config_db(tenant_id, route_key):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM rate_limit_configs WHERE tenant_id = $1 AND route_key = $2", tenant_id, route_key)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM rate_limit_configs WHERE tenant_id = ? AND route_key = ?", (tenant_id, route_key)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def set_rate_limit_config_db(tenant_id, route_key, max_requests, window_seconds):
    config_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO rate_limit_configs (id, tenant_id, route_key, max_requests, window_seconds, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
                ON CONFLICT (tenant_id, route_key)
                DO UPDATE SET max_requests = $4, window_seconds = $5, updated_at = NOW()
            """, config_id, tenant_id, route_key, max_requests, window_seconds)
            row = await pool.fetchrow("SELECT * FROM rate_limit_configs WHERE id = $1", config_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            existing = conn.execute(
                "SELECT id FROM rate_limit_configs WHERE tenant_id = ? AND route_key = ?",
                (tenant_id, route_key)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE rate_limit_configs SET max_requests = ?, window_seconds = ?, updated_at = ? WHERE id = ?",
                    (max_requests, window_seconds, now, existing["id"])
                )
                row_id = existing["id"]
            else:
                conn.execute(
                    "INSERT INTO rate_limit_configs (id, tenant_id, route_key, max_requests, window_seconds, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (config_id, tenant_id, route_key, max_requests, window_seconds, now, now)
                )
                row_id = config_id
            conn.commit()
            row = conn.execute("SELECT * FROM rate_limit_configs WHERE id = ?", (row_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_rate_limit_configs_db(tenant_id=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if tenant_id:
                rows = await pool.fetch("SELECT * FROM rate_limit_configs WHERE tenant_id = $1 ORDER BY route_key", tenant_id)
            else:
                rows = await pool.fetch("SELECT * FROM rate_limit_configs ORDER BY tenant_id, route_key")
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            if tenant_id:
                rows = conn.execute("SELECT * FROM rate_limit_configs WHERE tenant_id = ? ORDER BY route_key", (tenant_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM rate_limit_configs ORDER BY tenant_id, route_key").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def log_circuit_breaker_event_db(breaker_name, from_state, to_state, failure_count):
    event_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO circuit_breaker_events (id, breaker_name, from_state, to_state, failure_count, timestamp)
                VALUES ($1, $2, $3, $4, $5, NOW())
            """, event_id, breaker_name, from_state, to_state, failure_count)
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO circuit_breaker_events (id, breaker_name, from_state, to_state, failure_count, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (event_id, breaker_name, from_state, to_state, failure_count, now))
            conn.commit()
        finally:
            conn.close()


async def list_circuit_breaker_events_db(breaker_name=None, limit=100):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if breaker_name:
                rows = await pool.fetch("SELECT * FROM circuit_breaker_events WHERE breaker_name = $1 ORDER BY timestamp DESC LIMIT $2", breaker_name, limit)
            else:
                rows = await pool.fetch("SELECT * FROM circuit_breaker_events ORDER BY timestamp DESC LIMIT $1", limit)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            if breaker_name:
                rows = conn.execute("SELECT * FROM circuit_breaker_events WHERE breaker_name = ? ORDER BY timestamp DESC LIMIT ?", (breaker_name, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM circuit_breaker_events ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
