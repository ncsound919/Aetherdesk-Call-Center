"""Unit tests for voice router endpoints.

Tests non-WebSocket endpoints using TestClient with a minimal FastAPI app
that includes only the voice router. Dependencies (verify_api_key, database
functions, classifier, ASR/TTS services, fonster_client) are mocked or
overridden to isolate the router logic.
"""

import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

# Prevent heavy import cascade: asr.py -> faster_whisper -> ctranslate2 -> transformers
_WhisperModel = MagicMock
_fake_fw_transcribe = types.ModuleType("faster_whisper.transcribe")
_fake_fw_transcribe.WhisperModel = _WhisperModel
_fake_fw_transcribe.BatchedInferencePipeline = MagicMock

_fake_fw = types.ModuleType("faster_whisper")
_fake_fw.WhisperModel = _WhisperModel
_fake_fw.transcribe = _fake_fw_transcribe

_fake_ct2 = types.ModuleType("ctranslate2")
_fake_ct2_specs = types.ModuleType("ctranslate2.specs")
_fake_ct2_models = types.ModuleType("ctranslate2.models")
_fake_ct2_converters = types.ModuleType("ctranslate2.converters")
_fake_ct2_converters_transformers = types.ModuleType("ctranslate2.converters.transformers")
_fake_transformers = types.ModuleType("transformers")
_fake_transformers.pipeline = MagicMock
_fake_transformers_depver = types.ModuleType("transformers.dependency_versions_check")
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
sys.modules["transformers.dependency_versions_check"] = _fake_transformers_depver
sys.modules["transformers.utils"] = _fake_transformers_utils
sys.modules["transformers.utils.import_utils"] = _fake_transformers_utils_import

# Prevent apps.api.main from importing fully when the outbound endpoint
# does its local import. Provide a minimal module since only fonster_client
# is accessed.
_fake_main = types.ModuleType("apps.api.main")
_fake_main.redis_client = None
_fake_main.fonster_client = None
sys.modules["apps.api.main"] = _fake_main

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
import pytest

from apps.api.services.auth import verify_api_key


@pytest.fixture
def app():
    """Create a minimal FastAPI app with just the voice router."""
    from apps.api.routers.voice import router

    application = FastAPI()
    application.include_router(router)

    # Override verify_api_key to always return TENANT-001
    async def _override_api_key():
        return "TENANT-001"

    application.dependency_overrides[verify_api_key] = _override_api_key

    return application


@pytest.fixture
def client(app):
    """TestClient bound to the minimal voice app."""
    with TestClient(app) as c:
        yield c


