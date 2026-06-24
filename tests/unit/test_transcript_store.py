import time
import pytest
from unittest.mock import patch
from apps.api.services.transcript_store import TranscriptStore


class TestTranscriptStore:
    def setup_method(self):
        self.store = TranscriptStore(max_calls=10, max_transcripts_per_call=3, stale_ttl=3600)

    def test_add_and_get_transcript(self):
        self.store.add_transcript("call-1", {"role": "agent", "text": "Hello"})
        tx = self.store.get_transcripts("call-1")
        assert len(tx) == 1
        assert tx[0]["text"] == "Hello"

    def test_multiple_transcripts(self):
        self.store.add_transcript("call-1", {"role": "agent", "text": "A"})
        self.store.add_transcript("call-1", {"role": "customer", "text": "B"})
        tx = self.store.get_transcripts("call-1")
        assert len(tx) == 2

    def test_max_transcripts_per_call(self):
        for i in range(5):
            self.store.add_transcript("call-1", {"text": str(i)})
        tx = self.store.get_transcripts("call-1")
        assert len(tx) == 3
        assert tx[0]["text"] == "2"
        assert tx[-1]["text"] == "4"

    def test_get_transcripts_empty(self):
        assert self.store.get_transcripts("nonexistent") == []

    def test_get_or_create(self):
        tx = self.store.get_or_create("call-new")
        assert tx == []
        tx.append("item")
        tx2 = self.store.get_or_create("call-new")
        assert tx2 == ["item"]

    def test_cleanup(self):
        self.store.add_transcript("call-1", {"text": "hello"})
        self.store.cleanup("call-1")
        assert self.store.get_transcripts("call-1") == []

    def test_cleanup_nonexistent(self):
        self.store.cleanup("never-existed")
        pass

    def test_touch_updates_activity(self):
        self.store.add_transcript("call-1", {"text": "hello"})
        self.store.touch("call-1")
        assert "call-1" in self.store._last_activity

    @pytest.mark.asyncio
    async def test_cleanup_stale_loop_purges_expired(self):
        self.store.add_transcript("call-stale", {"text": "old"})
        self.store.add_transcript("call-fresh", {"text": "new"})
        self.store._last_activity["call-stale"] = time.time() - 7200
        self.store._last_activity["call-fresh"] = time.time()

        with patch("apps.api.services.transcript_store.asyncio.sleep", side_effect=[None, Exception("break")]):
            with pytest.raises(Exception, match="break"):
                await self.store.cleanup_stale_loop()

        assert self.store.get_transcripts("call-stale") == []
        assert len(self.store.get_transcripts("call-fresh")) == 1

    def test_lru_eviction(self):
        for i in range(12):
            self.store.add_transcript(f"call-{i}", {"text": str(i)})
        assert "call-0" not in self.store._transcripts

    def test_multiple_calls_isolation(self):
        self.store.add_transcript("call-a", {"text": "hello"})
        self.store.add_transcript("call-b", {"text": "world"})
        assert len(self.store.get_transcripts("call-a")) == 1
        assert len(self.store.get_transcripts("call-b")) == 1
