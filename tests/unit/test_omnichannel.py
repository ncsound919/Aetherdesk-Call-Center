"""Unit tests for api.routers.omnichannel."""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The api.routers package __init__ pulls in api.services.asr, which imports
# faster_whisper -> ctranslate2 -> torch at module level. Stub it out so the
# router imports stay fast and hermetic (no real model/torch loading).
_faster_whisper = types.ModuleType("faster_whisper")
_faster_whisper.WhisperModel = MagicMock
sys.modules.setdefault("faster_whisper", _faster_whisper)

from api.routers.omnichannel import router
from api.services.auth import verify_tenant_access


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)

    async def _override_tenant():
        return "TENANT-001"

    application.dependency_overrides[verify_tenant_access] = _override_tenant
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestSMS:
    def test_send_sms(self, client):
        with patch(
            "api.routers.omnichannel.sms_service.send_sms",
            new_callable=AsyncMock,
            return_value={"success": True, "sid": "SM123", "status": "sent"},
        ) as mock_send, patch(
            "api.routers.omnichannel.log_sms_db",
            new_callable=AsyncMock,
        ) as mock_log:
            resp = client.post(
                "/omnichannel/sms/send",
                json={"to_number": "+15551234567", "message": "Hello"},
            )
        assert resp.status_code == 200
        assert resp.json()["sid"] == "SM123"
        mock_send.assert_awaited_once_with("+15551234567", "Hello")
        mock_log.assert_awaited_once_with(
            "TENANT-001", "+15551234567", "Hello", status="sent", sid="SM123"
        )

    def test_send_bulk_sms(self, client):
        results = [
            {"to": "+15550000001", "sid": "SM1"},
            {"to": "+15550000002", "sid": "SM2"},
        ]
        with patch(
            "api.routers.omnichannel.sms_service.send_bulk_sms",
            new_callable=AsyncMock,
            return_value={"success": True, "results": results, "total": 2},
        ) as mock_bulk, patch(
            "api.routers.omnichannel.log_sms_db",
            new_callable=AsyncMock,
        ) as mock_log:
            resp = client.post(
                "/omnichannel/sms/bulk",
                json={"recipients": ["+15550000001", "+15550000002"], "message": "Hi"},
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2
        mock_bulk.assert_awaited_once_with(
            ["+15550000001", "+15550000002"], "Hi"
        )
        assert mock_log.await_count == 2

    def test_send_bulk_sms_missing_fields(self, client):
        resp = client.post("/omnichannel/sms/bulk", json={"message": "Hi"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "recipients and message are required"

        resp = client.post("/omnichannel/sms/bulk", json={"recipients": ["+1"]})
        assert resp.status_code == 400

    def test_create_sms_template(self, client):
        with patch(
            "api.routers.omnichannel.sms_service.create_sms_template",
            new_callable=AsyncMock,
            return_value={"id": "tpl-1", "name": "Greeting"},
        ) as mock_create:
            resp = client.post(
                "/omnichannel/sms/templates",
                json={"name": "Greeting", "body": "Hello {name}!"},
            )
        assert resp.status_code == 200
        mock_create.assert_awaited_once_with(
            "TENANT-001", "Greeting", "Hello {name}!"
        )

    def test_create_sms_template_failure(self, client):
        with patch(
            "api.routers.omnichannel.sms_service.create_sms_template",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/omnichannel/sms/templates",
                json={"name": "Greeting", "body": "Hello"},
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to create SMS template"

    def test_list_sms_templates(self, client):
        with patch(
            "api.routers.omnichannel.sms_service.get_sms_templates",
            new_callable=AsyncMock,
            return_value=[{"id": "tpl-1"}],
        ):
            resp = client.get("/omnichannel/sms/templates")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_sms_log(self, client):
        with patch(
            "api.routers.omnichannel.sms_service.get_sms_log",
            new_callable=AsyncMock,
            return_value=[{"id": "log-1"}],
        ) as mock_log:
            resp = client.get("/omnichannel/sms/log", params={"limit": 50, "offset": 10})
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        mock_log.assert_awaited_once_with("TENANT-001", limit=50, offset=10)

    def test_get_sms_log_validation(self, client):
        resp = client.get("/omnichannel/sms/log", params={"limit": 0})
        assert resp.status_code == 422

    def test_sms_inbound_webhook(self, client):
        with patch(
            "api.routers.omnichannel.sms_service.process_inbound_sms",
            new_callable=AsyncMock,
            return_value={"success": True, "from": "+15551234567", "processed": True},
        ) as mock_process, patch(
            "api.routers.omnichannel.log_sms_db",
            new_callable=AsyncMock,
        ) as mock_log:
            resp = client.post(
                "/omnichannel/sms/inbound",
                json={"from": "+15551234567", "body": "I need help"},
            )
        assert resp.status_code == 200
        assert resp.json()["processed"] is True
        mock_process.assert_awaited_once_with("+15551234567", "I need help", None)
        mock_log.assert_awaited_once_with(
            "TENANT-001",
            "+15551234567",
            "I need help",
            direction="inbound",
            status="received",
        )

    def test_sms_inbound_webhook_alternate_keys(self, client):
        with patch(
            "api.routers.omnichannel.sms_service.process_inbound_sms",
            new_callable=AsyncMock,
            return_value={"processed": True},
        ) as mock_process, patch(
            "api.routers.omnichannel.log_sms_db",
            new_callable=AsyncMock,
        ):
            resp = client.post(
                "/omnichannel/sms/inbound",
                json={"From": "+15550000001", "Body": "Hi", "session_id": "s9"},
            )
        assert resp.status_code == 200
        mock_process.assert_awaited_once_with("+15550000001", "Hi", "s9")


class TestChat:
    def test_create_chat_session(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.create_session",
            new_callable=AsyncMock,
            return_value={"id": "s1", "tenant_id": "TENANT-001"},
        ) as mock_create:
            resp = client.post(
                "/omnichannel/chat/sessions",
                json={
                    "visitor_id": "v1",
                    "visitor_name": "Bob",
                    "visitor_email": "bob@x.com",
                    "initial_message": "Hi",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "s1"
        mock_create.assert_awaited_once_with(
            "v1",
            "TENANT-001",
            name="Bob",
            email="bob@x.com",
            initial_message="Hi",
        )

    def test_create_chat_session_failure(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.create_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/omnichannel/chat/sessions", json={"visitor_id": "v1"}
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to create chat session"

    def test_send_chat_message(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.send_message",
            new_callable=AsyncMock,
            return_value={"id": "m1", "content": "Hi"},
        ) as mock_send:
            resp = client.post(
                "/omnichannel/chat/sessions/s1/messages",
                json={"content": "Hi", "sender_type": "visitor"},
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "m1"
        mock_send.assert_awaited_once_with("s1", "visitor", "Hi")

    def test_send_chat_message_not_found(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.send_message",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/omnichannel/chat/sessions/s1/messages",
                json={"content": "Hi", "sender_type": "visitor"},
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chat session not found"

    def test_get_chat_messages(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.get_messages",
            new_callable=AsyncMock,
            return_value=[{"id": "m1"}],
        ) as mock_get:
            resp = client.get(
                "/omnichannel/chat/sessions/s1/messages", params={"after_id": "m0"}
            )
        assert resp.status_code == 200
        mock_get.assert_awaited_once_with("s1", after_id="m0")

    def test_get_chat_messages_no_after_id(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.get_messages",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_get:
            resp = client.get("/omnichannel/chat/sessions/s1/messages")
        assert resp.status_code == 200
        mock_get.assert_awaited_once_with("s1", after_id=None)

    def test_assign_chat_agent(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.assign_agent",
            new_callable=AsyncMock,
            return_value={"id": "s1", "agent_id": "a1"},
        ) as mock_assign:
            resp = client.post(
                "/omnichannel/chat/sessions/s1/assign", json={"agent_id": "a1"}
            )
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "a1"
        mock_assign.assert_awaited_once_with("s1", "a1")

    def test_assign_chat_agent_missing_agent_id(self, client):
        resp = client.post("/omnichannel/chat/sessions/s1/assign", json={})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "agent_id is required"

    def test_assign_chat_agent_not_found(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.assign_agent",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/omnichannel/chat/sessions/s1/assign", json={"agent_id": "a1"}
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chat session not found"

    def test_close_chat_session(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.close_session",
            new_callable=AsyncMock,
            return_value={"id": "s1", "status": "closed"},
        ) as mock_close:
            resp = client.post("/omnichannel/chat/sessions/s1/close")
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"
        mock_close.assert_awaited_once_with("s1")

    def test_close_chat_session_not_found(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.close_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post("/omnichannel/chat/sessions/s1/close")
        assert resp.status_code == 404

    def test_get_waiting_sessions(self, client):
        with patch(
            "api.routers.omnichannel.chat_service.get_waiting_sessions",
            new_callable=AsyncMock,
            return_value=[{"id": "s1", "wait_time_seconds": 120}],
        ) as mock_waiting:
            resp = client.get("/omnichannel/chat/waiting")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        mock_waiting.assert_awaited_once_with("TENANT-001")
