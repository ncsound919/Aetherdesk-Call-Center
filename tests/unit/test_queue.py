import json
import time
import pytest
from apps.api.services.queue import InMemoryQueue, QueueManager, QUEUE_KEY, SESSION_KEY


class TestInMemoryQueue:
    def setup_method(self):
        self.q = InMemoryQueue()

    def test_lpush_and_rpop(self):
        self.q.lpush("q:test", "a")
        self.q.lpush("q:test", "b")
        assert self.q.rpop("q:test") == "a"
        assert self.q.rpop("q:test") == "b"
        assert self.q.rpop("q:test") is None

    def test_rpush_and_lrange(self):
        self.q.rpush("q:test", "x")
        self.q.rpush("q:test", "y")
        items = self.q.lrange("q:test", 0, -1)
        assert items == ["x", "y"]

    def test_lrange_with_bounds(self):
        self.q.rpush("q:test", "a")
        self.q.rpush("q:test", "b")
        self.q.rpush("q:test", "c")
        assert self.q.lrange("q:test", 0, 1) == ["a", "b"]
        assert self.q.lrange("q:test", 1, 2) == ["b", "c"]

    def test_lrange_empty_queue(self):
        assert self.q.lrange("nonexistent", 0, -1) == []

    def test_rpop_empty_queue(self):
        assert self.q.rpop("nonexistent") is None

    def test_setex_and_get(self):
        self.q.setex("session:abc", 300, '{"user": "test"}')
        assert self.q.get("session:abc") == '{"user": "test"}'

    def test_get_missing(self):
        assert self.q.get("nosession") is None

    def test_exists(self):
        self.q.setex("session:abc", 300, "x")
        assert self.q.exists("session:abc") is True
        assert self.q.exists("session:nope") is False

    def test_delete_removes_session_and_queue(self):
        self.q.setex("session:abc", 300, "x")
        self.q.rpush("q:test", "y")
        assert self.q.delete("session:abc") >= 1
        assert self.q.get("session:abc") is None
        assert self.q.delete("q:test") >= 1
        assert self.q.lrange("q:test", 0, -1) == []

    def test_delete_unknown_key(self):
        assert self.q.delete("nothing") == 0

    def test_ping(self):
        assert self.q.ping() is True

    def test_lpush_max_items(self):
        for i in range(10001):
            self.q.lpush("q:big", str(i))
        assert len(self.q.lrange("q:big", 0, -1)) == 10000

    def test_lpush_and_rpop_fifo_order(self):
        self.q.lpush("q:test", "first")
        self.q.lpush("q:test", "second")
        self.q.lpush("q:test", "third")
        assert self.q.rpop("q:test") == "first"


class TestQueueManager:
    def setup_method(self):
        self.imq = InMemoryQueue()
        self.qm = QueueManager(redis_client=None, use_fallback=True, in_memory_queue=self.imq)

    def test_enqueue_and_peek(self):
        self.qm.enqueue("inbound", {"session_id": "s1", "caller": "+1555"})
        items = self.qm.peek("inbound")
        assert len(items) == 1
        assert items[0]["caller"] == "+1555"

    def test_enqueue_adds_timestamp(self):
        self.qm.enqueue("inbound", {"session_id": "s1"})
        item = self.qm.peek("inbound")[0]
        assert "created_ts" in item

    def test_claim_returns_item(self):
        self.qm.enqueue("inbound", {"session_id": "s1", "caller": "+1555"})
        item = self.qm.claim("inbound", "agent-1")
        assert item is not None
        assert item["claimed_by"] == "agent-1"
        assert "claimed_ts" in item

    def test_claim_empty_queue(self):
        assert self.qm.claim("empty", "agent-1") is None

    def test_session_set_and_get(self):
        self.qm.session_set("sid-1", {"user": "alice"})
        data = self.qm.session_get("sid-1")
        assert data == {"user": "alice"}

    def test_session_get_missing(self):
        assert self.qm.session_get("nosession") is None

    def test_session_delete(self):
        self.qm.session_set("sid-1", {"user": "alice"})
        self.qm.session_delete("sid-1")
        assert self.qm.session_get("sid-1") is None

    def test_peek_multiple_items(self):
        self.qm.enqueue("inbound", {"session_id": "s1"})
        self.qm.enqueue("inbound", {"session_id": "s2"})
        self.qm.enqueue("inbound", {"session_id": "s3"})
        items = self.qm.peek("inbound", n=2)
        assert len(items) == 2
