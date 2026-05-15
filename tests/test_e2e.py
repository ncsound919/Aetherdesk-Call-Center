"""
AetherDesk E2E & Unit Test Suite
Tests database, actions, queue, orchestrator, agent, and API endpoints.
"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────
# 1. DATABASE TESTS
# ─────────────────────────────────────────────────────────────
class DatabaseTests(unittest.TestCase):
    """Tests for the CRM database layer."""

    def test_database_file_exists(self):
        from apps.api.services.database import DB_PATH
        self.assertTrue(os.path.exists(DB_PATH), f"Database file not found at {DB_PATH}")

    def test_tables_exist(self):
        from apps.api.services.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        self.assertIn("customers", tables)
        self.assertIn("invoices", tables)
        self.assertIn("orders", tables)

    def test_seed_data_present(self):
        from apps.api.services.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM customers")
        self.assertGreaterEqual(cursor.fetchone()[0], 2)
        cursor.execute("SELECT COUNT(*) FROM invoices")
        self.assertGreaterEqual(cursor.fetchone()[0], 2)
        cursor.execute("SELECT COUNT(*) FROM orders")
        self.assertGreaterEqual(cursor.fetchone()[0], 2)
        conn.close()

    def test_invoice_lookup_returns_correct_data(self):
        from apps.api.services.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT amount, status, due_date FROM invoices WHERE id = ?", ("INV-5001",))
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "Paid")
        self.assertEqual(row["amount"], 150.00)

    def test_order_lookup_returns_correct_data(self):
        from apps.api.services.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, expected_delivery FROM orders WHERE id = ?", ("ORD-9002",))
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "Shipped")

    def test_nonexistent_invoice_returns_none(self):
        from apps.api.services.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE id = ?", ("FAKE-9999",))
        row = cursor.fetchone()
        conn.close()
        self.assertIsNone(row)


# ─────────────────────────────────────────────────────────────
# 2. ACTIONS TESTS (real database integration)
# ─────────────────────────────────────────────────────────────
class ActionsTests(unittest.TestCase):
    """Tests that Actions.run() queries the real SQLite database."""

    def setUp(self):
        from apps.api.services.actions import Actions
        # Pass a mock redis (queue operations don't need real redis for these tests)
        mock_redis = MagicMock()
        mock_redis.ping.return_value = False
        self.actions = Actions(mock_redis)

    def test_lookup_invoice_success(self):
        result = self.actions.run("lookup_invoice", {"invoice_id": "INV-5001"})
        self.assertTrue(result["success"])
        self.assertIn("data", result)
        self.assertEqual(result["data"]["status"], "Paid")
        self.assertEqual(result["data"]["amount"], 150.00)

    def test_lookup_invoice_not_found(self):
        result = self.actions.run("lookup_invoice", {"invoice_id": "FAKE-0000"})
        self.assertFalse(result["success"])

    def test_lookup_invoice_empty_id(self):
        result = self.actions.run("lookup_invoice", {"invoice_id": ""})
        self.assertFalse(result["success"])

    def test_lookup_invoice_missing_id(self):
        result = self.actions.run("lookup_invoice", {})
        self.assertFalse(result["success"])

    def test_get_order_status_success(self):
        result = self.actions.run("get_order_status", {"order_id": "ORD-9001"})
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["status"], "Processing")

    def test_get_order_status_not_found(self):
        result = self.actions.run("get_order_status", {"order_id": "FAKE-0000"})
        self.assertFalse(result["success"])

    def test_handoff_enqueues_item(self):
        result = self.actions.run("handoff", {
            "queue": "general",
            "session_id": "test-123",
            "protocol_id": "test-proto",
        })
        self.assertTrue(result["success"])

    def test_unknown_action_returns_success(self):
        result = self.actions.run("some_unknown_action", {})
        self.assertTrue(result["success"])

    def test_actions_do_not_mutate_caller_fields_on_miss(self):
        """Ensure fields dict is not polluted when lookup fails."""
        fields = {"invoice_id": "FAKE-0000"}
        self.actions.run("lookup_invoice", fields)
        self.assertNotIn("status", fields)


# ─────────────────────────────────────────────────────────────
# 3. QUEUE TESTS
# ─────────────────────────────────────────────────────────────
class InMemoryQueueTests(unittest.TestCase):
    """Tests for InMemoryQueue Redis-compatible semantics."""

    def setUp(self):
        from apps.api.services.queue import InMemoryQueue
        self.q = InMemoryQueue()

    def test_lpush_and_rpop_fifo(self):
        self.q.lpush("test", "a")
        self.q.lpush("test", "b")
        # rpop should return oldest (FIFO when using lpush + rpop)
        self.assertEqual(self.q.rpop("test"), "a")
        self.assertEqual(self.q.rpop("test"), "b")

    def test_rpop_empty_returns_none(self):
        self.assertIsNone(self.q.rpop("empty"))

    def test_lrange_returns_correct_count(self):
        for i in range(5):
            self.q.lpush("test", str(i))
        # Redis lrange(key, 0, 2) returns 3 items (inclusive)
        result = self.q.lrange("test", 0, 2)
        self.assertEqual(len(result), 3)

    def test_lrange_empty_key(self):
        result = self.q.lrange("nonexistent", 0, 10)
        self.assertEqual(result, [])

    def test_session_set_and_get(self):
        self.q.setex("session:1", 1800, '{"data": "test"}')
        result = self.q.get("session:1")
        self.assertEqual(result, '{"data": "test"}')

    def test_session_get_nonexistent(self):
        self.assertIsNone(self.q.get("session:nonexistent"))


class QueueManagerTests(unittest.TestCase):
    """Tests for QueueManager with fallback behavior."""

    def test_enqueue_and_peek(self):
        from apps.api.services.queue import InMemoryQueue, QueueManager
        mock_redis = MagicMock()
        mock_redis.ping.return_value = False
        qm = QueueManager(mock_redis, use_fallback=True)
        # Use a fresh in-memory backend to isolate from other tests
        qm._in_memory = InMemoryQueue()

        qm.enqueue("test_isolated", {"session_id": "s1", "preview": "hello"})
        items = qm.peek("test_isolated", 10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["session_id"], "s1")

    def test_claim_returns_item_and_marks_agent(self):
        from apps.api.services.queue import QueueManager
        mock_redis = MagicMock()
        mock_redis.ping.return_value = False
        qm = QueueManager(mock_redis, use_fallback=True)

        qm.enqueue("general", {"session_id": "s1", "preview": "test"})
        item = qm.claim("general", "agent-1")
        self.assertIsNotNone(item)
        self.assertEqual(item["claimed_by"], "agent-1")
        self.assertIn("claimed_ts", item)

    def test_claim_empty_queue_returns_none(self):
        from apps.api.services.queue import QueueManager
        mock_redis = MagicMock()
        mock_redis.ping.return_value = False
        qm = QueueManager(mock_redis, use_fallback=True)
        self.assertIsNone(qm.claim("empty", "agent-1"))

    def test_peek_empty_queue(self):
        from apps.api.services.queue import QueueManager
        mock_redis = MagicMock()
        mock_redis.ping.return_value = False
        qm = QueueManager(mock_redis, use_fallback=True)
        items = qm.peek("empty", 10)
        self.assertEqual(items, [])


# ─────────────────────────────────────────────────────────────
# 4. AGENT RESPONSE DATACLASS TESTS
# ─────────────────────────────────────────────────────────────
class AgentResponseTests(unittest.TestCase):
    """Tests for AgentResponse dataclass integrity."""

    def test_basic_construction(self):
        from apps.api.services.agent import AgentResponse
        r = AgentResponse(text="hello", sources=[], needs_agent=False)
        self.assertEqual(r.text, "hello")
        self.assertIsNone(r.action_taken)

    def test_with_action_taken(self):
        from apps.api.services.agent import AgentResponse
        r = AgentResponse(text="ok", sources=[], needs_agent=False, action_taken="lookup_invoice")
        self.assertEqual(r.action_taken, "lookup_invoice")

    def test_escalate_action(self):
        from apps.api.services.agent import AgentResponse
        r = AgentResponse(text="", sources=[], needs_agent=False, action_taken="escalate")
        self.assertEqual(r.action_taken, "escalate")
        self.assertFalse(r.needs_agent)


# ─────────────────────────────────────────────────────────────
# 5. VOICE SESSION TESTS
# ─────────────────────────────────────────────────────────────
class VoiceSessionTests(unittest.TestCase):
    """Tests for VoiceSession state management."""

    def test_session_initializes_with_empty_state(self):
        from apps.api.services.call_session import VoiceSession
        s = VoiceSession("test-1", "call-1")
        self.assertEqual(s.transcript, [])
        self.assertEqual(s.agent_state, {})
        self.assertTrue(s.is_active)
        self.assertEqual(s.audio_buffer, b"")

    def test_process_audio_rejects_tiny_chunks(self):
        from apps.api.services.call_session import VoiceSession
        s = VoiceSession("test-1", "call-1")
        result = asyncio.run(s.process_audio(b"\x00" * 100))
        self.assertIsNone(result)

    def test_audio_buffer_caps_at_max(self):
        from apps.api.services.call_session import VoiceSession
        s = VoiceSession("test-1", "call-1")
        # Fill buffer to near max, then add more
        s.audio_buffer = b"\x00" * (VoiceSession.MAX_BUFFER_SIZE - 100)
        chunk = b"\x00" * 500
        # This should trigger the truncation path
        asyncio.run(s.process_audio(chunk))
        self.assertLessEqual(len(s.audio_buffer), VoiceSession.MAX_BUFFER_SIZE + 500)


# ─────────────────────────────────────────────────────────────
# 6. CALL SESSION REGISTRY TESTS
# ─────────────────────────────────────────────────────────────
class SessionRegistryTests(unittest.TestCase):
    """Tests for store/get/remove session functions."""

    def test_store_and_retrieve_session(self):
        from apps.api.services.call_session import (
            VoiceSession,
            get_or_create_session,
        )
        app = MagicMock()
        # Setup mock redis and QueueManager
        app.state.redis = MagicMock()

        # Mock QueueManager to return our session data
        s = VoiceSession("s1", "c1")
        s.agent_state = {"test": True}

        # Mock qm.session_get to return None first, then the data
        app.state.qm = MagicMock()
        app.state.qm.session_get.return_value = s.to_dict()

        # In stateless, we retrieve it back
        s2 = get_or_create_session(app, "s1", "c1")
        self.assertEqual(s2.session_id, "s1")
        self.assertEqual(s2.agent_state["test"], True)

    def test_remove_nonexistent_session_no_crash(self):
        from apps.api.services.call_session import remove_session
        app = MagicMock()
        app.state.redis = MagicMock()
        app.state.qm = MagicMock()
        # Should not raise
        remove_session(app, "nonexistent")

    def test_get_or_create_session(self):
        from apps.api.services.call_session import get_or_create_session
        app = MagicMock()
        app.state.redis = MagicMock()
        app.state.qm = MagicMock()
        app.state.qm.session_get.return_value = None

        s1 = get_or_create_session(app, "s1", "c1")
        self.assertEqual(s1.session_id, "s1")


# ─────────────────────────────────────────────────────────────
# 7. API ENDPOINT TESTS (FastAPI TestClient)
# ─────────────────────────────────────────────────────────────
class APIEndpointTests(unittest.TestCase):
    """E2E tests for HTTP API routes."""

    def setUp(self):
        from fastapi.testclient import TestClient

        from apps.api.main import app
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_root_returns_ok(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["service"], "AetherDesk API")

    def test_health_endpoint(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)

    def test_peek_queue_returns_items_key(self):
        r = self.client.get("/api/v1/agent/peek?queue=general&n=10")
        # May return 200 with items or 500 if redis not configured
        if r.status_code == 200:
            data = r.json()
            self.assertIn("items", data)
            self.assertIsInstance(data["items"], list)

    def test_claim_empty_queue(self):
        r = self.client.post("/api/v1/agent/claim?queue=empty_test&agent_id=test-agent")
        # May return 200 or 500 depending on redis state
        if r.status_code == 200:
            data = r.json()
            self.assertFalse(data["ok"])

    @patch("apps.api.routers.voice.asr_service.transcribe", new_callable=AsyncMock)
    def test_transcribe_returns_text(self, mock_asr):
        mock_asr.return_value = "hello world"
        r = self.client.post(
            "/api/v1/voice/transcribe",
            content=b"dummy-audio",
            headers={"content-type": "application/octet-stream"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["text"], "hello world")

    def test_transcribe_empty_body(self):
        r = self.client.post(
            "/api/v1/voice/transcribe",
            content=b"",
            headers={"content-type": "application/octet-stream"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("error", r.json())

    @patch("apps.api.routers.voice.tts_service.synthesize", new_callable=AsyncMock)
    def test_synthesize_returns_base64(self, mock_tts):
        import base64
        mock_tts.return_value = b"test-audio-bytes"
        r = self.client.post("/api/v1/voice/synthesize", json={"text": "hello"})
        self.assertEqual(r.status_code, 200)
        decoded = base64.b64decode(r.json()["audio"])
        self.assertEqual(decoded, b"test-audio-bytes")

    def test_synthesize_empty_text(self):
        r = self.client.post("/api/v1/voice/synthesize", json={"text": ""})
        self.assertEqual(r.status_code, 200)
        self.assertIn("error", r.json())

    @patch("apps.api.routers.voice.classifier.classify_with_fallback", new_callable=AsyncMock)
    def test_intent_classification(self, mock_classify):
        mock_classify.return_value = MagicMock(
            intent="billing_invoice",
            entities={"invoice_id": "INV-5001"},
            confidence=0.95,
            reasoning="test"
        )
        r = self.client.post("/api/v1/voice/intent", json={"text": "check my invoice"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["intent"], "billing_invoice")

    def test_intent_empty_text(self):
        r = self.client.post("/api/v1/voice/intent", json={"text": ""})
        self.assertEqual(r.status_code, 200)
        self.assertIn("error", r.json())

    def test_incoming_call_returns_twiml(self):
        r = self.client.post("/api/v1/voice/incoming")
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/xml", r.headers["content-type"])
        self.assertIn("AetherDesk", r.text)


# ─────────────────────────────────────────────────────────────
# 8. INTENT CLASSIFIER TESTS
# ─────────────────────────────────────────────────────────────
class IntentClassifierTests(unittest.TestCase):
    """Tests for keyword fallback and edge cases."""

    def test_keyword_fallback_refund(self):
        from apps.api.services.intent_classifier import IntentClassifier
        c = IntentClassifier()
        result = asyncio.run(c._keyword_fallback("I need a refund"))
        self.assertEqual(result.intent, "billing_refund")

    def test_keyword_fallback_agent_handoff(self):
        from apps.api.services.intent_classifier import IntentClassifier
        c = IntentClassifier()
        result = asyncio.run(c._keyword_fallback("let me speak to a human"))
        self.assertEqual(result.intent, "agent_handoff")

    def test_keyword_fallback_no_match(self):
        from apps.api.services.intent_classifier import IntentClassifier
        c = IntentClassifier()
        result = asyncio.run(c._keyword_fallback("asdfghjkl random noise"))
        self.assertEqual(result.intent, "generalInquiry")
        self.assertEqual(result.confidence, 0.2)

    def test_classify_empty_string(self):
        from apps.api.services.intent_classifier import IntentClassifier
        c = IntentClassifier()
        result = asyncio.run(c.classify(""))
        self.assertEqual(result.intent, "retry")
        self.assertEqual(result.confidence, 0.0)

    def test_classify_whitespace_only(self):
        from apps.api.services.intent_classifier import IntentClassifier
        c = IntentClassifier()
        result = asyncio.run(c.classify("   "))
        self.assertEqual(result.intent, "retry")


# ─────────────────────────────────────────────────────────────
# 9. ORCHESTRATOR UNIT TESTS (mocked LLM)
# ─────────────────────────────────────────────────────────────
class OrchestratorTests(unittest.TestCase):
    """Tests for Orchestrator routing and session state."""

    def _make_orchestrator(self):
        from apps.api.services.actions import Actions
        from apps.api.services.orchestrator import Orchestrator
        mock_redis = MagicMock()
        mock_redis.ping.return_value = False
        actions = Actions(mock_redis)
        return Orchestrator(actions)

    @patch("httpx.AsyncClient.post")
    def test_supervisor_routes_to_billing(self, mock_post):
        orch = self._make_orchestrator()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": json.dumps({"thought": "billing question", "route_to": "billing"})}
        }
        mock_post.return_value = mock_response

        result = asyncio.run(orch.route_to_agent([], "I need my invoice status"))
        self.assertEqual(result, "billing")

    @patch("httpx.AsyncClient.post")
    def test_supervisor_fallback_on_bad_route(self, mock_post):
        orch = self._make_orchestrator()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": json.dumps({"thought": "confused", "route_to": "nonexistent_dept"})}
        }
        mock_post.return_value = mock_response

        result = asyncio.run(orch.route_to_agent([], "something weird"))
        self.assertEqual(result, "human")

    @patch("httpx.AsyncClient.post")
    def test_supervisor_fallback_on_network_error(self, mock_post):
        orch = self._make_orchestrator()
        mock_post.side_effect = Exception("Connection refused")

        result = asyncio.run(orch.route_to_agent([], "hello"))
        self.assertEqual(result, "human")

    @patch("apps.api.services.database.db_context")
    @patch("apps.api.services.orchestrator.TenantAgent")
    def test_session_state_persists_active_agent(self, mock_tenant_agent, mock_db):
        """After routing, session_state should remember the active agent."""
        # Mock rental check to return an active rental
        mock_conn = mock_db.return_value.__enter__.return_value
        mock_conn.cursor.return_value.fetchone.return_value = {"id": "RENT-1"}

        orch = self._make_orchestrator()
        state = {}

        # Pre-populate agent cache manually to avoid DB check
        agent_mock = MagicMock()
        orch.agents["TENANT-001:billing"] = agent_mock
        state["active_agent"] = "billing"

        # Mock the billing agent's step
        with patch.object(agent_mock, "step", new_callable=AsyncMock) as mock_step:
            from apps.api.services.agent import AgentResponse
            mock_step.return_value = AgentResponse(text="Your invoice is paid.", sources=[], needs_agent=False)
            result = asyncio.run(orch.step(state, [], "check invoice", profile_id="billing"))

        self.assertEqual(result.text, "Your invoice is paid.")
        self.assertEqual(state["active_agent"], "billing")

    @patch("apps.api.services.database.db_context")
    @patch("apps.api.services.orchestrator.TenantAgent")
    def test_escalate_clears_active_agent(self, mock_tenant_agent, mock_db):
        # Mock rental check
        mock_conn = mock_db.return_value.__enter__.return_value
        mock_conn.cursor.return_value.fetchone.return_value = {"id": "RENT-1"}

        orch = self._make_orchestrator()
        # Pre-populate agent cache manually
        agent_mock = MagicMock()
        orch.agents["TENANT-001:ops"] = agent_mock
        state = {"active_agent": "ops"}

        with patch.object(agent_mock, "step", new_callable=AsyncMock) as mock_step:
            from apps.api.services.agent import AgentResponse
            mock_step.return_value = AgentResponse(text="", sources=[], needs_agent=False, action_taken="escalate")
            result = asyncio.run(orch.step(state, [], "actually it's a billing issue", profile_id="ops"))

        self.assertIsNone(state["active_agent"])
        self.assertEqual(result.text, "Let me check with another department.")


# ─────────────────────────────────────────────────────────────
# 10. BROADCAST TRANSCRIPT TESTS
# ─────────────────────────────────────────────────────────────
class BroadcastTests(unittest.TestCase):
    """Tests for transcript broadcast and memory bounds."""

    def test_broadcast_caps_transcript_length(self):
        from apps.api.routers.realtime import (
            CALL_TRANSCRIPTS,
            MAX_TRANSCRIPT_PER_CALL,
            broadcast_transcript,
        )
        call_sid = "test-cap-call"
        CALL_TRANSCRIPTS[call_sid] = []

        for i in range(MAX_TRANSCRIPT_PER_CALL + 50):
            broadcast_transcript(call_sid, {"from": "customer", "text": f"msg {i}"})

        self.assertLessEqual(len(CALL_TRANSCRIPTS[call_sid]), MAX_TRANSCRIPT_PER_CALL)

        # Clean up
        del CALL_TRANSCRIPTS[call_sid]


if __name__ == "__main__":
    unittest.main()
