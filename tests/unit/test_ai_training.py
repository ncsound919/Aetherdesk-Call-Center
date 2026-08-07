"""Unit tests for src/api/services/ai_training.py."""

import json
import types
from unittest.mock import AsyncMock, patch

import pytest

import api.services.ai_training as module
from api.services.ai_training import (
    AITrainingService,
    AITrainingServiceError,
    _async_sleep,
    _auto_version,
    _generate_mock_calls,
)

_segment_turns = AITrainingService._segment_turns


@pytest.fixture(autouse=True)
def _clear_caches():
    before_examples = dict(module._training_examples)
    before_data = dict(module._training_data_cache)
    module._training_examples.clear()
    module._training_data_cache.clear()
    yield
    module._training_examples.clear()
    module._training_data_cache.clear()
    module._training_examples.update(before_examples)
    module._training_data_cache.update(before_data)


def _fake_calls_module(calls):
    fake = types.ModuleType("api.services.db_calls")
    fake.list_calls = AsyncMock(return_value=calls)
    return fake


class TestCollectTrainingData:
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        module._training_data_cache["t1:2024-01-01:2024-01-02"] = [{"call_id": "c"}]
        with patch.dict("sys.modules", {"api.services.db_calls": _fake_calls_module([])}):
            result = await AITrainingService.collect_training_data(
                "t1", "2024-01-01", "2024-01-02"
            )
        assert result == [{"call_id": "c"}]

    @pytest.mark.asyncio
    async def test_collects_from_db(self):
        calls = [
            {
                "id": "c1",
                "transcription": "Hello there",
                "intent_detected": "billing",
                "call_status": "completed",
                "sentiment_score": 4.5,
                "agent_id": "a1",
                "caller_number": "+1555",
                "start_time": "t",
                "duration_seconds": 10,
            }
        ]
        with patch.dict(
            "sys.modules", {"api.services.db_calls": _fake_calls_module(calls)}
        ):
            result = await AITrainingService.collect_training_data(
                "t1", "2024-01-01", "2024-01-02"
            )
        assert result[0]["intent"] == "billing"
        assert result[0]["resolution"] == "completed"
        assert result[0]["csat_score"] == 4.5
        assert result[0]["call_id"] == "c1"

    @pytest.mark.asyncio
    async def test_empty_db_uses_mock_calls(self):
        with patch.dict(
            "sys.modules", {"api.services.db_calls": _fake_calls_module([])}
        ):
            result = await AITrainingService.collect_training_data(
                "t1", "2024-01-01", "2024-01-02"
            )
        assert result
        assert all("transcript" in c for c in result)

    @pytest.mark.asyncio
    async def test_skips_calls_without_transcript(self):
        calls = [
            {"id": "c1", "transcription": ""},
            {"id": "c2", "transcription": "Has content here"},
        ]
        with patch.dict(
            "sys.modules", {"api.services.db_calls": _fake_calls_module(calls)}
        ):
            result = await AITrainingService.collect_training_data(
                "t1", "2024-01-01", "2024-01-02"
            )
        assert [e["call_id"] for e in result] == ["c2"]

    @pytest.mark.asyncio
    async def test_uses_ai_summary_fallback(self):
        calls = [{"id": "c1", "transcription": "", "ai_summary": "Summary text"}]
        with patch.dict(
            "sys.modules", {"api.services.db_calls": _fake_calls_module(calls)}
        ):
            result = await AITrainingService.collect_training_data(
                "t1", "2024-01-01", "2024-01-02"
            )
        assert result[0]["transcript"] == "Summary text"


