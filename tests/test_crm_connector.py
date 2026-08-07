"""Tests for src/api/services/crm_connector.py — Salesforce + HubSpot connectors
and the CRMConnectorFactory."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import api.services.crm_connector as crm  # noqa: E402


class FakeResp:
    def __init__(self, payload=None, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("GET", "http://x")
            raise httpx.HTTPStatusError(
                "http error", request=req, response=httpx.Response(self.status_code, request=req)
            )

    def json(self):
        return self._payload


def sf_connector(monkeypatch, payload=None, status=200, exc=None):
    conn = crm.SalesforceConnector(
        "tenant-1", {"instance_url": "https://sf", "access_token": "tok"}
    )
    mock = AsyncMock()
    if exc is not None:
        mock.side_effect = exc
    else:
        mock.return_value = FakeResp(payload, status)
    monkeypatch.setattr(conn._client, "request", mock)
    return conn, mock


def hs_connector(monkeypatch, payload=None, status=200, exc=None):
    conn = crm.HubSpotConnector(
        "tenant-1", {"api_key": "key", "base_url": "https://api.hubapi.com"}
    )
    mock = AsyncMock()
    if exc is not None:
        mock.side_effect = exc
    else:
        mock.return_value = FakeResp(payload, status)
    monkeypatch.setattr(conn._client, "request", mock)
    monkeypatch.setattr(conn._client, "get", mock)
    return conn, mock


def test_std_response():
    r = crm._std_response(True, "sf", {"id": "1"})
    assert r["success"] is True
    assert r["provider"] == "sf"
    assert r["data"] == {"id": "1"}
    assert "timestamp" in r


class TestFactory:
    def test_get_connector_known_providers(self):
        assert crm.CRMConnectorFactory.get_connector("t", "salesforce", {}) is not None
        assert crm.CRMConnectorFactory.get_connector("t", "hubspot", {}) is not None

    def test_get_connector_unknown_provider(self):
        with pytest.raises(ValueError, match="Unsupported CRM provider"):
            crm.CRMConnectorFactory.get_connector("t", "nope", {})

    def test_from_tenant(self, monkeypatch):
        import api.services.db_integrations as dbi

        async def _cfg(tenant, integration_type=None):
            return [
                {"provider": "hubspot", "integration_type": "crm", "config_json": {"api_key": "k"}}
            ]

        monkeypatch.setattr(crm, "list_integration_configs_db", _cfg)
        conn = __import__("asyncio").run(crm.CRMConnectorFactory.from_tenant("t", "hubspot"))
        assert conn.provider == "hubspot"

    def test_from_tenant_missing(self, monkeypatch):
        import api.services.db_integrations as dbi

        async def _cfg(tenant, integration_type=None):
            return []

        monkeypatch.setattr(crm, "list_integration_configs_db", _cfg)
        with pytest.raises(ValueError, match="No CRM config"):
            __import__("asyncio").run(crm.CRMConnectorFactory.from_tenant("t", "hubspot"))


class TestSalesforce:
    def test_create_contact_success(self, monkeypatch):
        conn, mock = sf_connector(monkeypatch, payload={"id": "c1"})
        r = __import__("asyncio").run(conn.create_contact({"Name": "A"}))
        assert r["success"] is True
        assert r["data"]["id"] == "c1"

    def test_create_contact_failure(self, monkeypatch):
        conn, mock = sf_connector(monkeypatch, payload=None)
        r = __import__("asyncio").run(conn.create_contact({"Name": "A"}))
        assert r["success"] is False

    def test_create_contact_http_error(self, monkeypatch):
        req = httpx.Request("POST", "http://x")
        conn, _ = sf_connector(
            monkeypatch,
            exc=httpx.HTTPStatusError("boom", request=req, response=httpx.Response(400, request=req)),
        )
        r = __import__("asyncio").run(conn.create_contact({"Name": "A"}))
        assert r["success"] is False

    def test_create_contact_request_error(self, monkeypatch):
        req = httpx.Request("POST", "http://x")
        conn, _ = sf_connector(
            monkeypatch, exc=httpx.RequestError("network", request=req)
        )
        r = __import__("asyncio").run(conn.create_contact({"Name": "A"}))
        assert r["success"] is False

    def test_get_contact(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={"Id": "c1"})
        r = __import__("asyncio").run(conn.get_contact("c1"))
        assert r["success"] is True
        missing = __import__("asyncio").run(conn.get_contact("nope")) if False else None
        conn2, _ = sf_connector(monkeypatch, payload=None)
        r2 = __import__("asyncio").run(conn2.get_contact("nope"))
        assert r2["success"] is False
        del missing

    def test_update_contact(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={"id": "c1"})
        r = __import__("asyncio").run(conn.update_contact("c1", {"Name": "B"}))
        assert r["success"] is True

    def test_search_contacts(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={"searchRecords": [{"Id": "1"}]})
        r = __import__("asyncio").run(conn.search_contacts("bob"))
        assert r["success"] is True
        assert r["data"]["total"] == 1
        conn2, _ = sf_connector(monkeypatch, payload=None)
        r2 = __import__("asyncio").run(conn2.search_contacts("bob"))
        assert r2["data"]["total"] == 0

    def test_get_health(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={"status": "ok"})
        r = __import__("asyncio").run(conn.get_health())
        assert r["success"] is True
        conn2, _ = sf_connector(monkeypatch, payload=None)
        r2 = __import__("asyncio").run(conn2.get_health())
        assert r2["success"] is False

    def test_sync_contacts(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={"records": [{"Id": "1"}, {"Id": "2"}]})
        r = __import__("asyncio").run(conn.sync_contacts())
        assert r["success"] is True
        assert r["data"]["synced"] == 2
        conn2, _ = sf_connector(monkeypatch, payload=None)
        r2 = __import__("asyncio").run(conn2.sync_contacts())
        assert r2["success"] is False


class TestHubSpot:
    def test_create_contact(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload={"id": "c1"})
        r = __import__("asyncio").run(conn.create_contact({"Name": "A"}))
        assert r["success"] is True
        conn2, _ = hs_connector(monkeypatch, payload=None)
        r2 = __import__("asyncio").run(conn2.create_contact({"Name": "A"}))
        assert r2["success"] is False

    def test_get_contact(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload={"id": "c1"})
        assert __import__("asyncio").run(conn.get_contact("c1"))["success"] is True
        conn2, _ = hs_connector(monkeypatch, payload=None)
        assert __import__("asyncio").run(conn2.get_contact("nope"))["success"] is False

    def test_update_contact(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload={"id": "c1"})
        assert __import__("asyncio").run(conn.update_contact("c1", {"Name": "B"}))["success"] is True

    def test_search_contacts(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload={"results": [{"id": "1"}]})
        r = __import__("asyncio").run(conn.search_contacts("bob"))
        assert r["data"]["total"] == 1
        conn2, _ = hs_connector(monkeypatch, payload=None)
        r2 = __import__("asyncio").run(conn2.search_contacts("bob"))
        assert r2["data"]["total"] == 0

    def test_get_health(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload=None, status=200)
        r = __import__("asyncio").run(conn.get_health())
        assert r["success"] is True
        conn2, _ = hs_connector(monkeypatch, payload=None, status=500)
        r2 = __import__("asyncio").run(conn2.get_health())
        assert r2["success"] is False
        req = httpx.Request("GET", "http://x")
        conn3, _ = hs_connector(monkeypatch, exc=httpx.RequestError("down", request=req))
        r3 = __import__("asyncio").run(conn3.get_health())
        assert r3["success"] is False

    def test_sync_contacts(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload={"results": [{"id": "1"}]})
        assert __import__("asyncio").run(conn.sync_contacts())["success"] is True
        conn2, _ = hs_connector(monkeypatch, payload=None)
        assert __import__("asyncio").run(conn2.sync_contacts())["success"] is False

    def test_request_http_error(self, monkeypatch):
        req = httpx.Request("GET", "http://x")
        conn, _ = hs_connector(
            monkeypatch,
            exc=httpx.HTTPStatusError("boom", request=req, response=httpx.Response(400, request=req)),
        )
        r = __import__("asyncio").run(conn.search_contacts("bob"))
        assert r["success"] is True  # search falls back to empty success

    def test_request_error_branch(self, monkeypatch):
        req = httpx.Request("GET", "http://x")
        conn, _ = hs_connector(monkeypatch, exc=httpx.RequestError("down", request=req))
        r = __import__("asyncio").run(conn.search_contacts("bob"))
        assert r["success"] is True

    def test_update_contact_failure(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload=None)
        r = __import__("asyncio").run(conn.update_contact("c1", {"Name": "B"}))
        assert r["success"] is False

    def test_close(self, monkeypatch):
        conn, _ = hs_connector(monkeypatch, payload={})
        aclose = AsyncMock()
        monkeypatch.setattr(conn._client, "aclose", aclose)
        __import__("asyncio").run(conn.close())
        aclose.assert_awaited_once()


class TestSalesforceClose:
    def test_close(self, monkeypatch):
        conn, _ = sf_connector(monkeypatch, payload={})
        aclose = AsyncMock()
        monkeypatch.setattr(conn._client, "aclose", aclose)
        __import__("asyncio").run(conn.close())
        aclose.assert_awaited_once()

