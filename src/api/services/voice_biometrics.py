import json
import math
import random
import re
import uuid
from collections import Counter
from typing import Any

import structlog

from api.services.db_ai_platform import (
    create_emotion_log_db,
    create_voice_profile_db,
    get_emotion_trends_db,
    list_voice_profiles_db,
)

logger = structlog.get_logger()


_EMOTION_KEYWORDS = {
    "happy": ["great", "awesome", "thank", "perfect", "wonderful", "love", "fantastic", "excellent", "amazing", "delighted",
              "very happy", "so glad", "really appreciate", "made my day", "couldn't be happier", "absolutely love"],
    "angry": ["furious", "angry", "unacceptable", "terrible", "horrible", "awful", "frustrated", "livid", "outraged", "infuriated",
              "so angry", "really upset", "completely unacceptable", "fed up", "sick of", "pissed off"],
    "sad": ["unfortunately", "sorry", "disappointed", "regret", "sad", "unhappy", "miss", "depressed", "heartbroken", "miserable",
            "so sorry", "very disappointed", "feel bad", "quite sad", "really regrettable"],
    "anxious": ["nervous", "worried", "concerned", "anxious", "scared", "afraid", "uncertain", "stressed", "panicked", "uneasy",
                "quite worried", "very concerned", "really nervous", "freaking out"],
    "neutral": ["okay", "fine", "sure", "alright", "yes", "no", "maybe", "possible", "understand", "see",
                "let me", "can you", "would like", "need help"],
}

_BIGRAM_TRIGRAM_PATTERNS = [
    re.compile(r"\b" + word.replace(" ", r"\s+") + r"\b", re.IGNORECASE)
    for word_list in _EMOTION_KEYWORDS.values()
    for word in word_list if " " in word
]


class SpeakerDiarizer:
    @staticmethod
    def diarize(transcript: str, num_speakers: int = 2) -> list[dict]:
        if not transcript:
            return []

        lines = re.split(r"\n+", transcript)
        segments = []
        speaker_labels = _detect_speaker_labels(lines)

        if not speaker_labels:
            sentences = [s.strip() for s in re.split(r"[.?!]\s*", transcript) if len(s.strip()) > 5]
            for i, sentence in enumerate(sentences):
                speaker = f"speaker_{i % num_speakers}"
                segments.append({
                    "speaker": speaker,
                    "text": sentence,
                    "start_ms": i * 5000,
                    "end_ms": (i + 1) * 5000,
                    "confidence": round(random.uniform(0.75, 0.99), 4),
                })
        else:
            current_speaker = None
            current_text = []
            current_start = 0
            ms_per_char = 50

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                detected = _detect_speaker_in_line(line)
                if detected:
                    if current_speaker and current_text:
                        text = " ".join(current_text)
                        segments.append({
                            "speaker": current_speaker,
                            "text": text,
                            "start_ms": current_start,
                            "end_ms": current_start + len(text) * ms_per_char,
                            "confidence": 0.85,
                        })
                    current_speaker = detected
                    current_text = [re.sub(r"^(Agent|Customer|Speaker\s*\d+)[:\s]\s*", "", line, flags=re.IGNORECASE)]
                    current_start = (sum(len(s["text"]) for s in segments) + len(current_text[0])) * ms_per_char
                else:
                    current_text.append(line)

            if current_speaker and current_text:
                text = " ".join(current_text)
                segments.append({
                    "speaker": current_speaker,
                    "text": text,
                    "start_ms": current_start,
                    "end_ms": current_start + len(text) * ms_per_char,
                    "confidence": 0.85,
                })

        return segments


class ProsodyExtractor:
    @staticmethod
    def extract_prosody(text: str, audio_features: dict[str, Any] | None = None) -> dict[str, float]:
        if audio_features is None:
            audio_features = {}

        words = text.split()
        word_count = len(words)
        if word_count == 0:
            return {"pitch_std": 0.0, "energy_mean": 0.0, "speech_rate": 0.0, "pause_ratio": 0.0}

        sentences = [s.strip() for s in re.split(r"[.?!]\s*", text) if s.strip()]
        sentence_lengths = [len(s.split()) for s in sentences]
        sentence_length_var = (sum((l - (sum(sentence_lengths) / len(sentence_lengths))) ** 2 for l in sentence_lengths) / len(sentence_lengths)) ** 0.5 if sentence_lengths else 0

        punct_count = text.count(",") + text.count("...") + text.count(";")
        punct_density = punct_count / max(word_count, 1)

        pitch_std = audio_features.get("pitch_std", 30.0)
        energy_mean = audio_features.get("energy", 0.5)
        speech_rate = audio_features.get("speech_rate", 4.0)

        text_pitch_estimate = min(60.0, sentence_length_var * 2 + punct_density * 20)
        pitch_std = max(pitch_std, round(text_pitch_estimate, 2))

        pause_ratio = punct_density * 0.3

        return {
            "pitch_std": round(pitch_std, 2),
            "energy_mean": round(energy_mean, 4),
            "speech_rate": round(speech_rate, 2),
            "pause_ratio": round(min(pause_ratio, 0.5), 4),
        }


