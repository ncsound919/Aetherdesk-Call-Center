"""Comprehensive tests for database refactor — services, errors, and user journey."""
import asyncio
import json
import os
import sqlite3
import sys
import time
import uuid
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDatabaseConfig(unittest.TestCase):
    def test_db_config_constants(self):
        from apps.api.services.db_config import USE_POSTGRES, SQLITE_PATH
        self.assertIn("aetherdesk.db", SQLITE_PATH)
        self.assertFalse(USE_POSTGRES)

    def test_sqlite_path_exists(self):
        from apps.api.services.db_config import SQLITE_PATH
        self.assertTrue(os.path.exists(SQLITE_PATH), f"DB not found at {SQLITE_PATH}")


class TestDatabaseErrors(unittest.TestCase):
    def test_error_hierarchy(self):
        from apps.api.services.db_errors import DatabaseError, NotFoundError, PoolNotAvailableError
        self.assertTrue(issubclass(NotFoundError, DatabaseError))
        self.assertTrue(issubclass(PoolNotAvailableError, DatabaseError))

    def test_not_found_error_message(self):
        from apps.api.services.db_errors import NotFoundError
        err = NotFoundError("tenant", "t-123")
        self.assertIn("t-123", str(err))
        self.assertIn("tenant", str(err))
        self.assertEqual(err.detail, {"resource": "tenant", "id": "t-123"})

    def test_pool_unavailable_error(self):
        from apps.api.services.db_errors import PoolNotAvailableError
        err = PoolNotAvailableError()
        self.assertEqual(str(err), "Database pool not available")

    def test_database_error_with_detail(self):
        from apps.api.services.db_errors import DatabaseError
        err = DatabaseError("oops", {"code": 42})
        self.assertEqual(err.message, "oops")
        self.assertEqual(err.detail, {"code": 42})


class TestTranscriptStore(unittest.TestCase):
    def setUp(self):
        from apps.api.services.transcript_store import TranscriptStore
        self.store = TranscriptStore(max_calls=100, max_transcripts_per_call=50, stale_ttl=3600)

    def test_store_and_get_transcript(self):
        session_id = "test-session-1"
        entry = {"role": "user", "content": "Hello"}
        self.store.add_transcript(session_id, entry)
        transcript = self.store.get_transcripts(session_id)
        self.assertEqual(len(transcript), 1)
        self.assertEqual(transcript[0]["content"], "Hello")

    def test_append_transcript(self):
        session_id = "test-session-2"
        self.store.add_transcript(session_id, {"role": "user", "content": "Hi"})
        self.store.add_transcript(session_id, {"role": "assistant", "content": "Welcome"})
        transcript = self.store.get_transcripts(session_id)
        self.assertEqual(len(transcript), 2)

    def test_get_nonexistent_session(self):
        result = self.store.get_transcripts("no-such-session")
        self.assertEqual(result, [])

    def test_cleanup(self):
        session_id = "test-session-3"
        self.store.add_transcript(session_id, {"role": "user", "content": "X"})
        self.store.cleanup(session_id)
        result = self.store.get_transcripts(session_id)
        self.assertEqual(result, [])

    def test_get_or_create(self):
        session_id = "test-session-4"
        result = self.store.get_or_create(session_id)
        self.assertEqual(result, [])
        self.store.add_transcript(session_id, {"role": "user", "content": "A"})
        result2 = self.store.get_or_create(session_id)
        self.assertEqual(len(result2), 1)

    def test_touch(self):
        session_id = "test-session-5"
        self.store.add_transcript(session_id, {"role": "user", "content": "X"})
        self.store.touch(session_id)
        transcript = self.store.get_transcripts(session_id)
        self.assertEqual(len(transcript), 1)

    def test_large_transcript(self):
        session_id = "large-session"
        max_n = self.store._max_per_call
        for i in range(max_n):
            self.store.add_transcript(session_id, {"role": "user", "content": f"msg-{i}"})
        transcript = self.store.get_transcripts(session_id)
        self.assertEqual(len(transcript), max_n)

    def test_idempotent_cleanup_missing(self):
        self.store.cleanup("never-existed")
        self.store.cleanup("never-existed")


