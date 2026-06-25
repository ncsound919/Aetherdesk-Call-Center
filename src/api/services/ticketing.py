from abc import ABC, abstractmethod
from base64 import b64encode
from datetime import UTC, datetime

import httpx
import structlog

from api.services.db_integrations import list_integration_configs_db

logger = structlog.get_logger()


class TicketingConnector(ABC):
    @abstractmethod
    async def create_ticket(self, data: dict) -> dict:
        ...

    @abstractmethod
    async def get_ticket(self, ticket_id: str) -> dict:
        ...

    @abstractmethod
    async def update_ticket(self, ticket_id: str, data: dict) -> dict:
        ...

    @abstractmethod
    async def list_tickets(self, tenant_id: str, status: str | None = None) -> dict:
        ...

    @abstractmethod
    async def get_health(self) -> dict:
        ...


def _std_response(success, provider, data=None, error=None):
    return {
        "success": success,
        "data": data,
        "error": error,
        "provider": provider,
        "timestamp": datetime.now(UTC).isoformat(),
    }


class ZendeskConnector(TicketingConnector):
    def __init__(self, tenant_id: str, config: dict):
        self.tenant_id = tenant_id
        self.config = config
        self.provider = "zendesk"
        self.subdomain = config.get("subdomain", "")
        self.api_token = config.get("api_token", "")
        self.email = config.get("email", "")
        auth_str = f"{self.email}/token:{self.api_token}"
        encoded = b64encode(auth_str.encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=f"https://{self.subdomain}.zendesk.com",
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def _request(self, method, path, **kwargs):
        try:
            resp = await self._client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("zendesk_http_error", path=path, status=e.response.status_code, tenant_id=self.tenant_id)
            return None
        except httpx.RequestError as e:
            logger.error("zendesk_request_error", path=path, error=str(e), tenant_id=self.tenant_id)
            return None

    async def create_ticket(self, data: dict) -> dict:
        logger.info("zendesk_create_ticket", tenant_id=self.tenant_id)
        payload = {
            "ticket": {
                "subject": data.get("subject", ""),
                "description": data.get("description", ""),
                "priority": data.get("priority", "normal"),
                "status": data.get("status", "new"),
            }
        }
        if data.get("customer_id"):
            payload["ticket"]["requester_id"] = data["customer_id"]
        result = await self._request("POST", "/api/v2/tickets", json=payload)
        if result:
            ticket = result.get("ticket", {})
            return _std_response(True, self.provider, {"id": str(ticket.get("id")), "ticket_number": ticket.get("id"), **data})
        return _std_response(False, self.provider, error="Failed to create Zendesk ticket")

    async def get_ticket(self, ticket_id: str) -> dict:
        logger.info("zendesk_get_ticket", ticket_id=ticket_id)
        result = await self._request("GET", f"/api/v2/tickets/{ticket_id}")
        if result:
            ticket = result.get("ticket", {})
            return _std_response(True, self.provider, ticket)
        return _std_response(False, self.provider, error=f"Ticket {ticket_id} not found")

    async def update_ticket(self, ticket_id: str, data: dict) -> dict:
        logger.info("zendesk_update_ticket", ticket_id=ticket_id)
        payload = {"ticket": {}}
        for field in ("subject", "description", "priority", "status", "comment"):
            if field in data:
                if field == "comment":
                    payload["ticket"]["comment"] = {"body": data["comment"]}
                else:
                    payload["ticket"][field] = data[field]
        result = await self._request("PUT", f"/api/v2/tickets/{ticket_id}", json=payload)
        if result:
            return _std_response(True, self.provider, {"id": ticket_id, **data})
        return _std_response(False, self.provider, error=f"Failed to update ticket {ticket_id}")

    async def list_tickets(self, tenant_id: str, status: str | None = None) -> dict:
        logger.info("zendesk_list_tickets", tenant_id=tenant_id, status=status)
        params = {}
        if status:
            params["status"] = status
        result = await self._request("GET", "/api/v2/tickets", params=params)
        if result:
            tickets = result.get("tickets", [])
            return _std_response(True, self.provider, {"tickets": tickets, "total": len(tickets)})
        return _std_response(True, self.provider, {"tickets": [], "total": 0})

    async def get_health(self) -> dict:
        logger.info("zendesk_health_check")
        try:
            resp = await self._client.get("/api/v2/tickets", params={"per_page": 1})
            if resp.status_code == 200:
                return _std_response(True, self.provider, {"status": "healthy", "details": "Zendesk API reachable"})
            return _std_response(False, self.provider, error=f"Zendesk returned {resp.status_code}")
        except httpx.RequestError as e:
            return _std_response(False, self.provider, error=str(e))

    async def close(self):
        await self._client.aclose()


class ServiceNowConnector(TicketingConnector):
    def __init__(self, tenant_id: str, config: dict):
        self.tenant_id = tenant_id
        self.config = config
        self.provider = "servicenow"
        self.instance = config.get("instance", "").rstrip("/")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        auth_str = b64encode(f"{self.username}:{self.password}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=f"https://{self.instance}.service-now.com",
            headers={
                "Authorization": f"Basic {auth_str}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def _request(self, method, path, **kwargs):
        try:
            resp = await self._client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("servicenow_http_error", path=path, status=e.response.status_code, tenant_id=self.tenant_id)
            return None
        except httpx.RequestError as e:
            logger.error("servicenow_request_error", path=path, error=str(e), tenant_id=self.tenant_id)
            return None

    async def create_ticket(self, data: dict) -> dict:
        logger.info("servicenow_create_ticket", tenant_id=self.tenant_id)
        payload = {
            "short_description": data.get("subject", data.get("short_description", "")),
            "description": data.get("description", ""),
            "priority": self._map_priority(data.get("priority", "normal")),
            "state": self._map_status(data.get("status", "new")),
            "caller_id": data.get("customer_id", ""),
        }
        if data.get("call_id"):
            payload["u_call_id"] = data["call_id"]
        result = await self._request("POST", "/api/now/table/incident", json=payload)
        if result:
            rec = result.get("result", {})
            return _std_response(True, self.provider, {"id": rec.get("sys_id"), "sys_id": rec.get("sys_id"), "number": rec.get("number"), **data})
        return _std_response(False, self.provider, error="Failed to create ServiceNow incident")

    async def get_ticket(self, ticket_id: str) -> dict:
        logger.info("servicenow_get_ticket", ticket_id=ticket_id)
        result = await self._request("GET", f"/api/now/table/incident/{ticket_id}")
        if result:
            rec = result.get("result", {})
            return _std_response(True, self.provider, rec)
        return _std_response(False, self.provider, error=f"Incident {ticket_id} not found")

    async def update_ticket(self, ticket_id: str, data: dict) -> dict:
        logger.info("servicenow_update_ticket", ticket_id=ticket_id)
        payload = {}
        if "subject" in data:
            payload["short_description"] = data["subject"]
        if "description" in data:
            payload["description"] = data["description"]
        if "priority" in data:
            payload["priority"] = self._map_priority(data["priority"])
        if "status" in data:
            payload["state"] = self._map_status(data["status"])
        if "comment" in data:
            payload["work_notes"] = data["comment"]
        result = await self._request("PATCH", f"/api/now/table/incident/{ticket_id}", json=payload)
        if result:
            return _std_response(True, self.provider, {"id": ticket_id, **data})
        return _std_response(False, self.provider, error=f"Failed to update incident {ticket_id}")

    async def list_tickets(self, tenant_id: str, status: str | None = None) -> dict:
        logger.info("servicenow_list_tickets", tenant_id=tenant_id, status=status)
        params = {"sysparm_limit": 100}
        if status:
            params["sysparm_query"] = f"state={self._map_status(status)}"
        result = await self._request("GET", "/api/now/table/incident", params=params)
        if result:
            records = result.get("result", [])
            return _std_response(True, self.provider, {"tickets": records, "total": len(records)})
        return _std_response(True, self.provider, {"tickets": [], "total": 0})

    async def get_health(self) -> dict:
        logger.info("servicenow_health_check")
        try:
            resp = await self._client.get("/api/now/table/incident", params={"sysparm_limit": 1})
            if resp.status_code == 200:
                return _std_response(True, self.provider, {"status": "healthy", "details": "ServiceNow API reachable"})
            return _std_response(False, self.provider, error=f"ServiceNow returned {resp.status_code}")
        except httpx.RequestError as e:
            return _std_response(False, self.provider, error=str(e))

    def _map_priority(self, priority: str) -> int:
        mapping = {"low": 3, "normal": 2, "high": 1, "urgent": 1}
        return mapping.get(priority, 2)

    def _map_status(self, status: str) -> int:
        mapping = {"new": 1, "open": 2, "pending": 3, "solved": 6, "closed": 7}
        return mapping.get(status, 1)

    async def close(self):
        await self._client.aclose()


class TicketingService:
    def __init__(self, connector: TicketingConnector):
        self.connector = connector

    async def create_ticket(self, data: dict) -> dict:
        return await self.connector.create_ticket(data)

    async def get_ticket(self, ticket_id: str) -> dict:
        return await self.connector.get_ticket(ticket_id)

    async def update_ticket(self, ticket_id: str, data: dict) -> dict:
        return await self.connector.update_ticket(ticket_id, data)

    async def list_tickets(self, tenant_id: str, status: str | None = None) -> dict:
        return await self.connector.list_tickets(tenant_id, status)

    async def sync_from_call(self, call_data: dict) -> dict:
        logger.info("ticketing_sync_from_call", call_data=call_data)
        data = {
            "subject": call_data.get("caller_number", "Unknown"),
            "description": call_data.get("ai_summary", "Ticket from call sync"),
            "priority": "normal",
            "status": "new",
            "customer_id": call_data.get("caller_number"),
            "call_id": call_data.get("call_id"),
        }
        return await self.connector.create_ticket(data)

    async def get_health(self) -> dict:
        return await self.connector.get_health()


class TicketingFactory:
    _connectors = {"zendesk": ZendeskConnector, "servicenow": ServiceNowConnector}

    @classmethod
    def get_connector(cls, tenant_id: str, provider: str, config: dict) -> TicketingConnector:
        klass = cls._connectors.get(provider)
        if not klass:
            logger.warning("unknown_ticketing_provider", provider=provider)
            raise ValueError(f"Unsupported ticketing provider: {provider}")
        logger.info("ticketing_connector_created", provider=provider, tenant_id=tenant_id)
        return klass(tenant_id, config)

    @classmethod
    async def from_tenant(cls, tenant_id: str, provider: str) -> TicketingConnector:
        configs = await list_integration_configs_db(tenant_id, integration_type="ticketing")
        for cfg in configs:
            if cfg.get("provider") == provider:
                return cls.get_connector(tenant_id, provider, cfg.get("config_json", {}))
        raise ValueError(f"No ticketing config found for provider {provider} and tenant {tenant_id}")