class TestGenerateExamples:
    def test_generate_training_examples(self):
        transcripts = [
            {
                "call_id": "c1",
                "transcript": "First sentence here. Second longer sentence. Third part.",
                "intent": "billing",
                "resolution": "completed",
                "csat_score": 4.0,
            }
        ]
        result = AITrainingService.generate_training_examples(transcripts)
        assert result
        assert result[0]["source_call_id"] == "c1"
        assert result[0]["intent"] == "billing"
        assert "input" in result[0]
        assert "output" in result[0]

    def test_generate_training_examples_skips_empty(self):
        assert AITrainingService.generate_training_examples([{"transcript": ""}]) == []

    def test_generate_training_examples_context_window(self):
        transcripts = [
            {
                "call_id": "c1",
                "transcript": (
                    "Turn one here. Turn two here. Turn three here. "
                    "Turn four here. Turn five here. Turn six here. "
                    "Turn seven here. Turn eight here. Turn nine here."
                ),
            }
        ]
        result = AITrainingService.generate_training_examples(transcripts)
        assert len(result) >= 8

    def test_generate_classification_examples(self):
        transcripts = [
            {"call_id": "c1", "transcript": "First turn here. Second turn here.",
             "intent": "support"}
        ]
        result = AITrainingService.generate_classification_examples(transcripts)
        assert result
        assert result[0]["context"] is not None
        assert result[0]["intent"] == "support"

    def test_generate_classification_examples_skips_empty(self):
        assert AITrainingService.generate_classification_examples(
            [{"transcript": ""}]
        ) == []

    def test_generate_summarization_examples(self):
        transcripts = [
            {"call_id": "c1", "transcript": "Full conversation", "ai_summary": "Sum"}
        ]
        result = AITrainingService.generate_summarization_examples(transcripts)
        assert result[0]["summary"] == "Sum"

    def test_generate_summarization_resolution_fallback(self):
        transcripts = [
            {"call_id": "c1", "transcript": "Full conversation",
             "resolution": "Resolved"}
        ]
        result = AITrainingService.generate_summarization_examples(transcripts)
        assert result[0]["summary"] == "Resolved"

    def test_generate_summarization_skips_empty(self):
        assert AITrainingService.generate_summarization_examples(
            [{"transcript": ""}]
        ) == []

    def test_segment_turns(self):
        turns = _segment_turns("Hello there friend. Next turn here!")
        assert len(turns) >= 2
        assert all(len(t) > 10 for t in turns)

    def test_segment_turns_short_parts_dropped(self):
        assert _segment_turns("hi there") == []


class TestFilterLowQuality:
    def test_keeps_good_examples(self):
        ex = [{"text": "valid turn here"}]
        assert AITrainingService.filter_low_quality(ex) == ex

    def test_filters_low_asr_confidence(self):
        ex = [{"text": "valid turn here", "asr_confidence": 0.3}]
        assert AITrainingService.filter_low_quality(ex) == []

    def test_filters_short_text(self):
        ex = [{"output": "ab"}]
        assert AITrainingService.filter_low_quality(ex, min_turn_length=3) == []

    def test_uses_output_and_context_fallbacks(self):
        ex = [{"output": "a longer valid output text"}]
        assert AITrainingService.filter_low_quality(ex) == ex
        ex2 = [{"context": "another valid context text"}]
        assert AITrainingService.filter_low_quality(ex2) == ex2


class TestDatasetStatistics:
    def test_empty(self):
        stats = AITrainingService.generate_dataset_statistics([])
        assert stats == {
            "total_count": 0,
            "avg_turn_length": 0,
            "intent_distribution": {},
            "avg_csat": 0,
            "quality_histogram": {},
        }

    def test_with_data(self):
        examples = [
            {"output": "word word", "intent": "billing", "csat_score": 4.0,
             "quality_score": 0.1},
            {"output": "word word word", "intent": "billing", "csat_score": 5.0,
             "quality_score": 0.3},
            {"output": "word", "intent": "support", "csat_score": "bad",
             "quality_score": 0.5},
            {"output": "word word", "intent": "support", "csat_score": 2.0,
             "quality_score": 0.7},
            {"output": "word word word word", "intent": "sales",
             "csat_score": None, "quality_score": 0.9},
        ]
        stats = AITrainingService.generate_dataset_statistics(examples)
        assert stats["total_count"] == 5
        assert stats["avg_csat"] == round((4 + 5 + 2) / 3, 2)
        assert stats["intent_distribution"]["billing"] == 0.4
        assert stats["quality_histogram"] == {
            "0.0-0.2": 1,
            "0.2-0.4": 1,
            "0.4-0.6": 1,
            "0.6-0.8": 1,
            "0.8-1.0": 1,
        }
        assert stats["avg_turn_length"] > 0

    def test_quality_boundaries(self):
        examples = [
            {"output": "aaaa", "quality_score": 0.19},
            {"output": "aaaa", "quality_score": 0.39},
            {"output": "aaaa", "quality_score": 0.59},
            {"output": "aaaa", "quality_score": 0.79},
            {"output": "aaaa", "quality_score": 0.99},
        ]
        stats = AITrainingService.generate_dataset_statistics(examples)
        assert stats["quality_histogram"] == {
            "0.0-0.2": 1,
            "0.2-0.4": 1,
            "0.4-0.6": 1,
            "0.6-0.8": 1,
            "0.8-1.0": 1,
        }


