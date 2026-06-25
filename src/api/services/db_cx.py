import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


# ── Surveys ──────────────────────────────────────────────────────

async def create_survey_db(tenant_id, call_id=None, customer_id=None, rating=5, feedback=None, channel="voice", responded=1):
    survey_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO csat_surveys (id, tenant_id, call_id, customer_id, rating, feedback, channel, responded, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            """, survey_id, tenant_id, call_id, customer_id, rating, feedback, channel, responded)
            row = await pool.fetchrow("SELECT * FROM csat_surveys WHERE id = $1", survey_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO csat_surveys (id, tenant_id, call_id, customer_id, rating, feedback, channel, responded, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (survey_id, tenant_id, call_id, customer_id, rating, feedback, channel, responded, now))
            conn.commit()
            row = conn.execute("SELECT * FROM csat_surveys WHERE id = ?", (survey_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_surveys_db(tenant_id, limit=50, offset=0, min_rating=None, channel=None, start_date=None, end_date=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT * FROM csat_surveys WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if min_rating is not None:
                query += f" AND rating >= ${idx}"
                params.append(min_rating)
                idx += 1
            if channel:
                query += f" AND channel = ${idx}"
                params.append(channel)
                idx += 1
            if start_date:
                query += f" AND created_at >= ${idx}"
                params.append(start_date)
                idx += 1
            if end_date:
                query += f" AND created_at <= ${idx}"
                params.append(end_date)
                idx += 1
            query += f" ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}"
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT * FROM csat_surveys WHERE tenant_id = ?"
            params = [tenant_id]
            if min_rating is not None:
                query += " AND rating >= ?"
                params.append(min_rating)
            if channel:
                query += " AND channel = ?"
                params.append(channel)
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_csat_score_db(tenant_id, start_date=None, end_date=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT COALESCE(AVG(rating), 0) as avg_rating, COUNT(*) as total FROM csat_surveys WHERE tenant_id = $1"
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
            row = await pool.fetchrow(query, *params)
            if row:
                return {"avg_rating": float(row["avg_rating"]), "total_surveys": row["total"]}
            return {"avg_rating": 0, "total_surveys": 0}
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT COALESCE(AVG(rating), 0) as avg_rating, COUNT(*) as total FROM csat_surveys WHERE tenant_id = ?"
            params = [tenant_id]
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            row = conn.execute(query, params).fetchone()
            if row:
                return {"avg_rating": float(row["avg_rating"]), "total_surveys": row["total"]}
            return {"avg_rating": 0, "total_surveys": 0}
        finally:
            conn.close()


async def get_response_rate_db(tenant_id, start_date=None, end_date=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT COUNT(*) as total, SUM(CASE WHEN responded = 1 THEN 1 ELSE 0 END) as responded FROM csat_surveys WHERE tenant_id = $1"
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
            row = await pool.fetchrow(query, *params)
            if row and row["total"] > 0:
                rate = float(row["responded"] or 0) / float(row["total"])
                return {"response_rate": round(rate * 100, 2), "total_sent": row["total"], "total_responded": row["responded"] or 0}
            return {"response_rate": 0, "total_sent": 0, "total_responded": 0}
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT COUNT(*) as total, SUM(CASE WHEN responded = 1 THEN 1 ELSE 0 END) as responded FROM csat_surveys WHERE tenant_id = ?"
            params = [tenant_id]
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            row = conn.execute(query, params).fetchone()
            if row and row["total"] > 0:
                rate = float(row["responded"] or 0) / float(row["total"])
                return {"response_rate": round(rate * 100, 2), "total_sent": row["total"], "total_responded": row["responded"] or 0}
            return {"response_rate": 0, "total_sent": 0, "total_responded": 0}
        finally:
            conn.close()


async def get_nps_score_db(tenant_id, start_date=None, end_date=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN rating >= 9 THEN 1 ELSE 0 END) as promoters,
                    SUM(CASE WHEN rating >= 7 AND rating <= 8 THEN 1 ELSE 0 END) as passives,
                    SUM(CASE WHEN rating <= 6 THEN 1 ELSE 0 END) as detractors
                FROM csat_surveys WHERE tenant_id = $1 AND responded = 1
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
            row = await pool.fetchrow(query, *params)
            if row and row["total"] > 0:
                total = float(row["total"])
                promoters_pct = (float(row["promoters"] or 0) / total) * 100
                detractors_pct = (float(row["detractors"] or 0) / total) * 100
                nps = promoters_pct - detractors_pct
                return {
                    "nps": round(nps, 1),
                    "promoters": row["promoters"] or 0,
                    "passives": row["passives"] or 0,
                    "detractors": row["detractors"] or 0,
                    "total": row["total"],
                }
            return {"nps": 0, "promoters": 0, "passives": 0, "detractors": 0, "total": 0}
    else:
        conn = _get_sqlite_conn()
        try:
            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN rating >= 9 THEN 1 ELSE 0 END) as promoters,
                    SUM(CASE WHEN rating >= 7 AND rating <= 8 THEN 1 ELSE 0 END) as passives,
                    SUM(CASE WHEN rating <= 6 THEN 1 ELSE 0 END) as detractors
                FROM csat_surveys WHERE tenant_id = ? AND responded = 1
            """
            params = [tenant_id]
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            row = conn.execute(query, params).fetchone()
            if row and row["total"] > 0:
                total = float(row["total"])
                promoters_pct = (float(row["promoters"] or 0) / total) * 100
                detractors_pct = (float(row["detractors"] or 0) / total) * 100
                nps = promoters_pct - detractors_pct
                return {
                    "nps": round(nps, 1),
                    "promoters": row["promoters"] or 0,
                    "passives": row["passives"] or 0,
                    "detractors": row["detractors"] or 0,
                    "total": row["total"],
                }
            return {"nps": 0, "promoters": 0, "passives": 0, "detractors": 0, "total": 0}
        finally:
            conn.close()


async def get_sentiment_trends_db(tenant_id, start_date=None, end_date=None, granularity="day"):
    if granularity == "hour":
        pg_trunc = "date_trunc('hour', created_at)"
    else:
        pg_trunc = "date_trunc('day', created_at)"

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = f"""
                SELECT {pg_trunc} as period, sentiment, COUNT(*) as count
                FROM customer_interactions
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
            query += f" GROUP BY {pg_trunc}, sentiment ORDER BY period"
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            if granularity == "hour":
                fmt_expr = "strftime('%Y-%m-%d %H:00:00', created_at)"
            else:
                fmt_expr = "date(created_at)"
            query = f"""
                SELECT {fmt_expr} as period, sentiment, COUNT(*) as count
                FROM customer_interactions
                WHERE tenant_id = ?
            """
            params = [tenant_id]
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            query += f" GROUP BY {fmt_expr}, sentiment ORDER BY period"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_customer_360_db(tenant_id, customer_id):
    result = {"customer_id": customer_id, "interactions": [], "surveys": [], "summary": {}}

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            interactions = await pool.fetch(
                "SELECT * FROM customer_interactions WHERE tenant_id = $1 AND customer_id = $2 ORDER BY created_at DESC LIMIT 50",
                tenant_id, customer_id
            )
            result["interactions"] = [dict(r) for r in interactions]

            surveys = await pool.fetch(
                "SELECT * FROM csat_surveys WHERE tenant_id = $1 AND customer_id = $2 ORDER BY created_at DESC LIMIT 50",
                tenant_id, customer_id
            )
            result["surveys"] = [dict(r) for r in surveys]

            summary = await pool.fetchrow("""
                SELECT COUNT(DISTINCT interaction_type) as interaction_types,
                       COUNT(*) as total_interactions,
                       AVG(CASE WHEN sentiment = 'positive' THEN 1.0 WHEN sentiment = 'neutral' THEN 0.5 ELSE 0.0 END) as sentiment_avg
                FROM customer_interactions WHERE tenant_id = $1 AND customer_id = $2
            """, tenant_id, customer_id)
            if summary:
                result["summary"] = dict(summary)

            csat_summary = await pool.fetchrow("""
                SELECT COALESCE(AVG(rating), 0) as avg_csat, COUNT(*) as survey_count
                FROM csat_surveys WHERE tenant_id = $1 AND customer_id = $2
            """, tenant_id, customer_id)
            if csat_summary:
                result["summary"]["avg_csat"] = float(csat_summary["avg_csat"])
                result["summary"]["survey_count"] = csat_summary["survey_count"]
    else:
        conn = _get_sqlite_conn()
        try:
            interactions = conn.execute(
                "SELECT * FROM customer_interactions WHERE tenant_id = ? AND customer_id = ? ORDER BY created_at DESC LIMIT 50",
                (tenant_id, customer_id)
            ).fetchall()
            result["interactions"] = [dict(r) for r in interactions]

            surveys = conn.execute(
                "SELECT * FROM csat_surveys WHERE tenant_id = ? AND customer_id = ? ORDER BY created_at DESC LIMIT 50",
                (tenant_id, customer_id)
            ).fetchall()
            result["surveys"] = [dict(r) for r in surveys]

            summary = conn.execute("""
                SELECT COUNT(DISTINCT interaction_type) as interaction_types,
                       COUNT(*) as total_interactions,
                       AVG(CASE WHEN sentiment = 'positive' THEN 1.0 WHEN sentiment = 'neutral' THEN 0.5 ELSE 0.0 END) as sentiment_avg
                FROM customer_interactions WHERE tenant_id = ? AND customer_id = ?
            """, (tenant_id, customer_id)).fetchone()
            if summary:
                result["summary"] = dict(summary)

            csat_summary = conn.execute("""
                SELECT COALESCE(AVG(rating), 0) as avg_csat, COUNT(*) as survey_count
                FROM csat_surveys WHERE tenant_id = ? AND customer_id = ?
            """, (tenant_id, customer_id)).fetchone()
            if csat_summary:
                result["summary"]["avg_csat"] = float(csat_summary["avg_csat"])
                result["summary"]["survey_count"] = csat_summary["survey_count"]
        finally:
            conn.close()

    return result
