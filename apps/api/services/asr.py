import asyncio
import time

import numpy as np
import structlog
from faster_whisper import WhisperModel

from apps.api.middleware.metrics import track_asr_latency

logger = structlog.get_logger()

class ASRService:
    def __init__(self, model_size: str = "base", device: str = "auto"):
        self.model_size = model_size
        self.device = device
        self._model: WhisperModel | None = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        if self._model is None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._load_model)

    def _load_model(self):
        try:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type="float16" if self.device == "cuda" else "int8"
            )
        except Exception:
            # Fallback for devices that don't support float16
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8"
            )

    async def transcribe(self, audio_data: bytes, language: str = "en") -> str:
        if self._model is None:
            await self.initialize()

        start_time = time.time()
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_float32 = audio_array.astype(np.float32) / 32768.0

            loop = asyncio.get_running_loop()
            segments, info = await loop.run_in_executor(
                None,
                lambda: self._model.transcribe(audio_float32, language=language, beam_size=5)
            )

            text = " ".join([segment.text for segment in segments])
            return text.strip()
        except Exception as e:
            logger.error("asr_transcription_error", error=str(e))
            return ""
        finally:
            duration = time.time() - start_time
            track_asr_latency(duration, engine="faster-whisper")

    async def transcribe_streaming(self, audio_chunk: bytes) -> str | None:
        if self._model is None:
            await self.initialize()

        start_time = time.time()
        audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
        if len(audio_array) < 1600:
            return None

        audio_float32 = audio_array.astype(np.float32) / 32768.0

        loop = asyncio.get_running_loop()
        try:
            segments, _ = await loop.run_in_executor(
                None,
                lambda: self._model.transcribe(audio_float32, language="en", beam_size=1)
            )
            text = " ".join([s.text for s in segments])
            return text.strip() if text.strip() else None
        except Exception:
            return None
        finally:
            duration = time.time() - start_time
            track_asr_latency(duration, engine="faster-whisper")


asr_service = ASRService(model_size="base", device="auto")
