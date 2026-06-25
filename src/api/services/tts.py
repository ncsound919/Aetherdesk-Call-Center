import asyncio
import io
import os
import time

import structlog

from api.middleware.metrics import track_tts_latency

logger = structlog.get_logger()


class TTSService:
    def __init__(
        self,
        engines: str = "edge",
        voice: str = "en-US-AriaNeural",
        language: str = "en"
    ):
        self.engines = [e.strip() for e in engines.split(",")]
        self.current_engine = self.engines[0]
        self.voice = voice
        self.language = language

    def _get_engine_url(self, engine: str) -> str:
        if engine == "chatterbox":
            return os.getenv("CHATTERBOX_API_URL", "http://chatterbox:5001")
        elif engine == "qwen3":
            return os.getenv("QWEN_API_URL", "http://qwen3-tts:8000")
        return None

    async def synthesize(self, text: str) -> bytes:
        start_time = time.time()
        engines_to_try = self.engines.copy()

        for engine in engines_to_try:
            try:
                logger.info("tts_trying_engine", engine=engine, text_len=len(text))
                result = await self._synthesize_with_engine(text, engine)
                if result:
                    self.current_engine = engine
                    duration = time.time() - start_time
                    track_tts_latency(duration, engine=engine)
                    return result
            except Exception as e:
                logger.warning("tts_engine_failed", engine=engine, error=str(e))
                continue

        logger.error("tts_all_engines_failed")
        raise RuntimeError("TTS synthesis failed on all configured engines")

    async def _synthesize_with_engine(self, text: str, engine: str) -> bytes:
        if engine == "chatterbox":
            return await self._synthesize_chatterbox(text)
        elif engine == "qwen3":
            return await self._synthesize_qwen3(text)
        elif engine == "edge":
            return await self._synthesize_edge(text)
        else:
            raise ValueError(f"Unknown TTS engine: {engine}")

    def _get_chatterbox_voice(self) -> str:
        config_path = os.path.join(os.path.dirname(__file__), "../../../config/default_voice.json")
        if os.path.exists(config_path):
            try:
                import json
                with open(config_path) as f:
                    config = json.load(f)
                default_voice_id = config.get("default_voice_id")
                if default_voice_id:
                    profile_path = os.path.join(os.path.dirname(__file__), "../../../data/voice_clones", f"{default_voice_id}.json")
                    if os.path.exists(profile_path):
                        with open(profile_path) as f_profile:
                            profile = json.load(f_profile)
                        return profile.get("chatterbox_voice_id") or default_voice_id
                    return default_voice_id
            except Exception as e:
                logger.warning("failed_to_resolve_chatterbox_voice", error=str(e))
        return self.voice

    async def _synthesize_chatterbox(self, text: str) -> bytes:
        import httpx
        url = self._get_engine_url("chatterbox")
        voice_id = self._get_chatterbox_voice()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{url}/tts",
                json={"text": text, "voice": voice_id}
            )
            response.raise_for_status()
            return response.content

    async def _synthesize_qwen3(self, text: str) -> bytes:
        import httpx
        url = self._get_engine_url("qwen3")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{url}/v1/tts",
                json={
                    "input": text,
                    "model": os.getenv("QWEN_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
                    "voice": self.voice
                }
            )
            response.raise_for_status()
            return response.content

    async def _synthesize_edge(self, text: str) -> bytes:
        from RealtimeTTS import EdgeEngine, TextToAudioStream
        audio_chunks = []

        def on_audio_chunk(chunk):
            if chunk:
                audio_chunks.append(chunk)

        loop = asyncio.get_running_loop()
        def run_synthesis():
            engine = EdgeEngine(voice=self.voice)
            try:
                stream = TextToAudioStream(engine, on_audio_chunk=on_audio_chunk)
                stream.feed(text)
                stream.play(fast_sentence_fragment=True, buffer_threshold_seconds=0.1)
            finally:
                engine.shutdown()

        await loop.run_in_executor(None, run_synthesis)

        if audio_chunks:
            return b''.join(audio_chunks)
        raise Exception("Edge TTS returned no audio")

    async def synthesize_streaming(self, text: str):
        """Async generator that yields audio chunks as they are synthesized."""
        engine = self.current_engine

        if engine == "chatterbox":
            async for chunk in self._stream_chatterbox(text):
                yield chunk
        elif engine == "qwen3":
            async for chunk in self._stream_qwen3(text):
                yield chunk
        else:
            async for chunk in self._stream_edge(text):
                yield chunk

    async def _stream_chatterbox(self, text: str):
        import httpx
        url = self._get_engine_url("chatterbox")
        voice_id = self._get_chatterbox_voice()
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                f"{url}/tts/stream",
                json={"text": text, "voice": voice_id}
            ) as response:
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk

    async def _stream_qwen3(self, text: str):
        import httpx
        url = self._get_engine_url("qwen3")
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{url}/v1/tts/stream",
                json={
                    "input": text,
                    "model": os.getenv("QWEN_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
                }
            ) as response:
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk

    async def _stream_edge(self, text: str):
        from RealtimeTTS import EdgeEngine, TextToAudioStream
        q = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_audio_chunk(chunk):
            if chunk:
                loop.call_soon_threadsafe(q.put_nowait, chunk)

        def run_synthesis():
            try:
                engine = EdgeEngine(voice=self.voice)
                stream = TextToAudioStream(engine, on_audio_chunk=on_audio_chunk)
                stream.feed(text)
                stream.play(fast_sentence_fragment=True, buffer_threshold_seconds=0.1)
                engine.shutdown()
            except Exception as e:
                logger.error("tts_streaming_error", error=str(e))
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        synthesis_future = loop.run_in_executor(None, run_synthesis)

        try:
            while True:
                chunk = await asyncio.wait_for(q.get(), timeout=30.0)
                if chunk is None:
                    break
                yield chunk
        except TimeoutError:
            logger.error("tts_streaming_timeout", text_preview=text[:50])
        finally:
            if not synthesis_future.done():
                synthesis_future.cancel()

    async def synthesize_stream(self, text: str) -> io.BytesIO:
        audio_bytes = await self.synthesize(text)
        return io.BytesIO(audio_bytes)


def get_tts_service() -> TTSService:
    engines = os.getenv("TTS_ENGINE", "edge")
    voice = os.getenv("TTS_VOICE", "en-US-AriaNeural")

    # Load default voice from config if exists
    config_path = os.path.join(os.path.dirname(__file__), "../../../config/default_voice.json")
    if os.path.exists(config_path):
        try:
            import json
            with open(config_path) as f:
                config = json.load(f)
            default_voice_id = config.get("default_voice_id")
            if default_voice_id:
                profile_path = os.path.join(os.path.dirname(__file__), "../../../data/voice_clones", f"{default_voice_id}.json")
                if os.path.exists(profile_path):
                    with open(profile_path) as f_profile:
                        profile = json.load(f_profile)
                    chatterbox_voice_id = profile.get("chatterbox_voice_id")
                    if chatterbox_voice_id:
                        voice = chatterbox_voice_id
                    else:
                        voice = default_voice_id
                else:
                    voice = default_voice_id
        except Exception as e:
            logger.warning("failed_to_load_default_voice", error=str(e))

    return TTSService(engines=engines, voice=voice)


tts_service = get_tts_service()


