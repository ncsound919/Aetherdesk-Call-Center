import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from apps.api.services.call_session import VoiceSession


class TestVoiceSession:
    def test_create_session(self):
        session = VoiceSession("SESS-001", "CALL-001", "PROF-DEFAULT", "TENANT-001")
        assert session.session_id == "SESS-001"
        assert session.call_sid == "CALL-001"
        assert session.profile_id == "PROF-DEFAULT"
        assert session.tenant_id == "TENANT-001"
        assert session.is_active is True
        assert session.transcript == []
        assert session.audio_buffer == b""

    def test_to_dict(self):
        session = VoiceSession("SESS-001", "CALL-001")
        d = session.to_dict()
        assert d["session_id"] == "SESS-001"
        assert d["call_sid"] == "CALL-001"
        assert d["is_active"] is True

    def test_from_dict(self):
        data = {
            "session_id": "SESS-001",
            "call_sid": "CALL-001",
            "profile_id": "PROF-001",
            "tenant_id": "TENANT-001",
            "agent_state": {},
            "transcript": [{"from": "customer", "text": "hello"}],
            "is_active": True,
        }
        session = VoiceSession.from_dict(data)
        assert session.session_id == "SESS-001"
        assert len(session.transcript) == 1
        assert session.transcript[0]["text"] == "hello"

    def test_from_dict_default_profile(self):
        data = {
            "session_id": "SESS-002",
            "call_sid": "CALL-002",
            "is_active": False,
        }
        session = VoiceSession.from_dict(data)
        assert session.profile_id == "PROF-001"
        assert session.is_active is False

    def test_max_buffer_size(self):
        session = VoiceSession("SESS-001", "CALL-001")
        assert session.MAX_BUFFER_SIZE == 10 * 1024 * 1024

    def test_max_transcript_length(self):
        session = VoiceSession("SESS-001", "CALL-001")
        assert session.MAX_TRANSCRIPT_LENGTH == 100

    def test_agent_state_initialization(self):
        session = VoiceSession("SESS-001", "CALL-001")
        assert session.agent_state == {}


