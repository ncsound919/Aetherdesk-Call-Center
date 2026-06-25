import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_failover_test_db(tenant_id, service, result, duration_seconds, tested_by):
    test_id = str(uuid.uuid4())
    result_json = json.dumps(result) if isinstance(result, dict) else result
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO failover_tests (id, tenant_id, service, status, result_json, duration_seconds, tested_by, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            """, test_id, tenant_id, service, result.get("status", "unknown"), result_json, duration_seconds, tested_by)
            row = await pool.fetchrow("SELECT * FROM failover_tests WHERE id = $1", test_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO failover_tests (id, tenant_id, service, status, result_json, duration_seconds, tested_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (test_id, tenant_id, service, result.get("status", "unknown"), result_json, duration_seconds, tested_by, now))
            conn.commit()
            row = conn.execute("SELECT * FROM failover_tests WHERE id = ?", (test_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


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


async def create_chaos_experiment_db(tenant_id, target, fault_type, duration_seconds):
    exp_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO chaos_experiments (id, tenant_id, target, fault_type, duration_seconds, status, result_json, created_at)
                VALUES ($1, $2, $3, $4, $5, 'running', '{}'::jsonb, NOW())
            """, exp_id, tenant_id, target, fault_type, duration_seconds)
            row = await pool.fetchrow("SELECT * FROM chaos_experiments WHERE id = $1", exp_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO chaos_experiments (id, tenant_id, target, fault_type, duration_seconds, status, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, 'running', '{}', ?)
            """, (exp_id, tenant_id, target, fault_type, duration_seconds, now))
            conn.commit()
            row = conn.execute("SELECT * FROM chaos_experiments WHERE id = ?", (exp_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def update_chaos_experiment_db(exp_id, status, result):
    result_json = json.dumps(result) if isinstance(result, dict) else result
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                UPDATE chaos_experiments SET status = $1, result_json = $2::jsonb WHERE id = $3
            """, status, result_json, exp_id)
            row = await pool.fetchrow("SELECT * FROM chaos_experiments WHERE id = $1", exp_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("UPDATE chaos_experiments SET status = ?, result_json = ? WHERE id = ?", (status, result_json, exp_id))
            conn.commit()
            row = conn.execute("SELECT * FROM chaos_experiments WHERE id = ?", (exp_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_chaos_experiments_db(tenant_id, limit=50):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM chaos_experiments WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2", tenant_id, limit)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM chaos_experiments WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?", (tenant_id, limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def create_contract_db(tenant_id, vendor, terms, renewal_date, cost=None):
    contract_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO vendor_contracts (id, tenant_id, vendor, terms, renewal_date, status, cost, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, 'active', $6, NOW(), NOW())
            """, contract_id, tenant_id, vendor, terms, renewal_date, cost)
            row = await pool.fetchrow("SELECT * FROM vendor_contracts WHERE id = $1", contract_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO vendor_contracts (id, tenant_id, vendor, terms, renewal_date, status, cost, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """, (contract_id, tenant_id, vendor, terms, renewal_date, cost, now, now))
            conn.commit()
            row = conn.execute("SELECT * FROM vendor_contracts WHERE id = ?", (contract_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_contracts_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM vendor_contracts WHERE tenant_id = $1 ORDER BY renewal_date ASC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM vendor_contracts WHERE tenant_id = ? ORDER BY renewal_date ASC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_contract_alerts_db(tenant_id, days_ahead=30):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT * FROM vendor_contracts
                WHERE tenant_id = $1 AND status = 'active'
                AND renewal_date BETWEEN NOW() AND NOW() + INTERVAL '%s days'
                ORDER BY renewal_date ASC
            """ % days_ahead, tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM vendor_contracts
                WHERE tenant_id = ? AND status = 'active'
                AND renewal_date BETWEEN datetime('now') AND datetime('now', '+%s days')
                ORDER BY renewal_date ASC
            """ % days_ahead, (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def create_backup_channel_db(tenant_id, channel_type, config):
    channel_id = str(uuid.uuid4())
    config_json = json.dumps(config) if isinstance(config, dict) else config
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO backup_channels (id, tenant_id, channel_type, config_json, status, created_at)
                VALUES ($1, $2, $3, $4::jsonb, 'active', NOW())
            """, channel_id, tenant_id, channel_type, config_json)
            row = await pool.fetchrow("SELECT * FROM backup_channels WHERE id = $1", channel_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO backup_channels (id, tenant_id, channel_type, config_json, status, created_at)
                VALUES (?, ?, ?, ?, 'active', ?)
            """, (channel_id, tenant_id, channel_type, config_json, now))
            conn.commit()
            row = conn.execute("SELECT * FROM backup_channels WHERE id = ?", (channel_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_backup_channels_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM backup_channels WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM backup_channels WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def update_backup_channel_test_db(channel_id, status):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("UPDATE backup_channels SET last_test_at = NOW(), status = $1 WHERE id = $2", status, channel_id)
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("UPDATE backup_channels SET last_test_at = ?, status = ? WHERE id = ?", (now, status, channel_id))
            conn.commit()
        finally:
            conn.close()
