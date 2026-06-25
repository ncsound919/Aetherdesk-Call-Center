import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTTSServiceInit:
    def test_default_initialization(self):
        from api.services.tts import TTSService

        svc = TTSService()
        assert svc.engines == ["edge"]
        assert svc.current_engine == "edge"
        assert svc.voice == "en-US-AriaNeural"
        assert svc.language == "en"

    def test_custom_initialization(self):
        from api.services.tts import TTSService

        svc = TTSService(engines="chatterbox,qwen3", voice="en-US-JennyNeural", language="fr")
        assert svc.engines == ["chatterbox", "qwen3"]
        assert svc.current_engine == "chatterbox"
        assert svc.voice == "en-US-JennyNeural"
        assert svc.language == "fr"


class TestTTSServiceGetEngineUrl:
    def test_chatterbox_url(self):
        from api.services.tts import TTSService

        svc = TTSService()
        with patch.dict(os.environ, {"CHATTERBOX_API_URL": "http://custom:5001"}, clear=False):
            url = svc._get_engine_url("chatterbox")
            assert url == "http://custom:5001"

    def test_chatterbox_default_url(self):
        from api.services.tts import TTSService

        svc = TTSService()
        url = svc._get_engine_url("chatterbox")
        assert url == "http://chatterbox:5001"

    def test_qwen3_url(self):
        from api.services.tts import TTSService

        svc = TTSService()
        with patch.dict(os.environ, {"QWEN_API_URL": "http://custom-qwen:8000"}, clear=False):
            url = svc._get_engine_url("qwen3")
            assert url == "http://custom-qwen:8000"

    def test_qwen3_default_url(self):
        from api.services.tts import TTSService

        svc = TTSService()
        url = svc._get_engine_url("qwen3")
        assert url == "http://qwen3-tts:8000"

    def test_unknown_engine(self):
        from api.services.tts import TTSService

        svc = TTSService()
        url = svc._get_engine_url("nonexistent")
        assert url is None


class TestTTSServiceGetChatterboxVoice:
    def test_returns_default_when_no_config(self):
        from api.services.tts import TTSService

        svc = TTSService(voice="en-US-AriaNeural")
        with patch("api.services.tts.os.path.exists", return_value=False):
            result = svc._get_chatterbox_voice()
            assert result == "en-US-AriaNeural"

    def test_returns_voice_id_from_profile(self):
        from api.services.tts import TTSService

        svc = TTSService(voice="en-US-AriaNeural")
        config_data = {"default_voice_id": "voice-abc"}
        profile_data = {"chatterbox_voice_id": "chatter-xyz"}

        def fake_exists(path):
            if "default_voice.json" in path:
                return True
            if "voice-abc.json" in path:
                return True
            return False

        def fake_open(path, *args, **kwargs):
            content = ""
            if "default_voice.json" in str(path):
                content = json.dumps(config_data)
            elif "voice-abc.json" in str(path):
                content = json.dumps(profile_data)
            return MagicMock(
                __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=content))),
                __exit__=MagicMock(return_value=False),
            )

        with patch("api.services.tts.os.path.exists", side_effect=fake_exists), \
             patch("builtins.open", side_effect=fake_open), \
             patch("json.load", side_effect=lambda f: json.loads(f.read())):
            result = svc._get_chatterbox_voice()
            assert result == "chatter-xyz"

    def test_falls_back_to_default_voice_id_when_no_profile(self):
        from api.services.tts import TTSService

        svc = TTSService(voice="en-US-AriaNeural")
        config_data = {"default_voice_id": "voice-abc"}

        def fake_exists(path):
            if "default_voice.json" in path:
                return True
            if "voice-abc.json" in path:
                return False
            return False

        def fake_open(path, *args, **kwargs):
            return MagicMock(
                __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=json.dumps(config_data)))),
                __exit__=MagicMock(return_value=False),
            )

        with patch("api.services.tts.os.path.exists", side_effect=fake_exists), \
             patch("builtins.open", side_effect=fake_open), \
             patch("json.load", side_effect=lambda f: json.loads(f.read())):
            result = svc._get_chatterbox_voice()
            assert result == "voice-abc"

    def test_handles_config_read_error(self):
        from api.services.tts import TTSService

        svc = TTSService(voice="en-US-AriaNeural")
        with patch("api.services.tts.os.path.exists", return_value=True), \
             patch("builtins.open", side_effect=Exception("read error")):
            result = svc._get_chatterbox_voice()
            assert result == "en-US-AriaNeural"


