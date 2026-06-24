import asyncio
from typing import Any

from apps.api.services.asr import asr_service
from apps.api.services.queue import QueueManager
from apps.api.services.tts import tts_service


def _get_broadcast_transcript():
    from apps.api.routers.realtime import broadcast_transcript
    return broadcast_transcript


class VoiceSession:
    MAX_BUFFER_SIZE = 10 * 1024 * 1024
    MAX_TRANSCRIPT_LENGTH = 100

    def __init__(self, session_id: str, call_sid: str, profile_id: str = "PROF-001", tenant_id: str = "unknown"):
        self.session_id = session_id
        self.call_sid = call_sid
        self.profile_id = profile_id
        self.tenant_id = tenant_id
        self.agent_state: dict[str, Any] = {}
        self.audio_buffer: bytes = b""
        self.transcript: list[dict] = []
        self.is_active = True
        self.silence_duration = 0
        self.SILENCE_THRESHOLD = 300  # RMS energy threshold
        self.MAX_SILENCE_FRAMES = 15   # Approx 300-500ms of silence
        self.MAX_BUFFER_FRAMES = 100  # Approx 3-5 seconds max
        self._buffer_lock = asyncio.Lock()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "call_sid": self.call_sid,
            "profile_id": self.profile_id,
            "tenant_id": self.tenant_id,
            "agent_state": self.agent_state,
            "transcript": self.transcript,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VoiceSession":
        session = cls(data["session_id"], data["call_sid"], data.get("profile_id", "PROF-001"), data.get("tenant_id", "unknown"))
        session.agent_state = data.get("agent_state", {})
        session.transcript = data.get("transcript", [])
        session.is_active = data.get("is_active", True)
        return session

    async def process_audio(self, audio_chunk: bytes) -> str | None:
        import numpy as np
        if len(audio_chunk) < 320:
            return None

        async with self._buffer_lock:
            # Hard limit on buffer to prevent memory exhaustion
            if len(self.audio_buffer) >= self.MAX_BUFFER_SIZE:
                self.audio_buffer = self.audio_buffer[-self.MAX_BUFFER_SIZE // 2:]

            # Calculate energy to detect silence
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
            energy = np.sqrt(np.mean(audio_array.astype(float)**2))

            self.audio_buffer += audio_chunk

            # Buffer too large or silence detected
            if energy < self.SILENCE_THRESHOLD:
                self.silence_duration += 1
            else:
                self.silence_duration = 0

            should_transcribe = (
                (self.silence_duration >= self.MAX_SILENCE_FRAMES and len(self.audio_buffer) > 3200) or
                (len(self.audio_buffer) >= self.MAX_BUFFER_SIZE // 10)  # ~1MB fallback
            )

            if should_transcribe:
                text = await asr_service.transcribe_streaming(self.audio_buffer)
                self.audio_buffer = b""
                self.silence_duration = 0

                if text:
                    transcript_entry = {
                        "from": "customer",
                        "text": text,
                        "session_id": self.session_id
                    }
                    self.transcript.append(transcript_entry)
                    if len(self.transcript) > self.MAX_TRANSCRIPT_LENGTH:
                        self.transcript = self.transcript[-self.MAX_TRANSCRIPT_LENGTH:]
                    _get_broadcast_transcript()(self.call_sid, transcript_entry)
                    return text

        return None

    async def speak(self, text: str) -> bytes:
        audio = await tts_service.synthesize(text)
        transcript_entry = {
            "from": "agent",
            "text": text,
            "session_id": self.session_id
        }
        async with self._buffer_lock:
            self.transcript.append(transcript_entry)
        _get_broadcast_transcript()(self.call_sid, transcript_entry)
        return audio

    async def speak_stream(self, text: str, sentiment: str = "neutral", latency_ms: float = 0.0):
        """Async generator that yields audio chunks and logs the transcript."""
        transcript_entry = {
            "from": "agent",
            "text": text,
            "session_id": self.session_id,
            "sentiment": sentiment,
            "latency_ms": latency_ms
        }
        async with self._buffer_lock:
            self.transcript.append(transcript_entry)
        _get_broadcast_transcript()(self.call_sid, transcript_entry)

        async for chunk in tts_service.synthesize_streaming(text):
            yield chunk


def _get_queue_manager(app) -> QueueManager:
    if not hasattr(app.state, 'qm'):
        app.state.qm = QueueManager(app.state.redis)
    return app.state.qm


def store_session(app, session_id: str, session: VoiceSession):
    qm = _get_queue_manager(app)
    qm.session_set(session_id, session.to_dict())


def remove_session(app, session_id: str):
    qm = _get_queue_manager(app)
    qm.session_delete(session_id)


def get_or_create_session(app, session_id: str, call_sid: str = "unknown", profile_id: str = "PROF-001", tenant_id: str = "unknown") -> VoiceSession:
    qm = _get_queue_manager(app)
    data = qm.session_get(session_id)

    if data:
        return VoiceSession.from_dict(data)

    session = VoiceSession(session_id, call_sid, profile_id, tenant_id)
    store_session(app, session_id, session)
    return session


