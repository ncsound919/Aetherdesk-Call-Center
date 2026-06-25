import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


class TrainingService:
    async def list_courses(self, tenant_id):
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                rows = await pool.fetch("SELECT * FROM training_courses WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
                return [dict(r) for r in rows]
        else:
            conn = _get_sqlite_conn()
            try:
                rows = conn.execute("SELECT * FROM training_courses WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    async def create_course(self, tenant_id, title, description, modules, duration_hours):
        course_id = str(uuid.uuid4())
        modules_json = json.dumps(modules) if isinstance(modules, list) else modules
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                await pool.execute("""
                    INSERT INTO training_courses (id, tenant_id, title, description, modules_json, duration_hours, created_at)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6, NOW())
                """, course_id, tenant_id, title, description, modules_json, duration_hours)
                row = await pool.fetchrow("SELECT * FROM training_courses WHERE id = $1", course_id)
                return dict(row) if row else None
        else:
            conn = _get_sqlite_conn()
            try:
                now = datetime.now(UTC).isoformat()
                conn.execute("""
                    INSERT INTO training_courses (id, tenant_id, title, description, modules_json, duration_hours, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (course_id, tenant_id, title, description, modules_json, duration_hours, now))
                conn.commit()
                row = conn.execute("SELECT * FROM training_courses WHERE id = ?", (course_id,)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    async def enroll_agent(self, tenant_id, agent_id, course_id):
        enrollment_id = str(uuid.uuid4())
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                await pool.execute("""
                    INSERT INTO training_enrollments (id, tenant_id, agent_id, course_id, progress_pct, status, created_at)
                    VALUES ($1, $2, $3, $4, 0, 'enrolled', NOW())
                """, enrollment_id, tenant_id, agent_id, course_id)
                row = await pool.fetchrow("SELECT * FROM training_enrollments WHERE id = $1", enrollment_id)
                return dict(row) if row else None
        else:
            conn = _get_sqlite_conn()
            try:
                now = datetime.now(UTC).isoformat()
                conn.execute("""
                    INSERT INTO training_enrollments (id, tenant_id, agent_id, course_id, progress_pct, status, created_at)
                    VALUES (?, ?, ?, ?, 0, 'enrolled', ?)
                """, (enrollment_id, tenant_id, agent_id, course_id, now))
                conn.commit()
                row = conn.execute("SELECT * FROM training_enrollments WHERE id = ?", (enrollment_id,)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    async def track_progress(self, enrollment_id, module_id, status):
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                row = await pool.fetchrow("SELECT * FROM training_enrollments WHERE id = $1", enrollment_id)
                if not row:
                    return None
                progress = row.get("progress_pct", 0)
                new_progress = min(progress + 100.0 / 5, 100)
                new_status = "completed" if new_progress >= 100 else "in_progress"
                completed_at = "NOW()" if new_status == "completed" else None
                if completed_at:
                    await pool.execute("""
                        UPDATE training_enrollments SET progress_pct = $1, status = $2, completed_at = NOW() WHERE id = $3
                    """, new_progress, new_status, enrollment_id)
                else:
                    await pool.execute("""
                        UPDATE training_enrollments SET progress_pct = $1, status = $2 WHERE id = $3
                    """, new_progress, new_status, enrollment_id)
                row = await pool.fetchrow("SELECT * FROM training_enrollments WHERE id = $1", enrollment_id)
                return dict(row) if row else None
        else:
            conn = _get_sqlite_conn()
            try:
                row = conn.execute("SELECT * FROM training_enrollments WHERE id = ?", (enrollment_id,)).fetchone()
                if not row:
                    return None
                progress = row.get("progress_pct", 0)
                new_progress = min(progress + 100.0 / 5, 100)
                new_status = "completed" if new_progress >= 100 else "in_progress"
                now = datetime.now(UTC).isoformat()
                if new_status == "completed":
                    conn.execute("""
                        UPDATE training_enrollments SET progress_pct = ?, status = ?, completed_at = ? WHERE id = ?
                    """, (new_progress, new_status, now, enrollment_id))
                else:
                    conn.execute("""
                        UPDATE training_enrollments SET progress_pct = ?, status = ? WHERE id = ?
                    """, (new_progress, new_status, enrollment_id))
                conn.commit()
                row = conn.execute("SELECT * FROM training_enrollments WHERE id = ?", (enrollment_id,)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    async def get_agent_certifications(self, tenant_id, agent_id):
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                rows = await pool.fetch("""
                    SELECT e.*, c.title, c.description, c.duration_hours
                    FROM training_enrollments e
                    JOIN training_courses c ON e.course_id = c.id
                    WHERE e.tenant_id = $1 AND e.agent_id = $2 AND e.status = 'completed'
                    ORDER BY e.completed_at DESC
                """, tenant_id, agent_id)
                return [dict(r) for r in rows]
        else:
            conn = _get_sqlite_conn()
            try:
                rows = conn.execute("""
                    SELECT e.*, c.title, c.description, c.duration_hours
                    FROM training_enrollments e
                    JOIN training_courses c ON e.course_id = c.id
                    WHERE e.tenant_id = ? AND e.agent_id = ? AND e.status = 'completed'
                    ORDER BY e.completed_at DESC
                """, (tenant_id, agent_id)).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    async def create_coaching_session(self, tenant_id, agent_id, coach_id, focus_area, notes):
        session_id = str(uuid.uuid4())
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                await pool.execute("""
                    INSERT INTO coaching_sessions (id, tenant_id, agent_id, coach_id, focus_area, notes, status, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, 'scheduled', NOW())
                """, session_id, tenant_id, agent_id, coach_id, focus_area, notes)
                row = await pool.fetchrow("SELECT * FROM coaching_sessions WHERE id = $1", session_id)
                return dict(row) if row else None
        else:
            conn = _get_sqlite_conn()
            try:
                now = datetime.now(UTC).isoformat()
                conn.execute("""
                    INSERT INTO coaching_sessions (id, tenant_id, agent_id, coach_id, focus_area, notes, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?)
                """, (session_id, tenant_id, agent_id, coach_id, focus_area, notes, now))
                conn.commit()
                row = conn.execute("SELECT * FROM coaching_sessions WHERE id = ?", (session_id,)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    async def list_coaching_sessions(self, tenant_id, agent_id=None):
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                if agent_id:
                    rows = await pool.fetch("SELECT * FROM coaching_sessions WHERE tenant_id = $1 AND agent_id = $2 ORDER BY created_at DESC", tenant_id, agent_id)
                else:
                    rows = await pool.fetch("SELECT * FROM coaching_sessions WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
                return [dict(r) for r in rows]
        else:
            conn = _get_sqlite_conn()
            try:
                if agent_id:
                    rows = conn.execute("SELECT * FROM coaching_sessions WHERE tenant_id = ? AND agent_id = ? ORDER BY created_at DESC", (tenant_id, agent_id)).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM coaching_sessions WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()


training_service = TrainingService()