class TestVoiceSessionProcessAudio:
    @pytest.mark.asyncio
    async def test_small_chunk_returns_none(self):
        session = VoiceSession("SESS-PA1", "CALL-PA1")
        result = await session.process_audio(b"\x00" * 319)
        assert result is None
        assert session.audio_buffer == b""

    @pytest.mark.asyncio
    async def test_low_energy_triggers_silence(self):
        session = VoiceSession("SESS-PA2", "CALL-PA2")
        session.silence_duration = 15
        session.audio_buffer = b"\x00" * 5000

        with patch("numpy.frombuffer") as mock_fb, \
             patch("numpy.sqrt") as mock_sqrt, \
             patch("numpy.mean") as mock_mean, \
             patch("apps.api.services.call_session.asr_service") as mock_asr, \
             patch("apps.api.services.call_session._get_broadcast_transcript") as mock_get_bc:

            mock_arr = MagicMock()
            mock_arr.astype.return_value = mock_arr
            mock_fb.return_value = mock_arr
            mock_mean.return_value = 0.0
            mock_sqrt.return_value = 0.0

            mock_asr.transcribe_streaming = AsyncMock(return_value="need refill")
            mock_bc = MagicMock()
            mock_get_bc.return_value = mock_bc

            result = await session.process_audio(b"\x00" * 1000)

        assert result == "need refill"
        assert len(session.transcript) == 1
        assert session.transcript[0]["text"] == "need refill"
        assert session.transcript[0]["from"] == "customer"
        assert session.audio_buffer == b""
        assert session.silence_duration == 0
        mock_bc.assert_called_once()

    @pytest.mark.asyncio
    async def test_asr_returns_no_text(self):
        session = VoiceSession("SESS-PA3", "CALL-PA3")
        session.silence_duration = 15
        session.audio_buffer = b"\x00" * 5000

        with patch("numpy.frombuffer") as mock_fb, \
             patch("numpy.sqrt") as mock_sqrt, \
             patch("numpy.mean") as mock_mean, \
             patch("apps.api.services.call_session.asr_service") as mock_asr:

            mock_arr = MagicMock()
            mock_arr.astype.return_value = mock_arr
            mock_fb.return_value = mock_arr
            mock_mean.return_value = 0.0
            mock_sqrt.return_value = 0.0

            mock_asr.transcribe_streaming = AsyncMock(return_value=None)

            result = await session.process_audio(b"\x00" * 1000)

        assert result is None
        assert session.transcript == []

    @pytest.mark.asyncio
    async def test_high_energy_resets_silence(self):
        session = VoiceSession("SESS-PA4", "CALL-PA4")
        session.silence_duration = 10

        with patch("numpy.frombuffer") as mock_fb, \
             patch("numpy.sqrt") as mock_sqrt, \
             patch("numpy.mean") as mock_mean:

            mock_arr = MagicMock()
            mock_arr.astype.return_value = mock_arr
            mock_fb.return_value = mock_arr
            mock_mean.return_value = 250000.0
            mock_sqrt.return_value = 500.0

            result = await session.process_audio(b"\x00" * 2000)

        assert result is None
        assert session.silence_duration == 0

    @pytest.mark.asyncio
    async def test_buffer_overflow_trims(self):
        session = VoiceSession("SESS-PA5", "CALL-PA5")
        session.audio_buffer = b"\x01" * session.MAX_BUFFER_SIZE
        session.silence_duration = 20

        with patch("numpy.frombuffer") as mock_fb, \
             patch("numpy.sqrt") as mock_sqrt, \
             patch("numpy.mean") as mock_mean, \
             patch("apps.api.services.call_session.asr_service") as mock_asr, \
             patch("apps.api.services.call_session._get_broadcast_transcript") as mock_get_bc:

            mock_arr = MagicMock()
            mock_arr.astype.return_value = mock_arr
            mock_fb.return_value = mock_arr
            mock_mean.return_value = 0.0
            mock_sqrt.return_value = 0.0

            mock_asr.transcribe_streaming = AsyncMock(return_value="overflow text")
            mock_get_bc.return_value = MagicMock()

            result = await session.process_audio(b"\x00" * 1000)

        assert result == "overflow text"
        assert len(session.audio_buffer) <= session.MAX_BUFFER_SIZE // 2 + 1000

    @pytest.mark.asyncio
    async def test_large_buffer_fallback_triggers_transcribe(self):
        session = VoiceSession("SESS-PA6", "CALL-PA6")
        chunk_size = session.MAX_BUFFER_SIZE // 10 + 1
        session.audio_buffer = b"\x00" * chunk_size

        with patch("numpy.frombuffer") as mock_fb, \
             patch("numpy.sqrt") as mock_sqrt, \
             patch("numpy.mean") as mock_mean, \
             patch("apps.api.services.call_session.asr_service") as mock_asr, \
             patch("apps.api.services.call_session._get_broadcast_transcript") as mock_get_bc:

            mock_arr = MagicMock()
            mock_arr.astype.return_value = mock_arr
            mock_fb.return_value = mock_arr
            mock_mean.return_value = 100.0
            mock_sqrt.return_value = 10.0

            mock_asr.transcribe_streaming = AsyncMock(return_value="large buffer")
            mock_get_bc.return_value = MagicMock()

            result = await session.process_audio(b"\x00" * 1000)

        assert result == "large buffer"

    @pytest.mark.asyncio
    async def test_transcript_truncation(self):
        session = VoiceSession("SESS-PA7", "CALL-PA7")
        session.silence_duration = 15
        session.audio_buffer = b"\x00" * 5000
        session.transcript = [{"text": f"old_{i}"} for i in range(session.MAX_TRANSCRIPT_LENGTH)]

        with patch("numpy.frombuffer") as mock_fb, \
             patch("numpy.sqrt") as mock_sqrt, \
             patch("numpy.mean") as mock_mean, \
             patch("apps.api.services.call_session.asr_service") as mock_asr, \
             patch("apps.api.services.call_session._get_broadcast_transcript") as mock_get_bc:

            mock_arr = MagicMock()
            mock_arr.astype.return_value = mock_arr
            mock_fb.return_value = mock_arr
            mock_mean.return_value = 0.0
            mock_sqrt.return_value = 0.0

            mock_asr.transcribe_streaming = AsyncMock(return_value="new text")
            mock_get_bc.return_value = MagicMock()

            result = await session.process_audio(b"\x00" * 1000)

        assert result == "new text"
        assert len(session.transcript) == session.MAX_TRANSCRIPT_LENGTH
        assert session.transcript[-1]["text"] == "new text"


class TestVoiceSessionSpeak:
    @pytest.mark.asyncio
    async def test_speak_returns_audio(self):
        session = VoiceSession("SESS-SPK1", "CALL-SPK1")

        with patch("apps.api.services.call_session.tts_service") as mock_tts, \
             patch("apps.api.services.call_session._get_broadcast_transcript") as mock_get_bc:

            mock_tts.synthesize = AsyncMock(return_value=b"wav_audio_data")
            mock_bc = MagicMock()
            mock_get_bc.return_value = mock_bc

            audio = await session.speak("Hello, how can I help?")

        assert audio == b"wav_audio_data"
        assert len(session.transcript) == 1
        assert session.transcript[0]["text"] == "Hello, how can I help?"
        assert session.transcript[0]["from"] == "agent"
        mock_bc.assert_called_once_with("CALL-SPK1", session.transcript[0])


