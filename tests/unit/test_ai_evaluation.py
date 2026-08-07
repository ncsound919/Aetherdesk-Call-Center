"""Unit tests for src/api/services/ai_evaluation.py.

Covers calculate_accuracy_metrics, experiment creation/variant assignment,
experiment evaluation, confidence thresholds, and the legacy
AIEvaluationService wrapper. Module-level experiment stores are snapshot and
restored between tests.
"""

import pytest

import api.services.ai_evaluation as module
from api.services.ai_evaluation import (
    AIEvaluationService,
    assign_variant,
    calculate_accuracy_metrics,
    check_confidence_threshold,
    create_experiment,
    evaluate_experiment,
)


@pytest.fixture(autouse=True)
def _snapshot_state():
    before_exps = dict(module._experiments)
    before_results = dict(module._experiment_results)
    before_thresholds = dict(module._confidence_thresholds)
    yield
    module._experiments.clear()
    module._experiment_results.clear()
    module._confidence_thresholds.clear()
    module._experiments.update(before_exps)
    module._experiment_results.update(before_results)
    module._confidence_thresholds.update(before_thresholds)


def _result(intent, actual=None, correct=None, confidence=0.5):
    return {
        "predicted_intent": intent,
        "actual_intent": actual,
        "is_correct": correct if correct is not None else (intent == actual),
        "confidence": confidence,
    }


class TestCalculateAccuracyMetrics:
    def test_empty_results_defaults(self):
        result = calculate_accuracy_metrics([])
        assert result["accuracy"] == 0.0
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0
        assert result["f1"] == 0.0
        assert result["avg_confidence"] == 0.0
        assert result["intents"] == {}
        assert result["confusion_matrix"] == {}

    def test_perfect_predictions(self):
        results = [
            _result("billing", "billing", confidence=0.9),
            _result("support", "support", confidence=0.8),
        ]
        result = calculate_accuracy_metrics(results)
        assert result["accuracy"] == 1.0
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0
        assert result["avg_confidence"] == 0.85
        assert result["confusion_matrix"] == {
            "billing->billing": 1,
            "support->support": 1,
        }
        assert result["intents"]["billing"] == {
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "total": 1,
            "correct": 1,
        }

    def test_mixed_predictions(self):
        results = [
            _result("billing", "billing", confidence=1.0),
            _result("billing", "support", correct=False, confidence=0.5),
        ]
        result = calculate_accuracy_metrics(results)
        assert result["accuracy"] == 0.5
        assert result["precision"] == 0.25
        assert result["recall"] == 0.5
        assert result["f1"] == round((0.6667 + 0.0) / 2, 4)
        assert result["avg_confidence"] == 0.75
        assert result["confusion_matrix"] == {"billing->billing": 1, "support->billing": 1}
        billing = result["intents"]["billing"]
        assert billing["precision"] == 0.5
        assert billing["recall"] == 1.0
        assert billing["total"] == 2
        assert billing["correct"] == 1
        support = result["intents"]["support"]
        assert support["precision"] == 0.0
        assert support["recall"] == 0.0
        assert support["f1"] == 0.0
        assert support["total"] == 0

    def test_wrong_prediction_without_actual(self):
        results = [{"predicted_intent": "novel", "is_correct": False, "confidence": 0.1}]
        result = calculate_accuracy_metrics(results)
        assert result["accuracy"] == 0.0
        assert result["intents"]["novel"]["precision"] == 0.0
        assert result["intents"]["novel"]["recall"] == 0.0
        assert result["confusion_matrix"] == {"unlabeled->novel": 1}

    def test_wrong_prediction_same_intent(self):
        results = [{"predicted_intent": "ghost", "actual_intent": "ghost", "is_correct": False}]
        result = calculate_accuracy_metrics(results)
        assert result["intents"]["ghost"]["precision"] == 0.0
        assert result["intents"]["ghost"]["recall"] == 0.0

    def test_missing_predicted_intent_uses_unknown(self):
        results = [{"is_correct": True, "confidence": 0.7}]
        result = calculate_accuracy_metrics(results)
        assert result["intents"]["unknown"]["total"] == 1
        assert result["intents"]["unknown"]["correct"] == 1
        assert result["confusion_matrix"] == {"unlabeled->unknown": 1}

    def test_missing_confidence_defaults_zero(self):
        results = [{"predicted_intent": "billing", "actual_intent": "billing", "is_correct": True}]
        result = calculate_accuracy_metrics(results)
        assert result["avg_confidence"] == 0.0