class TestVoiceProfileStore(unittest.TestCase):
    def setUp(self):
        from apps.api.services.voice_profile_store import VoiceProfileStore
        self.store = VoiceProfileStore(max_profiles=100)

    def test_put_and_get(self):
        voice_id = "voice-1"
        profile_data = {"voice_id": "elevenlabs-abc", "name": "test-voice"}
        self.store.put(voice_id, profile_data)
        result = self.store.get(voice_id)
        self.assertEqual(result, profile_data)

    def test_get_nonexistent(self):
        result = self.store.get("no-such-voice")
        self.assertIsNone(result)

    def test_get_copy(self):
        voice_id = "voice-copy"
        self.store.put(voice_id, {"name": "original"})
        result = self.store.get_copy(voice_id)
        self.assertEqual(result, {"name": "original"})
        result["name"] = "mutated"
        original = self.store.get(voice_id)
        self.assertEqual(original["name"], "original")

    def test_delete(self):
        voice_id = "voice-del"
        self.store.put(voice_id, {"voice": "data"})
        self.assertTrue(self.store.delete(voice_id))
        self.assertIsNone(self.store.get(voice_id))

    def test_delete_nonexistent(self):
        self.assertFalse(self.store.delete("never-existed"))

    def test_contains(self):
        voice_id = "voice-contains"
        self.assertFalse(self.store.contains(voice_id))
        self.store.put(voice_id, {"x": 1})
        self.assertTrue(self.store.contains(voice_id))

    def test_list_all(self):
        self.store.put("v1", {"name": "one", "language": "en"})
        self.store.put("v2", {"name": "two", "language": "fr"})
        items = self.store.list_all()
        self.assertEqual(len(items), 2)

    def test_overwrite(self):
        voice_id = "voice-ovw"
        self.store.put(voice_id, {"version": 1})
        self.store.put(voice_id, {"version": 2})
        result = self.store.get(voice_id)
        self.assertEqual(result["version"], 2)

    def test_multiple_profiles(self):
        for i in range(10):
            self.store.put(f"profile-{i}", {"idx": i})
        self.assertEqual(len(self.store.list_all()), 10)

    def test_items_snapshot(self):
        self.store.put("k1", {"a": 1})
        self.store.put("k2", {"b": 2})
        snapshot = self.store.items_snapshot()
        self.assertEqual(len(snapshot), 2)


class TestInMemoryQueue(unittest.TestCase):
    def setUp(self):
        from apps.api.services.queue import InMemoryQueue
        self.q = InMemoryQueue()

    def test_lpush_rpop(self):
        self.q.lpush("queue:test", json.dumps({"id": 1}))
        result = self.q.rpop("queue:test")
        self.assertIsNotNone(result)
        self.assertEqual(json.loads(result)["id"], 1)

    def test_rpop_empty(self):
        result = self.q.rpop("queue:empty")
        self.assertIsNone(result)

    def test_lrange(self):
        key = "queue:test-lr"
        for i in range(3):
            self.q.lpush(key, json.dumps({"n": i}))
        items = self.q.lrange(key, 0, 2)
        self.assertEqual(len(items), 3)

    def test_rpush(self):
        key = "queue:test-rp"
        self.q.rpush(key, json.dumps({"x": 1}))
        self.q.rpush(key, json.dumps({"x": 2}))
        self.assertEqual(len(self.q.lrange(key, 0, -1)), 2)

    def test_get_setex(self):
        self.q.setex("session:abc", 300, json.dumps({"hello": "world"}))
        result = self.q.get("session:abc")
        self.assertEqual(json.loads(result)["hello"], "world")

    def test_get_missing(self):
        result = self.q.get("session:missing")
        self.assertIsNone(result)

    def test_exists(self):
        self.q.setex("session:exists-test", 300, "val")
        self.assertTrue(self.q.exists("session:exists-test"))
        self.assertFalse(self.q.exists("session:no-exists"))

    def test_delete(self):
        self.q.setex("session:del-test", 300, "val")
        self.assertEqual(self.q.delete("session:del-test"), 1)
        self.assertFalse(self.q.exists("session:del-test"))

    def test_ping(self):
        self.assertTrue(self.q.ping())

    def test_fifo_order(self):
        key = "queue:fifo"
        self.q.lpush(key, json.dumps({"n": 1}))
        self.q.lpush(key, json.dumps({"n": 2}))
        self.q.lpush(key, json.dumps({"n": 3}))
        self.assertEqual(json.loads(self.q.rpop(key))["n"], 1)
        self.assertEqual(json.loads(self.q.rpop(key))["n"], 2)
        self.assertEqual(json.loads(self.q.rpop(key))["n"], 3)

    def test_lifo_order(self):
        key = "queue:lifo"
        self.q.lpush(key, json.dumps({"n": 1}))
        self.q.lpush(key, json.dumps({"n": 2}))
        self.q.lpush(key, json.dumps({"n": 3}))
        items = self.q.lrange(key, 0, 2)
        self.assertEqual(len(items), 3)
        self.assertEqual(json.loads(items[0])["n"], 3)


