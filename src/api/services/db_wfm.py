import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


# ── Shifts ────────────────────────────────────────────────────────

async def create_shift_db(tenant_id, agent_id, start_time, end_time, shift_type="regular", notes=None):
    shift_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO wfm_shifts (id, tenant_id, agent_id, start_time, end_time, shift_type, status, notes, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, 'scheduled', $7, NOW(), NOW())
            """, shift_id, tenant_id, agent_id, start_time, end_time, shift_type, notes)
            row = await pool.fetchrow("SELECT * FROM wfm_shifts WHERE id = $1", shift_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO wfm_shifts (id, tenant_id, agent_id, start_time, end_time, shift_type, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?)
            """, (shift_id, tenant_id, agent_id, start_time, end_time, shift_type, notes, now, now))
            conn.commit()
            row = conn.execute("SELECT * FROM wfm_shifts WHERE id = ?", (shift_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_shifts_db(tenant_id, date_from=None, date_to=None, agent_id=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT s.*, a.name as agent_name FROM wfm_shifts s LEFT JOIN agents a ON s.agent_id = a.id WHERE s.tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if date_from:
                query += f" AND s.start_time >= ${idx}"
                params.append(date_from)
                idx += 1
            if date_to:
                query += f" AND s.start_time <= ${idx}"
                params.append(date_to)
                idx += 1
            if agent_id:
                query += f" AND s.agent_id = ${idx}"
                params.append(agent_id)
                idx += 1
            query += " ORDER BY s.start_time ASC"
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT s.*, a.name as agent_name FROM wfm_shifts s LEFT JOIN agents a ON s.agent_id = a.id WHERE s.tenant_id = ?"
            params = [tenant_id]
            if date_from:
                query += " AND s.start_time >= ?"
                params.append(date_from)
            if date_to:
                query += " AND s.start_time <= ?"
                params.append(date_to)
            if agent_id:
                query += " AND s.agent_id = ?"
                params.append(agent_id)
            query += " ORDER BY s.start_time ASC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def update_shift_db(shift_id, tenant_id, **kwargs):
    allowed = {"start_time", "end_time", "shift_type", "status", "notes"}
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
            set_parts.append("updated_at = NOW()")
            params.extend([shift_id, tenant_id])
            await pool.execute(
                f"UPDATE wfm_shifts SET {', '.join(set_parts)} WHERE id = ${idx} AND tenant_id = ${idx+1}",
                *params
            )
            row = await pool.fetchrow("SELECT * FROM wfm_shifts WHERE id = $1", shift_id)
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
            params.extend([shift_id, tenant_id])
            conn.execute(
                f"UPDATE wfm_shifts SET {', '.join(set_parts)} WHERE id = ? AND tenant_id = ?",
                params
            )
            conn.commit()
            row = conn.execute("SELECT * FROM wfm_shifts WHERE id = ?", (shift_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def delete_shift_db(shift_id, tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.execute("DELETE FROM wfm_shifts WHERE id = $1 AND tenant_id = $2", shift_id, tenant_id)
            return "DELETE" in result
    else:
        conn = _get_sqlite_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM wfm_shifts WHERE id = ? AND tenant_id = ?", (shift_id, tenant_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    return False


# ── Schedules ─────────────────────────────────────────────────────

async def create_schedule_db(tenant_id, date, forecasted_volume, forecasted_agents, notes=None):
    sched_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO wfm_schedules (id, tenant_id, date, forecasted_volume, forecasted_agents, notes, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
            """, sched_id, tenant_id, date, forecasted_volume, forecasted_agents, notes)
            row = await pool.fetchrow("SELECT * FROM wfm_schedules WHERE id = $1", sched_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO wfm_schedules (id, tenant_id, date, forecasted_volume, forecasted_agents, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (sched_id, tenant_id, date, forecasted_volume, forecasted_agents, notes, now, now))
            conn.commit()
            row = conn.execute("SELECT * FROM wfm_schedules WHERE id = ?", (sched_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_schedule_db(tenant_id, date):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM wfm_schedules WHERE tenant_id = $1 AND date = $2", tenant_id, date)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM wfm_schedules WHERE tenant_id = ? AND date = ?", (tenant_id, date)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def update_schedule_adherence_db(schedule_id, actual_volume, actual_agents, adherence_pct):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                UPDATE wfm_schedules SET actual_volume = $1, actual_agents = $2, adherence_pct = $3, updated_at = NOW()
                WHERE id = $4
            """, actual_volume, actual_agents, adherence_pct, schedule_id)
            row = await pool.fetchrow("SELECT * FROM wfm_schedules WHERE id = $1", schedule_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                UPDATE wfm_schedules SET actual_volume = ?, actual_agents = ?, adherence_pct = ?, updated_at = ?
                WHERE id = ?
            """, (actual_volume, actual_agents, adherence_pct, now, schedule_id))
            conn.commit()
            row = conn.execute("SELECT * FROM wfm_schedules WHERE id = ?", (schedule_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_schedules_db(tenant_id, date_from=None, date_to=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT * FROM wfm_schedules WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if date_from:
                query += f" AND date >= ${idx}"
                params.append(date_from)
                idx += 1
            if date_to:
                query += f" AND date <= ${idx}"
                params.append(date_to)
                idx += 1
            query += " ORDER BY date ASC"
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT * FROM wfm_schedules WHERE tenant_id = ?"
            params = [tenant_id]
            if date_from:
                query += " AND date >= ?"
                params.append(date_from)
            if date_to:
                query += " AND date <= ?"
                params.append(date_to)
            query += " ORDER BY date ASC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── QA Rubrics ────────────────────────────────────────────────────

async def create_qa_rubric_db(tenant_id, name, criteria, description=None):
    rubric_id = str(uuid.uuid4())
    criteria_json = json.dumps(criteria) if isinstance(criteria, list) else json.dumps([])
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO qa_rubrics (id, tenant_id, name, description, criteria, created_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, NOW())
            """, rubric_id, tenant_id, name, description, criteria_json)
            row = await pool.fetchrow("SELECT * FROM qa_rubrics WHERE id = $1", rubric_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO qa_rubrics (id, tenant_id, name, description, criteria, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (rubric_id, tenant_id, name, description, criteria_json, now))
            conn.commit()
            row = conn.execute("SELECT * FROM qa_rubrics WHERE id = ?", (rubric_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_qa_rubrics_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM qa_rubrics WHERE tenant_id = $1 AND is_active = TRUE ORDER BY created_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM qa_rubrics WHERE tenant_id = ? AND is_active = 1 ORDER BY created_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── QA Scores ─────────────────────────────────────────────────────

async def create_qa_score_db(tenant_id, call_id, agent_id, reviewer_id, rubric_id, scores_per_criterion, notes=None):
    score_id = str(uuid.uuid4())
    scores_json = json.dumps(scores_per_criterion) if isinstance(scores_per_criterion, dict) else json.dumps({})

    # Calculate total_score and max_score from the rubric criteria
    total_score = 0.0
    max_score = 0.0
    if isinstance(scores_per_criterion, dict):
        # Fetch rubric to get weights
        rubric = None
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                rubric = await pool.fetchrow("SELECT criteria FROM qa_rubrics WHERE id = $1", rubric_id)
        else:
            conn = _get_sqlite_conn()
            try:
                rubric = conn.execute("SELECT criteria FROM qa_rubrics WHERE id = ?", (rubric_id,)).fetchone()
            finally:
                conn.close()

        criteria_raw = rubric["criteria"] if rubric else None
        if isinstance(criteria_raw, str):
            criteria_list = json.loads(criteria_raw)
        elif isinstance(criteria_raw, list):
            criteria_list = criteria_raw
        else:
            criteria_list = []

        for criterion in criteria_list:
            cname = criterion.get("name", "")
            weight = criterion.get("weight", 0)
            raw_score = scores_per_criterion.get(cname, 0)
            total_score += (raw_score / 5.0) * weight
            max_score += weight

    if max_score == 0:
        max_score = 100.0

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO qa_scores (id, tenant_id, call_id, agent_id, reviewer_id, rubric_id, total_score, max_score, scores_per_criterion, notes, reviewed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, NOW())
            """, score_id, tenant_id, call_id, agent_id, reviewer_id, rubric_id, total_score, max_score, scores_json, notes)
            row = await pool.fetchrow("SELECT * FROM qa_scores WHERE id = $1", score_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO qa_scores (id, tenant_id, call_id, agent_id, reviewer_id, rubric_id, total_score, max_score, scores_per_criterion, notes, reviewed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (score_id, tenant_id, call_id, agent_id, reviewer_id, rubric_id, total_score, max_score, scores_json, notes, now))
            conn.commit()
            row = conn.execute("SELECT * FROM qa_scores WHERE id = ?", (score_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_qa_scores_db(tenant_id, agent_id=None, date_from=None, date_to=None, limit=100):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT qs.*, a.name as agent_name FROM qa_scores qs LEFT JOIN agents a ON qs.agent_id = a.id WHERE qs.tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if agent_id:
                query += f" AND qs.agent_id = ${idx}"
                params.append(agent_id)
                idx += 1
            if date_from:
                query += f" AND qs.reviewed_at >= ${idx}"
                params.append(date_from)
                idx += 1
            if date_to:
                query += f" AND qs.reviewed_at <= ${idx}"
                params.append(date_to)
                idx += 1
            query += f" ORDER BY qs.reviewed_at DESC LIMIT {limit}"
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT qs.*, a.name as agent_name FROM qa_scores qs LEFT JOIN agents a ON qs.agent_id = a.id WHERE qs.tenant_id = ?"
            params = [tenant_id]
            if agent_id:
                query += " AND qs.agent_id = ?"
                params.append(agent_id)
            if date_from:
                query += " AND qs.reviewed_at >= ?"
                params.append(date_from)
            if date_to:
                query += " AND qs.reviewed_at <= ?"
                params.append(date_to)
            query += f" ORDER BY qs.reviewed_at DESC LIMIT {limit}"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_agent_qa_summary_db(agent_id):
    result = {"avg_score": 0.0, "total_reviewed": 0, "trend": 0.0, "criteria_breakdown": {}}
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("""
                SELECT COUNT(*) as total, COALESCE(AVG(total_score), 0) as avg_score
                FROM qa_scores WHERE agent_id = $1
            """, agent_id)
            if row:
                result["total_reviewed"] = row["total"]
                result["avg_score"] = float(row["avg_score"])

            # Trend: compare last 30 vs previous 30
            recent = await pool.fetchval("""
                SELECT COALESCE(AVG(total_score), 0) FROM qa_scores
                WHERE agent_id = $1 AND reviewed_at >= NOW() - INTERVAL '30 days'
            """, agent_id)
            prev = await pool.fetchval("""
                SELECT COALESCE(AVG(total_score), 0) FROM qa_scores
                WHERE agent_id = $1 AND reviewed_at >= NOW() - INTERVAL '60 days' AND reviewed_at < NOW() - INTERVAL '30 days'
            """, agent_id)
            result["trend"] = float(recent or 0) - float(prev or 0)

            # Criteria breakdown from most recent score
            last = await pool.fetchrow("""
                SELECT scores_per_criterion FROM qa_scores WHERE agent_id = $1 ORDER BY reviewed_at DESC LIMIT 1
            """, agent_id)
            if last and last["scores_per_criterion"]:
                result["criteria_breakdown"] = last["scores_per_criterion"]
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT COUNT(*) as total, COALESCE(AVG(total_score), 0) as avg_score FROM qa_scores WHERE agent_id = ?", (agent_id,)).fetchone()
            if row:
                result["total_reviewed"] = row["total"]
                result["avg_score"] = float(row["avg_score"])

            recent = conn.execute("SELECT COALESCE(AVG(total_score), 0) as avg FROM qa_scores WHERE agent_id = ? AND reviewed_at >= datetime('now', '-30 days')", (agent_id,)).fetchone()
            prev = conn.execute("SELECT COALESCE(AVG(total_score), 0) as avg FROM qa_scores WHERE agent_id = ? AND reviewed_at >= datetime('now', '-60 days') AND reviewed_at < datetime('now', '-30 days')", (agent_id,)).fetchone()
            result["trend"] = float((recent or {}).get("avg", 0) or 0) - float((prev or {}).get("avg", 0) or 0)

            last = conn.execute("SELECT scores_per_criterion FROM qa_scores WHERE agent_id = ? ORDER BY reviewed_at DESC LIMIT 1", (agent_id,)).fetchone()
            if last and last["scores_per_criterion"]:
                try:
                    result["criteria_breakdown"] = json.loads(last["scores_per_criterion"])
                except (json.JSONDecodeError, TypeError):
                    result["criteria_breakdown"] = last["scores_per_criterion"]
        finally:
            conn.close()
    return result


# ── History Helpers ───────────────────────────────────────────────

async def get_call_volume_history_db(tenant_id, days=90):
    """Returns [{date, hour, count}] for the last N days of call volume."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT DATE(start_time) as date, EXTRACT(HOUR FROM start_time) as hour, COUNT(*) as count
                FROM call_sessions
                WHERE tenant_id = $1 AND start_time >= NOW() - INTERVAL '%s days'
                GROUP BY DATE(start_time), EXTRACT(HOUR FROM start_time)
                ORDER BY date, hour
            """ % days, tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT DATE(start_time) as date, CAST(strftime('%%H', start_time) AS INTEGER) as hour, COUNT(*) as count
                FROM call_sessions
                WHERE tenant_id = ? AND start_time >= datetime('now', ?)
                GROUP BY DATE(start_time), strftime('%%H', start_time)
                ORDER BY date, hour
            """, (tenant_id, f"-{days} days")).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_agent_status_history_db(tenant_id, agent_id, date):
    """Returns agent activity timeline for a given date."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("""
                SELECT activity_type, status_before, status_after, created_at, duration_seconds
                FROM agent_activity
                WHERE tenant_id = $1 AND agent_id = $2 AND DATE(created_at) = $3
                ORDER BY created_at ASC
            """, tenant_id, agent_id, date)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("""
                SELECT activity_type, status_before, status_after, created_at, duration_seconds
                FROM agent_activity
                WHERE tenant_id = ? AND agent_id = ? AND DATE(created_at) = ?
                ORDER BY created_at ASC
            """, (tenant_id, agent_id, date)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
