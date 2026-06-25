import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_model_db(
    tenant_id: str,
    name: str,
    version: str,
    model_type: str = "intent",
    config_json: str = "{}",
    metrics_json: str = "{}",
) -> dict | None:
    model_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO ai_models (id, tenant_id, name, version, model_type, config_json, metrics_json, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, 'staging', NOW())
            """, model_id, tenant_id, name, version, model_type, config_json, metrics_json)
            row = await pool.fetchrow("SELECT * FROM ai_models WHERE id = $1", model_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO ai_models (id, tenant_id, name, version, model_type, config_json, metrics_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'staging', ?)
            """, (model_id, tenant_id, name, version, model_type, config_json, metrics_json, now))
            conn.commit()
            row = conn.execute("SELECT * FROM ai_models WHERE id = ?", (model_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def list_models_db(tenant_id: str, model_type: str | None = None) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT * FROM ai_models WHERE tenant_id = $1"
            params = [tenant_id]
            if model_type:
                query += " AND model_type = $2"
                params.append(model_type)
            query += " ORDER BY created_at DESC"
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT * FROM ai_models WHERE tenant_id = ?"
            params = [tenant_id]
            if model_type:
                query += " AND model_type = ?"
                params.append(model_type)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


async def get_model_db(tenant_id: str, model_id: str) -> dict | None:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM ai_models WHERE id = $1 AND tenant_id = $2", model_id, tenant_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM ai_models WHERE id = ? AND tenant_id = ?", (model_id, tenant_id)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def get_model_version_db(tenant_id: str, model_id: str, version: str) -> dict | None:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow(
                "SELECT * FROM ai_models WHERE id = $1 AND tenant_id = $2 AND version = $3",
                model_id, tenant_id, version,
            )
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM ai_models WHERE id = ? AND tenant_id = ? AND version = ?",
                (model_id, tenant_id, version),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def promote_model_db(tenant_id: str, model_id: str, version: str, environment: str = "production") -> dict | None:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "UPDATE ai_models SET status = $1 WHERE tenant_id = $2 AND model_type = (SELECT model_type FROM ai_models WHERE id = $3 AND tenant_id = $4)",
                environment, tenant_id, model_id, tenant_id,
            )
            await pool.execute(
                "UPDATE ai_models SET status = $1 WHERE id = $2 AND tenant_id = $3 AND version = $4",
                environment, model_id, tenant_id, version,
            )
            row = await pool.fetchrow("SELECT * FROM ai_models WHERE id = $1 AND tenant_id = $2 AND version = $3", model_id, tenant_id, version)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            # Set same type models to staging
            model_type_row = conn.execute("SELECT model_type FROM ai_models WHERE id = ? AND tenant_id = ?", (model_id, tenant_id)).fetchone()
            if model_type_row:
                conn.execute(
                    "UPDATE ai_models SET status = 'staging' WHERE tenant_id = ? AND model_type = ? AND id != ?",
                    (tenant_id, model_type_row["model_type"], model_id),
                )
            conn.execute(
                "UPDATE ai_models SET status = ? WHERE id = ? AND tenant_id = ? AND version = ?",
                (environment, model_id, tenant_id, version),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM ai_models WHERE id = ? AND tenant_id = ? AND version = ?", (model_id, tenant_id, version)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def rollback_model_db(tenant_id: str, model_id: str, version: str) -> dict | None:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "UPDATE ai_models SET status = 'staging' WHERE id = $1 AND tenant_id = $2",
                model_id, tenant_id,
            )
            await pool.execute(
                "UPDATE ai_models SET status = 'production' WHERE id = $1 AND tenant_id = $2 AND version = $3",
                model_id, tenant_id, version,
            )
            row = await pool.fetchrow("SELECT * FROM ai_models WHERE id = $1 AND tenant_id = $2 AND version = $3", model_id, tenant_id, version)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute(
                "UPDATE ai_models SET status = 'staging' WHERE id = ? AND tenant_id = ?",
                (model_id, tenant_id),
            )
            conn.execute(
                "UPDATE ai_models SET status = 'production' WHERE id = ? AND tenant_id = ? AND version = ?",
                (model_id, tenant_id, version),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM ai_models WHERE id = ? AND tenant_id = ? AND version = ?", (model_id, tenant_id, version)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def get_active_model_db(tenant_id: str, model_type: str = "intent") -> dict | None:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow(
                "SELECT * FROM ai_models WHERE tenant_id = $1 AND model_type = $2 AND status = 'production' ORDER BY created_at DESC LIMIT 1",
                tenant_id, model_type,
            )
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM ai_models WHERE tenant_id = ? AND model_type = ? AND status = 'production' ORDER BY created_at DESC LIMIT 1",
                (tenant_id, model_type),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


# ── Training Jobs ──────────────────────────────────────────────────

async def create_training_job_db(
    tenant_id: str,
    name: str,
    model_base: str,
    hyperparams_json: str = "{}",
) -> dict | None:
    job_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO training_jobs (id, tenant_id, name, model_base, hyperparams_json, status, progress, example_count, created_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, 'pending', 0.0, 0, NOW())
            """, job_id, tenant_id, name, model_base, hyperparams_json)
            row = await pool.fetchrow("SELECT * FROM training_jobs WHERE id = $1", job_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO training_jobs (id, tenant_id, name, model_base, hyperparams_json, status, progress, example_count, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', 0.0, 0, ?)
            """, (job_id, tenant_id, name, model_base, hyperparams_json, now))
            conn.commit()
            row = conn.execute("SELECT * FROM training_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def get_training_job_db(job_id: str) -> dict | None:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM training_jobs WHERE id = $1", job_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM training_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def list_training_jobs_db(tenant_id: str) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM training_jobs WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM training_jobs WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


async def update_training_job_db(
    job_id: str,
    status: str | None = None,
    progress: float | None = None,
    example_count: int | None = None,
    result_json: str | None = None,
    error_message: str | None = None,
) -> dict | None:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            sets = []
            params = []
            idx = 1
            if status is not None:
                sets.append(f"status = ${idx}")
                params.append(status)
                idx += 1
            if progress is not None:
                sets.append(f"progress = ${idx}")
                params.append(progress)
                idx += 1
            if example_count is not None:
                sets.append(f"example_count = ${idx}")
                params.append(example_count)
                idx += 1
            if result_json is not None:
                sets.append(f"result_json = ${idx}::jsonb")
                params.append(result_json)
                idx += 1
            if error_message is not None:
                sets.append(f"error_message = ${idx}")
                params.append(error_message)
                idx += 1
            if status == "completed":
                sets.append("completed_at = NOW()")
            if sets:
                params.append(job_id)
                await pool.execute(f"UPDATE training_jobs SET {', '.join(sets)} WHERE id = ${idx}", *params)
            row = await pool.fetchrow("SELECT * FROM training_jobs WHERE id = $1", job_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            sets = []
            params = []
            if status is not None:
                sets.append("status = ?")
                params.append(status)
            if progress is not None:
                sets.append("progress = ?")
                params.append(progress)
            if example_count is not None:
                sets.append("example_count = ?")
                params.append(example_count)
            if result_json is not None:
                sets.append("result_json = ?")
                params.append(result_json)
            if error_message is not None:
                sets.append("error_message = ?")
                params.append(error_message)
            if status == "completed":
                sets.append("completed_at = ?")
                params.append(datetime.now(UTC).isoformat())
            if sets:
                params.append(job_id)
                conn.execute(f"UPDATE training_jobs SET {', '.join(sets)} WHERE id = ?", params)
                conn.commit()
            row = conn.execute("SELECT * FROM training_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


# ── Voice Profiles ────────────────────────────────────────────────

async def create_voice_profile_db(
    tenant_id: str,
    speaker_name: str,
    features_json: str = "{}",
) -> dict | None:
    profile_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO voice_profiles (id, tenant_id, speaker_name, features_json, created_at)
                VALUES ($1, $2, $3, $4::jsonb, NOW())
            """, profile_id, tenant_id, speaker_name, features_json)
            row = await pool.fetchrow("SELECT * FROM voice_profiles WHERE id = $1", profile_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO voice_profiles (id, tenant_id, speaker_name, features_json, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (profile_id, tenant_id, speaker_name, features_json, now))
            conn.commit()
            row = conn.execute("SELECT * FROM voice_profiles WHERE id = ?", (profile_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def list_voice_profiles_db(tenant_id: str) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM voice_profiles WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM voice_profiles WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


# ── Emotion Logs ──────────────────────────────────────────────────

async def create_emotion_log_db(
    tenant_id: str,
    call_id: str | None = None,
    speaker: str | None = None,
    emotion: str = "neutral",
    confidence: float = 0.0,
    timestamp_ms: int = 0,
) -> dict | None:
    log_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO emotion_logs (id, tenant_id, call_id, speaker, emotion, confidence, timestamp_ms, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            """, log_id, tenant_id, call_id, speaker, emotion, confidence, timestamp_ms)
            row = await pool.fetchrow("SELECT * FROM emotion_logs WHERE id = $1", log_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO emotion_logs (id, tenant_id, call_id, speaker, emotion, confidence, timestamp_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, tenant_id, call_id, speaker, emotion, confidence, timestamp_ms, now))
            conn.commit()
            row = conn.execute("SELECT * FROM emotion_logs WHERE id = ?", (log_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def get_emotion_trends_db(tenant_id: str, call_id: str) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch(
                "SELECT * FROM emotion_logs WHERE tenant_id = $1 AND call_id = $2 ORDER BY timestamp_ms ASC",
                tenant_id, call_id,
            )
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM emotion_logs WHERE tenant_id = ? AND call_id = ? ORDER BY timestamp_ms ASC",
                (tenant_id, call_id),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


# ── Datasets ────────────────────────────────────────────────────────

async def create_dataset_db(
    tenant_id: str,
    name: str,
    version: str = "1.0.0",
    recipe_type: str = "dialogue",
    recipe_version: str = "1.0",
    source_start_date: str | None = None,
    source_end_date: str | None = None,
    total_examples: int = 0,
    total_turns: int = 0,
    quality_score: float = 0.0,
    stats_json: str = "{}",
    status: str = "building",
) -> dict | None:
    dataset_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO datasets (id, tenant_id, name, version, recipe_type, recipe_version,
                    source_start_date, source_end_date, total_examples, total_turns,
                    quality_score, stats_json, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13, NOW())
            """, dataset_id, tenant_id, name, version, recipe_type, recipe_version,
                source_start_date, source_end_date, total_examples, total_turns,
                quality_score, stats_json, status)
            row = await pool.fetchrow("SELECT * FROM datasets WHERE id = $1", dataset_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO datasets (id, tenant_id, name, version, recipe_type, recipe_version,
                    source_start_date, source_end_date, total_examples, total_turns,
                    quality_score, stats_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (dataset_id, tenant_id, name, version, recipe_type, recipe_version,
                  source_start_date, source_end_date, total_examples, total_turns,
                  quality_score, stats_json, status, now))
            conn.commit()
            row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def list_datasets_db(tenant_id: str, recipe_type: str | None = None, limit: int = 50) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT * FROM datasets WHERE tenant_id = $1"
            params = [tenant_id]
            if recipe_type:
                query += " AND recipe_type = $2"
                params.append(recipe_type)
            query += " ORDER BY created_at DESC LIMIT $3"
            params.append(limit)
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT * FROM datasets WHERE tenant_id = ?"
            params = [tenant_id]
            if recipe_type:
                query += " AND recipe_type = ?"
                params.append(recipe_type)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


async def get_dataset_db(dataset_id: str) -> dict | None:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM datasets WHERE id = $1", dataset_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def update_dataset_db(
    dataset_id: str,
    total_examples: int | None = None,
    total_turns: int | None = None,
    quality_score: float | None = None,
    stats_json: str | None = None,
    status: str | None = None,
) -> dict | None:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            sets = []
            params = []
            idx = 1
            if total_examples is not None:
                sets.append(f"total_examples = ${idx}"); params.append(total_examples); idx += 1
            if total_turns is not None:
                sets.append(f"total_turns = ${idx}"); params.append(total_turns); idx += 1
            if quality_score is not None:
                sets.append(f"quality_score = ${idx}"); params.append(quality_score); idx += 1
            if stats_json is not None:
                sets.append(f"stats_json = ${idx}::jsonb"); params.append(stats_json); idx += 1
            if status is not None:
                sets.append(f"status = ${idx}"); params.append(status); idx += 1
            if sets:
                params.append(dataset_id)
                await pool.execute(f"UPDATE datasets SET {', '.join(sets)} WHERE id = ${idx}", *params)
            row = await pool.fetchrow("SELECT * FROM datasets WHERE id = $1", dataset_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            sets = []
            params = []
            if total_examples is not None:
                sets.append("total_examples = ?"); params.append(total_examples)
            if total_turns is not None:
                sets.append("total_turns = ?"); params.append(total_turns)
            if quality_score is not None:
                sets.append("quality_score = ?"); params.append(quality_score)
            if stats_json is not None:
                sets.append("stats_json = ?"); params.append(stats_json)
            if status is not None:
                sets.append("status = ?"); params.append(status)
            if sets:
                params.append(dataset_id)
                conn.execute(f"UPDATE datasets SET {', '.join(sets)} WHERE id = ?", params)
                conn.commit()
            row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


# ── Turns ───────────────────────────────────────────────────────────

async def create_turn_db(
    tenant_id: str,
    call_id: str | None = None,
    dataset_id: str | None = None,
    speaker: str = "customer",
    text: str = "",
    turn_index: int = 0,
    start_ms: int = 0,
    end_ms: int = 0,
    asr_confidence: float = 0.0,
    sentiment: str = "neutral",
    emotion: str = "neutral",
    intent: str | None = None,
    is_low_quality: int = 0,
) -> dict | None:
    turn_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO turns (id, tenant_id, call_id, dataset_id, speaker, text,
                    turn_index, start_ms, end_ms, asr_confidence, sentiment, emotion,
                    intent, is_low_quality, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
            """, turn_id, tenant_id, call_id, dataset_id, speaker, text,
                turn_index, start_ms, end_ms, asr_confidence, sentiment, emotion,
                intent, is_low_quality)
            row = await pool.fetchrow("SELECT * FROM turns WHERE id = $1", turn_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO turns (id, tenant_id, call_id, dataset_id, speaker, text,
                    turn_index, start_ms, end_ms, asr_confidence, sentiment, emotion,
                    intent, is_low_quality, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (turn_id, tenant_id, call_id, dataset_id, speaker, text,
                  turn_index, start_ms, end_ms, asr_confidence, sentiment, emotion,
                  intent, is_low_quality, now))
            conn.commit()
            row = conn.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def list_turns_db(dataset_id: str, limit: int = 500, offset: int = 0) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch(
                "SELECT * FROM turns WHERE dataset_id = $1 ORDER BY turn_index ASC LIMIT $2 OFFSET $3",
                dataset_id, limit, offset,
            )
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM turns WHERE dataset_id = ? ORDER BY turn_index ASC LIMIT ? OFFSET ?",
                (dataset_id, limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


# ── Labels ──────────────────────────────────────────────────────────

async def create_label_db(
    tenant_id: str,
    turn_id: str,
    labeler_id: str | None = None,
    label_type: str = "intent",
    label_value: str = "",
    confidence: float = 1.0,
    notes: str | None = None,
) -> dict | None:
    label_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO labels (id, tenant_id, turn_id, labeler_id, label_type,
                    label_value, confidence, notes, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            """, label_id, tenant_id, turn_id, labeler_id, label_type,
                label_value, confidence, notes)
            row = await pool.fetchrow("SELECT * FROM labels WHERE id = $1", label_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO labels (id, tenant_id, turn_id, labeler_id, label_type,
                    label_value, confidence, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (label_id, tenant_id, turn_id, labeler_id, label_type,
                  label_value, confidence, notes, now))
            conn.commit()
            row = conn.execute("SELECT * FROM labels WHERE id = ?", (label_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def list_labels_db(turn_id: str) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch(
                "SELECT * FROM labels WHERE turn_id = $1 ORDER BY created_at DESC",
                turn_id,
            )
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM labels WHERE turn_id = ? ORDER BY created_at DESC",
                (turn_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


# ── External Training Jobs ──────────────────────────────────────────

async def create_external_job_db(
    tenant_id: str,
    model_id: str,
    version: str,
    external_job_id: str,
    external_provider: str = "modal",
    status: str = "submitted",
) -> dict | None:
    import uuid as _uuid
    record_id = str(_uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO external_jobs (id, tenant_id, model_id, model_version,
                    external_job_id, external_provider, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            """, record_id, tenant_id, model_id, version, external_job_id, external_provider, status)
            row = await pool.fetchrow("SELECT * FROM external_jobs WHERE id = $1", record_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO external_jobs (id, tenant_id, model_id, model_version,
                    external_job_id, external_provider, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (record_id, tenant_id, model_id, version, external_job_id, external_provider, status, now))
            conn.commit()
            row = conn.execute("SELECT * FROM external_jobs WHERE id = ?", (record_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def list_external_jobs_db(tenant_id: str, model_id: str) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch(
                "SELECT * FROM external_jobs WHERE tenant_id = $1 AND model_id = $2 ORDER BY created_at DESC",
                tenant_id, model_id,
            )
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM external_jobs WHERE tenant_id = ? AND model_id = ? ORDER BY created_at DESC",
                (tenant_id, model_id),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


# ── Model Audit Log ─────────────────────────────────────────────────

async def create_model_audit_log_db(
    tenant_id: str,
    model_id: str,
    version: str,
    action: str,
    previous_state: str | None = None,
    new_state: str | None = None,
    actor: str | None = None,
) -> dict | None:
    import uuid as _uuid
    log_id = str(_uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO model_audit_log (id, tenant_id, model_id, model_version,
                    action, previous_state, new_state, actor, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            """, log_id, tenant_id, model_id, version, action, previous_state, new_state, actor)
            row = await pool.fetchrow("SELECT * FROM model_audit_log WHERE id = $1", log_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO model_audit_log (id, tenant_id, model_id, model_version,
                    action, previous_state, new_state, actor, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, tenant_id, model_id, version, action, previous_state, new_state, actor, now))
            conn.commit()
            row = conn.execute("SELECT * FROM model_audit_log WHERE id = ?", (log_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def get_model_audit_log_db(tenant_id: str, model_id: str) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch(
                "SELECT * FROM model_audit_log WHERE tenant_id = $1 AND model_id = $2 ORDER BY created_at DESC",
                tenant_id, model_id,
            )
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM model_audit_log WHERE tenant_id = ? AND model_id = ? ORDER BY created_at DESC",
                (tenant_id, model_id),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []


# ── Evaluation Metrics ──────────────────────────────────────────────

async def create_eval_metrics_db(
    tenant_id: str,
    model_id: str,
    version: str,
    metrics_json: str = "{}",
) -> dict | None:
    import uuid as _uuid
    record_id = str(_uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO eval_metrics (id, tenant_id, model_id, model_version,
                    metrics_json, created_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, NOW())
            """, record_id, tenant_id, model_id, version, metrics_json)
            row = await pool.fetchrow("SELECT * FROM eval_metrics WHERE id = $1", record_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO eval_metrics (id, tenant_id, model_id, model_version,
                    metrics_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (record_id, tenant_id, model_id, version, metrics_json, now))
            conn.commit()
            row = conn.execute("SELECT * FROM eval_metrics WHERE id = ?", (record_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return None


async def get_eval_metrics_db(tenant_id: str, model_id: str, version: str) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch(
                "SELECT * FROM eval_metrics WHERE tenant_id = $1 AND model_id = $2 AND model_version = $3 ORDER BY created_at DESC",
                tenant_id, model_id, version,
            )
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM eval_metrics WHERE tenant_id = ? AND model_id = ? AND model_version = ? ORDER BY created_at DESC",
                (tenant_id, model_id, version),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return []