class TestIncomingCall:
    """Tests for GET/POST /voice/incoming."""

    def test_incoming_json_with_session_ref(self, client):
        """Sending JSON with sessionRef returns connect verb response."""
        with patch("apps.api.routers.voice.create_call_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"id": "session-001"}

            resp = client.post(
                "/voice/incoming",
                json={
                    "sessionRef": "sess-abc-123",
                    "ingressNumber": "+15551234567",
                    "tenantId": "tenant-1",
                    "profileId": "PROF-001",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["verb"] == "connect"
            assert body["endpoint"] == "tcp://aetherdesk-voice:50061"
            assert body["metadata"]["session_ref"] == "sess-abc-123"
            assert body["metadata"]["call_sid"] == "sess-abc-123"
            assert body["metadata"]["tenant_id"] == "tenant-1"
            assert body["metadata"]["profile_id"] == "PROF-001"
            mock_create.assert_called_once()

    def test_incoming_json_minimal_fields(self, client):
        """Sending JSON with minimal fields uses defaults for missing values."""
        with patch("apps.api.routers.voice.create_call_session", new_callable=AsyncMock):
            resp = client.post(
                "/voice/incoming",
                json={"sessionRef": "sess-minimal"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["verb"] == "connect"
            assert body["metadata"]["session_ref"] == "sess-minimal"
            # Default values
            assert body["metadata"]["profile_id"] == "PROF-001"
            assert body["metadata"]["tenant_id"] is None

    def test_incoming_form_data(self, client):
        """Sending form data works and returns connect verb."""
        with patch("apps.api.routers.voice.create_call_session", new_callable=AsyncMock):
            resp = client.post(
                "/voice/incoming",
                data={
                    "session_ref": "sess-form-456",
                    "from": "+15559876543",
                    "tenant_id": "tenant-2",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["verb"] == "connect"
            assert body["metadata"]["session_ref"] == "sess-form-456"
            assert body["metadata"]["tenant_id"] == "tenant-2"

    def test_incoming_empty_body_uses_defaults(self, client):
        """Sending empty/malformed body uses defaults (uuid session, no tenant)."""
        with patch("apps.api.routers.voice.create_call_session", new_callable=AsyncMock):
            resp = client.post(
                "/voice/incoming",
                json={},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["verb"] == "connect"
            # session_ref generated as uuid
            assert body["metadata"]["session_ref"] is not None
            assert body["metadata"]["profile_id"] == "PROF-001"


class TestClassifyIntent:
    """Tests for POST /voice/intent."""

    def test_classify_with_text(self, client):
        """Sending text returns intent classification result."""
        with patch(
            "apps.api.routers.voice.classifier.classify_with_fallback",
            new_callable=AsyncMock,
        ) as mock_classify:
            mock_classify.return_value = MagicMock(
                intent="sales",
                entities={"product": "widget"},
                confidence=0.95,
                reasoning="User mentioned buying",
            )

            resp = client.post(
                "/voice/intent",
                json={"text": "I want to buy a widget"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["intent"] == "sales"
            assert body["entities"] == {"product": "widget"}
            assert body["confidence"] == 0.95
            assert body["reasoning"] == "User mentioned buying"
            mock_classify.assert_called_once_with("I want to buy a widget")

    def test_classify_empty_text_returns_error(self, client):
        """Sending empty text returns error response."""
        resp = client.post(
            "/voice/intent",
            json={"text": ""},
        )
        assert resp.status_code == 200
        assert resp.json() == {"error": "No text provided"}


class TestTranscribeAudio:
    """Tests for POST /voice/transcribe."""

    def test_transcribe_with_audio(self, client):
        """Sending audio bytes returns transcription."""
        with patch(
            "apps.api.routers.voice.asr_service.transcribe",
            new_callable=AsyncMock,
        ) as mock_transcribe:
            mock_transcribe.return_value = "hello world"

            resp = client.post(
                "/voice/transcribe",
                content=b"fake-audio-bytes",
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["text"] == "hello world"
            mock_transcribe.assert_called_once_with(b"fake-audio-bytes")

    def test_transcribe_empty_body_returns_error(self, client):
        """Sending empty body returns error."""
        resp = client.post(
            "/voice/transcribe",
            content=b"",
        )
        assert resp.status_code == 200
        assert resp.json() == {"error": "No audio provided"}

    def test_transcribe_oversized_audio_returns_error(self, client):
        """Sending audio larger than 25MB returns error."""
        oversized = b"x" * (26 * 1024 * 1024)
        resp = client.post(
            "/voice/transcribe",
            content=oversized,
        )
        assert resp.status_code == 200
        assert resp.json() == {"error": "Audio payload too large (max 25MB)"}


class TestSynthesizeSpeech:
    """Tests for POST /voice/synthesize."""

    def test_synthesize_with_text(self, client):
        """Sending text returns synthesized audio."""
        with patch(
            "apps.api.routers.voice.tts_service.synthesize",
            new_callable=AsyncMock,
        ) as mock_synth:
            mock_synth.return_value = b"fake-audio-data"

            resp = client.post(
                "/voice/synthesize",
                json={"text": "Hello world"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["audio"] is not None
            mock_synth.assert_called_once_with("Hello world")

    def test_synthesize_empty_text_returns_error(self, client):
        """Sending empty text returns error."""
        resp = client.post(
            "/voice/synthesize",
            json={"text": ""},
        )
        assert resp.status_code == 200
        assert resp.json() == {"error": "No text provided"}


class TestOutboundCall:
    """Tests for POST /voice/outbound."""

    def test_outbound_with_to_phone(self, client):
        """Sending to_phone triggers outbound call via fonster_client."""
        mock_fonster = AsyncMock()
        mock_fonster.create_application = AsyncMock(
            return_value={"ref": "call-ref-123"}
        )

        with patch("apps.api.main.fonster_client", mock_fonster):
            resp = client.post(
                "/voice/outbound",
                json={"to_phone": "+15551234567"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is True
            assert body["call_ref"] == "call-ref-123"
            assert body["status"] == "queued"
            mock_fonster.create_application.assert_called_once()

    def test_outbound_without_to_phone_returns_400(self, client):
        """Sending without to_phone returns 400."""
        resp = client.post(
            "/voice/outbound",
            json={},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing to_phone"

    def test_outbound_no_voice_client_returns_503(self, client):
        """When fonster_client is None, returns 503."""
        # The fake main module already has fonster_client = None, so
        # we just call the endpoint without patching.
        resp = client.post(
            "/voice/outbound",
            json={"to_phone": "+15551234567"},
        )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Voice client not available"

    def test_outbound_fonster_client_raises(self, client):
        """When fonster_client.create_application raises, returns 500."""
        mock_fonster = AsyncMock()
        mock_fonster.create_application = AsyncMock(
            side_effect=RuntimeError("API failure"),
        )

        with patch("apps.api.main.fonster_client", mock_fonster):
            resp = client.post(
                "/voice/outbound",
                json={"to_phone": "+15551234567"},
            )
            assert resp.status_code == 500
            assert "API failure" in resp.json()["detail"]


class TestIncomingCallEdgeCases:
    """Tests for edge cases in /voice/incoming."""

    def test_incoming_create_call_session_fails(self, client):
        """When create_call_session raises, handler still returns connect response."""
        with patch("apps.api.routers.voice.create_call_session", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = RuntimeError("DB error")

            resp = client.post(
                "/voice/incoming",
                json={
                    "sessionRef": "sess-abc-123",
                    "ingressNumber": "+15551234567",
                    "tenantId": "tenant-1",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["verb"] == "connect"
            assert body["metadata"]["session_ref"] == "sess-abc-123"


class TestHandleMediaStream:
    """Tests for the /voice/media-stream WebSocket endpoint.

    The handle_media_stream function uses lazy imports inside its body:
        from apps.api.services.auth import verify_websocket_token
        from apps.api.routers.realtime import manager
    Therefore patching must target the source modules.
    """

    @pytest.mark.asyncio
    async def test_missing_token(self):
        from apps.api.routers.voice import handle_media_stream

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = None

        await handle_media_stream(mock_ws)

        mock_ws.close.assert_called_once_with(code=4001, reason="Missing authentication token")

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        from apps.api.routers.voice import handle_media_stream

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "bad-token"

        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = None
            await handle_media_stream(mock_ws)

        mock_ws.close.assert_called_once_with(code=4003, reason="Invalid or expired token")

    @pytest.mark.asyncio
    async def test_connected_event(self):
        from apps.api.routers.voice import handle_media_stream

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "valid-token"

        messages = [json.dumps({"event": "connected"})]

        async def _iter_text():
            for m in messages:
                yield m

        mock_ws.iter_text = _iter_text

        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"agent_id": "agent-1"}
            await handle_media_stream(mock_ws)

        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_event(self):
        from apps.api.routers.voice import handle_media_stream

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "valid-token"

        messages = [json.dumps({
            "event": "start",
            "start": {"streamSid": "stream-1", "callSid": "call-123"},
            "tenantId": "tenant-1",
        })]

        async def _iter_text():
            for m in messages:
                yield m

        mock_ws.iter_text = _iter_text

        async def _empty_gen():
            if False:
                yield

        speak_stream_result = _empty_gen()

        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.routers.realtime.manager.register_voice_ws") as mock_register, \
             patch("apps.api.routers.voice.get_or_create_session") as mock_get_session, \
             patch("apps.api.routers.voice.store_session") as mock_store, \
             patch("apps.api.routers.voice.Actions") as mock_actions_cls, \
             patch("apps.api.routers.voice.Orchestrator") as mock_orch_cls:

            mock_verify.return_value = {"agent_id": "agent-1"}
            mock_session = AsyncMock()
            mock_session.profile_id = "PROF-001"
            mock_session.tenant_id = "tenant-1"
            mock_get_session.return_value = mock_session
            mock_session.speak_stream = MagicMock(return_value=speak_stream_result)

            mock_ws.app.state.redis = MagicMock()

            await handle_media_stream(mock_ws)

        mock_ws.accept.assert_called_once()
        mock_register.assert_called_once_with("call-123", mock_ws, "stream-1")
        mock_get_session.assert_called()

    @pytest.mark.asyncio
    async def test_media_event(self):
        from apps.api.routers.voice import handle_media_stream
        import base64

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "valid-token"

        audio_bytes = b'\x00\x00' * 160
        payload_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        messages = [
            json.dumps({"event": "start", "start": {"streamSid": "stream-1", "callSid": "call-123"}, "tenantId": "tenant-1"}),
            json.dumps({"event": "media", "media": {"payload": payload_b64}}),
        ]

        async def _iter_text():
            for m in messages:
                yield m

        mock_ws.iter_text = _iter_text

        async def _empty_gen():
            if False:
                yield

        speak_stream_result = _empty_gen()

        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.routers.realtime.manager.register_voice_ws") as mock_register, \
             patch("apps.api.routers.realtime.manager.unregister_voice_ws") as mock_unregister, \
             patch("apps.api.routers.voice.get_or_create_session") as mock_get_session, \
             patch("apps.api.routers.voice.store_session") as mock_store, \
             patch("apps.api.routers.realtime.cleanup_call_transcripts") as mock_cleanup, \
             patch("apps.api.routers.voice.Actions") as mock_actions_cls, \
             patch("apps.api.routers.voice.Orchestrator") as mock_orch_cls:

            mock_verify.return_value = {"agent_id": "agent-1"}
            mock_session = AsyncMock()
            mock_session.profile_id = "PROF-001"
            mock_session.tenant_id = "tenant-1"
            mock_get_session.return_value = mock_session
            mock_session.speak_stream = MagicMock(return_value=speak_stream_result)
            mock_session.process_audio.return_value = "hello world"

            mock_response = MagicMock()
            mock_response.text = "Hi there!"
            mock_response.sentiment = None
            mock_response.latency_ms = None
            mock_response.needs_agent = False

            mock_orch = AsyncMock()
            mock_orch.step.return_value = mock_response
            mock_orch_cls.return_value = mock_orch

            mock_ws.app.state.redis = MagicMock()

            await handle_media_stream(mock_ws)

        mock_ws.accept.assert_called_once()
        mock_session.process_audio.assert_called_once_with(audio_bytes)
        mock_orch.step.assert_called_once()

    @pytest.mark.asyncio
    async def test_media_event_needs_agent(self):
        from apps.api.routers.voice import handle_media_stream
        import base64

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "valid-token"

        payload_b64 = base64.b64encode(b'\x00\x00' * 160).decode("utf-8")

        messages = [
            json.dumps({"event": "start", "start": {"streamSid": "stream-1", "callSid": "call-123"}, "tenantId": "tenant-1"}),
            json.dumps({"event": "media", "media": {"payload": payload_b64}}),
        ]

        async def _iter_text():
            for m in messages:
                yield m

        mock_ws.iter_text = _iter_text

        async def _empty_gen():
            if False:
                yield

        speak_stream_result = _empty_gen()

        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.routers.realtime.manager.register_voice_ws") as mock_register, \
             patch("apps.api.routers.realtime.manager.unregister_voice_ws") as mock_unregister, \
             patch("apps.api.routers.voice.get_or_create_session") as mock_get_session, \
             patch("apps.api.routers.voice.store_session") as mock_store, \
             patch("apps.api.routers.realtime.cleanup_call_transcripts") as mock_cleanup, \
             patch("apps.api.routers.voice.Actions") as mock_actions_cls, \
             patch("apps.api.routers.voice.Orchestrator") as mock_orch_cls:

            mock_verify.return_value = {"agent_id": "agent-1"}
            mock_session = AsyncMock()
            mock_session.profile_id = "PROF-001"
            mock_session.tenant_id = "tenant-1"
            mock_get_session.return_value = mock_session
            mock_session.speak_stream = MagicMock(return_value=speak_stream_result)
            mock_session.process_audio.return_value = "help"
            mock_session.transcript = ["entry1"]

            mock_response = MagicMock()
            mock_response.text = "Connecting you to an agent"
            mock_response.sentiment = None
            mock_response.latency_ms = None
            mock_response.needs_agent = True

            mock_orch = AsyncMock()
            mock_orch.step.return_value = mock_response
            mock_orch_cls.return_value = mock_orch

            mock_ws.app.state.redis = MagicMock()

            await handle_media_stream(mock_ws)

        sent_calls = [c for c in mock_ws.send_json.call_args_list if c[0][0].get("event") == "mark"]
        assert len(sent_calls) > 0
        assert sent_calls[0][0][0]["mark"]["name"] == "handoff"

    @pytest.mark.asyncio
    async def test_media_event_no_session_id(self):
        from apps.api.routers.voice import handle_media_stream
        import base64

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "valid-token"

        messages = [json.dumps({
            "event": "media",
            "media": {"payload": base64.b64encode(b'\x00\x00' * 160).decode("utf-8")},
        })]

        async def _iter_text():
            for m in messages:
                yield m

        mock_ws.iter_text = _iter_text

        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"agent_id": "agent-1"}
            await handle_media_stream(mock_ws)

        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_event(self):
        from apps.api.routers.voice import handle_media_stream

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "valid-token"

        messages = [
            json.dumps({"event": "start", "start": {"streamSid": "stream-1", "callSid": "call-123"}, "tenantId": "tenant-1"}),
            json.dumps({"event": "stop"}),
        ]

        async def _iter_text():
            for m in messages:
                yield m

        mock_ws.iter_text = _iter_text

        async def _empty_gen():
            if False:
                yield

        speak_stream_result = _empty_gen()

        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.routers.realtime.manager.register_voice_ws") as mock_register, \
             patch("apps.api.routers.realtime.manager.unregister_voice_ws") as mock_unregister, \
             patch("apps.api.routers.voice.get_or_create_session") as mock_get_session, \
             patch("apps.api.routers.voice.store_session") as mock_store, \
             patch("apps.api.routers.voice.remove_session") as mock_remove, \
             patch("apps.api.routers.realtime.cleanup_call_transcripts") as mock_cleanup, \
             patch("apps.api.routers.voice.Actions") as mock_actions_cls, \
             patch("apps.api.routers.voice.Orchestrator") as mock_orch_cls:

            mock_verify.return_value = {"agent_id": "agent-1"}
            mock_session = AsyncMock()
            mock_session.profile_id = "PROF-001"
            mock_session.tenant_id = "tenant-1"
            mock_get_session.return_value = mock_session
            mock_session.speak_stream = MagicMock(return_value=speak_stream_result)

            mock_ws.app.state.redis = MagicMock()

            await handle_media_stream(mock_ws)

        mock_remove.assert_called_once()
        mock_unregister.assert_called_once_with("call-123")
        mock_cleanup.assert_called_once_with("call-123")

    @pytest.mark.asyncio
    async def test_websocket_disconnect(self):
        from apps.api.routers.voice import handle_media_stream

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "valid-token"

        async def _iter_text():
            raise WebSocketDisconnect()
            yield  # pragma: no cover

        mock_ws.iter_text = _iter_text

        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"agent_id": "agent-1"}
            await handle_media_stream(mock_ws)

        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_disconnect_after_start(self):
        from apps.api.routers.voice import handle_media_stream

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "valid-token"

        async def _iter_text():
            yield json.dumps({"event": "start", "start": {"streamSid": "stream-1", "callSid": "call-123"}, "tenantId": "tenant-1"})
            raise WebSocketDisconnect()

        mock_ws.iter_text = _iter_text

        async def _empty_gen():
            if False:
                yield

        speak_stream_result = _empty_gen()

        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.routers.realtime.manager.register_voice_ws") as mock_register, \
             patch("apps.api.routers.realtime.manager.unregister_voice_ws") as mock_unregister, \
             patch("apps.api.routers.voice.get_or_create_session") as mock_get_session, \
             patch("apps.api.routers.voice.store_session") as mock_store, \
             patch("apps.api.routers.voice.remove_session") as mock_remove, \
             patch("apps.api.routers.realtime.cleanup_call_transcripts") as mock_cleanup, \
             patch("apps.api.routers.voice.Actions") as mock_actions_cls, \
             patch("apps.api.routers.voice.Orchestrator") as mock_orch_cls:

            mock_verify.return_value = {"agent_id": "agent-1"}
            mock_session = AsyncMock()
            mock_session.profile_id = "PROF-001"
            mock_session.tenant_id = "tenant-1"
            mock_get_session.return_value = mock_session
            mock_session.speak_stream = MagicMock(return_value=speak_stream_result)

            mock_ws.app.state.redis = MagicMock()

            await handle_media_stream(mock_ws)

        mock_register.assert_called_once()
        mock_unregister.assert_called_once_with("call-123")
        mock_cleanup.assert_called_once_with("call-123")
        mock_remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_generic_exception(self):
        from apps.api.routers.voice import handle_media_stream

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.query_params.get.return_value = "valid-token"

        async def _iter_text():
            yield json.dumps({"event": "start", "start": {"streamSid": "stream-1", "callSid": "call-123"}, "tenantId": "tenant-1"})
            raise RuntimeError("Unexpected failure")

        mock_ws.iter_text = _iter_text

        async def _empty_gen():
            if False:
                yield

        speak_stream_result = _empty_gen()

        with patch("apps.api.services.auth.verify_websocket_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.routers.realtime.manager.register_voice_ws") as mock_register, \
             patch("apps.api.routers.realtime.manager.unregister_voice_ws") as mock_unregister, \
             patch("apps.api.routers.voice.get_or_create_session") as mock_get_session, \
             patch("apps.api.routers.voice.store_session") as mock_store, \
             patch("apps.api.routers.voice.remove_session") as mock_remove, \
             patch("apps.api.routers.realtime.cleanup_call_transcripts") as mock_cleanup, \
             patch("apps.api.routers.voice.Actions") as mock_actions_cls, \
             patch("apps.api.routers.voice.Orchestrator") as mock_orch_cls:

            mock_verify.return_value = {"agent_id": "agent-1"}
            mock_session = AsyncMock()
            mock_session.profile_id = "PROF-001"
            mock_session.tenant_id = "tenant-1"
            mock_get_session.return_value = mock_session
            mock_session.speak_stream = MagicMock(return_value=speak_stream_result)

            mock_ws.app.state.redis = MagicMock()

            await handle_media_stream(mock_ws)

        mock_register.assert_called_once()
        mock_unregister.assert_called_once_with("call-123")
        mock_cleanup.assert_called_once_with("call-123")
        mock_remove.assert_called_once()