class TestCreateDataset:
    @pytest.mark.asyncio
    async def test_create_returns_db_record(self):
        examples = [{"output": "a valid output here", "intent": "billing"}]
        with patch(
            "api.services.db_ai_platform.list_datasets_db",
            new_callable=AsyncMock,
            return_value=[{"name": "d", "version": "1.0.0"}],
        ), patch(
            "api.services.ai_training.create_dataset_db",
            new_callable=AsyncMock,
            return_value={"id": "ds-1", "name": "d", "version": "1.0.1"},
        ) as mock_create:
            result = await AITrainingService.create_dataset(
                "t1", "d", "dialogue", examples
            )
        assert result["id"] == "ds-1"
        assert mock_create.call_args.kwargs["version"] == "1.0.1"
        assert mock_create.call_args.kwargs["total_examples"] == 1
        assert mock_create.call_args.kwargs["status"] == "ready"

    @pytest.mark.asyncio
    async def test_create_fallback_when_none(self):
        examples = [{"output": "a valid output here"}]
        with patch(
            "api.services.db_ai_platform.list_datasets_db",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "api.services.ai_training.create_dataset_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await AITrainingService.create_dataset("t1", "d", "qa", examples)
        assert result["tenant_id"] == "t1"
        assert result["version"] == "1.0.0"
        assert result["id"]


class TestTurnQualityScore:
    def test_no_text_zero(self):
        assert AITrainingService.get_turn_quality_score({}) == 0.0

    def test_default_confidence(self):
        assert AITrainingService.get_turn_quality_score({"output": "hello there"}) == 1.0

    def test_positive_sentiment_boost(self):
        score = AITrainingService.get_turn_quality_score(
            {"output": "hello there", "sentiment": "positive"}
        )
        assert score == 1.0  # capped

    def test_mixed_sentiment(self):
        score = AITrainingService.get_turn_quality_score(
            {"output": "hello there", "sentiment": "mixed"}
        )
        assert 0.9 < score <= 1.0

    def test_low_asr_confidence(self):
        score = AITrainingService.get_turn_quality_score(
            {"output": "hello there", "asr_confidence": 0.5}
        )
        assert score == 0.5

    def test_silence_ratio_reduces(self):
        score = AITrainingService.get_turn_quality_score(
            {"output": "hello...world", "asr_confidence": 1.0}
        )
        assert score < 1.0


class TestCreateTrainingJob:
    @pytest.mark.asyncio
    async def test_db_record(self):
        with patch(
            "api.services.ai_training.create_training_job_db",
            new_callable=AsyncMock,
            return_value={"id": "job-1", "name": "n"},
        ) as mock_create:
            result = await AITrainingService.create_training_job(
                "t1", "n", "llama-3.1-8b"
            )
        assert result["id"] == "job-1"
        assert "hyperparams_json" in mock_create.call_args.kwargs

    @pytest.mark.asyncio
    async def test_fallback_when_none(self):
        with patch(
            "api.services.ai_training.create_training_job_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await AITrainingService.create_training_job(
                "t1", "n", hyperparams={"epochs": 5}
            )
        assert result["status"] == "pending"
        assert json.loads(result["hyperparams_json"]) == {"epochs": 5}


class TestExportForFineTuning:
    @pytest.mark.asyncio
    async def test_jsonl_with_cached_examples(self):
        module._training_examples["t1"] = [
            {
                "input": "i",
                "output": "o",
                "intent": "billing",
                "resolution": "res",
                "csat_score": 4.0,
            }
        ]
        with patch.object(
            AITrainingService,
            "collect_training_data",
            new_callable=AsyncMock,
        ) as mock_collect:
            result = await AITrainingService.export_for_fine_tuning("t1", "jsonl")
        lines = result.split("\n")
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["messages"] == [
            {"role": "user", "content": "i"},
            {"role": "assistant", "content": "o"},
        ]
        mock_collect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_jsonl_collects_when_no_cache(self):
        with patch.object(
            AITrainingService,
            "collect_training_data",
            new_callable=AsyncMock,
            return_value=[{"call_id": "c1", "transcript": "Sample transcript here"}],
        ):
            result = await AITrainingService.export_for_fine_tuning("t1", "jsonl")
        assert result  # jsonl string produced
        assert "t1" in module._training_examples

    @pytest.mark.asyncio
    async def test_other_format_returns_json(self):
        module._training_examples["t1"] = [{"input": "i", "output": "o"}]
        result = await AITrainingService.export_for_fine_tuning("t1", "json")
        parsed = json.loads(result)
        assert parsed == [{"input": "i", "output": "o"}]


class TestTrainingStatus:
    @pytest.mark.asyncio
    async def test_found(self):
        with patch(
            "api.services.ai_training.get_training_job_db",
            new_callable=AsyncMock,
            return_value={"id": "job-1", "status": "completed"},
        ):
            result = await AITrainingService.get_training_status("job-1")
        assert result == {"id": "job-1", "status": "completed"}

    @pytest.mark.asyncio
    async def test_not_found(self):
        with patch(
            "api.services.ai_training.get_training_job_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await AITrainingService.get_training_status("job-1")
        assert result == {"error": "Job not found", "job_id": "job-1"}

    @pytest.mark.asyncio
    async def test_list_training_jobs(self):
        with patch(
            "api.services.ai_training.list_training_jobs_db",
            new_callable=AsyncMock,
            return_value=[{"id": "job-1"}],
        ):
            assert await AITrainingService.list_training_jobs("t1") == [{"id": "job-1"}]


class TestSimulateTraining:
    @pytest.mark.asyncio
    async def test_runs_all_stages(self):
        with patch(
            "api.services.ai_training.update_training_job_db",
            new_callable=AsyncMock,
        ) as mock_update, patch(
            "api.services.ai_training._async_sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            await AITrainingService.simulate_training("job-1")
        # 8 stage updates + 1 final update
        assert mock_update.await_count == 9
        mock_sleep.assert_awaited()
        final_kwargs = mock_update.call_args_list[-1].kwargs
        assert final_kwargs["status"] == "completed"
        assert json.loads(final_kwargs["result_json"])["model_path"].endswith("job-1")


class TestExternalJobs:
    @pytest.mark.asyncio
    async def test_submit_success(self):
        with patch(
            "api.services.ai_training.get_dataset_db",
            new_callable=AsyncMock,
            return_value={"id": "ds-1"},
        ):
            result = await AITrainingService.submit_external_job(
                "t1", "ds-1", "llama", {"epochs": 3}, "modal"
            )
        assert result["provider"] == "modal"
        assert result["status"] == "submitted"
        assert result["external_job_id"].startswith("modal-")

    @pytest.mark.asyncio
    async def test_submit_missing_dataset_raises(self):
        with patch(
            "api.services.ai_training.get_dataset_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(AITrainingServiceError, match="not found"):
                await AITrainingService.submit_external_job("t1", "ds-1", "llama")

    @pytest.mark.asyncio
    async def test_submit_default_hyperparams(self):
        with patch(
            "api.services.ai_training.get_dataset_db",
            new_callable=AsyncMock,
            return_value={"id": "ds-1"},
        ):
            result = await AITrainingService.submit_external_job("t1", "ds-1", "llama")
        assert result["hyperparams"] == {
            "epochs": 3,
            "learning_rate": 2e-4,
            "batch_size": 8,
        }

    @pytest.mark.asyncio
    async def test_get_external_job_status(self):
        result = await AITrainingService.get_external_job_status("e1")
        assert result["external_job_id"] == "e1"
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_cancel_external_job(self):
        result = await AITrainingService.cancel_external_job("e1")
        assert result["status"] == "cancelled"


class TestModuleHelpers:
    def test_generate_mock_calls(self):
        calls = _generate_mock_calls("t1", "2024-01-01", "2024-01-02")
        assert calls
        assert all("transcription" in c for c in calls)
        assert all(c["tenant_id"] == "t1" for c in calls)

    def test_auto_version_empty(self):
        assert _auto_version([]) == "1.0.0"

    def test_auto_version_increments(self):
        assert _auto_version(["1.0.0", "2.1.3"]) == "2.1.4"

    def test_auto_version_ignores_garbage(self):
        assert _auto_version(["x", "y"]) == "1.0.0"

    @pytest.mark.asyncio
    async def test_async_sleep(self):
        with patch("api.services.ai_training.asyncio.sleep", new_callable=AsyncMock) as m:
            await _async_sleep(0.01)
        m.assert_awaited_once_with(0.01)
