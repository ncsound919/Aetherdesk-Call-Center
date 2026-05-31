import asyncio
import json
import os
import re

import structlog

logger = structlog.get_logger()


class MemoryService:
    """
    Long-term Memory Service inspired by Mem0/MemGPT.
    Extracts and persists customer-specific facts across sessions.
    """

    def __init__(self):
        self.storage_path = os.path.abspath("data/memory")
        os.makedirs(self.storage_path, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def _sanitize_filename(self, name: str) -> str:
        """Prevent path traversal and invalid characters."""
        clean = re.sub(r'[^a-zA-Z0-9_-]', '', name)
        if not clean:
            import hashlib
            return hashlib.md5(name.encode()).hexdigest()
        return clean

    def _get_tenant_path(self, tenant_id: str):
        safe_tenant = self._sanitize_filename(tenant_id)
        path = os.path.join(self.storage_path, safe_tenant)
        # Ensure path stays within storage directory (defense in depth)
        if not os.path.abspath(path).startswith(self.storage_path):
            raise ValueError("Path traversal attempt detected")
        os.makedirs(path, exist_ok=True)
        return path

    async def _get_lock(self, key: str) -> asyncio.Lock:
        async with self._global_lock:
            # H10 fix: clear idle (unlocked) locks when the dict grows too large.
            # Previous code kept locked locks (inverted condition) causing unbounded growth.
            if len(self._locks) > 1000:
                # Keep only locks that ARE currently held (in use); drop idle ones.
                self._locks = {
                    k: lock for k, lock in self._locks.items()
                    if lock.locked()  # keep in-use locks
                }
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def get_memories(self, tenant_id: str, customer_id: str) -> list[str]:
        """Fetch long-term facts about this specific customer."""
        safe_customer = self._sanitize_filename(customer_id)
        path = os.path.join(self._get_tenant_path(tenant_id), f"{safe_customer}.json")
        if not os.path.exists(path):
            return []
        try:
            def _read():
                with open(path) as f:
                    return json.load(f)
            data = await asyncio.to_thread(_read)
            return data.get("facts", [])
        except Exception as e:
            logger.error("memory_fetch_error", error=str(e))
            return []

    async def add_memories(self, tenant_id: str, customer_id: str, transcript: str):
        """Extracts new facts from a transcript and saves them safely."""
        safe_customer = self._sanitize_filename(customer_id)
        path = os.path.join(self._get_tenant_path(tenant_id), f"{safe_customer}.json")
        lock_key = f"{tenant_id}:{safe_customer}"
        lock = await self._get_lock(lock_key)
        async with lock:
            existing = await self.get_memories(tenant_id, customer_id)
            # Simple extraction heuristic for demo
            new_facts = []
            if "prefer" in transcript.lower():
                # Prevent massively long string injections
                safe_snippet = transcript[:200].replace('\n', ' ')
                new_facts.append(f"Derived from transcript: {safe_snippet}...")
            if not new_facts:
                return
            combined = list(set(existing + new_facts))
            # Cap to prevent unbounded growth
            if len(combined) > 50:
                combined = combined[-50:]
            try:
                def _write():
                    with open(path, 'w') as f:
                        json.dump({"facts": combined}, f)
                await asyncio.to_thread(_write)
                logger.info("memories_updated", tenant_id=tenant_id,
                            customer_id=customer_id, count=len(new_facts))
            except Exception as e:
                logger.error("memory_write_error", error=str(e))


memory_service = MemoryService()
