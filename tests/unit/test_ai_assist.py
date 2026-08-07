"""Unit tests for api.routers.ai_assist."""

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

from api.routers.ai_assist import router
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


VALID_SCHEMA = {"type": "object", "required": ["intent"]}


class TestValidateOutput:
    def test_validate_output_success(self, client):
        with patch(
            "api.routers.ai_assist.validator.get_validation_schema",
            return_value=VALID_SCHEMA,
        ) as mock_schema, patch(
            "api.routers.ai_assist.validator.validate_json_output",
            return_value={"valid": True, "errors": [], "fixed": None},
        ) as mock_validate:
            resp = client.post(
                "/ai-assist/validate",
                json={"output": '{"intent": "billing_invoice"}', "schema_name": "intent_classification"},
            )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True
        mock_schema.assert_called_once_with("intent_classification")
        mock_validate.assert_called_once_with(
            '{"intent": "billing_invoice"}', VALID_SCHEMA
        )

    def test_validate_output_schema_not_found(self, client):
        with patch(
            "api.routers.ai_assist.validator.get_validation_schema",
            return_value=None,
        ):
            resp = client.post(
                "/ai-assist/validate",
                json={"output": "{}", "schema_name": "unknown"},
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Schema 'unknown' not found"


class TestValidateIntent:
    def test_validate_intent_default_allowed(self, client):
        result = {"intent": "order_status", "confidence": 0.9}
        with patch(
            "api.routers.ai_assist.validator.validate_intent_result",
            return_value={"valid": True, "errors": [], "intent": "order_status"},
        ) as mock_validate:
            resp = client.post(
                "/ai-assist/validate/intent", json={"result": result}
            )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True
        call_args = mock_validate.call_args.args
        assert call_args[0] == result
        assert "order_status" in call_args[1]

    def test_validate_intent_custom_allowed(self, client):
        allowed = ["custom_intent"]
        with patch(
            "api.routers.ai_assist.validator.validate_intent_result",
            return_value={"valid": False, "errors": ["x"], "intent": ""},
        ) as mock_validate:
            resp = client.post(
                "/ai-assist/validate/intent",
                json={"result": {"intent": "foo"}, "allowed_intents": allowed},
            )
        assert resp.status_code == 200
        mock_validate.assert_called_once_with({"intent": "foo"}, allowed)


class TestFixOutput:
    def test_fix_output_success(self, client):
        with patch(
            "api.routers.ai_assist.validator.repair_with_llm_fallback",
            return_value='{"intent": "x"}',
        ) as mock_repair:
            resp = client.post(
                "/ai-assist/validate/fix",
                json={"output": "{'intent': 'x'}", "error": "parse error"},
            )
        assert resp.status_code == 200
        assert resp.json() == {
            "original": "{'intent': 'x'}",
            "fixed": '{"intent": "x"}',
        }
        mock_repair.assert_called_once_with("{'intent': 'x'}", "parse error")

    def test_fix_output_missing_output(self, client):
        resp = client.post("/ai-assist/validate/fix", json={"error": "boom"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "'output' field is required"


class TestSchemas:
    def test_list_schemas(self, client):
        with patch(
            "api.routers.ai_assist.validator.list_schemas",
            return_value=["intent_classification", "entity_extraction"],
        ) as mock_list:
            resp = client.get("/ai-assist/schemas")
        assert resp.status_code == 200
        assert resp.json()["schemas"] == [
            "intent_classification",
            "entity_extraction",
        ]

    def test_get_schema_success(self, client):
        with patch(
            "api.routers.ai_assist.validator.get_validation_schema",
            return_value=VALID_SCHEMA,
        ):
            resp = client.get("/ai-assist/schemas/intent_classification")
        assert resp.status_code == 200
        assert resp.json()["name"] == "intent_classification"
        assert resp.json()["schema"] == VALID_SCHEMA

    def test_get_schema_not_found(self, client):
        with patch(
            "api.routers.ai_assist.validator.get_validation_schema",
            return_value=None,
        ):
            resp = client.get("/ai-assist/schemas/unknown")
        assert resp.status_code == 404


class TestSuggestions:
    def test_get_suggestions(self, client):
        with patch(
            "api.routers.ai_assist.agent_assist_service.get_suggestions",
            new_callable=AsyncMock,
            return_value=[{"type": "action", "action": "offer_discount"}],
        ) as mock_suggest:
            resp = client.post(
                "/ai-assist/suggestions",
                json={
                    "call_id": "c1",
                    "transcript_segment": "I want a refund",
                    "context": {"current_intent": "billing_refund"},
                },
            )
        assert resp.status_code == 200
        assert len(resp.json()["suggestions"]) == 1
        context = mock_suggest.await_args.args[2]
        assert context["tenant_id"] == "TENANT-001"
        assert context["current_intent"] == "billing_refund"


class TestKnowledge:
    def test_search_knowledge(self, client):
        with patch(
            "api.routers.ai_assist.agent_assist_service.get_knowledge_snippets",
            new_callable=AsyncMock,
            return_value=[{"id": "1", "title": "Refund policy"}],
        ) as mock_search:
            resp = client.get(
                "/ai-assist/knowledge", params={"query": "refund", "limit": 3}
            )
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 1
        mock_search.assert_awaited_once_with("TENANT-001", "refund", 3)

    def test_search_knowledge_query_required(self, client):
        resp = client.get("/ai-assist/knowledge", params={"query": ""})
        assert resp.status_code == 422

    def test_search_knowledge_limit_validation(self, client):
        resp = client.get("/ai-assist/knowledge", params={"query": "x", "limit": 0})
        assert resp.status_code == 422

    def test_create_knowledge(self, client):
        with patch(
            "api.routers.ai_assist.agent_assist_service.create_knowledge_snippet",
            new_callable=AsyncMock,
            return_value={"id": "1", "title": "Refund policy"},
        ) as mock_create:
            resp = client.post(
                "/ai-assist/knowledge",
                json={
                    "title": "Refund policy",
                    "content": "30 day refund",
                    "tags": ["billing"],
                    "category": "billing",
                },
            )
        assert resp.status_code == 200
        mock_create.assert_awaited_once_with(
            "TENANT-001", "Refund policy", "30 day refund", ["billing"], "billing"
        )

    def test_delete_knowledge_success(self, client):
        with patch(
            "api.routers.ai_assist.agent_assist_service.delete_knowledge_snippet",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_delete:
            resp = client.delete("/ai-assist/knowledge/1")
        assert resp.status_code == 200
        assert resp.json() == {"success": True}
        mock_delete.assert_awaited_once_with("TENANT-001", "1")

    def test_delete_knowledge_not_found(self, client):
        with patch(
            "api.routers.ai_assist.agent_assist_service.delete_knowledge_snippet",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = client.delete("/ai-assist/knowledge/999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Knowledge snippet not found"


class TestNextBestAction:
    def test_get_next_best_action(self, client):
        with patch(
            "api.routers.ai_assist.agent_assist_service.get_next_best_action",
            new_callable=AsyncMock,
            return_value={"action": "escalate_to_supervisor"},
        ) as mock_nba:
            resp = client.get(
                "/ai-assist/nba",
                params={
                    "call_id": "c1",
                    "call_duration_seconds": 400,
                    "current_intent": "billing_refund",
                    "sentiment": "negative",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["action"] == "escalate_to_supervisor"
        context = mock_nba.await_args.args[0]
        assert context["call_id"] == "c1"
        assert context["call_duration_seconds"] == 400
        assert context["current_intent"] == "billing_refund"
        assert context["sentiment"] == "negative"

    def test_get_next_best_action_defaults(self, client):
        with patch(
            "api.routers.ai_assist.agent_assist_service.get_next_best_action",
            new_callable=AsyncMock,
            return_value={"action": "continue_monitoring"},
        ) as mock_nba:
            resp = client.get("/ai-assist/nba")
        assert resp.status_code == 200
        context = mock_nba.await_args.args[0]
        assert context["call_id"] == ""
        assert context["call_duration_seconds"] == 0
        assert context["current_intent"] is None
        assert context["sentiment"] == "neutral"


class TestRealtime:
    def test_get_realtime_stats(self, client):
        with patch(
            "api.routers.ai_assist.agent_assist_service.get_realtime_stats",
            new_callable=AsyncMock,
            return_value={"call_id": "c1", "duration_seconds": 15},
        ) as mock_stats:
            resp = client.get("/ai-assist/realtime/c1")
        assert resp.status_code == 200
        assert resp.json()["call_id"] == "c1"
        mock_stats.assert_awaited_once_with("c1")
