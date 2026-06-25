import json
import os
import time
import uuid

import aiohttp
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.services.auth import verify_api_key
from api.services.voice_profile_store import VoiceProfileStore

logger = structlog.get_logger()

router = APIRouter(prefix="/voice", tags=["voice"])

VOICE_CLONES_DIR = os.path.join(os.path.dirname(__file__), "../../../data/voice_clones")
os.makedirs(VOICE_CLONES_DIR, exist_ok=True)

MAX_VOICE_PROFILES = 100
_profile_store = VoiceProfileStore(max_profiles=MAX_VOICE_PROFILES)
MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024  # 10MB max upload
MIN_AUDIO_SIZE_BYTES = 32 * 1024  # ~2s at 16kHz mono 16-bit; reject trivially short clips

# Audio format magic-byte signatures
_AUDIO_MAGIC: list[tuple[bytes, str]] = [
    (b"RIFF", "wav"),      # WAV — first 4 bytes
    (b"fLaC", "flac"),    # FLAC
    (b"ID3", "mp3"),      # MP3 with ID3 tag
    (b"\xff\xfb", "mp3"), # MP3 without ID3
    (b"\xff\xf3", "mp3"), # MP3 MPEG-1 layer 3
    (b"\xff\xf2", "mp3"), # MP3 MPEG-2 layer 3
]


def _detect_audio_format(data: bytes) -> str | None:
    """Return detected audio format string or None if not a known audio format."""
    for magic, fmt in _AUDIO_MAGIC:
        if data[:len(magic)] == magic:
            return fmt
    return None


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
    temp_path = None
    try:
        # Read content and validate size BEFORE writing to disk
        content = await audio.read()
        if len(content) > MAX_AUDIO_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file too large. Max size: {MAX_AUDIO_SIZE_BYTES // (1024*1024)}MB"
            )
        if len(content) < MIN_AUDIO_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Audio file too small (got {len(content)} bytes). Need at least {MIN_AUDIO_SIZE_BYTES // 1024}KB (~2s of audio) for voice cloning."
            )

        # Validate audio format via magic bytes
        detected_fmt = _detect_audio_format(content)
        if detected_fmt is None:
            raise HTTPException(
                status_code=415,
                detail="Unsupported audio format. Upload WAV, FLAC, or MP3."
            )

        voice_id = f"voice_{uuid.uuid4().hex[:8]}"
        temp_path = os.path.join(VOICE_CLONES_DIR, f"{voice_id}_{uuid.uuid4().hex}_temp")

        with open(temp_path, "wb") as f:
            f.write(content)

        logger.info("voice_clone_started", voice_id=voice_id, voice_name=voice_name,
                    size_bytes=len(content), format=detected_fmt)

        voice_profile = await process_voice_clone(voice_id, temp_path, language)

        _profile_store.put(voice_id, voice_profile)

        final_path = os.path.join(VOICE_CLONES_DIR, f"{voice_id}.json")
        with open(final_path, "w") as f:
            json.dump(voice_profile, f, indent=2)

        logger.info("voice_clone_completed", voice_id=voice_id,
                    chatterbox_voice_id=voice_profile.get("chatterbox_voice_id"))

        return {
            "voice_id": voice_id,
            "voice_name": voice_name,
            "language": language,
            "status": "ready" if not voice_profile.get("fallback") else "fallback",
            "chatterbox_voice_id": voice_profile.get("chatterbox_voice_id"),
            "message": "Voice cloned successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("voice_clone_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Voice cloning failed: {str(e)}") from e
    finally:
        # Always clean up temp file, even on error
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


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
        "created_at": str(time.time()),
        "chatterbox_voice_id": None,  # populated below on success
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
                    # Capture the Chatterbox-assigned voice ID so TTS can reference it
                    chatterbox_id = result.get("id") or result.get("voice_id") or voice_id
                    voice_profile["chatterbox_voice_id"] = chatterbox_id
                    voice_profile.update({k: v for k, v in result.items()
                                          if k not in ("id", "voice_id")})
                    voice_profile["engine"] = "chatterbox"
                else:
                    body = await resp.text()
                    logger.warning("chatterbox_clone_bad_status",
                                   status=resp.status, body=body[:200])
                    voice_profile["fallback"] = True
    except Exception as e:
        logger.warning("chatterbox_clone_failed_using_default", error=str(e))
        voice_profile["engine"] = "chatterbox"
        voice_profile["fallback"] = True

    return voice_profile


@router.get("/clones", dependencies=[Depends(verify_api_key)])
async def list_voice_clones():
    """List all available voice clones."""
    clones = []

    # Thread-safe read of in-memory profiles
    for voice_id, profile in _profile_store.items_snapshot():
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
                if _profile_store.contains(voice_id):
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
                except (OSError, json.JSONDecodeError):
                    pass
    except OSError:
        pass  # Directory might not exist yet

    return {"voices": clones}


@router.get("/clones/{voice_id}", dependencies=[Depends(verify_api_key)])
async def get_voice_clone(voice_id: str):
    """Get details of a specific voice clone."""
    profile_copy = _profile_store.get_copy(voice_id)
    if profile_copy is not None:
        return profile_copy

    filepath = os.path.join(VOICE_CLONES_DIR, f"{voice_id}.json")
    if os.path.exists(filepath):
        with open(filepath) as f:
            return json.load(f)

    raise HTTPException(status_code=404, detail="Voice clone not found")


@router.delete("/clones/{voice_id}", dependencies=[Depends(verify_api_key)])
async def delete_voice_clone(voice_id: str):
    """Delete a voice clone."""
    _profile_store.delete(voice_id)

    filepath = os.path.join(VOICE_CLONES_DIR, f"{voice_id}.json")
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass

    return {"message": "Voice clone deleted"}


@router.post("/set-default", dependencies=[Depends(verify_api_key)])
async def set_default_voice(voice_id: str):
    """Set the default voice for TTS."""
    if not _profile_store.contains(voice_id):
        filepath = os.path.join(VOICE_CLONES_DIR, f"{voice_id}.json")
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Voice clone not found")

    config_path = os.path.join(os.path.dirname(__file__), "../../../config/default_voice.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump({"default_voice_id": voice_id}, f)

    logger.info("default_voice_set", voice_id=voice_id)
    return {"message": f"Default voice set to {voice_id}"}


@router.get("/default", dependencies=[Depends(verify_api_key)])
async def get_default_voice():
    """Get the default voice configuration."""
    config_path = os.path.join(os.path.dirname(__file__), "../../../config/default_voice.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)

    return {"default_voice_id": None, "engine": "chatterbox", "voice": "default"}