class TestCreateExperiment:
    def test_create_experiment(self):
        exp = create_experiment("A/B", "desc", "model-a", "model-b", 0.6)
        assert exp["id"] and len(exp["id"]) == 16
        assert exp["name"] == "A/B"
        assert exp["description"] == "desc"
        assert exp["model_a"] == "model-a"
        assert exp["model_b"] == "model-b"
        assert exp["traffic_split"] == 0.6
        assert exp["status"] == "active"
        assert exp["winner"] is None
        assert exp["created_at"]
        assert exp["stopped_at"] is None
        assert module._experiments[exp["id"]] is exp
        assert module._experiment_results[exp["id"]] == []

    def test_create_experiment_default_split(self):
        exp = create_experiment("n", "d", "a", "b")
        assert exp["traffic_split"] == 0.5

    def test_unique_ids(self):
        a = create_experiment("n1", "d", "a", "b")
        b = create_experiment("n2", "d", "a", "b")
        assert a["id"] != b["id"]


class TestAssignVariant:
    def test_experiment_not_found(self):
        assert assign_variant("missing", "s1") == {"error": "Experiment not found"}

    def test_traffic_split_one_always_model_a(self):
        exp = create_experiment("n", "d", "model-a", "model-b", traffic_split=1.0)
        for session in ["s1", "s2", "s3"]:
            out = assign_variant(exp["id"], session)
            assert out["variant"] == "model_a"
            assert out["model"] == "model-a"

    def test_traffic_split_zero_always_model_b(self):
        exp = create_experiment("n", "d", "model-a", "model-b", traffic_split=0.0)
        out = assign_variant(exp["id"], "s1")
        assert out["variant"] == "model_b"
        assert out["model"] == "model-b"

    def test_deterministic(self):
        exp = create_experiment("n", "d", "model-a", "model-b")
        first = assign_variant(exp["id"], "session-42")
        second = assign_variant(exp["id"], "session-42")
        assert first == second

    def test_bucket_in_range(self):
        exp = create_experiment("n", "d", "a", "b")
        out = assign_variant(exp["id"], "anything")
        assert 0.0 <= out["bucket"] < 1.0
        assert out["session_id"] == "anything"


class TestEvaluateExperiment:
    def test_empty_lists(self):
        result = evaluate_experiment([], [])
        assert result["total_a"] == 0
        assert result["total_b"] == 0
        assert result["conversion_rate_a"] == 0.0
        assert result["conversion_rate_b"] == 0.0
        assert result["winner"] is None
        assert result["statistical_significance"] == 0.0

    def test_significant_winner_model_a(self):
        a = [{"is_correct": True, "confidence": 0.9} for _ in range(10)]
        b = [{"is_correct": False, "confidence": 0.4} for _ in range(10)]
        result = evaluate_experiment(a, b)
        assert result["total_a"] == 10
        assert result["total_b"] == 10
        assert result["conversion_rate_a"] == 1.0
        assert result["conversion_rate_b"] == 0.0
        assert result["avg_confidence_a"] == 0.9
        assert result["avg_confidence_b"] == 0.4
        assert result["winner"] == "model_a"
        assert result["statistical_significance"] > 1.96

    def test_significant_winner_model_b(self):
        a = [{"is_correct": False} for _ in range(10)]
        b = [{"is_correct": True} for _ in range(10)]
        result = evaluate_experiment(a, b)
        assert result["winner"] == "model_b"
        assert result["statistical_significance"] > 1.96

    def test_not_significant(self):
        a = [{"is_correct": True if i % 5 else False} for i in range(10)]
        b = [{"is_correct": True if i % 2 else False} for i in range(10)]
        result = evaluate_experiment(a, b)
        assert result["winner"] is None

    def test_small_sample_no_winner(self):
        a = [{"is_correct": True} for _ in range(5)]
        b = [{"is_correct": False} for _ in range(5)]
        result = evaluate_experiment(a, b)
        assert result["winner"] is None
        assert result["statistical_significance"] == 0.0


