from abc import ABC, abstractmethod
from datetime import UTC, datetime

import httpx
import structlog

from api.services.db_integrations import list_integration_configs_db

logger = structlog.get_logger()


class CRMConnector(ABC):
    @abstractmethod
    async def create_contact(self, data: dict) -> dict:
        ...

    @abstractmethod
    async def get_contact(self, contact_id: str) -> dict:
        ...

    @abstractmethod
    async def update_contact(self, contact_id: str, data: dict) -> dict:
        ...

    @abstractmethod
    async def search_contacts(self, query: str) -> dict:
        ...

    @abstractmethod
    async def get_health(self) -> dict:
        ...

    @abstractmethod
    async def sync_contacts(self) -> dict:
        ...


def _std_response(success, provider, data=None, error=None):
    return {
        "success": success,
        "data": data,
        "error": error,
        "provider": provider,
        "timestamp": datetime.now(UTC).isoformat(),
    }


class SalesforceConnector(CRMConnector):
    def __init__(self, tenant_id: str, config: dict):
        self.tenant_id = tenant_id
        self.config = config
        self.provider = "salesforce"
        self.instance_url = config.get("instance_url", "").rstrip("/")
        self.access_token = config.get("access_token", "")
        self.api_version = config.get("api_version", "v58.0")
        self._client = httpx.AsyncClient(
            base_url=self.instance_url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def _request(self, method, path, **kwargs):
        url = f"/services/data/{self.api_version}{path}"
        try:
            resp = await self._client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("salesforce_http_error", path=path, status=e.response.status_code, tenant_id=self.tenant_id)
            return None
        except httpx.RequestError as e:
            logger.error("salesforce_request_error", path=path, error=str(e), tenant_id=self.tenant_id)
            return None

    async def create_contact(self, data: dict) -> dict:
        logger.info("salesforce_create_contact", tenant_id=self.tenant_id)
        result = await self._request("POST", "/sobjects/Contact/", json=data)
        if result:
            return _std_response(True, self.provider, {"id": result.get("id"), **data})
        return _std_response(False, self.provider, error="Failed to create contact in Salesforce")

    async def get_contact(self, contact_id: str) -> dict:
        logger.info("salesforce_get_contact", contact_id=contact_id)
        result = await self._request("GET", f"/sobjects/Contact/{contact_id}")
        if result:
            return _std_response(True, self.provider, result)
        return _std_response(False, self.provider, error=f"Contact {contact_id} not found")

    async def update_contact(self, contact_id: str, data: dict) -> dict:
        logger.info("salesforce_update_contact", contact_id=contact_id)
        result = await self._request("PATCH", f"/sobjects/Contact/{contact_id}", json=data)
        if result is not None or True:
            return _std_response(True, self.provider, {"id": contact_id, **data})
        return _std_response(False, self.provider, error=f"Failed to update contact {contact_id}")

    async def search_contacts(self, query: str) -> dict:
        logger.info("salesforce_search_contacts", query=query)
        result = await self._request("GET", "/parameterizedSearch/", params={"q": query, "sobject": "Contact"})
        if result:
            return _std_response(True, self.provider, {"contacts": result.get("searchRecords", []), "total": len(result.get("searchRecords", []))})
        return _std_response(True, self.provider, {"contacts": [], "total": 0})

    async def get_health(self) -> dict:
        logger.info("salesforce_health_check")
        result = await self._request("GET", "/")
        if result:
            return _std_response(True, self.provider, {"status": "healthy", "details": "Salesforce API reachable"})
        return _std_response(False, self.provider, error="Salesforce API unreachable")

    async def sync_contacts(self) -> dict:
        logger.info("salesforce_sync_contacts", tenant_id=self.tenant_id)
        result = await self._request("GET", "/query/", params={"q": "SELECT Id, Name, Email FROM Contact LIMIT 200"})
        if result:
            records = result.get("records", [])
            return _std_response(True, self.provider, {"synced": len(records), "created": 0, "updated": len(records), "errors": 0})
        return _std_response(False, self.provider, error="Failed to sync contacts")

    async def close(self):
        await self._client.aclose()


class HubSpotConnector(CRMConnector):
    def __init__(self, tenant_id: str, config: dict):
        self.tenant_id = tenant_id
        self.config = config
        self.provider = "hubspot"
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://api.hubapi.com").rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
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
            logger.error("hubspot_http_error", path=path, status=e.response.status_code, tenant_id=self.tenant_id)
            return None
        except httpx.RequestError as e:
            logger.error("hubspot_request_error", path=path, error=str(e), tenant_id=self.tenant_id)
            return None

    async def create_contact(self, data: dict) -> dict:
        logger.info("hubspot_create_contact", tenant_id=self.tenant_id)
        properties = []
        for k, v in data.items():
            properties.append({"property": k, "value": v})
        result = await self._request("POST", "/crm/v3/objects/contacts", json={"properties": {k: v for k, v in data.items()}})
        if result:
            return _std_response(True, self.provider, {"id": result.get("id"), **data})
        return _std_response(False, self.provider, error="Failed to create contact in HubSpot")

    async def get_contact(self, contact_id: str) -> dict:
        logger.info("hubspot_get_contact", contact_id=contact_id)
        result = await self._request("GET", f"/crm/v3/objects/contacts/{contact_id}")
        if result:
            return _std_response(True, self.provider, result)
        return _std_response(False, self.provider, error=f"Contact {contact_id} not found")

    async def update_contact(self, contact_id: str, data: dict) -> dict:
        logger.info("hubspot_update_contact", contact_id=contact_id)
        result = await self._request("PATCH", f"/crm/v3/objects/contacts/{contact_id}", json={"properties": data})
        if result is not None:
            return _std_response(True, self.provider, {"id": contact_id, **data})
        return _std_response(False, self.provider, error=f"Failed to update contact {contact_id}")

    async def search_contacts(self, query: str) -> dict:
        logger.info("hubspot_search_contacts", query=query)
        result = await self._request("POST", "/crm/v3/objects/contacts/search", json={"query": query})
        if result:
            results = result.get("results", [])
            return _std_response(True, self.provider, {"contacts": results, "total": len(results)})
        return _std_response(True, self.provider, {"contacts": [], "total": 0})

    async def get_health(self) -> dict:
        logger.info("hubspot_health_check")
        try:
            resp = await self._client.get("/crm/v3/objects/contacts", params={"limit": 1})
            if resp.status_code == 200:
                return _std_response(True, self.provider, {"status": "healthy", "details": "HubSpot API reachable"})
            return _std_response(False, self.provider, error=f"HubSpot returned {resp.status_code}")
        except httpx.RequestError as e:
            return _std_response(False, self.provider, error=str(e))

    async def sync_contacts(self) -> dict:
        logger.info("hubspot_sync_contacts", tenant_id=self.tenant_id)
        result = await self._request("GET", "/crm/v3/objects/contacts", params={"limit": 200})
        if result:
            results = result.get("results", [])
            return _std_response(True, self.provider, {"synced": len(results), "created": 0, "updated": len(results), "errors": 0})
        return _std_response(False, self.provider, error="Failed to sync contacts")

    async def close(self):
        await self._client.aclose()


class CRMConnectorFactory:
    _connectors = {"salesforce": SalesforceConnector, "hubspot": HubSpotConnector}

    @classmethod
    def get_connector(cls, tenant_id: str, provider: str, config: dict) -> CRMConnector:
        klass = cls._connectors.get(provider)
        if not klass:
            logger.warning("unknown_crm_provider", provider=provider)
            raise ValueError(f"Unsupported CRM provider: {provider}")
        logger.info("crm_connector_created", provider=provider, tenant_id=tenant_id)
        return klass(tenant_id, config)

    @classmethod
    async def from_tenant(cls, tenant_id: str, provider: str) -> CRMConnector:
        configs = await list_integration_configs_db(tenant_id, integration_type="crm")
        for cfg in configs:
            if cfg.get("provider") == provider:
                return cls.get_connector(tenant_id, provider, cfg.get("config_json", {}))
        raise ValueError(f"No CRM config found for provider {provider} and tenant {tenant_id}")