class TestTTSServiceSynthesize:
    @pytest.mark.asyncio
    async def test_success_first_engine(self):
        from api.services.tts import TTSService

        svc = TTSService()
        mock_audio = b"audio data"

        with patch.object(svc, "_synthesize_with_engine", new_callable=AsyncMock, return_value=mock_audio), \
             patch("api.services.tts.track_tts_latency"):
            result = await svc.synthesize("hello")
            assert result == mock_audio

    @pytest.mark.asyncio
    async def test_fallback_to_second_engine(self):
        from api.services.tts import TTSService

        svc = TTSService(engines="chatterbox,edge")
        mock_audio = b"edge audio"

        async def fake_synth(text, engine):
            if engine == "chatterbox":
                raise Exception("chatterbox failed")
            if engine == "edge":
                return mock_audio
            raise ValueError("unknown")

        with patch.object(svc, "_synthesize_with_engine", side_effect=fake_synth), \
             patch("api.services.tts.track_tts_latency"):
            result = await svc.synthesize("hello")
            assert result == mock_audio
            assert svc.current_engine == "edge"

    @pytest.mark.asyncio
    async def test_all_engines_fail_raises_error(self):
        from api.services.tts import TTSService

        svc = TTSService(engines="chatterbox,qwen3")

        with patch.object(svc, "_synthesize_with_engine", new_callable=AsyncMock, side_effect=Exception("failed")):
            with pytest.raises(RuntimeError, match="TTS synthesis failed on all configured engines"):
                await svc.synthesize("hello")

    @pytest.mark.asyncio
    async def test_tracks_latency(self):
        from api.services.tts import TTSService

        svc = TTSService()
        mock_audio = b"data"

        with patch.object(svc, "_synthesize_with_engine", new_callable=AsyncMock, return_value=mock_audio), \
             patch("api.services.tts.track_tts_latency") as mock_track:
            await svc.synthesize("hello")
            mock_track.assert_called_once()
            _, kwargs = mock_track.call_args
            assert kwargs.get("engine") == "edge"


class TestTTSServiceSynthesizeWithEngine:
    @pytest.mark.asyncio
    async def test_routes_to_chatterbox(self):
        from api.services.tts import TTSService

        svc = TTSService()
        with patch.object(svc, "_synthesize_chatterbox", new_callable=AsyncMock, return_value=b"data"):
            result = await svc._synthesize_with_engine("hello", "chatterbox")
            assert result == b"data"

    @pytest.mark.asyncio
    async def test_routes_to_qwen3(self):
        from api.services.tts import TTSService

        svc = TTSService()
        with patch.object(svc, "_synthesize_qwen3", new_callable=AsyncMock, return_value=b"data"):
            result = await svc._synthesize_with_engine("hello", "qwen3")
            assert result == b"data"

    @pytest.mark.asyncio
    async def test_routes_to_edge(self):
        from api.services.tts import TTSService

        svc = TTSService()
        with patch.object(svc, "_synthesize_edge", new_callable=AsyncMock, return_value=b"data"):
            result = await svc._synthesize_with_engine("hello", "edge")
            assert result == b"data"

    @pytest.mark.asyncio
    async def test_unknown_engine_raises(self):
        from api.services.tts import TTSService

        svc = TTSService()
        with pytest.raises(ValueError, match="Unknown TTS engine: unknown"):
            await svc._synthesize_with_engine("hello", "unknown")


class TestTTSServiceSynthesizeChatterbox:
    @pytest.mark.asyncio
    async def test_success(self):
        from api.services.tts import TTSService

        svc = TTSService()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"chatterbox audio"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(svc, "_get_chatterbox_voice", return_value="voice-id"):
            result = await svc._synthesize_chatterbox("hello")
            assert result == b"chatterbox audio"

    @pytest.mark.asyncio
    async def test_http_error(self):
        from api.services.tts import TTSService

        svc = TTSService()
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=Exception("HTTP 500"))

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(svc, "_get_chatterbox_voice", return_value="voice-id"):
            with pytest.raises(Exception, match="HTTP 500"):
                await svc._synthesize_chatterbox("hello")


class TestTTSServiceSynthesizeQwen3:
    @pytest.mark.asyncio
    async def test_success(self):
        from api.services.tts import TTSService

        svc = TTSService()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"qwen audio"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await svc._synthesize_qwen3("hello")
            assert result == b"qwen audio"

    @pytest.mark.asyncio
    async def test_http_error(self):
        from api.services.tts import TTSService

        svc = TTSService()
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=Exception("HTTP 500"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="HTTP 500"):
                await svc._synthesize_qwen3("hello")


