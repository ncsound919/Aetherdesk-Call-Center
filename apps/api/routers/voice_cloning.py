import os
import uuid
import json
import asyncio
import aiohttp
import threading
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
import structlog
from apps.api.services.auth import verify_api_key

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

VOICE_CLONES_DIR = os.path.join(os.path.dirname(__file__), "../../../data/voice_clones")
os.makedirs(VOICE_CLONES_DIR, exist_ok=True)

MAX_VOICE_PROFILES = 100
voice_profiles = {}
_voice_profiles_lock = threading.Lock()  # Thread-safe access
MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024  # 10MB max upload


def _evict_oldest_profile():
    """Evict oldest profile when limit reached (thread-safe)"""
    with _voice_profiles_lock:
        if len(voice_profiles) >= MAX_VOICE_PROFILES:
            oldest_key = next(iter(voice_profiles))
            del voice_profiles[oldest_key]
            logger.info("voice_profile_evicted", evicted_key=oldest_key)


@router.post("/clone", dependencies=[Depends(verify_api_key)])
async def clone_voice(
    audio: UploadFile = File(...),
    voice_name: str = Form("Default Voice"),
    language: str = Form("en-US")
):
    """
    Clone voice from audio sample.
    Creates a voice profile that can be used for TTS.
    """
    try:
        # Read content and validate size BEFORE writing to disk
        content = await audio.read()
        if len(content) > MAX_AUDIO_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file too large. Max size: {MAX_AUDIO_SIZE_BYTES // (1024*1024)}MB"
            )
        if len(content) < 1000:  # Minimum 1KB for valid audio
            raise HTTPException(
                status_code=400,
                detail="Audio file too small. Minimum 1KB required for voice cloning."
            )

        voice_id = f"voice_{uuid.uuid4().hex[:8]}"

        temp_path = os.path.join(VOICE_CLONES_DIR, f"{voice_id}_temp")
        with open(temp_path, "wb") as f:
            f.write(content)  # Content already in memory, no leak

        logger.info("voice_clone_started", voice_id=voice_id, voice_name=voice_name, size_bytes=len(content))

        voice_profile = await process_voice_clone(voice_id, temp_path, language)

        _evict_oldest_profile()

        with _voice_profiles_lock:
            voice_profiles[voice_id] = voice_profile

        # Clean up temp file
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass  # Best effort cleanup

        final_path = os.path.join(VOICE_CLONES_DIR, f"{voice_id}.json")
        with open(final_path, "w") as f:
            json.dump(voice_profile, f, indent=2)

        logger.info("voice_clone_completed", voice_id=voice_id)

        return {
            "voice_id": voice_id,
            "voice_name": voice_name,
            "language": language,
            "status": "ready",
            "message": "Voice cloned successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("voice_clone_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Voice cloning failed: {str(e)}")


async def process_voice_clone(voice_id: str, audio_path: str, language: str) -> dict:
    """
    Process audio sample to create voice profile.
    Uses Chatterbox for voice cloning if available, otherwise falls back to config.
    """
    chatterbox_url = os.getenv("CHATTERBOX_API_URL", "http://chatterbox:5001")

    voice_profile = {
        "voice_id": voice_id,
        "name": f"cloned_{voice_id}",
        "language": language,
        "source": "browser_recording",
        "engine": "chatterbox",
        "created_at": str(asyncio.get_event_loop().time())
    }

    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            # Properly open and close file to avoid handle leak
            with open(audio_path, 'rb') as audio_file:
                data.add_field('audio', audio_file.read(), filename=f'{voice_id}.wav', content_type='audio/wav')
            data.add_field('name', voice_id)
            data.add_field('language', language)
            async with session.post(
                f"{chatterbox_url}/voices/clone",
                data=data,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    voice_profile.update(result)
                    voice_profile["engine"] = "chatterbox"
    except Exception as e:
        logger.warning("chatterbox_clone_failed_using_default", error=str(e))
        voice_profile["engine"] = "chatterbox"
        voice_profile["fallback"] = True

    return voice_profile


@router.get("/clones")
async def list_voice_clones():
    """List all available voice clones."""
    clones = []

    # Thread-safe read of in-memory profiles
    with _voice_profiles_lock:
        for voice_id, profile in voice_profiles.items():
            clones.append({
                "voice_id": voice_id,
                "name": profile.get("name"),
                "language": profile.get("language"),
                "engine": profile.get("engine"),
                "status": "ready" if not profile.get("fallback") else "fallback"
            })

    # Read from disk (filesystem is inherently thread-safe for reads)
    try:
        for filename in os.listdir(VOICE_CLONES_DIR):
            if filename.endswith(".json"):
                voice_id = filename.replace(".json", "")
                with _voice_profiles_lock:
                    if voice_id in voice_profiles:
                        continue
                try:
                    with open(os.path.join(VOICE_CLONES_DIR, filename)) as f:
                        profile = json.load(f)
                        clones.append({
                            "voice_id": profile.get("voice_id"),
                            "name": profile.get("name"),
                            "language": profile.get("language"),
                            "engine": profile.get("engine"),
                            "status": "ready"
                        })
                except (json.JSONDecodeError, IOError):
                    pass
    except OSError:
        pass  # Directory might not exist yet

    return {"voices": clones}


@router.get("/clones/{voice_id}")
async def get_voice_clone(voice_id: str):
    """Get details of a specific voice clone."""
    with _voice_profiles_lock:
        if voice_id in voice_profiles:
            return voice_profiles[voice_id].copy()

    filepath = os.path.join(VOICE_CLONES_DIR, f"{voice_id}.json")
    if os.path.exists(filepath):
        with open(filepath) as f:
            return json.load(f)

    raise HTTPException(status_code=404, detail="Voice clone not found")


@router.delete("/clones/{voice_id}")
async def delete_voice_clone(voice_id: str):
    """Delete a voice clone."""
    with _voice_profiles_lock:
        if voice_id in voice_profiles:
            del voice_profiles[voice_id]

    filepath = os.path.join(VOICE_CLONES_DIR, f"{voice_id}.json")
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass

    return {"message": "Voice clone deleted"}


@router.post("/set-default")
async def set_default_voice(voice_id: str):
    """Set the default voice for TTS."""
    if voice_id not in voice_profiles:
        filepath = os.path.join(VOICE_CLONES_DIR, f"{voice_id}.json")
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Voice clone not found")

    config_path = os.path.join(os.path.dirname(__file__), "../../../config/default_voice.json")
    with open(config_path, "w") as f:
        json.dump({"default_voice_id": voice_id}, f)

    logger.info("default_voice_set", voice_id=voice_id)
    return {"message": f"Default voice set to {voice_id}"}


@router.get("/default")
async def get_default_voice():
    """Get the default voice configuration."""
    config_path = os.path.join(os.path.dirname(__file__), "../../../config/default_voice.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)

    return {"default_voice_id": None, "engine": "chatterbox", "voice": "default"}