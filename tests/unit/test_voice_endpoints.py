"""Unit tests for voice router HTTP endpoints.

Covers /voice/incoming, /voice/intent, /voice/transcribe, /voice/synthesize,
and /voice/outbound. External dependencies are mocked to prevent import
cascades and isolate router logic from real services.
"""

import base64
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Mock heavy C-extension modules that cause import failures in test env.
# These must be set BEFORE any api.* imports.
# ---------------------------------------------------------------------------
_fake_fw_transcribe = types.ModuleType("faster_whisper.transcribe")
_fake_fw_transcribe.WhisperModel = MagicMock
_fake_fw_transcribe.BatchedInferencePipeline = MagicMock

_fake_fw = types.ModuleType("faster_whisper")
_fake_fw.WhisperModel = MagicMock
_fake_fw.transcribe = _fake_fw_transcribe

_fake_ct2 = types.ModuleType("ctranslate2")
_fake_ct2_specs = types.ModuleType("ctranslate2.specs")
_fake_ct2_models = types.ModuleType("ctranslate2.models")
_fake_ct2_converters = types.ModuleType("ctranslate2.converters")
_fake_ct2_converters_transformers = types.ModuleType("ctranslate2.converters.transformers")

_fake_transformers = types.ModuleType("transformers")
_fake_transformers.pipeline = MagicMock
_fake_transformers_depend = types.ModuleType("transformers.dependency_versions_check")
_fake_transformers_utils = types.ModuleType("transformers.utils")
_fake_transformers_utils_import = types.ModuleType("transformers.utils.import_utils")

sys.modules["faster_whisper"] = _fake_fw
sys.modules["faster_whisper.transcribe"] = _fake_fw_transcribe
sys.modules["ctranslate2"] = _fake_ct2
sys.modules["ctranslate2.specs"] = _fake_ct2_specs
sys.modules["ctranslate2.models"] = _fake_ct2_models
sys.modules["ctranslate2.converters"] = _fake_ct2_converters
sys.modules["ctranslate2.converters.transformers"] = _fake_ct2_converters_transformers
sys.modules["transformers"] = _fake_transformers
sys.modules["transformers.dependency_versions_check"] = _fake_transformers_depend
sys.modules["transformers.utils"] = _fake_transformers_utils
sys.modules["transformers.utils.import_utils"] = _fake_transformers_utils_import

# Minimal api.main stub — the outbound endpoint does a lazy
# `from api.main import fonster_client as voice_client` inside the handler.
# If the real api.main is ever imported it crashes on an undefined
# sentry_dsn variable.  We permanently inject a stub so the lazy import
# always resolves to this safe version.
_fake_main = types.ModuleType("api.main")
_fake_main.redis_client = None
_fake_main.fonster_client = None
sys.modules["api.main"] = _fake_main

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.services.auth import verify_api_key
from api.routers.voice import router

# ---------------------------------------------------------------------------
# Build a minimal FastAPI app with only the voice router.
# ---------------------------------------------------------------------------
app = FastAPI()
app.include_router(router)
app.dependency_overrides[verify_api_key] = lambda: "TENANT-001"
client = TestClient(app)


# =============================================================================
# POST /voice/incoming
# =============================================================================


