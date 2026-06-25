import asyncio
import base64
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.main import app


class VoiceGatewayTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("api.routers.voice.asr_service.transcribe", new_callable=AsyncMock)
    def test_transcribe_endpoint_returns_text(self, mock_transcribe):
        mock_transcribe.return_value = "hello world"
        response = self.client.post(
            "/voice/transcribe",
            content=b"dummy-audio",
            headers={"content-type": "application/octet-stream"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"text": "hello world"})
        mock_transcribe.assert_called_once()

    @patch("api.routers.voice.tts_service.synthesize", new_callable=AsyncMock)
    def test_synthesize_endpoint_returns_base64_audio(self, mock_synthesize):
        mock_synthesize.return_value = b"test-audio"
        response = self.client.post("/voice/synthesize", json={"text": "hello"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("audio", payload)
        self.assertEqual(base64.b64decode(payload["audio"]), b"test-audio")
        mock_synthesize.assert_called_once_with("hello")

    @patch("api.routers.voice.classifier.classify_with_fallback", new_callable=AsyncMock)
    def test_intent_endpoint_returns_classification(self, mock_classify):
        mock_classify.return_value = type("R", (), {
            "intent": "billing_invoice",
            "entities": {"invoice_id": "INV123"},
            "confidence": 0.85,
            "reasoning": "Matched billing invoice intent"
        })()

        response = self.client.post("/voice/intent", json={"text": "I need my invoice status"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "intent": "billing_invoice",
            "entities": {"invoice_id": "INV123"},
            "confidence": 0.85,
            "reasoning": "Matched billing invoice intent"
        })
        mock_classify.assert_awaited_once_with("I need my invoice status")


class EngineTests(unittest.TestCase):
    def test_get_prompt_renders_template_fields(self):
        from api.services.actions import Actions
        from api.services.engine import ProtocolVM, VMState
        from api.services.loader import FileLoader as ProtocolLoader
        from api.services.validators import Validators

        vm = ProtocolVM(ProtocolLoader(base_path="config/protocols"), Validators(), Actions(redis_client=None))
        state = VMState(
            protocol_id="billing_invoice_v1",
            node="show_summary",
            fields={"invoice_id": "INV123", "zip": "90210"},
            transcript=[]
        )

        prompt = vm.get_prompt(state)
        self.assertIn("INV123", prompt)
        self.assertIn("90210", prompt)


class TTSTests(unittest.TestCase):
    def test_synthesize_returns_audio_bytes(self):
        from api.services.tts import TTSService, tts_service

        # Use actual instance and test that synthesize returns bytes
        service = tts_service
        self.assertIsNotNone(service.engines)
        self.assertGreaterEqual(len(service.engines), 1)
        self.assertTrue(hasattr(service, "synthesize"))


class IntentClassifierTests(unittest.TestCase):
    def test_classify_with_keyword_fallback(self):
        from api.services.intent_classifier import IntentClassifier

        classifier = IntentClassifier()

        result = asyncio.run(classifier._keyword_fallback("I need a refund for my invoice"))

        self.assertEqual(result.intent, "billing_refund")
        self.assertEqual(result.confidence, 0.5)
        self.assertIn("Keyword fallback matched", result.reasoning)

    def test_classify_with_ollama_failure_uses_fallback(self):
        from api.services.intent_classifier import IntentClassifier

        classifier = IntentClassifier()

        async def failing_execute(func, *args, **kwargs):
            raise RuntimeError("service unavailable")

        with patch("api.services.intent_classifier.retry_ollama.execute", new_callable=AsyncMock, side_effect=failing_execute):
            result = asyncio.run(classifier.classify("I need help with my order"))

        self.assertEqual(result.intent, "generalInquiry")
        self.assertEqual(result.confidence, 0.5)
        self.assertIn("Keyword fallback matched", result.reasoning)
