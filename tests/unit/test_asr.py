import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np


class TestASRServiceInit:
    def test_default_initialization(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        assert svc.model_size == "base"
        assert svc.device == "auto"
        assert svc._model is None

    def test_custom_initialization(self):
        from apps.api.services.asr import ASRService

        svc = ASRService(model_size="large-v3", device="cpu")
        assert svc.model_size == "large-v3"
        assert svc.device == "cpu"


class TestASRServiceLoadModel:
    @pytest.mark.asyncio
    async def test_initialize_loads_model(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()

        with patch.object(svc, "_load_model") as mock_load:
            await svc.initialize()
            mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_skips_if_loaded(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        svc._model = MagicMock()

        with patch.object(svc, "_load_model") as mock_load:
            await svc.initialize()
            mock_load.assert_not_called()

    def test_load_model_success(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()

        with patch("apps.api.services.asr.WhisperModel") as mock_whisper:
            svc._load_model()
            mock_whisper.assert_called_once_with("base", device="auto", compute_type="int8")
            assert svc._model is not None

    def test_load_model_fallback_on_error(self):
        from apps.api.services.asr import ASRService
        from faster_whisper import WhisperModel

        svc = ASRService(device="cuda")

        with patch("apps.api.services.asr.WhisperModel") as mock_whisper:
            mock_whisper.side_effect = [
                Exception("float16 not supported"),
                MagicMock(spec=WhisperModel)
            ]
            svc._load_model()

            assert mock_whisper.call_count == 2
            mock_whisper.assert_any_call("base", device="cuda", compute_type="float16")
            mock_whisper.assert_called_with("base", device="cpu", compute_type="int8")


class TestASRServiceTranscribe:
    @pytest.mark.asyncio
    async def test_transcribe_success(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "hello world"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        svc._model = mock_model

        audio_data = np.array([100, 200, 300], dtype=np.int16).tobytes()

        with patch("apps.api.middleware.metrics.ASR_LATENCY"):
            result = await svc.transcribe(audio_data, language="en")

        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_transcribe_auto_initialize(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "test"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())

        audio_data = np.array([100, 200], dtype=np.int16).tobytes()

        with patch.object(svc, "initialize", new_callable=AsyncMock) as mock_init, \
             patch("apps.api.middleware.metrics.ASR_LATENCY"):
            svc._model = mock_model
            result = await svc.transcribe(audio_data)

        assert result == "test"

    @pytest.mark.asyncio
    async def test_transcribe_error_returns_empty_string(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = Exception("transcription failed")
        svc._model = mock_model

        audio_data = np.array([100], dtype=np.int16).tobytes()

        with patch("apps.api.middleware.metrics.ASR_LATENCY"):
            result = await svc.transcribe(audio_data)

        assert result == ""

    @pytest.mark.asyncio
    async def test_transcribe_tracks_latency(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "latency test"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        svc._model = mock_model

        audio_data = np.array([100], dtype=np.int16).tobytes()

        with patch("apps.api.services.asr.track_asr_latency") as mock_track:
            await svc.transcribe(audio_data)

        mock_track.assert_called_once()
        _, kwargs = mock_track.call_args
        assert kwargs.get("engine") == "faster-whisper"


class TestASRServiceTranscribeStreaming:
    @pytest.mark.asyncio
    async def test_transcribe_streaming_success(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "streaming result"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        svc._model = mock_model

        audio_data = np.zeros(32000, dtype=np.int16).tobytes()

        with patch("apps.api.middleware.metrics.ASR_LATENCY"):
            result = await svc.transcribe_streaming(audio_data)

        assert result == "streaming result"

    @pytest.mark.asyncio
    async def test_transcribe_streaming_short_audio_returns_none(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        svc._model = MagicMock()

        audio_data = np.zeros(100, dtype=np.int16).tobytes()

        result = await svc.transcribe_streaming(audio_data)
        assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_streaming_auto_initialize(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "stream"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())

        audio_data = np.zeros(32000, dtype=np.int16).tobytes()

        with patch.object(svc, "initialize", new_callable=AsyncMock) as mock_init, \
             patch("apps.api.middleware.metrics.ASR_LATENCY"):
            svc._model = mock_model
            result = await svc.transcribe_streaming(audio_data)

        assert result == "stream"

    @pytest.mark.asyncio
    async def test_transcribe_streaming_error_returns_none(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = Exception("stream error")
        svc._model = mock_model

        audio_data = np.zeros(32000, dtype=np.int16).tobytes()

        with patch("apps.api.middleware.metrics.ASR_LATENCY"):
            result = await svc.transcribe_streaming(audio_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_streaming_empty_text_returns_none(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "   "
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        svc._model = mock_model

        audio_data = np.zeros(32000, dtype=np.int16).tobytes()

        with patch("apps.api.middleware.metrics.ASR_LATENCY"):
            result = await svc.transcribe_streaming(audio_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_streaming_tracks_latency(self):
        from apps.api.services.asr import ASRService

        svc = ASRService()
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "tracked"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        svc._model = mock_model

        audio_data = np.zeros(32000, dtype=np.int16).tobytes()

        with patch("apps.api.services.asr.track_asr_latency") as mock_track:
            await svc.transcribe_streaming(audio_data)

        mock_track.assert_called_once()
