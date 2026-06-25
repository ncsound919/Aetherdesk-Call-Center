import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_quality_metric_db(tenant_id, call_id, agent_id, mos, jitter_ms, packet_loss_pct, latency_ms, rtt_samples, codec, quality_rating):
    metric_id = str(uuid.uuid4())
    rtt_json = json.dumps(rtt_samples) if isinstance(rtt_samples, list) else json.dumps([])
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO voice_quality_metrics (id, tenant_id, call_id, agent_id, mos, jitter_ms, packet_loss_pct, latency_ms, rtt_samples_json, codec, quality_rating, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, NOW())
            """, metric_id, tenant_id, call_id, agent_id, mos, jitter_ms, packet_loss_pct, latency_ms, rtt_json, codec, quality_rating)
            row = await pool.fetchrow("SELECT * FROM voice_quality_metrics WHERE id = $1", metric_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO voice_quality_metrics (id, tenant_id, call_id, agent_id, mos, jitter_ms, packet_loss_pct, latency_ms, rtt_samples_json, codec, quality_rating, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (metric_id, tenant_id, call_id, agent_id, mos, jitter_ms, packet_loss_pct, latency_ms, rtt_json, codec, quality_rating, now))
            conn.commit()
            row = conn.execute("SELECT * FROM voice_quality_metrics WHERE id = ?", (metric_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_quality_metrics_db(tenant_id, limit=50, offset=0, min_mos=None, start_date=None, end_date=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT * FROM voice_quality_metrics WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if min_mos is not None:
                query += f" AND mos >= ${idx}"
                params.append(min_mos)
                idx += 1
            if start_date:
                query += f" AND created_at >= ${idx}"
                params.append(start_date)
                idx += 1
            if end_date:
                query += f" AND created_at <= ${idx}"
                params.append(end_date)
                idx += 1
            query += " ORDER BY created_at DESC"
            query += f" LIMIT {limit} OFFSET {offset}"
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT * FROM voice_quality_metrics WHERE tenant_id = ?"
            params = [tenant_id]
            if min_mos is not None:
                query += " AND mos >= ?"
                params.append(min_mos)
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            query += " ORDER BY created_at DESC"
            query += f" LIMIT {limit} OFFSET {offset}"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_quality_summary_db(tenant_id, start_date=None, end_date=None):
    result = {
        "avg_mos": 0.0,
        "total_calls": 0,
        "p95_jitter_ms": 0.0,
        "p95_packet_loss_pct": 0.0,
        "quality_distribution": {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "bad": 0},
    }
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            base_query = "FROM voice_quality_metrics WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if start_date:
                base_query += f" AND created_at >= ${idx}"
                params.append(start_date)
                idx += 1
            if end_date:
                base_query += f" AND created_at <= ${idx}"
                params.append(end_date)
                idx += 1

            agg = await pool.fetchrow(f"SELECT COUNT(*) as total, COALESCE(AVG(mos), 0) as avg_mos {base_query}", *params)
            if agg:
                result["total_calls"] = agg["total"]
                result["avg_mos"] = float(agg["avg_mos"])

            rows = await pool.fetch(f"SELECT mos, jitter_ms, packet_loss_pct, quality_rating {base_query}", *params)
            if rows:
                data = [dict(r) for r in rows]
                jitters = sorted([r["jitter_ms"] for r in data])
                losses = sorted([r["packet_loss_pct"] for r in data])
                n = len(jitters)
                result["p95_jitter_ms"] = jitters[int(n * 0.95)] if n > 0 else 0.0
                result["p95_packet_loss_pct"] = losses[int(n * 0.95)] if n > 0 else 0.0
                for r in data:
                    rating = r.get("quality_rating", "unknown")
                    if rating in result["quality_distribution"]:
                        result["quality_distribution"][rating] += 1
    else:
        conn = _get_sqlite_conn()
        try:
            base_query = "FROM voice_quality_metrics WHERE tenant_id = ?"
            params = [tenant_id]
            if start_date:
                base_query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                base_query += " AND created_at <= ?"
                params.append(end_date)

            agg = conn.execute(f"SELECT COUNT(*) as total, COALESCE(AVG(mos), 0) as avg_mos {base_query}", params).fetchone()
            if agg:
                result["total_calls"] = agg["total"]
                result["avg_mos"] = float(agg["avg_mos"])

            rows = conn.execute(f"SELECT mos, jitter_ms, packet_loss_pct, quality_rating {base_query}", params).fetchall()
            if rows:
                data = [dict(r) for r in rows]
                jitters = sorted([r["jitter_ms"] for r in data])
                losses = sorted([r["packet_loss_pct"] for r in data])
                n = len(jitters)
                result["p95_jitter_ms"] = jitters[int(n * 0.95)] if n > 0 else 0.0
                result["p95_packet_loss_pct"] = losses[int(n * 0.95)] if n > 0 else 0.0
                for r in data:
                    rating = r.get("quality_rating", "unknown")
                    if rating in result["quality_distribution"]:
                        result["quality_distribution"][rating] += 1
        finally:
            conn.close()
    return result


async def get_quality_trends_db(tenant_id, start_date=None, end_date=None, granularity="hour"):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if granularity == "hour":
                trunc = "date_trunc('hour', created_at)"
            elif granularity == "day":
                trunc = "date_trunc('day', created_at)"
            else:
                trunc = "date_trunc('hour', created_at)"

            query = f"""
                SELECT {trunc} as bucket,
                       COUNT(*) as call_count,
                       AVG(mos) as avg_mos,
                       AVG(jitter_ms) as avg_jitter,
                       AVG(packet_loss_pct) as avg_packet_loss,
                       AVG(latency_ms) as avg_latency
                FROM voice_quality_metrics
                WHERE tenant_id = $1
            """
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
            query += " GROUP BY bucket ORDER BY bucket ASC"
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            if granularity == "hour":
                trunc = "strftime('%Y-%m-%dT%H:00:00', created_at)"
            elif granularity == "day":
                trunc = "strftime('%Y-%m-%d', created_at)"
            else:
                trunc = "strftime('%Y-%m-%dT%H:00:00', created_at)"

            query = f"""
                SELECT {trunc} as bucket,
                       COUNT(*) as call_count,
                       AVG(mos) as avg_mos,
                       AVG(jitter_ms) as avg_jitter,
                       AVG(packet_loss_pct) as avg_packet_loss,
                       AVG(latency_ms) as avg_latency
                FROM voice_quality_metrics
                WHERE tenant_id = ?
            """
            params = [tenant_id]
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            query += " GROUP BY bucket ORDER BY bucket ASC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_call_quality_db(tenant_id, call_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow(
                "SELECT * FROM voice_quality_metrics WHERE tenant_id = $1 AND call_id = $2 ORDER BY created_at DESC LIMIT 1",
                tenant_id, call_id
            )
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM voice_quality_metrics WHERE tenant_id = ? AND call_id = ? ORDER BY created_at DESC LIMIT 1",
                (tenant_id, call_id)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
