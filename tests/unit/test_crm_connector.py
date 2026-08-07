"""Tests for src/api/services/crm_connector.py — Salesforce + HubSpot connectors
and CRMConnectorFactory. External httpx calls are mocked."""

import asyncio
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.crm_connector import (
    CRMConnectorFactory,
    HubSpotConnector,
    SalesforceConnector,
    _std_response,
)


class FakeResp:
    def __init__(self, payload=None, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("GET", "http://x")
            raise httpx.HTTPStatusError(
                "http error",
                request=req,
                response=httpx.Response(self.status_code, request=req),
            )

    def json(self):
        return self._payload


def _run(coro):
    return asyncio.run(coro)


def _mock_client(monkeypatch, connector, payload=None, status=200, exc=None):
    mock = AsyncMock()
    if exc is not None:
        mock.side_effect = exc
    else:
        mock.return_value = FakeResp(payload, status)
    monkeypatch.setattr(connector._client, "request", mock)
    monkeypatch.setattr(connector._client, "get", mock)
    return mock


def sf_connector(monkeypatch, payload=None, status=200, exc=None):
    conn = SalesforceConnector(
        "tenant-1", {"instance_url": "https://sf/", "access_token": "tok"}
    )
    mock = _mock_client(monkeypatch, conn, payload, status, exc)
    return conn, mock


def hs_connector(monkeypatch, payload=None, status=200, exc=None):
    conn = HubSpotConnector(
        "tenant-1", {"api_key": "key", "base_url": "https://api.hubapi.com"}
    )
    mock = _mock_client(monkeypatch, conn, payload, status, exc)
    return conn, mock


# ---------------------------------------------------------------------------
# _std_response
# ---------------------------------------------------------------------------


class TestStdResponse:
    def test_std_response(self):
        r = _std_response(True, "salesforce", {"id": "1"})
        assert r["success"] is True
        assert r["provider"] == "salesforce"
        assert r["data"] == {"id": "1"}
        assert "timestamp" in r


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_get_connector_known_providers(self):
        assert isinstance(
            CRMConnectorFactory.get_connector("t", "salesforce", {}), SalesforceConnector
        )
        assert isinstance(
            CRMConnectorFactory.get_connector("t", "hubspot", {}), HubSpotConnector
        )

    def test_get_connector_unknown_provider(self):
        with pytest.raises(ValueError, match="Unsupported CRM provider"):
            CRMConnectorFactory.get_connector("t", "nope", {})

    @pytest.mark.asyncio
    async def test_from_tenant_found(self):
        async def fake_list(tenant_id, integration_type=None):
            return [
                {"provider": "hubspot", "config_json": {"api_key": "k"}},
                {"provider": "salesforce", "config_json": {"instance_url": "https://sf"}},
            ]

        with patch("api.services.crm_connector.list_integration_configs_db", new=fake_list):
            conn = await CRMConnectorFactory.from_tenant("t", "salesforce")
        assert isinstance(conn, SalesforceConnector)

    @pytest.mark.asyncio
    async def test_from_tenant_missing(self):
        async def fake_list(tenant_id, integration_type=None):
            return []

        with patch("api.services.crm_connector.list_integration_configs_db", new=fake_list):
            with pytest.raises(ValueError, match="No CRM config"):
                await CRMConnectorFactory.from_tenant("t", "hubspot")


# ---------------------------------------------------------------------------
# Salesforce
# ---------------------------------------------------------------------------


class TestSalesforce:
    def test_init(self):
        conn = SalesforceConnector("t", {"instance_url": "https://sf/", "access_token": "tok"})
        assert conn.provider == "salesforce"
        assert conn.instance_url == "https://sf"
        assert conn.api_version == "v58.0"
        assert "Bearer tok" in conn._client.headers["Authorization"]

    def test_request_http_error(self, monkeypatch):
        req = httpx.Request("POST", "http://x")
        conn, _ = sf_connector(
            monkeypatch,
            exc=httpx.HTTPStatusError("boom", request=req, response=httpx.Response(400, request=req)),
        )
        assert _run(conn._request("POST", "/sobjects/Contact/", json={})) is None

    def test_request_request_error(self, monkeypatch):
        req = httpx.Request("POST", "http://x")
        conn, _ = sf_connector(monkeypatch, exc=httpx.RequestError("down", request=req))
        assert _run(conn._request("POST", "/sobjects/Contact/", json={})) is None

    @pytest.mark.asyncio
    async def test_create_contact_success(self, monkeypatch):
        conn, mock = sf_connector(monkeypatch, payload={"id": "c1"})
        r = await conn.create_contact({"Name": "A"})
        assert r["success"] is True
        assert r["data"]["id"] == "c1"
        assert mock.call_args.args[1] == "/services/data/v58.0/sobjects/Contact/"

    @pytest.mark.asyncio
    async def test_create_contact_failure(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload=None)
        r = await conn.create_contact({"Name": "A"})
        assert r["success"] is False
        assert "Failed to create" in r["error"]

    @pytest.mark.asyncio
    async def test_get_contact_success_and_failure(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={"Id": "c1"})
        r = await conn.get_contact("c1")
        assert r["success"] is True
        assert r["data"] == {"Id": "c1"}

        conn2, _ = sf_connector(monkeypatch, payload=None)
        r2 = await conn2.get_contact("nope")
        assert r2["success"] is False
        assert "not found" in r2["error"]

    @pytest.mark.asyncio
    async def test_update_contact(self, monkeypatch):
        conn, mock = sf_connector(monkeypatch, payload={"id": "c1"})
        r = await conn.update_contact("c1", {"Name": "B"})
        assert r["success"] is True
        assert r["data"]["id"] == "c1"
        assert mock.call_args.args[0] == "PATCH"

    @pytest.mark.asyncio
    async def test_search_contacts_success_and_empty(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={"searchRecords": [{"Id": "1"}, {"Id": "2"}]})
        r = await conn.search_contacts("bob")
        assert r["success"] is True
        assert r["data"]["total"] == 2

        conn2, _ = sf_connector(monkeypatch, payload=None)
        r2 = await conn2.search_contacts("bob")
        assert r2["success"] is True
        assert r2["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_get_health(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={"status": "ok"})
        r = await conn.get_health()
        assert r["success"] is True
        assert r["data"]["status"] == "healthy"

        conn2, _ = sf_connector(monkeypatch, payload=None)
        r2 = await conn2.get_health()
        assert r2["success"] is False
        assert "unreachable" in r2["error"]

    @pytest.mark.asyncio
    async def test_sync_contacts(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={"records": [{"Id": "1"}, {"Id": "2"}]})
        r = await conn.sync_contacts()
        assert r["success"] is True
        assert r["data"]["synced"] == 2
        assert r["data"]["updated"] == 2

        conn2, _ = sf_connector(monkeypatch, payload=None)
        r2 = await conn2.sync_contacts()
        assert r2["success"] is False
        assert "Failed to sync" in r2["error"]

    @pytest.mark.asyncio
    async def test_close(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={})
        aclose = AsyncMock()
        monkeypatch.setattr(conn._client, "aclose", aclose)
        await conn.close()
        aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# HubSpot
# ---------------------------------------------------------------------------


class TestHubSpot:
    def test_init(self):
        conn = HubSpotConnector("t", {"api_key": "key"})
        assert conn.provider == "hubspot"
        assert conn.base_url == "https://api.hubapi.com"
        assert "Bearer key" in conn._client.headers["Authorization"]

    def test_request_http_error(self, monkeypatch):
        req = httpx.Request("GET", "http://x")
        conn, _ = hs_connector(
            monkeypatch,
            exc=httpx.HTTPStatusError("boom", request=req, response=httpx.Response(400, request=req)),
        )
        assert _run(conn._request("GET", "/crm/v3/objects/contacts")) is None

    def test_request_request_error(self, monkeypatch):
        req = httpx.Request("GET", "http://x")
        conn, _ = hs_connector(monkeypatch, exc=httpx.RequestError("down", request=req))
        assert _run(conn._request("GET", "/crm/v3/objects/contacts")) is None

    @pytest.mark.asyncio
    async def test_create_contact(self, monkeypatch):
        conn, mock = hs_connector(monkeypatch, payload={"id": "c1"})
        r = await conn.create_contact({"email": "a@b.com", "name": "A"})
        assert r["success"] is True
        assert r["data"]["id"] == "c1"
        assert mock.call_args.kwargs["json"] == {"properties": {"email": "a@b.com", "name": "A"}}

    @pytest.mark.asyncio
    async def test_create_contact_failure(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload=None)
        r = await conn.create_contact({"name": "A"})
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_get_contact_success_and_failure(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload={"id": "c1"})
        r = await conn.get_contact("c1")
        assert r["success"] is True

        conn2, _ = hs_connector(monkeypatch, payload=None)
        r2 = await conn2.get_contact("nope")
        assert r2["success"] is False

    @pytest.mark.asyncio
    async def test_update_contact_success_and_failure(self, monkeypatch):
        conn, mock = hs_connector(monkeypatch, payload={"id": "c1"})
        r = await conn.update_contact("c1", {"name": "B"})
        assert r["success"] is True
        assert mock.call_args.kwargs["json"] == {"properties": {"name": "B"}}

        conn2, _ = hs_connector(monkeypatch, payload=None)
        r2 = await conn2.update_contact("c1", {"name": "B"})
        assert r2["success"] is False

    @pytest.mark.asyncio
    async def test_search_contacts(self, monkeypatch):
        conn, mock = hs_connector(monkeypatch, payload={"results": [{"id": "1"}]})
        r = await conn.search_contacts("bob")
        assert r["success"] is True
        assert r["data"]["total"] == 1
        assert mock.call_args.kwargs["json"] == {"query": "bob"}

        conn2, _ = hs_connector(monkeypatch, payload=None)
        r2 = await conn2.search_contacts("bob")
        assert r2["success"] is True
        assert r2["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_get_health(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload=None, status=200)
        r = await conn.get_health()
        assert r["success"] is True
        assert r["data"]["status"] == "healthy"

        conn2, _ = hs_connector(monkeypatch, payload=None, status=500)
        r2 = await conn2.get_health()
        assert r2["success"] is False
        assert "500" in r2["error"]

        req = httpx.Request("GET", "http://x")
        conn3, _ = hs_connector(monkeypatch, exc=httpx.RequestError("down", request=req))
        r3 = await conn3.get_health()
        assert r3["success"] is False

    @pytest.mark.asyncio
    async def test_sync_contacts(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload={"results": [{"id": "1"}]})
        r = await conn.sync_contacts()
        assert r["success"] is True
        assert r["data"]["synced"] == 1

        conn2, _ = hs_connector(monkeypatch, payload=None)
        r2 = await conn2.sync_contacts()
        assert r2["success"] is False

    @pytest.mark.asyncio
    async def test_close(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload={})
        aclose = AsyncMock()
        monkeypatch.setattr(conn._client, "aclose", aclose)
        await conn.close()
        aclose.assert_awaited_once()
