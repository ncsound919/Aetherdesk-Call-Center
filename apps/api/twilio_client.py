import logging
import os
from typing import Any

from twilio.rest import Client as TwilioRestClient

logger = logging.getLogger(__name__)


class TwilioVoiceClient:
    """Drop-in replacement for FonosterHTTPClient using Twilio REST API.

    Makes outbound calls via Twilio instead of FreeSWITCH/Fonoster.
    No Docker or local SIP infrastructure required.
    """

    ACTIVE_CALL_TTL = 3600  # 1 hour max for completed calls in memory

    def __init__(self):
        account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.getenv("TWILIO_FROM_NUMBER", "")
        self.webhook_base = os.getenv("TWILIO_WEBHOOK_BASE", os.getenv("API_URL", "http://localhost:8000"))

        if not account_sid or not auth_token:
            logger.warning("Twilio credentials not configured — calls will be simulated")
            self.client = None
        else:
            self.client = TwilioRestClient(account_sid, auth_token)

        self.active_calls: dict[str, dict] = {}
        self._call_created_at: dict[str, float] = {}

    def _cleanup_expired_calls(self):
        """Remove completed calls older than TTL from memory."""
        import time
        now = time.time()
        expired = [
            sid for sid, info in list(self.active_calls.items())
            if info.get("status") in ("completed", "failed", "canceled")
            and now - self._call_created_at.get(sid, now) > self.ACTIVE_CALL_TTL
        ]
        for sid in expired:
            self.active_calls.pop(sid, None)
            self._call_created_at.pop(sid, None)

    async def create_application(self, request: dict) -> dict:
        """Create a voice application / initiate an outbound call.

        Mirrors the FonosterHTTPClient.create_application interface.
        """
        self._cleanup_expired_calls()
        variables = request.get("variables", {})
        to_phone = variables.get("outbound_number", "")
        caller_id = variables.get("outbound_caller_id", self.from_number)

        if not to_phone:
            logger.error("Twilio outbound call missing to_phone")
            return {"ref": None, "status": "failed", "error": "Missing to_phone"}

        return await self._place_call(to_phone, caller_id)

    async def _place_call(self, to_phone: str, caller_id: str | None = None) -> dict:
        """Place an outbound call via Twilio REST API."""
        caller_id = caller_id or self.from_number
        call_sid = f"TW-{os.urandom(4).hex().upper()}"

        status_callback = f"{self.webhook_base}/webhooks/twilio/call-status"
        voice_url = f"{self.webhook_base}/webhooks/twilio/voice"

        if self.client is None:
            logger.info(f"MOCK call to {to_phone} from {caller_id} — Twilio not configured")
            import time as _time
            self._call_created_at[call_sid] = _time.time()
            self.active_calls[call_sid] = {
                "to": to_phone,
                "from": caller_id,
                "status": "queued",
                "ref": call_sid,
            }
            return {"ref": call_sid, "status": "queued", "sid": call_sid, "_mock": True}

        try:
            call = self.client.calls.create(
                to=to_phone,
                from_=caller_id,
                url=voice_url,
                status_callback=status_callback,
                status_callback_event=["initiated", "ringing", "answered", "completed"],
                timeout=30,
            )
            sid = call.sid
            import time as _time
            self._call_created_at[sid] = _time.time()
            self.active_calls[sid] = {
                "to": to_phone,
                "from": caller_id,
                "status": "initiated",
                "ref": sid,
            }
            logger.info(f"Twilio call placed: {sid} -> {to_phone}")
            return {"ref": sid, "status": "queued", "sid": sid}

        except Exception as e:
            logger.error(f"Twilio call failed: {e}")
            return {"ref": call_sid, "status": "failed", "error": str(e), "_mock": True}

    async def get_application(self, ref: str) -> dict | None:
        """Get call details by SID."""
        self._cleanup_expired_calls()
        if self.client is None:
            info = self.active_calls.get(ref)
            return info
        try:
            call = self.client.calls(ref).fetch()
            return {"ref": call.sid, "status": call.status, "to": call.to, "from": call.from_}
        except Exception as e:
            logger.error(f"Twilio get call failed: {e}")
            return None

    async def health_check(self) -> dict:
        """Check if Twilio client is operational."""
        if self.client is None:
            return {"healthy": False, "provider": "twilio", "detail": "Not configured"}
        try:
            self.client.api.accounts.get().fetch()
            return {"healthy": True, "provider": "twilio"}
        except Exception as e:
            return {"healthy": False, "provider": "twilio", "error": str(e)}

    async def close(self):
        """No-op for Twilio client."""
        logger.info("Twilio client closed")

    async def list_applications(self) -> list[dict]:
        return []

    async def delete_application(self, ref: str) -> bool:
        return True

    async def send_command(self, app_ref: str, command: str, **kwargs) -> dict:
        return {"success": False, "error": "Not supported via Twilio API"}

    async def answer_call(self, app_ref: str) -> dict:
        return {"success": False, "error": "Not supported via Twilio API"}

    async def hangup_call(self, app_ref: str) -> dict:
        try:
            if self.client and app_ref.startswith("CA"):
                self.client.calls(app_ref).update(status="completed")
                return {"success": True}
            return {"success": True, "_mock": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def say_text(self, app_ref: str, text: str, voice: str = "alice") -> dict:
        return {"success": True, "_mock": True}

    async def gather_speech(self, app_ref: str, timeout: int = 15000, language: str = "en-US", hints: list[str] | None = None) -> dict:
        return {"success": True, "text": "", "_mock": True}
