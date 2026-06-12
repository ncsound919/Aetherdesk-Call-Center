"""Transcript storage service — replaces global CALL_TRANSCRIPTS + CALL_LAST_ACTIVITY."""

import asyncio
import time

import structlog
from cachetools import LRUCache

logger = structlog.get_logger()


class TranscriptStore:
    """Bounded in-memory cache of call transcripts with stale cleanup."""

    def __init__(self, max_calls: int = 1000, max_transcripts_per_call: int = 200, stale_ttl: int = 3600):
        self._transcripts: LRUCache = LRUCache(maxsize=max_calls)
        self._last_activity: LRUCache = LRUCache(maxsize=max_calls)
        self._max_per_call = max_transcripts_per_call
        self._stale_ttl = stale_ttl

    def add_transcript(self, call_sid: str, entry: dict) -> None:
        self._transcripts.setdefault(call_sid, [])
        self._last_activity[call_sid] = time.time()
        transcripts = self._transcripts[call_sid]
        transcripts.append(entry)
        if len(transcripts) > self._max_per_call:
            self._transcripts[call_sid] = transcripts[-self._max_per_call:]

    def get_transcripts(self, call_sid: str) -> list:
        return list(self._transcripts.get(call_sid, []))

    def get_or_create(self, call_sid: str) -> list:
        return self._transcripts.setdefault(call_sid, [])

    def cleanup(self, call_sid: str) -> None:
        self._transcripts.pop(call_sid, None)
        self._last_activity.pop(call_sid, None)

    def touch(self, call_sid: str) -> None:
        self._last_activity[call_sid] = time.time()

    async def cleanup_stale_loop(self) -> None:
        """Background task to purge stale transcripts."""
        while True:
            await asyncio.sleep(600)
            now = time.time()
            stale = [sid for sid, ts in list(self._last_activity.items()) if now - ts > self._stale_ttl]
            for sid in stale:
                self.cleanup(sid)
                logger.info("stale_transcript_purged", call_sid=sid)
