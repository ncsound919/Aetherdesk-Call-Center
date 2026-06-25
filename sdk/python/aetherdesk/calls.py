class CallsAPI:
    def __init__(self, client):
        self._client = client

    def list(self, params: dict | None = None) -> list[dict]:
        return self._client._request("GET", "/api/v1/calls", params=params)

    def get(self, call_id: str) -> dict:
        return self._client._request("GET", f"/api/v1/calls/{call_id}")

    def create(self, data: dict) -> dict:
        return self._client._request("POST", "/api/v1/calls", json=data)

    def action(self, call_id: str, action: str) -> dict:
        return self._client._request("POST", f"/api/v1/calls/{call_id}/action", json={"action": action})

    def get_transcript(self, call_id: str) -> dict:
        return self._client._request("GET", f"/api/v1/calls/{call_id}/transcript")

    def get_recording(self, call_id: str) -> dict:
        return self._client._request("GET", f"/api/v1/calls/{call_id}/recording")

    def get_metrics(self, call_id: str) -> dict:
        return self._client._request("GET", f"/api/v1/calls/{call_id}/metrics")
