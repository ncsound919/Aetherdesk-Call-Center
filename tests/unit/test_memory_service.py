"""Unit tests for src/api/services/memory_service.py."""

import asyncio
import hashlib
import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from api.services.memory_service import MemoryService, memory_service


def _make_service(tmp_path):
    svc = MemoryService()
    svc.storage_path = str(tmp_path)
    return svc


class TestMemoryServiceInit:
    def test_default_initialization(self):
        svc = MemoryService()
        assert os.path.isdir(svc.storage_path)
        assert svc._locks == {}
        assert isinstance(svc._global_lock, asyncio.Lock)

    def test_singleton_exists(self):
        assert isinstance(memory_service, MemoryService)


class TestSanitizeFilename:
    def test_keeps_safe_characters(self):
        svc = MemoryService()
        assert svc._sanitize_filename("cust-123_ABC") == "cust-123_ABC"

    def test_strips_unsafe_characters(self):
        svc = MemoryService()
        assert svc._sanitize_filename("cust id@#$") == "custid"

    def test_empty_returns_hash(self):
        svc = MemoryService()
        result = svc._sanitize_filename("!!!")
        assert result == hashlib.sha256(b"!!!").hexdigest()[:16]
        assert len(result) == 16


class TestGetTenantPath:
    def test_creates_tenant_dir(self, tmp_path):
        svc = _make_service(tmp_path)
        path = svc._get_tenant_path("tenant-1")
        assert path == os.path.join(str(tmp_path), "tenant-1")
        assert os.path.isdir(path)

    def test_raises_on_path_traversal(self):
        svc = MemoryService()
        svc.storage_path = "relative_mem_dir"
        with pytest.raises(ValueError):
            svc._get_tenant_path("../../etc")


class TestGetLock:
    @pytest.mark.asyncio
    async def test_same_key_returns_same_lock(self):
        svc = MemoryService()
        lock1 = await svc._get_lock("a:b")
        lock2 = await svc._get_lock("a:b")
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_different_keys_return_different_locks(self):
        svc = MemoryService()
        lock1 = await svc._get_lock("a:1")
        lock2 = await svc._get_lock("a:2")
        assert lock1 is not lock2

    @pytest.mark.asyncio
    async def test_prunes_unlocked_locks_when_over_limit(self):
        svc = MemoryService()
        svc._locks = {}
        for i in range(1001):
            svc._locks[f"key{i}"] = asyncio.Lock()
        held = asyncio.Lock()
        await held.acquire()
        svc._locks["held"] = held

        lock = await svc._get_lock("newkey")
        assert lock is not None
        assert "held" in svc._locks
        assert "newkey" in svc._locks
        assert len(svc._locks) == 2


class TestGetMemories:
    @pytest.mark.asyncio
    async def test_missing_file_returns_empty(self, tmp_path):
        svc = _make_service(tmp_path)
        assert await svc.get_memories("tenant-1", "cust-1") == []

    @pytest.mark.asyncio
    async def test_returns_facts(self, tmp_path):
        svc = _make_service(tmp_path)
        tenant_path = svc._get_tenant_path("tenant-1")
        with open(os.path.join(tenant_path, "cust-1.json"), "w") as f:
            json.dump({"facts": ["likes tea", "travels a lot"]}, f)
        assert await svc.get_memories("tenant-1", "cust-1") == [
            "likes tea",
            "travels a lot",
        ]

    @pytest.mark.asyncio
    async def test_missing_facts_key_returns_empty(self, tmp_path):
        svc = _make_service(tmp_path)
        tenant_path = svc._get_tenant_path("tenant-1")
        with open(os.path.join(tenant_path, "cust-1.json"), "w") as f:
            json.dump({"other": 1}, f)
        assert await svc.get_memories("tenant-1", "cust-1") == []

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty(self, tmp_path):
        svc = _make_service(tmp_path)
        tenant_path = svc._get_tenant_path("tenant-1")
        with open(os.path.join(tenant_path, "cust-1.json"), "w") as f:
            f.write("{not json")
        assert await svc.get_memories("tenant-1", "cust-1") == []

    @pytest.mark.asyncio
    async def test_read_error_logged_and_returns_empty(self, tmp_path):
        svc = _make_service(tmp_path)
        tenant_path = svc._get_tenant_path("tenant-1")
        with open(os.path.join(tenant_path, "cust-1.json"), "w") as f:
            json.dump({"facts": ["x"]}, f)
        with patch(
            "api.services.memory_service.asyncio.to_thread",
            side_effect=RuntimeError("io error"),
        ), patch(
            "api.services.memory_service.logger.error"
        ) as mock_error:
            result = await svc.get_memories("tenant-1", "cust-1")
        assert result == []
        mock_error.assert_called_once()