class TestVoiceSessionSpeakStream:
    @pytest.mark.asyncio
    async def test_speak_stream_yields_chunks(self):
        session = VoiceSession("SESS-SPK2", "CALL-SPK2")

        async def mock_stream(text):
            yield b"chunk_a"
            yield b"chunk_b"

        with patch("apps.api.services.call_session.tts_service") as mock_tts, \
             patch("apps.api.services.call_session._get_broadcast_transcript") as mock_get_bc:

            mock_tts.synthesize_streaming = mock_stream
            mock_bc = MagicMock()
            mock_get_bc.return_value = mock_bc

            collected = []
            async for chunk in session.speak_stream("Stream this", sentiment="positive", latency_ms=42.0):
                collected.append(chunk)

        assert collected == [b"chunk_a", b"chunk_b"]
        assert len(session.transcript) == 1
        assert session.transcript[0]["text"] == "Stream this"
        assert session.transcript[0]["sentiment"] == "positive"
        assert session.transcript[0]["latency_ms"] == 42.0
        mock_bc.assert_called_once()

    @pytest.mark.asyncio
    async def test_speak_stream_default_params(self):
        session = VoiceSession("SESS-SPK3", "CALL-SPK3")

        async def mock_stream(text):
            yield b"data"

        with patch("apps.api.services.call_session.tts_service") as mock_tts, \
             patch("apps.api.services.call_session._get_broadcast_transcript") as mock_get_bc:

            mock_tts.synthesize_streaming = mock_stream
            mock_get_bc.return_value = MagicMock()

            collected = []
            async for chunk in session.speak_stream("Test"):
                collected.append(chunk)

        assert collected == [b"data"]
        assert session.transcript[0]["sentiment"] == "neutral"
        assert session.transcript[0]["latency_ms"] == 0.0


class TestVoiceSessionManagement:
    def test_store_session(self):
        session = VoiceSession("SESS-MGT1", "CALL-MGT1")
        mock_app = MagicMock()
        mock_qm = MagicMock()
        mock_app.state.qm = mock_qm

        with patch("apps.api.services.call_session._get_queue_manager", return_value=mock_qm):
            from apps.api.services.call_session import store_session
            store_session(mock_app, "SESS-MGT1", session)

        mock_qm.session_set.assert_called_once_with("SESS-MGT1", session.to_dict())

    def test_remove_session(self):
        mock_app = MagicMock()
        mock_qm = MagicMock()
        mock_app.state.qm = mock_qm

        with patch("apps.api.services.call_session._get_queue_manager", return_value=mock_qm):
            from apps.api.services.call_session import remove_session
            remove_session(mock_app, "SESS-MGT2")

        mock_qm.session_delete.assert_called_once_with("SESS-MGT2")

    def test_get_or_create_session_new(self):
        session = VoiceSession("SESS-MGT3", "CALL-MGT3")
        mock_app = MagicMock()
        mock_qm = MagicMock()
        mock_qm.session_get.return_value = None
        mock_app.state.qm = mock_qm

        with patch("apps.api.services.call_session._get_queue_manager", return_value=mock_qm), \
             patch("apps.api.services.call_session.store_session") as mock_store:

            from apps.api.services.call_session import get_or_create_session
            result = get_or_create_session(mock_app, "SESS-MGT3", "CALL-MGT3", "PROF-002", "TENANT-002")

        assert isinstance(result, VoiceSession)
        assert result.session_id == "SESS-MGT3"
        assert result.call_sid == "CALL-MGT3"
        assert result.profile_id == "PROF-002"
        assert result.tenant_id == "TENANT-002"
        mock_store.assert_called_once()

    def test_get_or_create_session_existing(self):
        mock_app = MagicMock()
        mock_qm = MagicMock()
        existing_data = {
            "session_id": "SESS-MGT4",
            "call_sid": "CALL-MGT4",
            "profile_id": "PROF-001",
            "tenant_id": "TENANT-001",
            "agent_state": {},
            "transcript": [],
            "is_active": True,
        }
        mock_qm.session_get.return_value = existing_data
        mock_app.state.qm = mock_qm

        with patch("apps.api.services.call_session._get_queue_manager", return_value=mock_qm), \
             patch("apps.api.services.call_session.store_session") as mock_store:

            from apps.api.services.call_session import get_or_create_session
            result = get_or_create_session(mock_app, "SESS-MGT4")

        assert isinstance(result, VoiceSession)
        assert result.session_id == "SESS-MGT4"
        assert result.call_sid == "CALL-MGT4"
        mock_store.assert_not_called()

    def test_get_queue_manager_caches(self):
        mock_app = MagicMock()
        mock_app.state.qm = None

        from apps.api.services.call_session import _get_queue_manager
        qm1 = _get_queue_manager(mock_app)
        qm2 = _get_queue_manager(mock_app)

        assert qm1 is qm2
        assert qm1 is mock_app.state.qm