class TestCheckConfidenceThreshold:
    def test_proceed(self):
        assert check_confidence_threshold(0.9, {"proceed": 0.8, "review": 0.5}) == "proceed"

    def test_review(self):
        assert check_confidence_threshold(0.6, {"proceed": 0.8, "review": 0.5}) == "review"

    def test_escalate(self):
        assert check_confidence_threshold(0.3, {"proceed": 0.8, "review": 0.5}) == "escalate"

    def test_boundaries(self):
        assert check_confidence_threshold(0.8, {"proceed": 0.8, "review": 0.5}) == "proceed"
        assert check_confidence_threshold(0.5, {"proceed": 0.8, "review": 0.5}) == "review"

    def test_default_thresholds(self):
        assert check_confidence_threshold(0.85, {}) == "proceed"
        assert check_confidence_threshold(0.6, {}) == "review"
        assert check_confidence_threshold(0.4, {}) == "escalate"


class TestAIEvaluationService:
    def test_track_intent_accuracy_correct(self):
        out = AIEvaluationService.track_intent_accuracy("i1", "billing", "billing", 0.9)
        assert out["is_correct"] == 1
        assert out["predicted_intent"] == "billing"
        assert out["actual_intent"] == "billing"
        assert out["confidence"] == 0.9

    def test_track_intent_accuracy_incorrect(self):
        out = AIEvaluationService.track_intent_accuracy("i1", "billing", "support", 0.5)
        assert out["is_correct"] == 0

    def test_calculate_accuracy_metrics_delegates(self):
        results = [_result("billing", "billing")]
        out = AIEvaluationService.calculate_accuracy_metrics(results)
        assert out["accuracy"] == 1.0

    def test_create_experiment_delegates(self):
        out = AIEvaluationService.create_experiment("n", "d", "a", "b")
        assert out["status"] == "active"

    def test_assign_variant_delegates(self):
        exp = create_experiment("n", "d", "a", "b", traffic_split=1.0)
        out = AIEvaluationService.assign_variant(exp["id"], "s1")
        assert out["variant"] == "model_a"

    def test_evaluate_experiment_not_found(self):
        assert AIEvaluationService.evaluate_experiment("missing") == {
            "error": "Experiment not found"
        }

    def test_evaluate_experiment_no_results(self):
        exp = create_experiment("n", "d", "a", "b")
        out = AIEvaluationService.evaluate_experiment(exp["id"])
        assert out["experiment_id"] == exp["id"]
        assert out["status"] == "active"
        assert out["total_evaluations"] == 0
        assert out["winner"] is None

    def test_evaluate_experiment_with_results(self):
        exp = create_experiment("n", "d", "model-a", "model-b")
        module._experiment_results[exp["id"]] = [
            {"variant": "model_a", "is_correct": True, "confidence": 0.9}
            for _ in range(10)
        ] + [
            {"variant": "model_b", "is_correct": False, "confidence": 0.4}
            for _ in range(10)
        ]
        out = AIEvaluationService.evaluate_experiment(exp["id"])
        assert out["experiment_id"] == exp["id"]
        assert out["total_evaluations"] == 20
        assert out["name"] == "n"
        assert out["model_a"] == "model-a"
        assert out["model_b"] == "model-b"
        assert out["conversion_rate_a"] == 1.0
        assert out["conversion_rate_b"] == 0.0
        assert out["winner"] == "model_a"

    def test_check_confidence_threshold_wrapper(self):
        out = AIEvaluationService.check_confidence_threshold(
            0.9, {"proceed": 0.8, "review": 0.5}
        )
        assert out["confidence"] == 0.9
        assert out["action"] == "proceed"
        assert out["thresholds"]["proceed"] == 0.8

    def test_get_confidence_distribution(self):
        out = AIEvaluationService.get_confidence_distribution("t1")
        assert out["total"] == 0
        assert out["avg_confidence"] == 0.0
        assert [b["label"] for b in out["buckets"]] == [
            "0.0-0.2",
            "0.2-0.4",
            "0.4-0.6",
            "0.6-0.8",
            "0.8-1.0",
        ]
        assert all(b["count"] == 0 for b in out["buckets"])
