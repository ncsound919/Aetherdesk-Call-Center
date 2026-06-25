import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_lineage_entry_db(tenant_id, source_table, source_id, target_table, target_id, operation, metadata_json=None):
    entry_id = str(uuid.uuid4())
    meta_str = json.dumps(metadata_json) if isinstance(metadata_json, dict) else (metadata_json or "{}")
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("""
                INSERT INTO data_lineage (id, tenant_id, source_table, source_id, target_table, target_id, operation, metadata_json, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW())
                RETURNING *
            """, entry_id, tenant_id, source_table, source_id, target_table, target_id, operation, meta_str)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO data_lineage (id, tenant_id, source_table, source_id, target_table, target_id, operation, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (entry_id, tenant_id, source_table, source_id, target_table, target_id, operation, meta_str, now))
            conn.commit()
            row = conn.execute("SELECT * FROM data_lineage WHERE id = ?", (entry_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_record_lineage_db(tenant_id, table, record_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT * FROM data_lineage
                WHERE tenant_id = $1
                  AND ((source_table = $2 AND source_id = $3) OR (target_table = $2 AND target_id = $3))
                ORDER BY created_at DESC
            """, tenant_id, table, record_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM data_lineage
                WHERE tenant_id = ?
                  AND ((source_table = ? AND source_id = ?) OR (target_table = ? AND target_id = ?))
                ORDER BY created_at DESC
            """, (tenant_id, table, record_id, table, record_id)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_lineage_graph_db(tenant_id, start_date=None, end_date=None, limit=500):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT * FROM data_lineage WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if start_date:
                query += f" AND created_at >= ${idx}"
                params.append(start_date)
                idx += 1
            if end_date:
                query += f" AND created_at <= ${idx}"
                params.append(end_date)
                idx += 1
            query += f" ORDER BY created_at DESC LIMIT {limit}"
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT * FROM data_lineage WHERE tenant_id = ?"
            params = [tenant_id]
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            query += f" ORDER BY created_at DESC LIMIT {limit}"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_column_lineage_db(tenant_id, table, column):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT * FROM data_lineage
                WHERE tenant_id = $1 AND column_name = $2
                  AND (source_table = $3 OR target_table = $3)
                ORDER BY created_at DESC
            """, tenant_id, column, table)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM data_lineage
                WHERE tenant_id = ? AND column_name = ? AND (source_table = ? OR target_table = ?)
                ORDER BY created_at DESC
            """, (tenant_id, column, table)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_data_health_score_db(tenant_id):
    result = {"completeness": 100.0, "consistency": 100.0, "freshness": 100.0, "overall": 100.0}
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("""
                SELECT
                    COUNT(*) as total,
                    COALESCE(AVG(CASE WHEN metadata_json != '{}'::jsonb THEN 1.0 ELSE 0.0 END), 0) * 100 as completeness,
                    COALESCE(COUNT(DISTINCT operation) * 100.0 / NULLIF(COUNT(*), 0), 100) as consistency,
                    COALESCE(EXTRACT(EPOCH FROM NOW() - MAX(created_at)), 0) as seconds_since_last
                FROM data_lineage
                WHERE tenant_id = $1
            """, tenant_id)
            if row:
                total = row["total"]
                if total > 0:
                    result["completeness"] = round(float(row["completeness"]), 1)
                    result["consistency"] = min(round(float(row["consistency"]), 1), 100.0)
                    secs = float(row["seconds_since_last"])
                    if secs < 3600:
                        result["freshness"] = 100.0
                    elif secs < 86400:
                        result["freshness"] = 75.0
                    elif secs < 604800:
                        result["freshness"] = 50.0
                    else:
                        result["freshness"] = 25.0
                    result["overall"] = round((result["completeness"] + result["consistency"] + result["freshness"]) / 3, 1)
            else:
                return result
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("""
                SELECT COUNT(*) as total FROM data_lineage WHERE tenant_id = ?
            """, (tenant_id,)).fetchone()
            total = row["total"] if row else 0
            if total > 0:
                meta_row = conn.execute("""
                    SELECT COUNT(*) as cnt FROM data_lineage WHERE tenant_id = ? AND metadata_json != '{}'
                """, (tenant_id,)).fetchone()
                meta_count = meta_row["cnt"] if meta_row else 0
                result["completeness"] = round((meta_count / total) * 100, 1) if total > 0 else 100.0

                op_row = conn.execute("""
                    SELECT COUNT(DISTINCT operation) as cnt FROM data_lineage WHERE tenant_id = ?
                """, (tenant_id,)).fetchone()
                distinct_ops = op_row["cnt"] if op_row else 1
                result["consistency"] = min(round((distinct_ops / total) * 100, 1) if total > 0 else 100.0, 100.0)

                last_row = conn.execute("""
                    SELECT created_at FROM data_lineage WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 1
                """, (tenant_id,)).fetchone()
                if last_row and last_row["created_at"]:
                    last_str = last_row["created_at"]
                    from datetime import datetime as dt
                    try:
                        last_dt = dt.fromisoformat(last_str)
                        now = datetime.now(UTC)
                        secs = (now - last_dt.replace(tzinfo=UTC)).total_seconds() if last_dt.tzinfo else (now - last_dt.replace(tzinfo=UTC)).total_seconds()
                        if secs < 3600:
                            result["freshness"] = 100.0
                        elif secs < 86400:
                            result["freshness"] = 75.0
                        elif secs < 604800:
                            result["freshness"] = 50.0
                        else:
                            result["freshness"] = 25.0
                    except Exception:
                        pass
                result["overall"] = round((result["completeness"] + result["consistency"] + result["freshness"]) / 3, 1)
            else:
                return {"completeness": 0, "consistency": 0, "freshness": 0, "overall": 0}
        finally:
            conn.close()
    return result
