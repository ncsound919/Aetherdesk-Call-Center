import time

import httpx
import structlog

logger = structlog.get_logger()

_vendor_status: dict[str, dict] = {}
_last_check: float = 0
CHECK_INTERVAL = 60  # seconds

class VendorHealthMonitor:
    async def check_all_vendors(self) -> dict:
        """Check health of all external vendors."""
        global _last_check
        now = time.time()
        if now - _last_check < CHECK_INTERVAL:
            return _vendor_status

        results = {}
        results["twilio"] = await self._check_twilio()
        results["deepgram"] = await self._check_deepgram()
        results["groq"] = await self._check_groq()
        results["chatterbox"] = await self._check_chatterbox()

        _vendor_status.update(results)
        _last_check = now

        # Check for any degraded vendors
        degraded = [name for name, status in results.items() if status["status"] != "healthy"]
        if degraded:
            logger.warning("vendor_degradation_detected", vendors=degraded)

        return results

    async def _check_twilio(self) -> dict:
        """Check Twilio API health."""
        import os
        sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        token = os.getenv("TWILIO_AUTH_TOKEN", "")
        if not sid or not token:
            return {"status": "not_configured", "message": "No Twilio credentials"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
                    auth=(sid, token)
                )
                if resp.status_code == 200:
                    return {"status": "healthy", "latency_ms": int(resp.elapsed.total_seconds() * 1000)}
                return {"status": "degraded", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def _check_deepgram(self) -> dict:
        """Check Deepgram API health."""
        import os
        key = os.getenv("DEEPGRAM_API_KEY", "")
        if not key:
            return {"status": "not_configured", "message": "No Deepgram API key"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.deepgram.com/v1/projects",
                    headers={"Authorization": f"Token {key}"}
                )
                if resp.status_code in (200, 401):
                    return {"status": "healthy"}
                return {"status": "degraded", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def _check_groq(self) -> dict:
        """Check Groq API health."""
        import os
        key = os.getenv("GROQ_API_KEY", "")
        if not key:
            return {"status": "not_configured", "message": "No Groq API key"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if resp.status_code == 200:
                    return {"status": "healthy"}
                return {"status": "degraded", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def _check_chatterbox(self) -> dict:
        """Check Chatterbox TTS health."""
        import os
        url = os.getenv("CHATTERBOX_API_URL", "http://chatterbox:5001")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{url}/health")
                if resp.status_code == 200:
                    return {"status": "healthy"}
                return {"status": "degraded", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def get_vendor_status(self) -> dict:
        return dict(_vendor_status)

    def get_degraded_vendors(self) -> list:
        return [name for name, status in _vendor_status.items() if status.get("status") != "healthy"]

vendor_health_monitor = VendorHealthMonitor()
