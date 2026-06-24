"""Unit tests for AuditMiddleware.

Tests PHI redaction, resource type classification, and the full
dispatch path with a mocked database backend.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.middleware.audit import _get_resource_type, _redact_phi


# ── _redact_phi ────────────────────────────────────────────────────

class TestRedactPhi:
    """Verify PHI field redaction logic."""

    def test_redacts_known_phi_fields(self):
        data = {
            "caller_number": "+1555123",
            "email": "a@b.com",
            "ssn": "123-45-6789",
            "caller_name": "John",
        }
        result = _redact_phi(data)
        for key in data:
            assert result[key] == "[REDACTED-PHI]", f"{key} should be redacted"

    def test_preserves_non_phi_fields(self):
        data = {"caller_number": "+1555123", "session_id": "abc-123", "duration": 30}
        result = _redact_phi(data)
        assert result["caller_number"] == "[REDACTED-PHI]"
        assert result["session_id"] == "abc-123"
        assert result["duration"] == 30

    def test_redacts_nested_dict(self):
        data = {"nested": {"email": "a@b.com", "score": 10}, "outer": "ok"}
        result = _redact_phi(data)
        assert result["nested"]["email"] == "[REDACTED-PHI]"
        assert result["nested"]["score"] == 10
        assert result["outer"] == "ok"

    def test_redacts_list_of_dicts(self):
        data = {"items": [{"email": "a@b.com"}, {"email": "c@d.com", "age": 5}]}
        result = _redact_phi(data)
        assert result["items"][0]["email"] == "[REDACTED-PHI]"
        assert result["items"][1]["email"] == "[REDACTED-PHI]"
        assert result["items"][1]["age"] == 5

    def test_deeply_nested_structure(self):
        data = {
            "level1": {
                "level2": {
                    "patient_id": "P-001",
                    "meta": {"source": "clinic"},
                }
            }
        }
        result = _redact_phi(data)
        assert result["level1"]["level2"]["patient_id"] == "[REDACTED-PHI]"
        assert result["level1"]["level2"]["meta"]["source"] == "clinic"

    def test_handles_non_dict(self):
        assert _redact_phi("string") == "string"
        assert _redact_phi(42) == 42
        assert _redact_phi(None) is None
        assert _redact_phi([1, 2, 3]) == [1, 2, 3]

    def test_handles_empty_dict(self):
        assert _redact_phi({}) == {}

    def test_field_key_is_case_insensitive(self):
        data = {"CALLER_NUMBER": "+1555123", "Email": "a@b.com", "SSN": "123-45-6789"}
        result = _redact_phi(data)
        assert result["CALLER_NUMBER"] == "[REDACTED-PHI]"
        assert result["Email"] == "[REDACTED-PHI]"
        assert result["SSN"] == "[REDACTED-PHI]"

    def test_list_with_mixed_types(self):
        data = {
            "contacts": [
                {"email": "a@b.com"},
                "not_a_dict",
                42,
                {"phone": "+1555", "name": "John"},
            ]
        }
        result = _redact_phi(data)
        assert result["contacts"][0]["email"] == "[REDACTED-PHI]"
        assert result["contacts"][1] == "not_a_dict"
        assert result["contacts"][2] == 42
        assert result["contacts"][3]["phone"] == "[REDACTED-PHI]"
        assert result["contacts"][3]["name"] == "[REDACTED-PHI]"


# ── _get_resource_type ────────────────────────────────────────────

class TestGetResourceType:
    """Verify path-to-resource-type mapping."""

    def test_call_data_paths(self):
        assert _get_resource_type("/api/v1/calls") == "call_data"
        assert _get_resource_type("/api/v1/calls/123") == "call_data"
        assert _get_resource_type("/voice/intent") == "call_data"
        assert _get_resource_type("/voice/outbound") == "call_data"

    def test_call_event_data_paths(self):
        assert _get_resource_type("/api/v1/calls/webhooks") == "call_data"
        assert _get_resource_type("/api/v1/webhooks/fonster") == "call_event_data"
        assert _get_resource_type("/voice/incoming") == "call_event_data"

    def test_call_media_data_paths(self):
        assert _get_resource_type("/voice/media-stream") == "call_media_data"
        assert _get_resource_type("/voice/transcribe") == "call_media_data"
        assert _get_resource_type("/voice/synthesize") == "call_media_data"

    def test_tenant_data_paths(self):
        assert _get_resource_type("/api/v1/tenants") == "tenant_data"
        assert _get_resource_type("/api/v1/tenants/abc") == "tenant_data"
        assert _get_resource_type("/api/v1/tenants/") == "tenant_data"

    def test_agent_data_paths(self):
        assert _get_resource_type("/api/v1/agents") == "agent_data"
        assert _get_resource_type("/api/v1/agents/42") == "agent_data"
        assert _get_resource_type("/api/v1/agents/") == "agent_data"

    def test_non_phi_paths(self):
        assert _get_resource_type("/health") == "general"
        assert _get_resource_type("/metrics") == "general"
        assert _get_resource_type("/docs") == "general"
        assert _get_resource_type("/openapi.json") == "general"

    def test_unknown_paths(self):
        assert _get_resource_type("/some/random/path") == "general"
        assert _get_resource_type("") == "general"

    def test_substring_does_not_false_match(self):
        assert _get_resource_type("/not-calls/foo") == "general"

    def test_prefix_matches_subpath(self):
        assert _get_resource_type("/voice/incoming/12345") == "call_event_data"
        assert _get_resource_type("/api/v1/calls/some/deep/path") == "call_data"


# ── AuditMiddleware dispatch ───────────────────────────────────────

@pytest.fixture
def mock_db():
    """Mock SQLite connection so no real DB is touched."""
    with patch("apps.api.middleware.audit.USE_POSTGRES", False):
        mock_conn = MagicMock()
        with patch("apps.api.services.database._get_sqlite_conn", return_value=mock_conn):
            yield mock_conn


@pytest.fixture
def app():
    """Minimal FastAPI app with AuditMiddleware."""
    application = FastAPI()

    from apps.api.middleware.audit import AuditMiddleware

    application.add_middleware(AuditMiddleware)

    @application.get("/health")
    async def health():
        return {"status": "healthy"}

    @application.get("/api/v1/calls")
    async def get_calls():
        return {"calls": []}

    @application.post("/api/v1/calls")
    async def create_call():
        return {"status": "created", "id": "call-1"}

    @application.post("/health")
    async def health_post():
        return {"status": "healthy"}

    @application.put("/api/v1/calls/123")
    async def update_call():
        return {"status": "updated"}

    return application


@pytest.fixture
def client(app, mock_db):
    """TestClient bound to the minimal audit app."""
    with TestClient(app) as c:
        yield c


class TestAuditMiddlewareDispatch:
    """Verify dispatch behaviour: headers and DB logging."""

    def test_get_non_phi_sets_audit_logged_false(self, client, mock_db):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.headers.get("x-audit-logged") == "false"
        assert resp.headers.get("x-request-id") is not None
        mock_db.execute.assert_not_called()

    def test_get_phi_sets_audit_logged_true(self, client, mock_db):
        resp = client.get("/api/v1/calls")
        assert resp.status_code == 200
        assert resp.headers.get("x-audit-logged") == "true"
        assert resp.headers.get("x-request-id") is not None
        mock_db.execute.assert_called_once()

    def test_post_phi_logs_audit(self, client, mock_db):
        resp = client.post("/api/v1/calls", json={"caller_number": "+1555123"})
        assert resp.status_code == 200
        assert resp.headers.get("x-audit-logged") == "true"

        mock_db.execute.assert_called_once()
        sql, params = mock_db.execute.call_args[0]
        assert "INSERT INTO audit_log" in sql
        assert params[3] == "call_data"

    def test_post_phi_redacts_body_in_log(self, client, mock_db):
        resp = client.post(
            "/api/v1/calls",
            json={"caller_number": "+1555123", "session_id": "abc-123"},
        )
        assert resp.status_code == 200

        _, params = mock_db.execute.call_args[0]
        new_values = json.loads(params[6])
        body = new_values["body"]
        assert body["caller_number"] == "[REDACTED-PHI]"
        assert body["session_id"] == "abc-123"

    def test_put_phi_logs_audit(self, client, mock_db):
        resp = client.put("/api/v1/calls/123", json={"status": "completed"})
        assert resp.status_code == 200
        assert resp.headers.get("x-audit-logged") == "true"
        mock_db.execute.assert_called_once()

    def test_post_non_phi_does_not_log(self, client, mock_db):
        resp = client.post("/health", json={"foo": "bar"})
        assert resp.status_code == 200
        assert resp.headers.get("x-audit-logged") == "false"
        mock_db.execute.assert_not_called()

    def test_invalid_json_body_does_not_crash(self, client, mock_db):
        """When request body is malformed JSON, middleware catches and continues."""
        resp = client.post(
            "/api/v1/calls",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        mock_db.execute.assert_called_once()
        _, params = mock_db.execute.call_args[0]
        new_values = json.loads(params[6])
        assert new_values["body"] == {"_parse_error": True}

    def test_nested_body_redaction(self, client, mock_db):
        resp = client.post(
            "/api/v1/calls",
            json={"patient": {"email": "john@doe.com", "age": 30}},
        )
        assert resp.status_code == 200
        _, params = mock_db.execute.call_args[0]
        new_values = json.loads(params[6])
        body = new_values["body"]
        assert body["patient"]["email"] == "[REDACTED-PHI]"
        assert body["patient"]["age"] == 30

    def test_voice_incoming_path_is_phi(self, client, mock_db):
        @client.app.post("/voice/incoming")
        async def voice_incoming():
            return {"status": "ok"}

        resp = client.post("/voice/incoming")
        assert resp.headers.get("x-audit-logged") == "true"
        mock_db.execute.assert_called_once()
        _, params = mock_db.execute.call_args[0]
        assert params[3] == "call_event_data"

    def test_metrics_path_is_not_phi(self, client, mock_db):
        @client.app.get("/metrics")
        async def metrics():
            return {"metrics": "ok"}

        resp = client.get("/metrics")
        assert resp.headers.get("x-audit-logged") == "false"
        mock_db.execute.assert_not_called()
