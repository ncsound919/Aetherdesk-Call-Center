class AgentsAPI:
    def __init__(self, client):
        self._client = client

    def list(self) -> list[dict]:
        return self._client._request("GET", "/api/v1/agents")

    def create(self, name: str, agent_type: str = "ai", skills: list[str] | None = None) -> dict:
        payload = {
            "name": name,
            "agent_type": agent_type,
            "skills": skills or [],
        }
        return self._client._request("POST", "/api/v1/agents", json=payload)

    def get(self, agent_id: str) -> dict:
        return self._client._request("GET", f"/api/v1/agents/{agent_id}")

    def update_status(self, agent_id: str, status: str) -> dict:
        return self._client._request("PATCH", f"/api/v1/agents/{agent_id}/status", json={"status": status})

    def update(self, agent_id: str, data: dict) -> dict:
        return self._client._request("PUT", f"/api/v1/agents/{agent_id}", json=data)

    def delete(self, agent_id: str) -> dict:
        return self._client._request("DELETE", f"/api/v1/agents/{agent_id}")