class TestHandleIncomingCall:
    """Tests for the incoming call webhook."""

    def test_returns_connect_response_structure(self):
        """JSON payload produces verb/connect/endpoint/metadata."""
        with patch("api.routers.voice.create_call_session", new_callable=AsyncMock) as mock_create:
            resp = client.post(
                "/voice/incoming",
                json={
                    "sessionRef": "sess-001",
                    "ingressNumber": "+15550001111",
                    "tenantId": "TENANT-A",
                    "profileId": "PROF-X",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["verb"] == "connect"
            assert body["endpoint"] == "tcp://aetherdesk-voice:50061"
            meta = body["metadata"]
            assert meta["session_ref"] == "sess-001"
            assert meta["call_sid"] == "sess-001"
            assert meta["tenant_id"] == "TENANT-A"
            assert meta["profile_id"] == "PROF-X"

    def test_creates_call_session_in_db(self):
        """Database create_call_session is invoked with correct parameters."""
        with patch("api.routers.voice.create_call_session", new_callable=AsyncMock) as mock_create:
            client.post(
                "/voice/incoming",
                json={
                    "sessionRef": "sess-db-001",
                    "ingressNumber": "+15550002222",
                    "tenantId": "TENANT-B",
                    "to": "+15550003333",
                },
            )
            mock_create.assert_awaited_once_with(
                tenant_id="TENANT-B",
                agent_id=None,
                caller_number="+15550002222",
                called_number="+15550003333",
                call_direction="inbound",
                sip_call_id="sess-db-001",
            )

    def test_minimal_json_uses_defaults(self):
        """Missing optional fields get sensible defaults."""
        with patch("api.routers.voice.create_call_session", new_callable=AsyncMock):
            resp = client.post("/voice/incoming", json={})
            body = resp.json()
            assert body["verb"] == "connect"
            assert body["metadata"]["profile_id"] == "PROF-001"
            assert body["metadata"]["tenant_id"] is None
            assert body["metadata"]["session_ref"] is not None

    def test_form_data_payload(self):
        """Form-encoded data with snake_case keys works."""
        with patch("api.routers.voice.create_call_session", new_callable=AsyncMock):
            resp = client.post(
                "/voice/incoming",
                data={
                    "session_ref": "sess-form-789",
                    "from": "+15550004444",
                    "tenant_id": "TENANT-C",
                },
            )
            body = resp.json()
            assert body["metadata"]["session_ref"] == "sess-form-789"
            assert body["metadata"]["tenant_id"] == "TENANT-C"

    def test_db_failure_still_returns_connect(self):
        """DB error in create_call_session does not block the response."""
        with patch("api.routers.voice.create_call_session", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = RuntimeError("DB unavailable")
            resp = client.post(
                "/voice/incoming",
                json={"sessionRef": "sess-fail-001", "tenantId": "TENANT-D"},
            )
            assert resp.status_code == 200
            assert resp.json()["verb"] == "connect"


# =============================================================================
# POST /voice/intent
# =============================================================================


class TestClassifyTranscript:
    """Tests for the intent classification endpoint."""

    def test_returns_intent_entities_confidence(self):
        """Text payload returns full classification result."""
        mock_result = MagicMock(
            intent="pharmacy_refill",
            entities={"rx_number": "12345"},
            confidence=0.92,
            reasoning="Caller mentioned prescription refill",
        )
        with patch(
            "api.routers.voice.classifier.classify_with_fallback",
            new_callable=AsyncMock,
        ) as mock_classify:
            mock_classify.return_value = mock_result
            resp = client.post(
                "/voice/intent",
                json={"text": "I need to refill prescription 12345"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["intent"] == "pharmacy_refill"
            assert body["entities"] == {"rx_number": "12345"}
            assert body["confidence"] == 0.92
            assert "reasoning" in body
            mock_classify.assert_awaited_once_with("I need to refill prescription 12345")

    def test_empty_text_returns_error(self):
        """Empty string returns error dict."""
        resp = client.post("/voice/intent", json={"text": ""})
        assert resp.status_code == 200
        assert resp.json() == {"error": "No text provided"}

    def test_missing_text_key_returns_error(self):
        """Missing text key in body also treated as empty."""
        resp = client.post("/voice/intent", json={})
        assert resp.status_code == 200
        assert resp.json() == {"error": "No text provided"}


# =============================================================================
# POST /voice/transcribe
# =============================================================================


class TestTranscribeAudio:
    """Tests for the audio transcription endpoint."""

    def test_returns_transcribed_text(self):
        """Audio bytes return transcribed text."""
        with patch(
            "api.routers.voice.asr_service.transcribe",
            new_callable=AsyncMock,
        ) as mock_transcribe:
            mock_transcribe.return_value = "hello from the caller"
            resp = client.post(
                "/voice/transcribe",
                content=b"fake-pcm-audio-data",
            )
            assert resp.status_code == 200
            assert resp.json()["text"] == "hello from the caller"
            mock_transcribe.assert_awaited_once_with(b"fake-pcm-audio-data")

    def test_empty_body_returns_error(self):
        """Zero-length audio returns error."""
        resp = client.post("/voice/transcribe", content=b"")
        assert resp.status_code == 200
        assert resp.json() == {"error": "No audio provided"}

    def test_oversized_audio_returns_error(self):
        """Audio > 25 MB returns size-limit error."""
        oversized = b"\x00" * (25 * 1024 * 1024 + 1)
        resp = client.post("/voice/transcribe", content=oversized)
        assert resp.status_code == 200
        assert resp.json() == {"error": "Audio payload too large (max 25MB)"}


# =============================================================================
# POST /voice/synthesize
# =============================================================================


class TestSynthesizeText:
    """Tests for the text-to-speech endpoint."""

    def test_returns_base64_audio(self):
        """Text payload returns base64-encoded audio bytes."""
        fake_audio = b"\xff\xfb\x90\x00" * 100
        with patch(
            "api.routers.voice.tts_service.synthesize",
            new_callable=AsyncMock,
        ) as mock_synth:
            mock_synth.return_value = fake_audio
            resp = client.post(
                "/voice/synthesize",
                json={"text": "Hello, how can I help?"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "audio" in body
            decoded = base64.b64decode(body["audio"])
            assert decoded == fake_audio
            mock_synth.assert_awaited_once_with("Hello, how can I help?")

    def test_empty_text_returns_error(self):
        """Empty string returns error dict."""
        resp = client.post("/voice/synthesize", json={"text": ""})
        assert resp.status_code == 200
        assert resp.json() == {"error": "No text provided"}

    def test_missing_text_key_returns_error(self):
        """Missing text key in body also treated as empty."""
        resp = client.post("/voice/synthesize", json={})
        assert resp.status_code == 200
        assert resp.json() == {"error": "No text provided"}


# =============================================================================
# POST /voice/outbound
# =============================================================================


class TestTriggerOutboundCall:
    """Tests for the outbound call trigger endpoint.

    The outbound handler does a lazy import:
        from api.main import fonster_client as voice_client
    We use patch() to set the attribute on whatever module is live in sys.modules,
    which works regardless of whether it's the fake or real api.main.
    """

    def test_returns_ok_when_client_available(self):
        """Valid to_phone with active fonster_client returns ok + call_ref."""
        mock_fonster = AsyncMock()
        mock_fonster.create_application = AsyncMock(
            return_value={"ref": "outbound-ref-001"}
        )
        with patch("api.main.fonster_client", mock_fonster):
            resp = client.post(
                "/voice/outbound",
                json={"to_phone": "+15551234567"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is True
            assert body["call_ref"] == "outbound-ref-001"
            assert body["status"] == "queued"
            mock_fonster.create_application.assert_awaited_once()

    def test_returns_400_when_no_to_phone(self):
        """Missing to_phone raises 400."""
        resp = client.post("/voice/outbound", json={})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing to_phone"

    def test_returns_503_when_no_voice_client(self):
        """None fonster_client raises 503."""
        with patch("api.main.fonster_client", None):
            resp = client.post(
                "/voice/outbound",
                json={"to_phone": "+15551234567"},
            )
            assert resp.status_code == 503
            assert resp.json()["detail"] == "Voice client not available"

    def test_returns_500_on_fonster_exception(self):
        """Client raising an exception yields 500."""
        mock_fonster = AsyncMock()
        mock_fonster.create_application = AsyncMock(
            side_effect=RuntimeError("SIP error")
        )
        with patch("api.main.fonster_client", mock_fonster):
            resp = client.post(
                "/voice/outbound",
                json={"to_phone": "+15551234567"},
            )
            assert resp.status_code == 500
            assert "SIP error" in resp.json()["detail"]

    def test_passes_profile_id_through(self):
        """Custom profile_id is forwarded in the fonster payload."""
        mock_fonster = AsyncMock()
        mock_fonster.create_application = AsyncMock(return_value={"ref": "r1"})
        with patch("api.main.fonster_client", mock_fonster):
            client.post(
                "/voice/outbound",
                json={
                    "to_phone": "+15559990000",
                    "profile_id": "PROF-CUSTOM",
                },
            )
            call_kwargs = mock_fonster.create_application.call_args[0][0]
            assert call_kwargs["variables"]["profile_id"] == "PROF-CUSTOM"
