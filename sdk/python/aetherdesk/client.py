import httpx

from .agents import AgentsAPI
from .calls import CallsAPI
from .voice import VoiceAPI

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3


class AetherDeskClient:
    def __init__(self, api_key: str, base_url: str = "https://api.aetherdesk.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "AetherDesk-Python-SDK/0.1.0",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        self.voice = VoiceAPI(self)
        self.calls = CallsAPI(self)
        self.agents = AgentsAPI(self)

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectionError) as e:
                if attempt < MAX_RETRIES - 1:
                    continue
                raise
        return None

    def close(self):
        self._client.close()
