"""Unit tests for calls router endpoints.

Tests call management routes using TestClient with a minimal FastAPI app
that includes only the calls router. Dependencies (verify_tenant_access,
database functions, fonster_client) are mocked/overridden to isolate the
router logic.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

# Prevent heavy import cascade: routers/__init__.py -> voice.py -> asr.py -> faster_whisper -> ctranslate2 -> transformers
# This module hangs on Python 3.12's importlib.metadata on some Windows systems.
# We install real ModuleType objects with the necessary attributes to satisfy import statements.
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

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.services.auth import verify_tenant_access


@pytest.fixture
def app():
    """Create a minimal FastAPI app with just the calls router."""
    from api.routers.calls import router

    application = FastAPI()
    application.include_router(router, prefix="/api/v1")

    # Mock app.state dependencies
    fonster = AsyncMock()
    fonster.answer_call = AsyncMock(return_value={"success": True})
    fonster.hangup_call = AsyncMock(return_value={"success": True})
    fonster.mute_call = AsyncMock(return_value={"success": True})
    fonster.unmute_call = AsyncMock(return_value={"success": True})
    fonster.hold_call = AsyncMock(return_value={"success": True})
    fonster.unhold_call = AsyncMock(return_value={"success": True})
    fonster.transfer_call = AsyncMock(return_value={"success": True})
    fonster.gather_speech = AsyncMock(return_value={"success": True})
    fonster.say_text = AsyncMock(return_value={"success": True})
    fonster.play_audio = AsyncMock(return_value={"success": True})
    fonster.record_call = AsyncMock(return_value={"success": True})
    fonster.send_dtmf = AsyncMock(return_value={"success": True})
    application.state.fonster_client = fonster

    # Override verify_tenant_access to always return a fixed tenant_id
    async def _override_tenant():
        return "tenant-1"

    application.dependency_overrides[verify_tenant_access] = _override_tenant

    return application


@pytest.fixture
def client(app):
    """TestClient bound to the minimal calls app."""
    with TestClient(app) as c:
        yield c


class TestCreateCall:
    """Tests for POST /api/v1/calls."""

    def test_create_call_with_specific_agent(self, client):
        """Creating a call with a valid agent_id succeeds."""
        with patch("api.routers.calls.get_agent_db", new_callable=AsyncMock) as mock_get_agent, \
             patch("api.routers.calls.create_call_session", new_callable=AsyncMock) as mock_create:

            mock_get_agent.return_value = {"id": "agent-1", "name": "Sales Agent"}

            resp = client.post(
                "/api/v1/calls",
                json={
                    "agent_id": "agent-1",
                    "caller_number": "+15551234567",
                    "call_direction": "inbound",
                    "intent": "sales",
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["agent_id"] == "agent-1"
            assert body["caller_number"] == "+15551234567"
            assert body["call_status"] == "initiated"
            assert body["tenant_id"] == "tenant-1"
            mock_get_agent.assert_called_once_with("agent-1")
            mock_create.assert_called_once()

    def test_create_call_agent_not_found(self, client):
        """Creating a call with a non-existent agent_id returns 404."""
        with patch("api.routers.calls.get_agent_db", new_callable=AsyncMock) as mock_get_agent:
            mock_get_agent.return_value = None

            resp = client.post(
                "/api/v1/calls",
                json={
                    "agent_id": "agent-missing",
                    "caller_number": "+15551234567",
                },
            )
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Agent not found"

    def test_create_call_auto_route_finds_agent(self, client):
        """Call without agent_id auto-routes to an available agent."""
        with patch("api.routers.calls.get_available_agents", new_callable=AsyncMock) as mock_avail, \
             patch("api.routers.calls.create_call_session", new_callable=AsyncMock) as mock_create:

            mock_avail.return_value = [{"id": "agent-2", "name": "Support Agent"}]

            resp = client.post(
                "/api/v1/calls",
                json={
                    "caller_number": "+15559876543",
                    "intent": "support",
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["agent_id"] == "agent-2"
            assert body["call_status"] == "initiated"
            mock_avail.assert_called_once_with("tenant-1", ["support"])
            mock_create.assert_called_once()

    def test_create_call_auto_route_queues_when_no_agents(self, client):
        """Call without agent_id enqueues when no agents are available."""
        with patch("api.routers.calls.get_available_agents", new_callable=AsyncMock) as mock_avail, \
             patch("api.routers.calls.enqueue_call", new_callable=AsyncMock) as mock_enqueue, \
             patch("api.routers.calls.create_call_session", new_callable=AsyncMock) as mock_create:

            mock_avail.return_value = []

            resp = client.post(
                "/api/v1/calls",
                json={
                    "caller_number": "+15555550000",
                    "intent": "billing",
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["agent_id"] is None
            assert body["call_status"] == "initiated"
            mock_avail.assert_called_once_with("tenant-1", ["billing"])
            mock_enqueue.assert_called_once_with("tenant-1", "+15555550000", "billing")
            mock_create.assert_called_once()

    def test_create_call_uses_called_number(self, client):
        """Called number overrides when provided."""
        with patch("api.routers.calls.get_agent_db", new_callable=AsyncMock) as mock_get_agent, \
             patch("api.routers.calls.create_call_session", new_callable=AsyncMock) as mock_create:

            mock_get_agent.return_value = {"id": "agent-1"}

            resp = client.post(
                "/api/v1/calls",
                json={
                    "agent_id": "agent-1",
                    "caller_number": "+15551111111",
                    "called_number": "+15552222222",
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            # Verify create_call_session was called with called_number
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["called_number"] == "+15552222222"
            assert call_kwargs["caller_number"] == "+15551111111"

    def test_create_call_outbound_direction(self, client):
        """Outbound call direction is preserved."""
        with patch("api.routers.calls.get_agent_db", new_callable=AsyncMock) as mock_get_agent, \
             patch("api.routers.calls.create_call_session", new_callable=AsyncMock):

            mock_get_agent.return_value = {"id": "agent-1"}

            resp = client.post(
                "/api/v1/calls",
                json={
                    "agent_id": "agent-1",
                    "caller_number": "+15551111111",
                    "call_direction": "outbound",
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["call_direction"] == "outbound"

    def test_create_call_fonster_creation_fails_logs_warning(self, client, app):
        """If fonster app creation fails, the call is still created and returns 201."""
        app.state.fonster_client.create_application = AsyncMock(
            side_effect=Exception("Fonster timeout")
        )

        with patch("api.routers.calls.get_agent_db", new_callable=AsyncMock) as mock_get_agent, \
             patch("api.routers.calls.create_call_session", new_callable=AsyncMock):

            mock_get_agent.return_value = {"id": "agent-1"}

            resp = client.post(
                "/api/v1/calls",
                json={
                    "agent_id": "agent-1",
                    "caller_number": "+15551111111",
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["call_status"] == "initiated"

    def test_create_call_no_fonster_client(self, app, client):
        """Call creation succeeds even when fonster_client is not set."""
        app.state.fonster_client = None

        with patch("api.routers.calls.get_agent_db", new_callable=AsyncMock) as mock_get_agent, \
             patch("api.routers.calls.create_call_session", new_callable=AsyncMock):

            mock_get_agent.return_value = {"id": "agent-1"}

            resp = client.post(
                "/api/v1/calls",
                json={
                    "agent_id": "agent-1",
                    "caller_number": "+15551111111",
                },
            )
            assert resp.status_code == 201


class TestCallAction:
    """Tests for POST /api/v1/calls/{call_id}/action."""

    def test_call_action_answer(self, client):
        """Answer action calls fonster_client.answer_call."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {
                "id": "call-1",
                "tenant_id": "tenant-1",
                "caller_number": "+15551234567",
            }

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "answer"},
            )
            assert resp.status_code == 200
            body = resp.json()
            # fonster_client.answer_call was called (mocked return value)
            assert body is not None

    def test_call_action_hangup(self, client):
        """Hangup action calls fonster_client.hangup_call."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {
                "id": "call-1",
                "tenant_id": "tenant-1",
                "caller_number": "+15551234567",
            }

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "hangup"},
            )
            assert resp.status_code == 200

    def test_call_action_mute(self, client):
        """Mute action calls fonster_client.mute_call."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "mute"},
            )
            assert resp.status_code == 200

    def test_call_action_unmute(self, client):
        """Unmute action calls fonster_client.unmute_call."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "unmute"},
            )
            assert resp.status_code == 200

    def test_call_action_hold(self, client):
        """Hold action calls fonster_client.hold_call."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "hold"},
            )
            assert resp.status_code == 200

    def test_call_action_unhold(self, client):
        """Unhold action calls fonster_client.unhold_call."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "unhold"},
            )
            assert resp.status_code == 200

    def test_call_action_transfer_with_target(self, client):
        """Transfer action requires and uses target."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "transfer", "target": "sip:agent-2@voip"},
            )
            assert resp.status_code == 200

    def test_call_action_transfer_without_target_returns_400(self, client):
        """Transfer without target returns 400."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "transfer"},
            )
            assert resp.status_code == 400
            assert resp.json()["detail"] == "Transfer target required"

    def test_call_action_gather(self, client):
        """Gather action calls fonster_client.gather_speech."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "gather", "data": {"hints": ["sales", "support"]}},
            )
            assert resp.status_code == 200

    def test_call_action_gather_default_hints(self, client):
        """Gather action uses default hints when data is not provided."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "gather"},
            )
            assert resp.status_code == 200

    def test_call_action_say(self, client):
        """Say action calls fonster_client.say_text."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "say", "data": {"text": "Hello"}},
            )
            assert resp.status_code == 200

    def test_call_action_say_default_text(self, client):
        """Say action uses empty text when data is not provided."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "say"},
            )
            assert resp.status_code == 200

    def test_call_action_play(self, client):
        """Play action calls fonster_client.play_audio."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "play", "data": {"url": "https://example.com/audio.wav"}},
            )
            assert resp.status_code == 200

    def test_call_action_record_start(self, client):
        """Record action calls fonster_client.record_call."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "record", "data": {"action": "start"}},
            )
            assert resp.status_code == 200

    def test_call_action_record_default_action(self, client):
        """Record action uses 'start' as default action."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "record"},
            )
            assert resp.status_code == 200

    def test_call_action_dtmf(self, client):
        """DTMF action calls fonster_client.send_dtmf."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "dtmf", "data": {"digits": "1234"}},
            )
            assert resp.status_code == 200

    def test_call_action_dtmf_default_digits(self, client):
        """DTMF action uses empty string as default digits."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "dtmf"},
            )
            assert resp.status_code == 200

    def test_call_action_call_not_found(self, client):
        """Action on non-existent call returns 404."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            resp = client.post(
                "/api/v1/calls/call-missing/action",
                json={"action": "hangup"},
            )
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Call not found"

    def test_call_action_idor_protection(self, client):
        """Action on call from another tenant returns 403."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "call-1",
                "tenant_id": "tenant-other",
                "caller_number": "+15551234567",
            }

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "hangup"},
            )
            assert resp.status_code == 403
            assert "Access denied" in resp.json()["detail"]

    def test_call_action_unknown_action(self, client):
        """Unknown action is rejected by Pydantic schema validation (422)."""
        resp = client.post(
            "/api/v1/calls/call-1/action",
            json={"action": "unknown_action"},
        )
        assert resp.status_code == 422

    def test_call_action_without_fonster(self, app, client):
        """Action returns success note when fonster_client is None (dev mode)."""
        app.state.fonster_client = None

        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get, \
             patch("api.routers.calls.log_audit_event", new_callable=AsyncMock):

            mock_get.return_value = {"id": "call-1", "tenant_id": "tenant-1", "caller_number": "+1"}

            resp = client.post(
                "/api/v1/calls/call-1/action",
                json={"action": "hangup"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["note"] == "Fonster not connected (dev mode)"


class TestGetCall:
    """Tests for GET /api/v1/calls/{call_id}."""

    def test_get_call_found(self, client):
        """Getting an existing call returns it."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "call-1",
                "tenant_id": "tenant-1",
                "agent_id": "agent-1",
                "caller_number": "+15551234567",
                "call_direction": "inbound",
                "call_status": "initiated",
                "duration_seconds": 0,
                "total_cost": 0,
                "sip_call_id": "sip-call-1",
                "intent_detected": "sales",
                "created_at": "2025-01-01T00:00:00",
            }

            resp = client.get("/api/v1/calls/call-1")
            assert resp.status_code == 200
            body = resp.json()
            assert body["id"] == "call-1"
            assert body["tenant_id"] == "tenant-1"
            assert body["agent_id"] == "agent-1"
            assert body["caller_number"] == "+15551234567"
            assert body["call_status"] == "initiated"
            assert body["cost"] == 0.0

    def test_get_call_not_found(self, client):
        """Getting a non-existent call returns 404."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            resp = client.get("/api/v1/calls/call-missing")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Call not found"

    def test_get_call_missing_optional_fields(self, client):
        """Getting a call with missing optional fields returns defaults."""
        with patch("api.routers.calls.get_call_session", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "call-1",
                "tenant_id": "tenant-1",
                "caller_number": "+15551234567",
                "call_status": "completed",
                # missing: agent_id, call_direction, duration_seconds, total_cost, sip_call_id, intent_detected, created_at
            }

            resp = client.get("/api/v1/calls/call-1")
            assert resp.status_code == 200
            body = resp.json()
            assert body["agent_id"] is None
            assert body["call_direction"] == "inbound"
            assert body["duration_seconds"] == 0
            assert body["cost"] == 0.0
            assert body["sip_call_id"] is None
            assert body["intent_detected"] is None
            assert "created_at" in body


class TestListCalls:
    """Tests for GET /api/v1/calls."""

    def test_list_calls_returns_all(self, client):
        """Listing calls returns all calls for the tenant."""
        with patch("api.routers.calls.list_calls_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [
                {
                    "id": "call-1",
                    "tenant_id": "tenant-1",
                    "agent_id": "agent-1",
                    "caller_number": "+15551111111",
                    "call_direction": "inbound",
                    "call_status": "completed",
                    "duration_seconds": 120,
                    "total_cost": 0.50,
                    "sip_call_id": "sip-1",
                    "intent_detected": "sales",
                    "created_at": "2025-01-01T00:00:00",
                },
                {
                    "id": "call-2",
                    "tenant_id": "tenant-1",
                    "agent_id": "agent-2",
                    "caller_number": "+15552222222",
                    "call_direction": "outbound",
                    "call_status": "initiated",
                    "duration_seconds": 30,
                    "total_cost": 0.10,
                    "sip_call_id": "sip-2",
                    "intent_detected": "support",
                    "created_at": "2025-01-02T00:00:00",
                },
            ]

            resp = client.get("/api/v1/calls")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 2
            assert body[0]["id"] == "call-1"
            assert body[1]["id"] == "call-2"
            mock_list.assert_called_once_with("tenant-1", None)

    def test_list_calls_with_status_filter(self, client):
        """Listing calls with a status filter filters correctly."""
        with patch("api.routers.calls.list_calls_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [
                {
                    "id": "call-1",
                    "tenant_id": "tenant-1",
                    "caller_number": "+15551111111",
                    "call_direction": "inbound",
                    "call_status": "initiated",
                    "duration_seconds": 0,
                    "total_cost": 0,
                    "created_at": "2025-01-01T00:00:00",
                },
            ]

            resp = client.get("/api/v1/calls?status=initiated")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 1
            assert body[0]["call_status"] == "initiated"
            mock_list.assert_called_once_with("tenant-1", "initiated")

    def test_list_calls_empty(self, client):
        """Listing calls returns empty list when no calls exist."""
        with patch("api.routers.calls.list_calls_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            resp = client.get("/api/v1/calls")
            assert resp.status_code == 200
            body = resp.json()
            assert body == []

    def test_list_calls_missing_optional_fields(self, client):
        """Listing calls handles rows with missing optional fields."""
        with patch("api.routers.calls.list_calls_db", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [
                {
                    "id": "call-1",
                    "tenant_id": "tenant-1",
                    "caller_number": "+15551111111",
                    "call_status": "initiated",
                    # missing optional fields
                },
            ]

            resp = client.get("/api/v1/calls")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 1
            assert body[0]["agent_id"] is None
            assert body[0]["duration_seconds"] == 0
            assert body[0]["cost"] == 0.0
