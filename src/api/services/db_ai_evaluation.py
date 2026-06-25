import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


# ── Evaluation Results ────────────────────────────────────────────

async def create_evaluation_db(
    tenant_id, experiment_id, call_id, predicted_intent,
    actual_intent, confidence, is_correct, model_used=None, latency_ms=0.0
):
    eval_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO ai_evaluation_results
                    (id, tenant_id, experiment_id, call_id, predicted_intent,
                     actual_intent, confidence, is_correct, model_used, latency_ms, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            """, eval_id, tenant_id, experiment_id, call_id, predicted_intent,
                actual_intent, confidence, is_correct, model_used, latency_ms)
            row = await pool.fetchrow("SELECT * FROM ai_evaluation_results WHERE id = $1", eval_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO ai_evaluation_results
                    (id, tenant_id, experiment_id, call_id, predicted_intent,
                     actual_intent, confidence, is_correct, model_used, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (eval_id, tenant_id, experiment_id, call_id, predicted_intent,
                  actual_intent, confidence, is_correct, model_used, latency_ms, now))
            conn.commit()
            row = conn.execute("SELECT * FROM ai_evaluation_results WHERE id = ?", (eval_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_evaluations_db(tenant_id, limit=100, offset=0, experiment_id=None, start_date=None, end_date=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT * FROM ai_evaluation_results WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if experiment_id:
                query += f" AND experiment_id = ${idx}"
                params.append(experiment_id)
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
            query = "SELECT * FROM ai_evaluation_results WHERE tenant_id = ?"
            params = [tenant_id]
            if experiment_id:
                query += " AND experiment_id = ?"
                params.append(experiment_id)
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            query += f" ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_accuracy_metrics_db(tenant_id, start_date=None, end_date=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT * FROM ai_evaluation_results WHERE tenant_id = $1"
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
            rows = await pool.fetch(query, *params)
            results = [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT * FROM ai_evaluation_results WHERE tenant_id = ?"
            params = [tenant_id]
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            rows = conn.execute(query, params).fetchall()
            results = [dict(r) for r in rows]
        finally:
            conn.close()

    if not results:
        return {
            "total_evaluations": 0, "accuracy": 0.0,
            "intents": {},
            "confusion_matrix": {},
            "avg_confidence": 0.0,
        }

    total = len(results)
    correct = sum(1 for r in results if r.get("is_correct"))
    accuracy = correct / total if total else 0.0

    # Per-intent metrics
    intent_map = {}
    for r in results:
        intent = r.get("predicted_intent", "unknown")
        if intent not in intent_map:
            intent_map[intent] = {"tp": 0, "fp": 0, "fn": 0, "total": 0, "correct": 0}
        intent_map[intent]["total"] += 1
        if r.get("is_correct"):
            intent_map[intent]["correct"] += 1
            intent_map[intent]["tp"] += 1
        else:
            intent_map[intent]["fp"] += 1
            actual = r.get("actual_intent")
            if actual and actual != intent:
                intent_map[actual] = intent_map.get(actual, {"tp": 0, "fp": 0, "fn": 0, "total": 0, "correct": 0})
                intent_map[actual]["fn"] += 1

    intents = {}
    for intent, m in intent_map.items():
        tp, fp, fn = m["tp"], m["fp"], m["fn"]
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        intents[intent] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "total": m["total"],
            "correct": m["correct"],
        }

    # Confidence distribution
    confidences = [r.get("confidence", 0) for r in results]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    # Simple confusion matrix summary
    confusion_matrix = {}
    for r in results:
        predicted = r.get("predicted_intent", "unknown")
        actual = r.get("actual_intent") or "unlabeled"
        key = f"{actual}->{predicted}"
        confusion_matrix[key] = confusion_matrix.get(key, 0) + 1

    return {
        "total_evaluations": total,
        "accuracy": round(accuracy, 4),
        "intents": intents,
        "confusion_matrix": confusion_matrix,
        "avg_confidence": round(avg_confidence, 4),
    }


# ── Experiments ───────────────────────────────────────────────────

async def create_experiment_db(tenant_id, name, description, model_a, model_b, traffic_split):
    exp_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO ai_experiments
                    (id, tenant_id, name, description, model_a, model_b, traffic_split, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'active', NOW())
            """, exp_id, tenant_id, name, description, model_a, model_b, traffic_split)
            row = await pool.fetchrow("SELECT * FROM ai_experiments WHERE id = $1", exp_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO ai_experiments
                    (id, tenant_id, name, description, model_a, model_b, traffic_split, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """, (exp_id, tenant_id, name, description, model_a, model_b, traffic_split, now))
            conn.commit()
            row = conn.execute("SELECT * FROM ai_experiments WHERE id = ?", (exp_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_experiments_db(tenant_id, status=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT * FROM ai_experiments WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if status:
                query += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            query += " ORDER BY created_at DESC"
            rows = await pool.fetch(query, *params)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT * FROM ai_experiments WHERE tenant_id = ?"
            params = [tenant_id]
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_experiment_db(tenant_id, experiment_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow(
                "SELECT * FROM ai_experiments WHERE id = $1 AND tenant_id = $2",
                experiment_id, tenant_id
            )
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT * FROM ai_experiments WHERE id = ? AND tenant_id = ?",
                (experiment_id, tenant_id)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def update_experiment_db(tenant_id, experiment_id, winner=None, status=None, stopped_at=None):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            set_parts = []
            params = []
            idx = 1
            if winner is not None:
                set_parts.append(f"winner = ${idx}")
                params.append(winner)
                idx += 1
            if status is not None:
                set_parts.append(f"status = ${idx}")
                params.append(status)
                idx += 1
            if stopped_at is not None:
                set_parts.append(f"stopped_at = ${idx}")
                params.append(stopped_at)
                idx += 1
            if not set_parts:
                return None
            params.extend([experiment_id, tenant_id])
            await pool.execute(
                f"UPDATE ai_experiments SET {', '.join(set_parts)} WHERE id = ${idx} AND tenant_id = ${idx+1}",
                *params
            )
            row = await pool.fetchrow("SELECT * FROM ai_experiments WHERE id = $1", experiment_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            set_parts = []
            params = []
            if winner is not None:
                set_parts.append("winner = ?")
                params.append(winner)
            if status is not None:
                set_parts.append("status = ?")
                params.append(status)
            if stopped_at is not None:
                set_parts.append("stopped_at = ?")
                params.append(stopped_at)
            if not set_parts:
                return None
            params.extend([experiment_id, tenant_id])
            conn.execute(
                f"UPDATE ai_experiments SET {', '.join(set_parts)} WHERE id = ? AND tenant_id = ?",
                params
            )
            conn.commit()
            row = conn.execute("SELECT * FROM ai_experiments WHERE id = ?", (experiment_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_confidence_distribution_db(tenant_id, start_date=None, end_date=None):
    """Returns histogram buckets for confidence scores."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            query = "SELECT confidence FROM ai_evaluation_results WHERE tenant_id = $1"
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
            rows = await pool.fetch(query, *params)
            confidences = [r["confidence"] for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            query = "SELECT confidence FROM ai_evaluation_results WHERE tenant_id = ?"
            params = [tenant_id]
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)
            rows = conn.execute(query, params).fetchall()
            confidences = [r["confidence"] for r in rows]
        finally:
            conn.close()

    buckets = [
        {"label": "0.0-0.2", "min": 0.0, "max": 0.2, "count": 0},
        {"label": "0.2-0.4", "min": 0.2, "max": 0.4, "count": 0},
        {"label": "0.4-0.6", "min": 0.4, "max": 0.6, "count": 0},
        {"label": "0.6-0.8", "min": 0.6, "max": 0.8, "count": 0},
        {"label": "0.8-1.0", "min": 0.8, "max": 1.0, "count": 0},
    ]

    for c in confidences:
        for b in buckets:
            if b["min"] <= c < b["max"] or (b["max"] == 1.0 and c == 1.0):
                b["count"] += 1
                break

    return {
        "total": len(confidences),
        "buckets": buckets,
        "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
    }
