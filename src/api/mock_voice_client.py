import logging
import os
import uuid

logger = logging.getLogger(__name__)


class MockVoiceClient:
    """Mock voice client — logs calls instead of placing them.

    Used when neither Fonoster nor Twilio is configured.
    Allows all routes and call flows to be tested without telephony.
    """

    ACTIVE_CALL_TTL = 3600  # 1 hour max for completed calls in memory

    def __init__(self):
        self.active_calls: dict[str, dict] = {}
        self._call_created_at: dict[str, float] = {}

    def _cleanup_expired_calls(self):
        """Remove completed calls older than TTL from memory."""
        import time
        now = time.time()
        expired = [
            ref for ref, info in list(self.active_calls.items())
            if info.get("status") in ("completed", "failed", "canceled")
            and now - self._call_created_at.get(ref, now) > self.ACTIVE_CALL_TTL
        ]
        for ref in expired:
            self.active_calls.pop(ref, None)
            self._call_created_at.pop(ref, None)

    async def create_application(self, request: dict) -> dict:
        self._cleanup_expired_calls()
        import time as _time
        variables = request.get("variables", {})
        to_phone = variables.get("outbound_number", "unknown")
        caller_id = variables.get("outbound_caller_id", os.getenv("TWILIO_FROM_NUMBER", "mock"))

        call_ref = f"MOCK-{uuid.uuid4().hex[:8].upper()}"
        self._call_created_at[call_ref] = _time.time()
        self.active_calls[call_ref] = {
            "to": to_phone,
            "from": caller_id,
            "status": "queued",
            "ref": call_ref,
        }

        logger.info(
            "MOCK outbound call",
            ref=call_ref,
            to=to_phone,
            from_=caller_id,
        )
        print(f"\n  === MOCK CALL: {to_phone} (ref: {call_ref}) ===")
        print("  Set TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_FROM_NUMBER")
        print("  in .env to place real calls via Twilio.\n")

        return {"ref": call_ref, "status": "queued", "sid": call_ref, "_mock": True}

    async def get_application(self, ref: str) -> dict | None:
        self._cleanup_expired_calls()
        return self.active_calls.get(ref)

    async def health_check(self) -> dict:
        return {"healthy": True, "provider": "mock", "detail": "Mock mode — calls are not placed"}

    async def close(self):
        logger.info("Mock voice client closed")

    async def list_applications(self) -> list:
        return list(self.active_calls.values())

    async def delete_application(self, ref: str) -> bool:
        self.active_calls.pop(ref, None)
        return True

    async def answer_call(self, app_ref: str) -> dict:
        return {"success": True, "_mock": True}

    async def hangup_call(self, app_ref: str) -> dict:
        return {"success": True, "_mock": True}

    async def hold_call(self, app_ref: str) -> dict:
        return {"success": True, "_mock": True}

    async def unhold_call(self, app_ref: str) -> dict:
        return {"success": True, "_mock": True}

    async def transfer_call(self, app_ref: str, target: str) -> dict:
        return {"success": True, "_mock": True}

    async def mute_call(self, app_ref: str) -> dict:
        return {"success": True, "_mock": True}

    async def unmute_call(self, app_ref: str) -> dict:
        return {"success": True, "_mock": True}

    async def record_call(self, app_ref: str, action: str = "start") -> dict:
        return {"success": True, "_mock": True}

    async def say_text(self, app_ref: str, text: str, voice: str = "alice") -> dict:
        return {"success": True, "_mock": True}

    async def gather_speech(self, app_ref: str, timeout: int = 15000, language: str = "en-US", hints: list[str] | None = None) -> dict:
        return {"success": True, "text": "(mock input)", "_mock": True}

    async def play_audio(self, app_ref: str, url: str) -> dict:
        return {"success": True, "_mock": True}

    async def send_dtmf(self, app_ref: str, digits: str) -> dict:
        return {"success": True, "_mock": True}

    async def send_command(self, app_ref: str, command: str, **kwargs) -> dict:
        return {"success": True, "command": command, "_mock": True}

    async def register_webhook(self, app_ref: str, url: str, events: list[str]) -> dict:
        return {"success": True, "_mock": True}
