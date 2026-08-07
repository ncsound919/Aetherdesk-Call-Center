"""Unit tests for src/api/services/voice_biometrics.py."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.services.voice_biometrics import (
    EmotionDetector,
    ProsodyExtractor,
    SpeakerDiarizer,
    VoiceBiometricsService,
    _detect_speaker_in_line,
    _detect_speaker_labels,
)

_cosine_similarity = VoiceBiometricsService._cosine_similarity


class TestSpeakerDiarizer:
    def test_empty_transcript(self):
        assert SpeakerDiarizer.diarize("") == []

    def test_no_labels_splits_sentences(self):
        segments = SpeakerDiarizer.diarize(
            "Hello there. This is a longer second sentence! And a third one here?",
            num_speakers=2,
        )
        assert len(segments) >= 2
        assert segments[0]["speaker"] == "speaker_0"
        assert segments[1]["speaker"] == "speaker_1"
        assert all(0 <= s["confidence"] <= 1 for s in segments)

    def test_agent_customer_labels(self):
        transcript = (
            "Agent: Welcome to support.\n"
            "Customer: I need help please.\n"
            "Agent: Sure, what happened.\n"
            "Customer: My bill is wrong."
        )
        segments = SpeakerDiarizer.diarize(transcript)
        assert segments[0]["speaker"] == "agent"
        assert segments[1]["speaker"] == "customer"
        assert len(segments) == 4
        assert all(s["confidence"] == 0.85 for s in segments)

    def test_speaker_number_labels(self):
        transcript = (
            "Speaker 1: First turn.\n"
            "Speaker 2: Second turn.\n"
            "Continuing second speaker line."
        )
        segments = SpeakerDiarizer.diarize(transcript)
        assert segments[0]["speaker"] == "speaker_1"
        assert segments[1]["speaker"] == "speaker_2"
        # continuation line merged into speaker_2 segment
        assert "Continuing second speaker line." in segments[1]["text"]

    def test_single_label_then_continuation(self):
        transcript = "Agent: Only one labeled line.\nNo further labels here."
        segments = SpeakerDiarizer.diarize(transcript)
        assert len(segments) == 1
        assert segments[0]["speaker"] == "agent"

    def test_empty_lines_skipped_in_labeled_branch(self):
        transcript = "Agent: First line.\n\nCustomer: Second line.\n\n"
        segments = SpeakerDiarizer.diarize(transcript)
        assert [s["speaker"] for s in segments] == ["agent", "customer"]


class TestSpeakerDetection:
    def test_agent_label(self):
        assert _detect_speaker_in_line("Agent: hello") == "agent"

    def test_customer_label_space(self):
        assert _detect_speaker_in_line("Customer thanks") == "customer"

    def test_speaker_numbered(self):
        assert _detect_speaker_in_line("Speaker 3: hi") == "speaker_3"

    def test_lowercase(self):
        assert _detect_speaker_in_line("agent: hi") == "agent"

    def test_no_match(self):
        assert _detect_speaker_in_line("just some text") is None

    def test_detect_labels_collects(self):
        lines = ["Agent: a", "Customer: b", "random"]
        labels = _detect_speaker_labels(lines)
        assert set(labels) == {"agent", "customer"}

    def test_detect_labels_empty(self):
        assert _detect_speaker_labels(["nothing here"]) == []


class TestProsodyExtractor:
    def test_empty_text(self):
        assert ProsodyExtractor.extract_prosody("") == {
            "pitch_std": 0.0,
            "energy_mean": 0.0,
            "speech_rate": 0.0,
            "pause_ratio": 0.0,
        }

    def test_no_features_uses_defaults(self):
        result = ProsodyExtractor.extract_prosody("Hello there friend")
        assert result["pitch_std"] == 30.0
        assert result["energy_mean"] == 0.5
        assert result["speech_rate"] == 4.0

    def test_with_features(self):
        result = ProsodyExtractor.extract_prosody(
            "Hello world",
            {"pitch_std": 55.0, "energy": 0.9, "speech_rate": 5.5},
        )
        assert result["pitch_std"] == 55.0
        assert result["energy_mean"] == 0.9
        assert result["speech_rate"] == 5.5

    def test_pause_ratio_capped(self):
        result = ProsodyExtractor.extract_prosody(
            "a, b; c... d, e... f; g, h... i",
        )
        assert result["pause_ratio"] <= 0.5


class TestEmotionDetector:
    def test_empty_text_random(self):
        det = EmotionDetector()
        result = det.detect("")
        assert "emotion" in result
        assert "confidence" in result
        assert set(result["scores"]) >= {"happy", "angry", "sad", "anxious", "neutral"}

    def test_keyword_happy(self):
        det = EmotionDetector()
        result = det.detect("This is absolutely great and fantastic service")
        assert result["emotion"] == "happy"
        assert result["scores"]["happy"] > 0

    def test_bigram_pattern_boosts(self):
        det = EmotionDetector()
        result = det.detect("I am so glad you helped me")
        assert result["emotion"] == "happy"

    def test_high_energy_prosody(self):
        det = EmotionDetector()
        result = det.detect(
            "okay sure fine",
            {"energy_mean": 0.9, "pitch_std": 55.0},
        )
        assert result["scores"]["angry"] > 0

    def test_low_energy_prosody(self):
        det = EmotionDetector()
        result = det.detect(
            "okay sure fine",
            {"energy_mean": 0.1, "pitch_std": 5.0},
        )
        assert result["scores"]["sad"] > 0

    def test_smoothing_across_calls(self):
        det = EmotionDetector()
        det.detect("thank you so much")
        second = det.detect("thank you so much")
        assert len(det._segment_history) == 2
        assert "emotion" in second


class TestCreateVoiceProfile:
    @pytest.mark.asyncio
    async def test_with_features(self):
        with patch(
            "api.services.voice_biometrics.create_voice_profile_db",
            new_callable=AsyncMock,
            return_value={"id": "vp-1", "speaker_name": "Alice"},
        ) as mock_create:
            result = await VoiceBiometricsService().create_voice_profile(
                "t1", "Alice", {"mfcc": [1.0]}
            )
        assert result["id"] == "vp-1"
        assert json.loads(mock_create.call_args.kwargs["features_json"]) == {
            "mfcc": [1.0]
        }

    @pytest.mark.asyncio
    async def test_generates_features_when_none(self):
        with patch(
            "api.services.voice_biometrics.create_voice_profile_db",
            new_callable=AsyncMock,
            return_value={"id": "vp-1"},
        ) as mock_create:
            result = await VoiceBiometricsService().create_voice_profile(
                "t1", "Bob", None
            )
        assert result["id"] == "vp-1"
        features = json.loads(mock_create.call_args.kwargs["features_json"])
        assert "mfcc" in features
        assert "pitch_mean" in features

    @pytest.mark.asyncio
    async def test_fallback_when_db_returns_none(self):
        with patch(
            "api.services.voice_biometrics.create_voice_profile_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await VoiceBiometricsService().create_voice_profile(
                "t1", "Carol", {"mfcc": [1.0]}
            )
        assert result["speaker_name"] == "Carol"
        assert result["tenant_id"] == "t1"
        assert result["id"]


class TestIdentifySpeaker:
    @pytest.mark.asyncio
    async def test_no_profiles(self):
        with patch(
            "api.services.voice_biometrics.list_voice_profiles_db",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await VoiceBiometricsService().identify_speaker(
                "t1", {"mfcc": [1.0]}
            )
        assert result == [{"speaker": "unknown", "confidence": 0.0, "match": False}]

    @pytest.mark.asyncio
    async def test_with_matching_profile_string_features(self):
        profiles = [
            {
                "id": "vp-1",
                "speaker_name": "Alice",
                "features_json": json.dumps({"f1": 1.0, "f2": 2.0}),
            }
        ]
        with patch(
            "api.services.voice_biometrics.list_voice_profiles_db",
            new_callable=AsyncMock,
            return_value=profiles,
        ):
            result = await VoiceBiometricsService().identify_speaker(
                "t1", {"features": {"f1": 1.0, "f2": 2.0}}
            )
        assert result[0]["speaker"] == "Alice"
        assert result[0]["match"] is True
        assert result[0]["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_with_dict_features_and_ranking(self):
        profiles = [
            {
                "id": "vp-1",
                "speaker_name": "Far",
                "features_json": {"f1": 0.0, "f2": 1.0},
            },
            {
                "id": "vp-2",
                "speaker_name": "Near",
                "features_json": {"f1": 1.0, "f2": 0.0},
            },
        ]
        with patch(
            "api.services.voice_biometrics.list_voice_profiles_db",
            new_callable=AsyncMock,
            return_value=profiles,
        ):
            result = await VoiceBiometricsService().identify_speaker(
                "t1", {"features": {"f1": 1.0, "f2": 0.0}}
            )
        assert result[0]["speaker"] == "Near"
        assert result[1]["speaker"] == "Far"


class TestCosineSimilarity:
    def test_no_common_keys(self):
        sim = _cosine_similarity({"a": 1}, {"b": 2})
        assert 0.0 <= sim <= 0.5

    def test_zero_norm(self):
        sim = _cosine_similarity({"a": 0}, {"a": 0})
        assert 0.0 <= sim <= 0.5

    def test_identical_vectors(self):
        sim = _cosine_similarity({"a": 1.0, "b": 2.0}, {"a": 1.0, "b": 2.0})
        assert sim == pytest.approx(1.0)

    def test_non_numeric_values_ignored(self):
        sim = _cosine_similarity({"a": "x"}, {"a": "y"})
        assert 0.0 <= sim <= 0.5


class TestDetectEmotion:
    def test_with_audio_features(self):
        result = VoiceBiometricsService().detect_emotion(
            {"text": "this is fantastic service", "energy": 0.8, "pitch_std": 50.0}
        )
        assert "emotion" in result
        assert "scores" in result

    def test_without_audio_features(self):
        result = VoiceBiometricsService().detect_emotion(None)
        assert "emotion" in result


class TestPassthroughs:
    @pytest.mark.asyncio
    async def test_get_speaker_segments(self):
        svc = VoiceBiometricsService()
        segments = await svc.get_speaker_segments("Agent: hello\nCustomer: hi")
        assert segments

    def test_diarize(self):
        svc = VoiceBiometricsService()
        assert svc.diarize("", num_speakers=3) == []

    def test_extract_prosody(self):
        svc = VoiceBiometricsService()
        result = svc.extract_prosody("hello there", {"energy": 0.5})
        assert result["energy_mean"] == 0.5


class TestEmotionTrends:
    @pytest.mark.asyncio
    async def test_logs_present(self):
        with patch(
            "api.services.voice_biometrics.get_emotion_trends_db",
            new_callable=AsyncMock,
            return_value=[{"id": "1", "emotion": "happy"}],
        ):
            result = await VoiceBiometricsService().get_emotion_trends("t1", "call-1")
        assert result == [{"id": "1", "emotion": "happy"}]

    @pytest.mark.asyncio
    async def test_empty_logs_generate_fallback(self):
        with patch(
            "api.services.voice_biometrics.get_emotion_trends_db",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await VoiceBiometricsService().get_emotion_trends("t1", "call-1")
        assert len(result) == 10
        assert all(r["call_id"] == "call-1" for r in result)

    @pytest.mark.asyncio
    async def test_log_emotion(self):
        with patch(
            "api.services.voice_biometrics.create_emotion_log_db",
            new_callable=AsyncMock,
        ) as mock_create:
            await VoiceBiometricsService().log_emotion(
                "t1", "call-1", "customer", "happy", 0.9, 1000
            )
        assert mock_create.call_args.kwargs["emotion"] == "happy"
        assert mock_create.call_args.kwargs["timestamp_ms"] == 1000


class TestBatchProcessEmotions:
    @pytest.mark.asyncio
    async def test_with_trends(self):
        svc = VoiceBiometricsService()
        with patch.object(
            svc,
            "get_emotion_trends",
            new_callable=AsyncMock,
            return_value=[
                {"emotion": "happy"},
                {"emotion": "happy"},
                {"emotion": "neutral"},
            ],
        ):
            result = await svc.batch_process_emotions("t1", ["call-1"])
        assert result[0]["dominant_emotion"] == "happy"
        assert result[0]["segments"] == 3
        assert result[0]["emotion_counts"] == {"happy": 2, "neutral": 1}

    @pytest.mark.asyncio
    async def test_empty_trends_skipped(self):
        svc = VoiceBiometricsService()
        with patch.object(
            svc,
            "get_emotion_trends",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await svc.batch_process_emotions("t1", ["call-1", "call-2"])
        assert result == []