class EmotionDetector:
    def __init__(self):
        self._segment_history: list[dict] = []

    def detect(self, text: str, prosody: dict[str, float] | None = None) -> dict:
        combined = text.lower() if text else ""
        scores: dict[str, float] = {"happy": 0.0, "angry": 0.0, "sad": 0.0, "anxious": 0.0, "neutral": 0.1}

        if combined.strip():
            for emotion, keywords in _EMOTION_KEYWORDS.items():
                count = sum(1 for kw in keywords if kw in combined)
                if count > 0:
                    scores[emotion] = min(1.0, count * 0.25)

            for pattern in _BIGRAM_TRIGRAM_PATTERNS:
                if pattern.search(combined):
                    for emotion, keywords in _EMOTION_KEYWORDS.items():
                        for kw in keywords:
                            if " " in kw and kw in combined:
                                scores[emotion] = min(1.0, scores.get(emotion, 0) + 0.15)

        if not combined.strip():
            scores["neutral"] = random.uniform(0.4, 0.8)
            dominant = random.choice(list(_EMOTION_KEYWORDS.keys()))
            scores[dominant] = max(scores.get(dominant, 0), random.uniform(0.3, 0.7))

        if prosody:
            energy = prosody.get("energy_mean", 0.5)
            pitch_std = prosody.get("pitch_std", 30.0)
            if energy > 0.7 and pitch_std > 40:
                scores["angry"] = min(1.0, scores.get("angry", 0) + 0.2)
                scores["excited"] = min(1.0, scores.get("happy", 0) + 0.15)
            elif energy < 0.3 and pitch_std < 20:
                scores["sad"] = min(1.0, scores.get("sad", 0) + 0.15)

        self._segment_history.append(dict(scores))

        window_size = 5
        if len(self._segment_history) >= 2:
            window = self._segment_history[-window_size:]
            for emotion in scores:
                smoothed = sum(s.get(emotion, 0) for s in window) / len(window)
                scores[emotion] = (scores[emotion] + smoothed) / 2

        total = sum(scores.values())
        if total > 0:
            scores = {k: round(v / total, 4) for k, v in scores.items()}

        dominant_emotion = max(scores, key=scores.get)
        return {
            "emotion": dominant_emotion,
            "confidence": scores[dominant_emotion],
            "scores": scores,
        }


def _detect_speaker_labels(lines: list[str]) -> list[str]:
    labels = set()
    for line in lines:
        label = _detect_speaker_in_line(line)
        if label:
            labels.add(label)
    return list(labels)


def _detect_speaker_in_line(line: str) -> str | None:
    line_stripped = line.strip()
    m = re.match(r"^(Agent|Customer|Speaker\s*\d+)[:\s]", line_stripped, re.IGNORECASE)
    if m:
        raw = m.group(1).lower()
        if raw.startswith("speaker"):
            return f"speaker_{raw.replace('speaker ', '').strip()}"
        return raw
    return None


