import hashlib
import math
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()

# In-memory stores for confidence thresholds and experiments (per-tenant)
_confidence_thresholds: dict[str, dict] = {}
_experiments: dict[str, dict] = {}
_experiment_results: dict[str, list] = {}


# ── Top-Level Functions ────────────────────────────────────────────

def calculate_accuracy_metrics(results: list[dict]) -> dict:
    if not results:
        return {
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "intents": {},
            "confusion_matrix": {},
            "avg_confidence": 0.0,
        }

    total = len(results)
    correct = sum(1 for r in results if r.get("is_correct"))
    accuracy = correct / total if total else 0.0

    intent_map: dict[str, dict] = {}
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
                if actual not in intent_map:
                    intent_map[actual] = {"tp": 0, "fp": 0, "fn": 0, "total": 0, "correct": 0}
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

    confidences = [r.get("confidence", 0) for r in results]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    confusion_matrix = {}
    for r in results:
        predicted = r.get("predicted_intent", "unknown")
        actual = r.get("actual_intent") or "unlabeled"
        key = f"{actual}->{predicted}"
        confusion_matrix[key] = confusion_matrix.get(key, 0) + 1

    return {
        "accuracy": round(accuracy, 4),
        "precision": round(sum(intents[i]["precision"] for i in intents) / len(intents), 4) if intents else 0.0,
        "recall": round(sum(intents[i]["recall"] for i in intents) / len(intents), 4) if intents else 0.0,
        "f1": round(sum(intents[i]["f1"] for i in intents) / len(intents), 4) if intents else 0.0,
        "intents": intents,
        "confusion_matrix": confusion_matrix,
        "avg_confidence": round(avg_confidence, 4),
    }


def create_experiment(name: str, description: str, model_a: str, model_b: str, traffic_split: float = 0.5) -> dict:
    exp_id = hashlib.sha256(
        f"{name}:{model_a}:{model_b}:{datetime.now(UTC).isoformat()}".encode()
    ).hexdigest()[:16]

    experiment = {
        "id": exp_id,
        "name": name,
        "description": description,
        "model_a": model_a,
        "model_b": model_b,
        "traffic_split": traffic_split,
        "status": "active",
        "winner": None,
        "created_at": datetime.now(UTC).isoformat(),
        "stopped_at": None,
    }
    _experiments[exp_id] = experiment
    _experiment_results[exp_id] = []
    return experiment


def assign_variant(experiment_id: str, session_id: str) -> dict:
    exp = _experiments.get(experiment_id)
    if not exp:
        return {"error": "Experiment not found"}

    hash_input = f"{experiment_id}:{session_id}"
    hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
    bucket = (hash_val % 10000) / 10000.0

    variant = "model_a" if bucket < exp["traffic_split"] else "model_b"
    model = exp["model_a"] if variant == "model_a" else exp["model_b"]

    return {
        "experiment_id": experiment_id,
        "session_id": session_id,
        "variant": variant,
        "model": model,
        "bucket": round(bucket, 4),
    }


def evaluate_experiment(results_a: list[dict], results_b: list[dict]) -> dict:
    a_correct = sum(1 for r in results_a if r.get("is_correct")) if results_a else 0
    b_correct = sum(1 for r in results_b if r.get("is_correct")) if results_b else 0

    a_rate = a_correct / len(results_a) if results_a else 0.0
    b_rate = b_correct / len(results_b) if results_b else 0.0

    a_conf = sum(r.get("confidence", 0) for r in results_a) / len(results_a) if results_a else 0.0
    b_conf = sum(r.get("confidence", 0) for r in results_b) / len(results_b) if results_b else 0.0

    significance = 0.0
    winner = None
    if len(results_a) >= 10 and len(results_b) >= 10:
        p_pool = (a_correct + b_correct) / (len(results_a) + len(results_b))
        se = math.sqrt(p_pool * (1 - p_pool) * (1 / len(results_a) + 1 / len(results_b)))
        if se > 0:
            z = (a_rate - b_rate) / se
            significance = round(abs(z), 4)
            if significance > 1.96:
                winner = "model_a" if a_rate > b_rate else "model_b"

    return {
        "total_a": len(results_a),
        "total_b": len(results_b),
        "conversion_rate_a": round(a_rate, 4),
        "conversion_rate_b": round(b_rate, 4),
        "avg_confidence_a": round(a_conf, 4),
        "avg_confidence_b": round(b_conf, 4),
        "statistical_significance": significance,
        "winner": winner,
    }


def check_confidence_threshold(confidence: float, thresholds: dict) -> str:
    proceed_threshold = thresholds.get("proceed", 0.8)
    review_threshold = thresholds.get("review", 0.5)

    if confidence >= proceed_threshold:
        return "proceed"
    elif confidence >= review_threshold:
        return "review"
    else:
        return "escalate"


# ── Backward Compatible Class ─────────────────────────────────────

class AIEvaluationService:
    """Legacy wrapper — prefer top-level functions for new code."""

    @staticmethod
    def track_intent_accuracy(intent_id, predicted_intent, actual_intent, confidence):
        is_correct = 1 if predicted_intent == actual_intent else 0
        return {
            "intent_id": intent_id,
            "predicted_intent": predicted_intent,
            "actual_intent": actual_intent,
            "confidence": confidence,
            "is_correct": is_correct,
        }

    @staticmethod
    def calculate_accuracy_metrics(results):
        return calculate_accuracy_metrics(results)

    @staticmethod
    def create_experiment(name, description, model_a, model_b, traffic_split=0.5):
        return create_experiment(name, description, model_a, model_b, traffic_split)

    @staticmethod
    def assign_variant(experiment_id, session_id):
        return assign_variant(experiment_id, session_id)

    @staticmethod
    def evaluate_experiment(experiment_id):
        exp = _experiments.get(experiment_id)
        if not exp:
            return {"error": "Experiment not found"}

        results = _experiment_results.get(experiment_id, [])
        if not results:
            return {
                "experiment_id": experiment_id,
                "status": exp["status"],
                "total_evaluations": 0,
                "winner": exp["winner"],
            }

        a_results = [r for r in results if r.get("variant") == "model_a"]
        b_results = [r for r in results if r.get("variant") == "model_b"]

        comp = evaluate_experiment(a_results, b_results)
        return {
            "experiment_id": experiment_id,
            "status": exp["status"],
            "name": exp["name"],
            "model_a": exp["model_a"],
            "model_b": exp["model_b"],
            "total_evaluations": len(results),
            **comp,
        }

    @staticmethod
    def check_confidence_threshold(confidence, thresholds):
        action = check_confidence_threshold(confidence, thresholds)
        return {
            "confidence": confidence,
            "action": action,
            "thresholds": thresholds,
        }

    @staticmethod
    def get_confidence_distribution(tenant_id, start_date=None, end_date=None):
        buckets = [
            {"label": "0.0-0.2", "min": 0.0, "max": 0.2, "count": 0},
            {"label": "0.2-0.4", "min": 0.2, "max": 0.4, "count": 0},
            {"label": "0.4-0.6", "min": 0.4, "max": 0.6, "count": 0},
            {"label": "0.6-0.8", "min": 0.6, "max": 0.8, "count": 0},
            {"label": "0.8-1.0", "min": 0.8, "max": 1.0, "count": 0},
        ]
        return {"total": 0, "buckets": buckets, "avg_confidence": 0.0}
