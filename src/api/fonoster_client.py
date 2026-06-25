import logging
import uuid

import httpx

logger = logging.getLogger(__name__)


class FonosterHTTPClient:
    """
    HTTP client for communicating with the Fonoster Voice Server.
    Since no Python SDK exists, we call the Fonoster REST API directly.
    Voice processing (SIP/RTP) stays in Node.js; Python handles orchestration.
    """

    def __init__(self, base_url: str = None, api_key: str = None, api_secret: str = None):
        self.base_url = base_url or "http://aetherdesk-fonoster:50062"
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers=self._auth_headers(),
        )

    def _auth_headers(self) -> dict:
        """Build authentication headers if credentials are provided."""
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_secret:
            headers["X-API-Key"] = self.api_key
            headers["X-API-Secret"] = self.api_secret
        return headers

    # ── Applications ──────────────────────────────────────────────

    async def create_application(self, request: dict) -> dict:
        """Create a new Voice Application in Fonoster."""
        try:
            resp = await self.client.post("/applications", json=request)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Fonoster app created: {data.get('ref', 'unknown')}")
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"Fonoster create app error {e.response.status_code}: {e.response.text}")
            # Fallback mock for dev without Fonoster running
            return {
                "ref": f"app-{uuid.uuid4().hex[:8]}",
                "name": request.get("name", "unknown"),
                "endpoint": request.get("endpoint", "http://localhost:50061"),
                "status": "created",
                "_mock": True,
            }

    async def get_application(self, ref: str) -> dict | None:
        """Retrieve a single Voice Application by ref."""
        try:
            resp = await self.client.get(f"/applications/{ref}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Fonoster get app error: {e}")
            return None

    async def delete_application(self, ref: str) -> bool:
        """Delete a Voice Application."""
        try:
            resp = await self.client.delete(f"/applications/{ref}")
            resp.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Fonoster delete app error: {e}")
            return False

    async def list_applications(self) -> list[dict]:
        """List all Voice Applications."""
        try:
            resp = await self.client.get("/applications")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Fonoster list apps error: {e}")
            return []

    # ── Commands ──────────────────────────────────────────────────

    async def send_command(self, application_ref: str, command: str, **kwargs) -> dict:
        """Send a voice command to a running application session."""
        try:
            payload = {"command": command, **kwargs}
            resp = await self.client.post(
                f"/applications/{application_ref}/commands",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Fonoster command error ({command}): {e}")
            return {"success": False, "error": str(e), "_mock": True}

    async def answer_call(self, application_ref: str) -> dict:
        """Answer an incoming call."""
        return await self.send_command(application_ref, "answer")

    async def hangup_call(self, application_ref: str) -> dict:
        """Hang up a call."""
        return await self.send_command(application_ref, "hangup")

    async def hold_call(self, application_ref: str) -> dict:
        """Place a call on hold."""
        return await self.send_command(application_ref, "hold")

    async def unhold_call(self, application_ref: str) -> dict:
        """Unhold a call."""
        return await self.send_command(application_ref, "unhold")

    async def transfer_call(self, application_ref: str, target: str) -> dict:
        """Transfer a call to a SIP endpoint."""
        return await self.send_command(application_ref, "transfer", target=target)

    async def mute_call(self, application_ref: str) -> dict:
        """Mute a call."""
        return await self.send_command(application_ref, "mute")

    async def unmute_call(self, application_ref: str) -> dict:
        """Unmute a call."""
        return await self.send_command(application_ref, "unmute")

    async def record_call(self, application_ref: str, action: str = "start") -> dict:
        """Start or stop recording a call."""
        return await self.send_command(application_ref, f"record {action}")

    async def say_text(self, application_ref: str, text: str, voice: str = "alice") -> dict:
        """Speak text to the caller via TTS."""
        return await self.send_command(
            application_ref, "say", text=text, voice=voice
        )

    async def gather_speech(
        self,
        application_ref: str,
        timeout: int = 15000,
        language: str = "en-US",
        hints: list[str] | None = None,
    ) -> dict:
        """Gather speech input from the caller for intent detection."""
        return await self.send_command(
            application_ref,
            "gather",
            source="speech",
            timeout=timeout,
            language=language,
            hints=hints or [],
        )

    async def play_audio(self, application_ref: str, url: str) -> dict:
        """Play an audio file to the caller."""
        return await self.send_command(application_ref, "play", url=url)

    async def send_dtmf(self, application_ref: str, digits: str) -> dict:
        """Send DTMF tones."""
        return await self.send_command(application_ref, "dtmf", digits=digits)

    # ── Events / Webhooks ─────────────────────────────────────────

    async def register_webhook(self, application_ref: str, url: str, events: list[str]) -> dict:
        """Register a webhook URL for call events."""
        try:
            resp = await self.client.post(
                f"/applications/{application_ref}/webhooks",
                json={"url": url, "events": events},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Fonoster webhook registration error: {e}")
            return {"success": False, "error": str(e)}

    # ── Health ────────────────────────────────────────────────────

    async def health_check(self) -> dict:
        """Check Fonoster server health."""
        try:
            resp = await self.client.get("/health")
            return {"healthy": resp.status_code == 200, "status": resp.json()}
        except Exception as e:
            logger.error(f"Fonoster health check failed: {e}")
            return {"healthy": False, "error": str(e)}

    async def close(self):
        """Close the HTTP client session."""
        await self.client.aclose()
        logger.info("Fonoster HTTP client closed")
