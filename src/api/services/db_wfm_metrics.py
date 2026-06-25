import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_aht_db(tenant_id, agent_id, call_id, duration_seconds):
    record_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO wfm_aht (id, tenant_id, agent_id, call_id, duration_seconds, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
            """, record_id, tenant_id, agent_id, call_id, duration_seconds)
            row = await pool.fetchrow("SELECT * FROM wfm_aht WHERE id = $1", record_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO wfm_aht (id, tenant_id, agent_id, call_id, duration_seconds, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (record_id, tenant_id, agent_id, call_id, duration_seconds, now))
            conn.commit()
            row = conn.execute("SELECT * FROM wfm_aht WHERE id = ?", (record_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def create_fcr_db(tenant_id, customer_id, call_id, resolved, follow_up_call_id=None):
    record_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO wfm_fcr (id, tenant_id, customer_id, call_id, resolved, follow_up_call_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
            """, record_id, tenant_id, customer_id, call_id, 1 if resolved else 0, follow_up_call_id)
            row = await pool.fetchrow("SELECT * FROM wfm_fcr WHERE id = $1", record_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO wfm_fcr (id, tenant_id, customer_id, call_id, resolved, follow_up_call_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (record_id, tenant_id, customer_id, call_id, 1 if resolved else 0, follow_up_call_id, now))
            conn.commit()
            row = conn.execute("SELECT * FROM wfm_fcr WHERE id = ?", (record_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def create_csat_db(tenant_id, customer_id, call_id, rating):
    record_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO wfm_csat (id, tenant_id, customer_id, call_id, rating, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
            """, record_id, tenant_id, customer_id, call_id, rating)
            row = await pool.fetchrow("SELECT * FROM wfm_csat WHERE id = $1", record_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO wfm_csat (id, tenant_id, customer_id, call_id, rating, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (record_id, tenant_id, customer_id, call_id, rating, now))
            conn.commit()
            row = conn.execute("SELECT * FROM wfm_csat WHERE id = ?", (record_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def create_nps_db(tenant_id, customer_id, call_id, score):
    record_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO wfm_nps (id, tenant_id, customer_id, call_id, score, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
            """, record_id, tenant_id, customer_id, call_id, score)
            row = await pool.fetchrow("SELECT * FROM wfm_nps WHERE id = $1", record_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO wfm_nps (id, tenant_id, customer_id, call_id, score, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (record_id, tenant_id, customer_id, call_id, score, now))
            conn.commit()
            row = conn.execute("SELECT * FROM wfm_nps WHERE id = ?", (record_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_aht_stats_db(tenant_id, period="7d"):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            interval_map = {"24h": "24 hours", "7d": "7 days", "30d": "30 days", "90d": "90 days"}
            interval = interval_map.get(period, "7 days")
            rows = await pool.fetch("""
                SELECT duration_seconds FROM wfm_aht
                WHERE tenant_id = $1 AND created_at >= NOW() - INTERVAL '%s'
            """ % interval, tenant_id)
            durations = [r["duration_seconds"] for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            days_map = {"24h": "-1 days", "7d": "-7 days", "30d": "-30 days", "90d": "-90 days"}
            days = days_map.get(period, "-7 days")
            rows = conn.execute("""
                SELECT duration_seconds FROM wfm_aht
                WHERE tenant_id = ? AND created_at >= datetime('now', ?)
            """, (tenant_id, days)).fetchall()
            durations = [r["duration_seconds"] for r in rows]
        finally:
            conn.close()

    if not durations:
        return {"avg": 0, "p50": 0, "p90": 0, "p99": 0, "count": 0}

    durations.sort()
    n = len(durations)
    avg = sum(durations) / n

    def percentile(p):
        k = (n - 1) * p / 100
        f = int(k)
        c = f + 1
        if c >= n:
            return durations[-1]
        return durations[f] + (k - f) * (durations[c] - durations[f])

    return {
        "avg": round(avg, 2),
        "p50": round(percentile(50), 2),
        "p90": round(percentile(90), 2),
        "p99": round(percentile(99), 2),
        "count": n,
    }


async def get_fcr_stats_db(tenant_id, period="7d"):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            interval_map = {"24h": "24 hours", "7d": "7 days", "30d": "30 days", "90d": "90 days"}
            interval = interval_map.get(period, "7 days")
            rows = await pool.fetch("""
                SELECT resolved FROM wfm_fcr
                WHERE tenant_id = $1 AND created_at >= NOW() - INTERVAL '%s'
            """ % interval, tenant_id)
    else:
        conn = _get_sqlite_conn()
        try:
            days_map = {"24h": "-1 days", "7d": "-7 days", "30d": "-30 days", "90d": "-90 days"}
            days = days_map.get(period, "-7 days")
            rows = conn.execute("""
                SELECT resolved FROM wfm_fcr
                WHERE tenant_id = ? AND created_at >= datetime('now', ?)
            """, (tenant_id, days)).fetchall()
        finally:
            conn.close()

    total = len(rows)
    if total == 0:
        return {"fcr_rate": 0.0, "resolved": 0, "total": 0}
    resolved = sum(1 for r in rows if r["resolved"])
    return {"fcr_rate": round(resolved / total * 100, 2), "resolved": resolved, "total": total}


async def get_csat_trend_db(tenant_id, period="7d"):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            interval_map = {"24h": "24 hours", "7d": "7 days", "30d": "30 days", "90d": "90 days"}
            interval = interval_map.get(period, "7 days")
            rows = await pool.fetch("""
                SELECT DATE(created_at) as date, AVG(rating) as avg_rating, COUNT(*) as count
                FROM wfm_csat
                WHERE tenant_id = $1 AND created_at >= NOW() - INTERVAL '%s'
                GROUP BY DATE(created_at)
                ORDER BY date
            """ % interval, tenant_id)
            return [{"date": str(r["date"]), "avg_rating": round(float(r["avg_rating"]), 2), "count": r["count"]} for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            days_map = {"24h": "-1 days", "7d": "-7 days", "30d": "-30 days", "90d": "-90 days"}
            days = days_map.get(period, "-7 days")
            rows = conn.execute("""
                SELECT DATE(created_at) as date, AVG(rating) as avg_rating, COUNT(*) as count
                FROM wfm_csat
                WHERE tenant_id = ? AND created_at >= datetime('now', ?)
                GROUP BY DATE(created_at)
                ORDER BY date
            """, (tenant_id, days)).fetchall()
            return [{"date": r["date"], "avg_rating": round(r["avg_rating"], 2), "count": r["count"]} for r in rows]
        finally:
            conn.close()
    return []


async def get_nps_stats_db(tenant_id, period="7d"):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            interval_map = {"24h": "24 hours", "7d": "7 days", "30d": "30 days", "90d": "90 days"}
            interval = interval_map.get(period, "7 days")
            rows = await pool.fetch("""
                SELECT score FROM wfm_nps
                WHERE tenant_id = $1 AND created_at >= NOW() - INTERVAL '%s'
            """ % interval, tenant_id)
    else:
        conn = _get_sqlite_conn()
        try:
            days_map = {"24h": "-1 days", "7d": "-7 days", "30d": "-30 days", "90d": "-90 days"}
            days = days_map.get(period, "-7 days")
            rows = conn.execute("""
                SELECT score FROM wfm_nps
                WHERE tenant_id = ? AND created_at >= datetime('now', ?)
            """, (tenant_id, days)).fetchall()
        finally:
            conn.close()

    scores = [r["score"] for r in rows]
    total = len(scores)
    if total == 0:
        return {"nps_score": 0, "promoters": 0, "passives": 0, "detractors": 0, "total": 0}
    promoters = sum(1 for s in scores if s >= 9)
    passives = sum(1 for s in scores if 7 <= s <= 8)
    detractors = sum(1 for s in scores if s <= 6)
    nps = round((promoters - detractors) / total * 100, 2)
    return {"nps_score": nps, "promoters": promoters, "passives": passives, "detractors": detractors, "total": total}


async def list_aht_db(tenant_id, limit=50):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM wfm_aht WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2", tenant_id, limit)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM wfm_aht WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?", (tenant_id, limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def list_fcr_db(tenant_id, limit=50):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM wfm_fcr WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2", tenant_id, limit)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM wfm_fcr WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?", (tenant_id, limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def list_csat_db(tenant_id, limit=50):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM wfm_csat WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2", tenant_id, limit)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM wfm_csat WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?", (tenant_id, limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
