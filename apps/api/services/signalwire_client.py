import os
import logging
from twilio.rest import Client
from typing import Optional

logger = logging.getLogger(__name__)

class SignalWireClient:
    def __init__(self):
        self.project_id = os.getenv("SIGNALWIRE_PROJECT_ID", "8d9f65dd-efe2-4c2f-80ca-c317a9b00610")
        self.api_token = os.getenv("SIGNALWIRE_API_TOKEN")
        self.space_url = os.getenv("SIGNALWIRE_SPACE_URL", "overlay365.signalwire.com")
        self.from_number = os.getenv("SIGNALWIRE_FROM_NUMBER", "+15555555555")
        
        if self.project_id and self.api_token:
            # Twilio SDK allows custom base URL for SignalWire compatibility
            from twilio.http.http_client import TwilioHttpClient
            http_client = TwilioHttpClient()
            self.client = Client(self.project_id, self.api_token, http_client=http_client)
            self.client.http_client.session.auth = (self.project_id, self.api_token)
            # Signalwire space URL
            self.base_url = f"https://{self.space_url}"
        else:
            self.client = None

    def make_call(self, to_phone: str, webhook_url: str) -> dict:
        """Trigger an outbound call using SignalWire."""
        if not self.client:
            logger.warning("SignalWire credentials not fully configured. Using mock fallback.")
            import uuid
            return {
                "ref": f"app-{uuid.uuid4().hex[:8]}",
                "status": "queued",
                "_mock": True
            }

        try:
            # We construct the REST API call directly since Twilio SDK region overrides can be tricky
            import requests
            url = f"https://{self.space_url}/api/laml/2010-04-01/Accounts/{self.project_id}/Calls.json"
            payload = {
                "Url": webhook_url,
                "To": to_phone,
                "From": self.from_number,
                "Method": "POST"
            }
            auth = (self.project_id, self.api_token)
            
            response = requests.post(url, data=payload, auth=auth)
            response.raise_for_status()
            data = response.json()
            
            return {
                "ref": data.get("sid"),
                "status": data.get("status", "queued")
            }
        except Exception as e:
            logger.error(f"SignalWire call failed: {e}")
            raise

signalwire_client = SignalWireClient()