class TestTTSServiceSynthesizeEdge:
    @pytest.mark.asyncio
    async def test_returns_audio_when_chunks_present(self):
        from api.services.tts import TTSService

        svc = TTSService()
        collected_chunks = []

        def capture_on_audio_chunk(engine, on_audio_chunk=None):
            on_audio_chunk(b"chunk1")
            on_audio_chunk(b"chunk2")
            stream = MagicMock()
            stream.feed = MagicMock()
            stream.play = MagicMock()
            return stream

        mock_engine = MagicMock()

        with patch("RealtimeTTS.EdgeEngine", return_value=mock_engine), \
             patch("RealtimeTTS.TextToAudioStream", side_effect=capture_on_audio_chunk), \
             patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = MagicMock()

            async def fake_run_in_executor(executor, func):
                func()

            mock_loop.run_in_executor = fake_run_in_executor
            mock_get_loop.return_value = mock_loop

            result = await svc._synthesize_edge("hello")
            assert result == b"chunk1chunk2"

    @pytest.mark.asyncio
    async def test_no_audio_raises(self):
        from api.services.tts import TTSService

        svc = TTSService()
        mock_engine = MagicMock()
        mock_stream = MagicMock()
        mock_stream.feed = MagicMock()
        mock_stream.play = MagicMock()

        with patch("RealtimeTTS.EdgeEngine", return_value=mock_engine), \
             patch("RealtimeTTS.TextToAudioStream", return_value=mock_stream), \
             patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop
            mock_loop.run_in_executor = AsyncMock(return_value=None)

            with pytest.raises(Exception, match="Edge TTS returned no audio"):
                await svc._synthesize_edge("hello")


class TestTTSServiceSynthesizeStream:
    @pytest.mark.asyncio
    async def test_returns_bytes_io(self):
        from api.services.tts import TTSService

        svc = TTSService()
        mock_audio = b"streamed audio"
        with patch.object(svc, "synthesize", new_callable=AsyncMock, return_value=mock_audio):
            result = await svc.synthesize_stream("hello")
            assert result.read() == mock_audio


class TestTTSServiceSynthesizeStreaming:
    @pytest.mark.asyncio
    async def test_streaming_chatterbox(self):
        from api.services.tts import TTSService

        svc = TTSService(engines="chatterbox")
        svc.current_engine = "chatterbox"

        with patch.object(svc, "_stream_chatterbox") as mock_stream:
            mock_stream.return_value.__aiter__.return_value = [b"chunk1", b"chunk2"]
            chunks = []
            async for chunk in svc.synthesize_streaming("hello"):
                chunks.append(chunk)
            assert chunks == [b"chunk1", b"chunk2"]

    @pytest.mark.asyncio
    async def test_streaming_qwen3(self):
        from api.services.tts import TTSService

        svc = TTSService(engines="qwen3")
        svc.current_engine = "qwen3"

        with patch.object(svc, "_stream_qwen3") as mock_stream:
            mock_stream.return_value.__aiter__.return_value = [b"chunk1"]
            chunks = []
            async for chunk in svc.synthesize_streaming("hello"):
                chunks.append(chunk)
            assert chunks == [b"chunk1"]

    @pytest.mark.asyncio
    async def test_streaming_edge(self):
        from api.services.tts import TTSService

        svc = TTSService()

        with patch.object(svc, "_stream_edge") as mock_stream:
            mock_stream.return_value.__aiter__.return_value = [b"chunk1", b"chunk2"]
            chunks = []
            async for chunk in svc.synthesize_streaming("hello"):
                chunks.append(chunk)
            assert chunks == [b"chunk1", b"chunk2"]


class TestGetTTSService:
    def test_default_config(self):
        from api.services.tts import get_tts_service

        with patch("api.services.tts.os.path.exists", return_value=False), \
             patch.dict(os.environ, {}, clear=True):
            svc = get_tts_service()
            assert svc.engines == ["edge"]
            assert svc.voice == "en-US-AriaNeural"

    def test_custom_env_config(self):
        from api.services.tts import get_tts_service

        with patch("api.services.tts.os.path.exists", return_value=False), \
             patch.dict(os.environ, {"TTS_ENGINE": "chatterbox", "TTS_VOICE": "en-US-JennyNeural"}, clear=True):
            svc = get_tts_service()
            assert svc.engines == ["chatterbox"]
            assert svc.voice == "en-US-JennyNeural"

    def test_loads_from_config_file(self):
        from api.services.tts import get_tts_service

        config_data = {"default_voice_id": "voice-abc"}
        profile_data = {"chatterbox_voice_id": "chatter-xyz"}

        def fake_exists(path):
            if "default_voice.json" in path:
                return True
            if "voice-abc.json" in path:
                return True
            return False

        def fake_open(path, *args, **kwargs):
            content = ""
            if "default_voice.json" in str(path):
                content = json.dumps(config_data)
            elif "voice-abc.json" in str(path):
                content = json.dumps(profile_data)
            return MagicMock(
                __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=content))),
                __exit__=MagicMock(return_value=False),
            )

        with patch("api.services.tts.os.path.exists", side_effect=fake_exists), \
             patch("builtins.open", side_effect=fake_open), \
             patch("json.load", side_effect=lambda f: json.loads(f.read())), \
             patch.dict(os.environ, {"TTS_ENGINE": "chatterbox"}, clear=True):
            svc = get_tts_service()
            assert svc.voice == "chatter-xyz"
