"""
ML-dependent E2E suite for AetherDesk.
Voice cloning, semantic retrieval, classifier/model-backed flows.
Requires scipy/sklearn/sentence-transformers to be installed.
"""
import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("USE_POSTGRES", "false")
os.environ.setdefault("ENCRYPTION_KEY", "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE=")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")

import pytest
import unittest

pytestmark = pytest.mark.e2e_ml


@pytest.fixture(scope="session")
def _verify_ml_deps():
    """Verify ML dependencies are available before running tests."""
    try:
        import scipy  # noqa
        import sklearn  # noqa
    except ImportError:
        pytest.skip("ML dependencies (scipy/sklearn) not available")
    return True


# ──────────────────────────────────────────────
# VOICE CLONING
# ──────────────────────────────────────────────
class TestVoiceCloning:
    """Voice clone CRUD and validation"""

    def test_clone_requires_auth(self, client, _verify_ml_deps):
        resp = client.post("/api/v1/voice/clone")
        assert resp.status_code in (401, 403, 422)

    def test_clone_rejects_small_audio(self, client, _verify_ml_deps):
        tiny = b"\x00" * 100
        resp = client.post(
            "/api/v1/voice/clone",
            files={"audio": ("test.wav", tiny, "audio/wav")},
            data={"voice_name": "Test Voice", "language": "en-US"},
            headers={"x-api-key": "dev-api-key"},
        )
        assert resp.status_code == 400

    def test_clone_validates_format(self, client, _verify_ml_deps):
        resp = client.post(
            "/api/v1/voice/clone",
            files={"audio": ("test.bin", b"\x00\x01\x02" * 20000, "application/octet-stream")},
            data={"voice_name": "Test", "language": "en-US"},
            headers={"x-api-key": "dev-api-key"},
        )
        assert resp.status_code == 415

    def test_clone_rejects_too_large(self, client, _verify_ml_deps):
        resp = client.post(
            "/api/v1/voice/clone",
            files={"audio": ("test.wav", b"\x00" * 11_000_000, "audio/wav")},
            data={"voice_name": "Test", "language": "en-US"},
            headers={"x-api-key": "dev-api-key"},
        )
        assert resp.status_code == 413

    def test_list_clones(self, client, _verify_ml_deps):
        resp = client.get("/api/v1/voice/clones")
        assert resp.status_code == 200
        assert "voices" in resp.json()

    def test_default_voice_config(self, client, _verify_ml_deps):
        resp = client.get("/api/v1/voice/default")
        assert resp.status_code == 200
        assert "default_voice_id" in resp.json()


# ──────────────────────────────────────────────
# INTENT CLASSIFIER
# ──────────────────────────────────────────────
class TestIntentClassifier:
    """Intent classification with ML model"""

    def test_classify_billing_invoice(self, client, _verify_ml_deps):
        with unittest.mock.patch(
            "apps.api.routers.voice.classifier.classify_with_fallback",
            new_callable=unittest.mock.AsyncMock,
        ) as mock_c:
            mock_c.return_value = type("R", (), {
                "intent": "billing_invoice",
                "entities": {},
                "confidence": 0.85,
                "reasoning": "Billing",
            })()
            resp = client.post(
                "/voice/intent",
                json={"text": "I need my invoice"},
                headers={"x-api-key": "dev-api-key"},
            )
            assert resp.status_code == 200
            assert resp.json()["intent"] == "billing_invoice"

    def test_keyword_fallback_billing(self, client, _verify_ml_deps):
        from apps.api.services.intent_classifier import classifier
        import asyncio
        result = asyncio.run(classifier.classify_with_fallback("I need my invoice"))
        assert result.intent is not None
        assert result.confidence >= 0


# ──────────────────────────────────────────────
# TTS SERVICE
# ──────────────────────────────────────────────
class TestTTSService:
    """TTS engine initialization and fallback"""

    def test_tts_initialization(self, client, _verify_ml_deps):
        from apps.api.services.tts import TTSService
        svc = TTSService(engines="edge", voice="en-US-AriaNeural")
        assert svc.engines == ["edge"]

    def test_tts_unknown_engine_raises(self, client, _verify_ml_deps):
        from apps.api.services.tts import TTSService
        svc = TTSService()
        import asyncio
        with pytest.raises(ValueError, match="Unknown TTS engine"):
            asyncio.run(svc._synthesize_with_engine("test", "nonexistent"))
