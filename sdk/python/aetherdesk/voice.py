class VoiceAPI:
    def __init__(self, client):
        self._client = client

    def make_call(self, to_number: str, agent_id: str, caller_id: str | None = None) -> dict:
        payload = {
            "to_number": to_number,
            "agent_id": agent_id,
        }
        if caller_id:
            payload["caller_id"] = caller_id
        return self._client._request("POST", "/api/v1/calls", json=payload)

    def get_call_status(self, call_id: str) -> dict:
        return self._client._request("GET", f"/api/v1/calls/{call_id}")

    def get_transcript(self, call_id: str) -> dict:
        return self._client._request("GET", f"/api/v1/calls/{call_id}/transcript")

    def list_calls(self, params: dict | None = None) -> list[dict]:
        return self._client._request("GET", "/api/v1/calls", params=params)
