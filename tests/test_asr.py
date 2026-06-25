import os
from unittest.mock import AsyncMock, patch

import pytest


class TestASRProviderSelection:
    def test_defaults_to_faster_whisper(self):
        from api.services.asr import STT_ENGINE
        assert STT_ENGINE == "faster-whisper"

    def test_reads_deepgram_from_env(self):
        os.environ["STT_ENGINE"] = "deepgram"
        os.environ["DEEPGRAM_API_KEY"] = "test-dg-key"
        import importlib
        from api import services
        importlib.reload(services.asr)
        from api.services.asr import STT_ENGINE, DEEPGRAM_API_KEY, ASRService

        assert STT_ENGINE == "deepgram"
        assert DEEPGRAM_API_KEY == "test-dg-key"
        svc = ASRService()
        assert svc._engine == "deepgram"

        del os.environ["STT_ENGINE"]
        del os.environ["DEEPGRAM_API_KEY"]
        importlib.reload(services.asr)

    def test_falls_back_to_faster_whisper_when_deepgram_key_missing(self):
        os.environ["STT_ENGINE"] = "deepgram"
        if "DEEPGRAM_API_KEY" in os.environ:
            del os.environ["DEEPGRAM_API_KEY"]
        import importlib
        from api import services
        importlib.reload(services.asr)
        from api.services.asr import ASRService

        svc = ASRService()
        assert svc._engine == "faster-whisper"

        del os.environ["STT_ENGINE"]
        importlib.reload(services.asr)

    @patch("api.services.asr.httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_deepgram_transcribe_returns_text(self, mock_client):
        os.environ["STT_ENGINE"] = "deepgram"
        os.environ["DEEPGRAM_API_KEY"] = "test-dg-key"
        import importlib
        from api import services
        importlib.reload(services.asr)
        from api.services.asr import ASRService

        mock_post = AsyncMock()
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "results": {
                "channels": [{
                    "alternatives": [{"transcript": "hello world"}]
                }]
            }
        }
        mock_client.return_value.__aenter__.return_value.post = mock_post

        svc = ASRService()
        result = await svc.transcribe(b"fake-audio-data")
        assert result == "hello world"

        del os.environ["STT_ENGINE"]
        del os.environ["DEEPGRAM_API_KEY"]
        importlib.reload(services.asr)
