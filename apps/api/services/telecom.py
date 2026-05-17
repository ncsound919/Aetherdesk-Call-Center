"""
Telecom Provider Abstraction Layer
Supports multiple backends: VoiceBlender, Fonoster, Telnyx
"""

import os
import uuid
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class TelecomProvider(Enum):
    VOICEBLENDER = "voiceblender"
    FONOSTER = "fonoster"
    TELNYX = "telnyx"


class TelecomBackend(ABC):
    """Abstract base class for telecom providers"""

    @abstractmethod
    async def make_call(self, to: str, from_: str, app_ref: str) -> Dict[str, Any]:
        """Initiate an outbound call"""
        pass

    @abstractmethod
    async def answer_call(self, session_ref: str) -> Dict[str, Any]:
        """Answer an incoming call"""
        pass

    @abstractmethod
    async def hangup(self, session_ref: str) -> Dict[str, Any]:
        """Hang up a call"""
        pass

    @abstractmethod
    async def play_audio(self, session_ref: str, url: str) -> Dict[str, Any]:
        """Play audio to caller"""
        pass

    @abstractmethod
    async def speak_text(self, session_ref: str, text: str, voice: str = None) -> Dict[str, Any]:
        """Speak text via TTS"""
        pass

    @abstractmethod
    async def gather_speech(self, session_ref: str, timeout_ms: int = 5000) -> Dict[str, Any]:
        """Gather speech input"""
        pass

    @abstractmethod
    async def transfer(self, session_ref: str, target: str) -> Dict[str, Any]:
        """Transfer call"""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check provider health"""
        pass


class VoiceBlenderBackend(TelecomBackend):
    """VoiceBlender - Go-based open source SIP/WebRTC/AI framework"""

    def __init__(self):
        self.base_url = os.getenv("VOICEBLENDER_URL", "http://localhost:8080")
        self.sip_port = int(os.getenv("VOICEBLENDER_SIP_PORT", "5060"))
        self.timeout = 30.0

    async def make_call(self, to: str, from_: str, app_ref: str) -> Dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # VoiceBlender uses SIP originate
                response = await client.post(
                    f"{self.base_url}/v1/legs",
                    json={
                        "to": to,
                        "from": from_,
                        "app_ref": app_ref,
                    }
                )
                if response.status_code == 201 or response.status_code == 200:
                    return {"success": True, "leg_id": response.json().get("id"), "provider": "voiceblender"}
                return {"success": False, "error": response.text, "provider": "voiceblender"}
        except Exception as e:
            logger.warning("voiceblender_call_failed", error=str(e))
            return {"success": False, "error": str(e), "provider": "voiceblender", "mock": True}

    async def answer_call(self, session_ref: str) -> Dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/v1/legs/{session_ref}/answer")
                return {"success": response.status_code == 200, "provider": "voiceblender"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "voiceblender"}

    async def hangup(self, session_ref: str) -> Dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.delete(f"{self.base_url}/v1/legs/{session_ref}")
                return {"success": response.status_code == 200, "provider": "voiceblender"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "voiceblender"}

    async def play_audio(self, session_ref: str, url: str) -> Dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/legs/{session_ref}/play",
                    json={"url": url}
                )
                return {"success": response.status_code == 200, "provider": "voiceblender"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "voiceblender"}

    async def speak_text(self, session_ref: str, text: str, voice: str = None) -> Dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/legs/{session_ref}/tts",
                    json={"text": text, "voice": voice or "default"}
                )
                return {"success": response.status_code == 200, "provider": "voiceblender"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "voiceblender"}

    async def gather_speech(self, session_ref: str, timeout_ms: int = 5000) -> Dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/legs/{session_ref}/stt",
                    json={"timeout_ms": timeout_ms}
                )
                return {"success": response.status_code == 200, "provider": "voiceblender"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "voiceblender"}

    async def transfer(self, session_ref: str, target: str) -> Dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/legs/{session_ref}/transfer",
                    json={"target": target}
                )
                return {"success": response.status_code == 200, "provider": "voiceblender"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "voiceblender"}

    async def health_check(self) -> Dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return {"healthy": response.status_code == 200, "provider": "voiceblender"}
        except Exception as e:
            return {"healthy": False, "error": str(e), "provider": "voiceblender"}


class FonosterBackend(TelecomBackend):
    """Fonoster - Already integrated in the project"""

    def __init__(self):
        from apps.api.fonoster_client import FonosterHTTPClient
        self.base_url = os.getenv("FONOSTER_URL", "http://aetherdesk-fonoster:50062")
        self.client = None

    def _get_client(self):
        if self.client is None:
            from apps.api.fonoster_client import FonosterHTTPClient
            self.client = FonosterHTTPClient(base_url=self.base_url)
        return self.client

    async def make_call(self, to: str, from_: str, app_ref: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            result = await client.create_application({
                "name": f"Outbound-{to}",
                "type": "EXTERNAL",
                "endpoint": f"tcp://aetherdesk-voice:50061",
                "variables": {"outbound_number": to, "outbound_caller_id": from_},
            })
            return {"success": True, "ref": result.get("ref"), "provider": "fonoster"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "fonoster", "mock": True}

    async def answer_call(self, session_ref: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            return await client.answer_call(session_ref)
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "fonoster"}

    async def hangup(self, session_ref: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            return await client.hangup_call(session_ref)
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "fonoster"}

    async def play_audio(self, session_ref: str, url: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            return await client.play_audio(session_ref, url)
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "fonoster"}

    async def speak_text(self, session_ref: str, text: str, voice: str = None) -> Dict[str, Any]:
        try:
            client = self._get_client()
            return await client.say_text(session_ref, text, voice=voice or "alice")
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "fonoster"}

    async def gather_speech(self, session_ref: str, timeout_ms: int = 5000) -> Dict[str, Any]:
        try:
            client = self._get_client()
            return await client.gather_speech(session_ref, timeout=timeout_ms)
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "fonoster"}

    async def transfer(self, session_ref: str, target: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            return await client.transfer_call(session_ref, target)
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "fonoster"}

    async def health_check(self) -> Dict[str, Any]:
        try:
            client = self._get_client()
            return await client.health_check()
        except Exception as e:
            return {"healthy": False, "error": str(e), "provider": "fonoster"}


class TelnyxBackend(TelecomBackend):
    """Telnyx - Commercial telecom provider"""

    def __init__(self):
        self.api_key = os.getenv("TELNYX_API_KEY", "")
        self.from_number = os.getenv("TELNYX_FROM_NUMBER", "")
        self.base_url = "https://api.telnyx.com/v2"
        self.timeout = 30.0

    async def make_call(self, to: str, from_: str, app_ref: str) -> Dict[str, Any]:
        if not self.api_key:
            return {"success": False, "error": "Telnyx API key not configured", "provider": "telnyx"}

        try:
            import httpx
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/calls",
                    json={
                        "from": from_ or self.from_number,
                        "to": to,
                        "callback_url": os.getenv("TELNYX_CALLBACK_URL", ""),
                    },
                    headers=headers
                )
                if response.status_code in (200, 201):
                    data = response.json()
                    return {
                        "success": True,
                        "call_id": data.get("data", {}).get("id"),
                        "provider": "telnyx"
                    }
                return {"success": False, "error": response.text, "provider": "telnyx"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "telnyx"}

    async def answer_call(self, session_ref: str) -> Dict[str, Any]:
        if not self.api_key:
            return {"success": False, "error": "Telnyx API key not configured", "provider": "telnyx"}

        try:
            import httpx
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/calls/{session_ref}/actions/answer",
                    headers=headers
                )
                return {"success": response.status_code == 200, "provider": "telnyx"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "telnyx"}

    async def hangup(self, session_ref: str) -> Dict[str, Any]:
        if not self.api_key:
            return {"success": False, "error": "Telnyx API key not configured", "provider": "telnyx"}

        try:
            import httpx
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/calls/{session_ref}/actions/hangup",
                    headers=headers
                )
                return {"success": response.status_code == 200, "provider": "telnyx"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "telnyx"}

    async def play_audio(self, session_ref: str, url: str) -> Dict[str, Any]:
        if not self.api_key:
            return {"success": False, "error": "Telnyx API key not configured", "provider": "telnyx"}

        try:
            import httpx
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/calls/{session_ref}/actions/speak",
                    json={"payload": url, "service": "audio"},
                    headers=headers
                )
                return {"success": response.status_code == 200, "provider": "telnyx"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "telnyx"}

    async def speak_text(self, session_ref: str, text: str, voice: str = None) -> Dict[str, Any]:
        if not self.api_key:
            return {"success": False, "error": "Telnyx API key not configured", "provider": "telnyx"}

        try:
            import httpx
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/calls/{session_ref}/actions/speak",
                    json={
                        "payload": text,
                        "voice": voice or "simon",
                        "language": "en-US"
                    },
                    headers=headers
                )
                return {"success": response.status_code == 200, "provider": "telnyx"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "telnyx"}

    async def gather_speech(self, session_ref: str, timeout_ms: int = 5000) -> Dict[str, Any]:
        if not self.api_key:
            return {"success": False, "error": "Telnyx API key not configured", "provider": "telnyx"}

        try:
            import httpx
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/calls/{session_ref}/actions/gather_speech",
                    json={"timeout_ms": timeout_ms},
                    headers=headers
                )
                return {"success": response.status_code == 200, "provider": "telnyx"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "telnyx"}

    async def transfer(self, session_ref: str, target: str) -> Dict[str, Any]:
        if not self.api_key:
            return {"success": False, "error": "Telnyx API key not configured", "provider": "telnyx"}

        try:
            import httpx
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/calls/{session_ref}/actions/transfer",
                    json={"to": target},
                    headers=headers
                )
                return {"success": response.status_code == 200, "provider": "telnyx"}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "telnyx"}

    async def health_check(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"healthy": False, "error": "Telnyx API key not configured", "provider": "telnyx"}

        try:
            import httpx
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health", headers=headers)
                return {"healthy": response.status_code == 200, "provider": "telnyx"}
        except Exception as e:
            return {"healthy": False, "error": str(e), "provider": "telnyx"}


class TelecomRouter:
    """Routes telecom requests to the appropriate backend based on configuration"""

    def __init__(self):
        self._backend: Optional[TelecomBackend] = None

    def get_backend(self, provider: TelecomProvider = None) -> TelecomBackend:
        """Get the backend for the specified provider or default"""
        if provider is None:
            default = os.getenv("DEFAULT_TELECOM_PROVIDER", "fonoster")
            provider = TelecomProvider(default)

        if self._backend is not None and isinstance(self._backend, type(self._get_backend_class(provider))):
            return self._backend

        self._backend = self._get_backend_class(provider)()
        return self._backend

    def _get_backend_class(self, provider: TelecomProvider):
        if provider == TelecomProvider.VOICEBLENDER:
            return VoiceBlenderBackend
        elif provider == TelecomProvider.FONOSTER:
            return FonosterBackend
        elif provider == TelecomProvider.TELNYX:
            return TelnyxBackend
        else:
            return FonosterBackend

    async def make_call(self, to: str, from_: str = None, provider: TelecomProvider = None) -> Dict[str, Any]:
        backend = self.get_backend(provider)
        app_ref = str(uuid.uuid4())
        return await backend.make_call(to, from_ or "", app_ref)

    async def answer_call(self, session_ref: str, provider: TelecomProvider = None) -> Dict[str, Any]:
        backend = self.get_backend(provider)
        return await backend.answer_call(session_ref)

    async def hangup(self, session_ref: str, provider: TelecomProvider = None) -> Dict[str, Any]:
        backend = self.get_backend(provider)
        return await backend.hangup(session_ref)

    async def speak(self, session_ref: str, text: str, voice: str = None, provider: TelecomProvider = None) -> Dict[str, Any]:
        backend = self.get_backend(provider)
        return await backend.speak_text(session_ref, text, voice)

    async def health_check(self, provider: TelecomProvider = None) -> Dict[str, Any]:
        backend = self.get_backend(provider)
        return await backend.health_check()


telecom_router = TelecomRouter()