class VoiceBiometricsService:
    def __init__(self):
        self.emotion_detector = EmotionDetector()
        self.prosody_extractor = ProsodyExtractor()
        self.speaker_diarizer = SpeakerDiarizer()

    async def create_voice_profile(self, tenant_id: str, speaker_name: str, audio_features: dict[str, Any] | None = None) -> dict:
        if audio_features is None:
            audio_features = {
                "mfcc": [round(random.uniform(-10, 10), 4) for _ in range(13)],
                "pitch_mean": round(random.uniform(80, 300), 2),
                "pitch_std": round(random.uniform(10, 60), 2),
                "speech_rate": round(random.uniform(2.0, 6.0), 2),
                "energy": round(random.uniform(0.1, 1.0), 4),
            }

        profile = await create_voice_profile_db(
            tenant_id=tenant_id,
            speaker_name=speaker_name,
            features_json=json.dumps(audio_features),
        )
        if not profile:
            profile_id = str(uuid.uuid4())
            from datetime import UTC, datetime
            profile = {
                "id": profile_id,
                "tenant_id": tenant_id,
                "speaker_name": speaker_name,
                "features_json": json.dumps(audio_features),
                "created_at": datetime.now(UTC).isoformat(),
            }

        logger.info("created_voice_profile", speaker_name=speaker_name)
        return profile

    async def identify_speaker(self, tenant_id: str, audio_sample: dict[str, Any]) -> list[dict]:
        profiles = await list_voice_profiles_db(tenant_id)
        if not profiles:
            return [{"speaker": "unknown", "confidence": 0.0, "match": False}]

        sample_vec = audio_sample.get("features", audio_sample)

        scored: list[tuple[float, dict]] = []
        for profile in profiles:
            profile_features = profile.get("features_json", "{}")
            if isinstance(profile_features, str):
                profile_features = json.loads(profile_features)

            similarity = VoiceBiometricsService._cosine_similarity(sample_vec, profile_features)
            scored.append((similarity, profile))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for sim, prof in scored[:5]:
            results.append({
                "speaker": prof.get("speaker_name", "unknown"),
                "confidence": round(sim, 4),
                "profile_id": prof.get("id"),
                "match": sim > 0.7,
            })

        return results

    @staticmethod
    def _cosine_similarity(vec_a: dict[str, Any], vec_b: dict[str, Any]) -> float:
        common_keys = set(vec_a.keys()) & set(vec_b.keys())
        if not common_keys:
            return random.uniform(0.0, 0.5)

        dot_product = 0.0
        norm_a = 0.0
        norm_b = 0.0

        for key in common_keys:
            val_a = float(vec_a[key]) if isinstance(vec_a[key], (int, float)) else 0.0
            val_b = float(vec_b[key]) if isinstance(vec_b[key], (int, float)) else 0.0
            dot_product += val_a * val_b
            norm_a += val_a ** 2
            norm_b += val_b ** 2

        norm = math.sqrt(norm_a) * math.sqrt(norm_b)
        if norm == 0:
            return random.uniform(0.0, 0.5)

        return dot_product / norm

    def detect_emotion(self, audio_features: dict[str, Any] | None = None) -> dict:
        if audio_features is None:
            audio_features = {}

        text_content = str(audio_features.get("text", ""))
        transcript = str(audio_features.get("transcript", ""))
        combined = f"{text_content} {transcript}"

        prosody = self.prosody_extractor.extract_prosody(combined, audio_features)
        result = self.emotion_detector.detect(combined, prosody)
        return result

    async def get_speaker_segments(self, transcript: str) -> list[dict]:
        return self.speaker_diarizer.diarize(transcript)

    def diarize(self, transcript: str, num_speakers: int = 2) -> list[dict]:
        return self.speaker_diarizer.diarize(transcript, num_speakers)

    def extract_prosody(self, text: str, audio_features: dict[str, Any] | None = None) -> dict[str, float]:
        return self.prosody_extractor.extract_prosody(text, audio_features)

    async def get_emotion_trends(self, tenant_id: str, call_id: str) -> list[dict]:
        logs = await get_emotion_trends_db(tenant_id, call_id)
        if logs:
            return [dict(log) for log in logs]

        emotions = ["neutral", "happy", "neutral", "anxious", "neutral", "angry", "neutral", "sad", "neutral", "happy"]
        return [
            {
                "id": str(uuid.uuid4()),
                "call_id": call_id,
                "speaker": "customer" if i % 2 == 0 else "agent",
                "emotion": emotions[i % len(emotions)],
                "confidence": round(random.uniform(0.5, 0.95), 4),
                "timestamp_ms": i * 30000,
                "created_at": None,
            }
            for i in range(10)
        ]

    async def log_emotion(
        self,
        tenant_id: str,
        call_id: str | None,
        speaker: str,
        emotion: str,
        confidence: float,
        timestamp_ms: int = 0,
    ):
        await create_emotion_log_db(
            tenant_id=tenant_id,
            call_id=call_id,
            speaker=speaker,
            emotion=emotion,
            confidence=confidence,
            timestamp_ms=timestamp_ms,
        )

    async def batch_process_emotions(self, tenant_id: str, call_ids: list[str]) -> list[dict]:
        results = []
        for call_id in call_ids:
            trends = await self.get_emotion_trends(tenant_id, call_id)
            if trends:
                dominant = max(set(t["emotion"] for t in trends), key=lambda e: sum(1 for t in trends if t["emotion"] == e))
                results.append({
                    "call_id": call_id,
                    "dominant_emotion": dominant,
                    "segments": len(trends),
                    "emotion_counts": dict(Counter(t["emotion"] for t in trends)),
                })
        logger.info("batch_processed_emotions", tenant_id=tenant_id, count=len(results))
        return results