class TestAddMemories:
    @pytest.mark.asyncio
    async def test_no_preference_does_not_write(self, tmp_path):
        svc = _make_service(tmp_path)
        await svc.add_memories("tenant-1", "cust-1", "The customer ordered two widgets")
        file_path = os.path.join(
            str(tmp_path), "tenant-1", "cust-1.json"
        )
        assert not os.path.exists(file_path)

    @pytest.mark.asyncio
    async def test_extracts_fact_from_transcript(self, tmp_path):
        svc = _make_service(tmp_path)
        await svc.add_memories("tenant-1", "cust-1", "The customer says I prefer email.")
        facts = await svc.get_memories("tenant-1", "cust-1")
        assert len(facts) == 1
        assert facts[0].startswith("Derived from transcript: ")
        assert "prefer email" in facts[0]

    @pytest.mark.asyncio
    async def test_truncates_snippet_and_strips_newlines(self, tmp_path):
        svc = _make_service(tmp_path)
        long_transcript = "I prefer" + "\n" + "y" * 300
        await svc.add_memories("tenant-1", "cust-1", long_transcript)
        facts = await svc.get_memories("tenant-1", "cust-1")
        assert len(facts) == 1
        fact = facts[0]
        assert "\n" not in fact
        assert len(fact) - len("Derived from transcript: ") - len("...") == 200

    @pytest.mark.asyncio
    async def test_deduplicates_facts(self, tmp_path):
        svc = _make_service(tmp_path)
        for _ in range(2):
            await svc.add_memories("tenant-1", "cust-1", "I prefer mornings.")
        facts = await svc.get_memories("tenant-1", "cust-1")
        assert len(facts) == 1

    @pytest.mark.asyncio
    async def test_merges_with_existing_facts(self, tmp_path):
        svc = _make_service(tmp_path)
        await svc.add_memories("tenant-1", "cust-1", "I prefer mornings.")
        await svc.add_memories("tenant-1", "cust-1", "She prefers evenings.")
        facts = await svc.get_memories("tenant-1", "cust-1")
        assert len(facts) == 2

    @pytest.mark.asyncio
    async def test_caps_at_fifty_facts(self, tmp_path):
        svc = _make_service(tmp_path)
        existing = [f"fact-{i}" for i in range(50)]
        with patch.object(
            svc, "get_memories", new_callable=AsyncMock, return_value=existing
        ), patch(
            "api.services.memory_service.asyncio.to_thread"
        ) as mock_to_thread:
            await svc.add_memories("tenant-1", "cust-1", "I prefer text.")
        written = mock_to_thread.call_args_list[-1][0][0]
        written()
        file_path = os.path.join(str(tmp_path), "tenant-1", "cust-1.json")
        with open(file_path) as f:
            facts = json.load(f).get("facts")
        assert len(facts) == 50

    @pytest.mark.asyncio
    async def test_write_error_is_swallowed(self, tmp_path):
        svc = _make_service(tmp_path)
        with patch.object(
            svc, "get_memories", new_callable=AsyncMock, return_value=[]
        ), patch(
            "api.services.memory_service.asyncio.to_thread",
            side_effect=RuntimeError("disk full"),
        ), patch(
            "api.services.memory_service.logger.error"
        ) as mock_error:
            await svc.add_memories("tenant-1", "cust-1", "I prefer tea.")
        mock_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_per_tenant_lock(self, tmp_path):
        svc = _make_service(tmp_path)
        with patch.object(
            svc, "_get_lock", new_callable=AsyncMock
        ) as mock_lock:
            lock = asyncio.Lock()
            mock_lock.return_value = lock
            await svc.add_memories("tenant-1", "cust-1", "I prefer tea.")
        mock_lock.assert_called_once_with("tenant-1:cust-1")