class TestQueueManager(unittest.TestCase):
    def setUp(self):
        from apps.api.services.queue import QueueManager, InMemoryQueue
        mock_redis = MagicMock()
        mock_redis.ping.return_value = False
        self.qm = QueueManager(mock_redis, use_fallback=True)
        self.in_mem = InMemoryQueue()

    def test_enqueue_and_peek(self):
        self.qm.enqueue("test-q", {"session_id": "sess-1", "data": "hello"})
        items = self.qm.peek("test-q", 10)
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]["session_id"], "sess-1")

    def test_claim(self):
        self.qm.enqueue("claim-q", {"session_id": "sess-c"})
        item = self.qm.claim("claim-q", "agent-1")
        self.assertIsNotNone(item)
        self.assertEqual(item["session_id"], "sess-c")
        self.assertEqual(item["claimed_by"], "agent-1")

    def test_claim_empty(self):
        item = self.qm.claim("empty-q", "agent-1")
        self.assertIsNone(item)

    def test_session_set_and_get(self):
        self.qm.session_set("session-key", {"hello": "world"})
        result = self.qm.session_get("session-key")
        self.assertEqual(result["hello"], "world")

    def test_session_get_missing(self):
        result = self.qm.session_get("no-such-key")
        self.assertIsNone(result)

    def test_session_delete(self):
        self.qm.session_set("del-me", {"val": 1})
        self.qm.session_delete("del-me")
        self.assertIsNone(self.qm.session_get("del-me"))

    def test_idempotent_session_delete(self):
        self.qm.session_delete("never-existed")


class TestDatabaseLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from apps.api.services.database import init_sqlite_schema
        init_sqlite_schema()

    def setUp(self):
        self.tenant_id = None
        self.agent_id = None

    def _create_tenant(self):
        from apps.api.services.database import create_tenant
        slug = f"test-{uuid.uuid4().hex[:8]}"
        result = asyncio.run(create_tenant(
            name=f"Test {slug}", email=f"{slug}@test.com", slug=slug,
            phone="+1234567890", plan_id="starter", settings={"tz": "UTC"},
            gdpr_consent=True
        ))
        self.assertIn("id", result)
        self.tenant_id = result["id"]
        return result

    def _create_agent(self, agent_type="voice"):
        from apps.api.services.database import create_agent
        agent_name = f"agent-{uuid.uuid4().hex[:8]}"
        result = asyncio.run(create_agent(
            tenant_id=self.tenant_id, name=agent_name, display_name=agent_name,
            agent_type=agent_type, skills=["general"], config={"language": "en"},
            phone="+1987654321"
        ))
        self.assertIn("id", result)
        self.agent_id = result["id"]
        return result

    def _create_call(self):
        from apps.api.services.database import create_call_session
        call_id = f"call-{uuid.uuid4().hex[:8]}"
        result = asyncio.run(create_call_session(
            tenant_id=self.tenant_id, agent_id=self.agent_id,
            caller_number="+15551234567",
        ))
        self.assertIn("id", result)
        return result

    def test_tenant_crud(self):
        from apps.api.services.database import create_tenant, get_tenant_db, get_tenant_by_api_key
        tenant = self._create_tenant()
        tenant_id = tenant["id"]

        fetched = asyncio.run(get_tenant_db(tenant_id))
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["email"], tenant["email"])

        fetched_by_key = asyncio.run(get_tenant_by_api_key(tenant["api_key"]))
        self.assertIsNotNone(fetched_by_key)
        self.assertEqual(fetched_by_key["id"], tenant_id)

    def test_nonexistent_tenant_returns_none(self):
        from apps.api.services.database import get_tenant_db
        result = asyncio.run(get_tenant_db("no-such-tenant"))
        self.assertIsNone(result)

    def test_agent_crud(self):
        from apps.api.services.database import create_agent, get_agent_db
        self._create_tenant()
        agent = self._create_agent()

        fetched = asyncio.run(get_agent_db(self.agent_id))
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], self.agent_id)
        self.assertEqual(fetched["tenant_id"], self.tenant_id)

    def test_nonexistent_agent_returns_none(self):
        from apps.api.services.database import get_agent_db
        result = asyncio.run(get_agent_db("no-such-agent"))
        self.assertIsNone(result)

    def test_call_session_crud(self):
        from apps.api.services.database import create_call_session, get_call_session, update_call_status
        self._create_tenant()
        self._create_agent()
        call = self._create_call()
        session_id = call["id"]

        fetched = asyncio.run(get_call_session(session_id))
        self.assertIsNotNone(fetched)
        self.assertIn(fetched["call_status"], ("ringing", "in_progress"))

        asyncio.run(update_call_status(session_id, "completed"))
        fetched2 = asyncio.run(get_call_session(session_id))
        self.assertEqual(fetched2["call_status"], "completed")

    def test_nonexistent_call_returns_none(self):
        from apps.api.services.database import get_call_session
        result = asyncio.run(get_call_session("no-such-call"))
        self.assertIsNone(result)

    def test_list_calls(self):
        from apps.api.services.database import list_calls
        self._create_tenant()
        self._create_agent()
        self._create_call()
        calls = asyncio.run(list_calls(self.tenant_id))
        self.assertGreaterEqual(len(calls), 1)

    def test_enqueue_dequeue(self):
        from apps.api.services.database import enqueue_call, dequeue_call
        self._create_tenant()
        asyncio.run(enqueue_call(self.tenant_id, "+15551234567"))
        dequeued = asyncio.run(dequeue_call(self.tenant_id, "any-agent"))
        self.assertIsNotNone(dequeued)

    def test_usage_stats(self):
        from apps.api.services.database import get_usage_stats
        self._create_tenant()
        stats = asyncio.run(get_usage_stats(self.tenant_id))
        self.assertIsNotNone(stats)

    def test_audit_log(self):
        from apps.api.services.database import log_audit_event
        self._create_tenant()
        asyncio.run(log_audit_event(
            tenant_id=self.tenant_id, user_id="test-user",
            action="test_action", resource_type="test",
            resource_id="res-1"
        ))

    def test_full_user_journey(self):
        from apps.api.services.database import (
            create_tenant, create_agent, create_call_session,
            get_tenant_db, get_agent_db, get_call_session,
            update_call_status, get_usage_stats,
        )
        slug = f"journey-{uuid.uuid4().hex[:8]}"
        tenant = asyncio.run(create_tenant(
            name="Journey Test", email=f"{slug}@test.com", slug=slug, gdpr_consent=True
        ))
        tid = tenant["id"]
        agent = asyncio.run(create_agent(
            tenant_id=tid, name="journey-agent", display_name="Journey Agent",
            agent_type="voice", skills=["general"], config={}, phone="+15551111111"
        ))
        aid = agent["id"]
        call = asyncio.run(create_call_session(
            tenant_id=tid, agent_id=aid, caller_number="+15552222222"
        ))
        sid = call["id"]

        asyncio.run(get_tenant_db(tid))
        asyncio.run(get_agent_db(aid))
        asyncio.run(get_call_session(sid))
        asyncio.run(update_call_status(sid, "completed"))
        stats = asyncio.run(get_usage_stats(tid))
        self.assertIsNotNone(stats)

    def test_duplicate_slug_raises_integrity_error(self):
        from apps.api.services.database import create_tenant
        slug = f"dup-{uuid.uuid4().hex[:8]}"
        asyncio.run(create_tenant(
            name="First", email=f"{slug}@test.com", slug=slug, gdpr_consent=True
        ))
        with self.assertRaises(sqlite3.IntegrityError):
            asyncio.run(create_tenant(
                name="Second", email=f"{slug}2@test.com", slug=slug, gdpr_consent=True
            ))


class TestDatabaseLayerEdgeCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from apps.api.services.database import init_sqlite_schema
        init_sqlite_schema()

    def test_get_tenant_settings(self):
        from apps.api.services.database import (get_tenant_settings_db,
                                                 update_tenant_settings_db, create_tenant)
        slug = f"settings-{uuid.uuid4().hex[:8]}"
        tenant = asyncio.run(create_tenant(
            name="Settings", email=f"{slug}@test.com", slug=slug, gdpr_consent=True
        ))
        asyncio.run(update_tenant_settings_db(tenant["id"], {"api_feeds": "[]"}))
        settings = asyncio.run(get_tenant_settings_db(tenant["id"]))
        self.assertIsNotNone(settings)
        self.assertEqual(settings["tenant_id"], tenant["id"])

    def test_update_tenant_settings(self):
        from apps.api.services.database import update_tenant_settings_db, create_tenant
        slug = f"upset-{uuid.uuid4().hex[:8]}"
        tenant = asyncio.run(create_tenant(
            name="UpSet", email=f"{slug}@test.com", slug=slug, gdpr_consent=True
        ))
        result = asyncio.run(update_tenant_settings_db(tenant["id"], {"auto_mode_enabled": 1}))
        self.assertIsNone(result)

    def test_verify_tenant_api_key(self):
        from apps.api.services.database import verify_tenant_api_key, create_tenant
        slug = f"vkey-{uuid.uuid4().hex[:8]}"
        tenant = asyncio.run(create_tenant(
            name="VKey", email=f"{slug}@test.com", slug=slug, gdpr_consent=True
        ))
        result = asyncio.run(verify_tenant_api_key(tenant["id"], tenant["api_key"]))
        self.assertTrue(result)

    def test_list_tenants(self):
        from apps.api.services.database import list_tenants_db
        tenants = asyncio.run(list_tenants_db())
        self.assertGreaterEqual(len(tenants), 0)

    def test_list_agents(self):
        from apps.api.services.database import list_agents, create_tenant, create_agent
        slug = f"lagent-{uuid.uuid4().hex[:8]}"
        tenant = asyncio.run(create_tenant(
            name="LAgent", email=f"{slug}@test.com", slug=slug, gdpr_consent=True
        ))
        asyncio.run(create_agent(
            tenant_id=tenant["id"], name="la-1", display_name="LA1",
            agent_type="voice", skills=["general"], config={}, phone="+15551111111"
        ))
        agents = asyncio.run(list_agents(tenant["id"]))
        self.assertGreaterEqual(len(agents), 1)

    def test_get_available_agents(self):
        from apps.api.services.database import get_available_agents, create_tenant, create_agent
        slug = f"avail-{uuid.uuid4().hex[:8]}"
        tenant = asyncio.run(create_tenant(
            name="Avail", email=f"{slug}@test.com", slug=slug, gdpr_consent=True
        ))
        agents = asyncio.run(get_available_agents(tenant["id"]))
        self.assertIsInstance(agents, list)


class TestEncryptionUtils(unittest.TestCase):
    def test_encrypt_none(self):
        from apps.api.services.database import encrypt_val
        result = encrypt_val(None)
        self.assertIsNone(result)

    def test_decrypt_none(self):
        from apps.api.services.database import decrypt_val
        result = decrypt_val(None)
        self.assertIsNone(result)

    def test_encrypt_empty_string(self):
        from apps.api.services.database import encrypt_val
        result = encrypt_val("")
        self.assertIsNotNone(result)

    def test_encrypt_string_returns_string(self):
        from apps.api.services.database import encrypt_val
        result = encrypt_val("hello")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)

    def test_decrypt_roundtrip(self):
        from apps.api.services.database import encrypt_val, decrypt_val
        original = "sensitive-data-123"
        encrypted = encrypt_val(original)
        decrypted = decrypt_val(encrypted)
        self.assertEqual(decrypted, original)

    def test_decrypt_garbage_returns_input_when_unencrypted(self):
        from apps.api.services.database import decrypt_val
        result = decrypt_val("not-valid-encrypted-data")
        self.assertEqual(result, "not-valid-encrypted-data")


class TestWebhookAndOrders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from apps.api.services.database import init_sqlite_schema
        init_sqlite_schema()

    def test_lookup_nonexistent_invoice(self):
        from apps.api.services.database import lookup_invoice_db
        result = asyncio.run(lookup_invoice_db("FAKE-000"))
        self.assertIsNone(result)

    def test_get_nonexistent_order(self):
        from apps.api.services.database import get_order_status_db
        result = asyncio.run(get_order_status_db("FAKE-000"))
        self.assertIsNone(result)

    def test_get_webhook_url(self):
        from apps.api.services.database import get_webhook_url_db, create_tenant
        slug = f"wh-{uuid.uuid4().hex[:8]}"
        tenant = asyncio.run(create_tenant(
            name="Webhook", email=f"{slug}@test.com", slug=slug, gdpr_consent=True
        ))
        result = asyncio.run(get_webhook_url_db(tenant["id"]))
        self.assertIsNone(result)

    def test_process_approval(self):
        from apps.api.services.database import process_approval_db, create_tenant
        slug = f"pa-{uuid.uuid4().hex[:8]}"
        tenant = asyncio.run(create_tenant(
            name="ProcApp", email=f"{slug}@test.com", slug=slug, gdpr_consent=True
        ))
        asyncio.run(process_approval_db("approval-1", "approved", tenant["id"]))

    def test_get_pending_approvals(self):
        from apps.api.services.database import get_pending_approvals_db, create_tenant
        slug = f"pa2-{uuid.uuid4().hex[:8]}"
        tenant = asyncio.run(create_tenant(
            name="PendingApp", email=f"{slug}@test.com", slug=slug, gdpr_consent=True
        ))
        approvals = asyncio.run(get_pending_approvals_db(tenant["id"]))
        self.assertIsInstance(approvals, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
