"""Tests for src/api/services/ticketing.py — Zendesk + ServiceNow connectors,
TicketingService, and TicketingFactory. External httpx calls are mocked."""

import asyncio
from base64 import b64encode

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.ticketing import (
    ServiceNowConnector,
    TicketingConnector,
    TicketingFactory,
    TicketingService,
    ZendeskConnector,
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


def zendesk_conn(monkeypatch, payload=None, status=200, exc=None):
    conn = ZendeskConnector(
        "tenant-1",
        {"subdomain": "acme", "api_token": "tok", "email": "support@acme.com"},
    )
    mock = _mock_client(monkeypatch, conn, payload, status, exc)
    return conn, mock


def servicenow_conn(monkeypatch, payload=None, status=200, exc=None):
    conn = ServiceNowConnector(
        "tenant-1",
        {"instance": "acme.service-now.com/", "username": "u", "password": "p"},
    )
    mock = _mock_client(monkeypatch, conn, payload, status, exc)
    return conn, mock


# ---------------------------------------------------------------------------
# _std_response
# ---------------------------------------------------------------------------


class TestStdResponse:
    def test_basic(self):
        r = _std_response(True, "zendesk", {"id": "1"})
        assert r["success"] is True
        assert r["provider"] == "zendesk"
        assert r["data"] == {"id": "1"}
        assert r["error"] is None
        assert "timestamp" in r

    def test_error(self):
        r = _std_response(False, "sf", error="boom")
        assert r["success"] is False
        assert r["error"] == "boom"


# ---------------------------------------------------------------------------
# ZendeskConnector
# ---------------------------------------------------------------------------


class TestZendesk:
    def test_init_builds_basic_auth(self, monkeypatch):
        conn = ZendeskConnector(
            "t",
            {"subdomain": "acme", "api_token": "tok", "email": "support@acme.com"},
        )
        expected = b64encode(b"support@acme.com/token:tok").decode()
        assert conn.provider == "zendesk"
        assert conn.subdomain == "acme"
        assert "Basic" in conn._client.headers["Authorization"]
        assert expected in conn._client.headers["Authorization"]

    def test_request_success(self, monkeypatch):
        conn, mock = zendesk_conn(monkeypatch, payload={"ok": True})
        result = _run(conn._request("GET", "/api/v2/tickets"))
        assert result == {"ok": True}

    def test_request_http_status_error(self, monkeypatch):
        req = httpx.Request("GET", "http://x")
        conn, _ = zendesk_conn(
            monkeypatch,
            exc=httpx.HTTPStatusError("boom", request=req, response=httpx.Response(500, request=req)),
        )
        assert _run(conn._request("GET", "/x")) is None

    def test_request_request_error(self, monkeypatch):
        req = httpx.Request("GET", "http://x")
        conn, _ = zendesk_conn(monkeypatch, exc=httpx.RequestError("down", request=req))
        assert _run(conn._request("GET", "/x")) is None

    @pytest.mark.asyncio
    async def test_create_ticket_success(self, monkeypatch):
        conn, mock = zendesk_conn(monkeypatch, payload={"ticket": {"id": 42}})
        r = await conn.create_ticket({"subject": "S", "description": "D"})
        assert r["success"] is True
        assert r["data"]["id"] == "42"
        assert r["data"]["ticket_number"] == 42
        mock.assert_called_once_with(
            "POST", "/api/v2/tickets", json={"ticket": {"subject": "S", "description": "D", "priority": "normal", "status": "new"}}
        )

    @pytest.mark.asyncio
    async def test_create_ticket_with_requester(self, monkeypatch):
        conn, mock = zendesk_conn(monkeypatch, payload={"ticket": {"id": 7}})
        r = await conn.create_ticket({"subject": "S", "customer_id": "CUST-9"})
        assert r["success"] is True
        call_kwargs = mock.call_args.kwargs["json"]["ticket"]
        assert call_kwargs["requester_id"] == "CUST-9"

    @pytest.mark.asyncio
    async def test_create_ticket_failure(self, monkeypatch):
        conn, _ = zendesk_conn(monkeypatch, payload=None)
        r = await conn.create_ticket({"subject": "S"})
        assert r["success"] is False
        assert "Failed to create" in r["error"]

    @pytest.mark.asyncio
    async def test_get_ticket_success_and_failure(self, monkeypatch):
        conn, _ = zendesk_conn(monkeypatch, payload={"ticket": {"id": 1}})
        r = await conn.get_ticket("1")
        assert r["success"] is True
        assert r["data"]["id"] == 1

        conn2, _ = zendesk_conn(monkeypatch, payload=None)
        r2 = await conn2.get_ticket("nope")
        assert r2["success"] is False
        assert "not found" in r2["error"]

    @pytest.mark.asyncio
    async def test_update_ticket_with_comment(self, monkeypatch):
        conn, mock = zendesk_conn(monkeypatch, payload={"ticket": {"id": 1}})
        r = await conn.update_ticket(
            "1", {"subject": "New", "priority": "high", "comment": "please fix"}
        )
        assert r["success"] is True
        ticket = mock.call_args.kwargs["json"]["ticket"]
        assert ticket["subject"] == "New"
        assert ticket["priority"] == "high"
        assert ticket["comment"] == {"body": "please fix"}

    @pytest.mark.asyncio
    async def test_update_ticket_failure(self, monkeypatch):
        conn, _ = zendesk_conn(monkeypatch, payload=None)
        r = await conn.update_ticket("1", {"status": "closed"})
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_list_tickets(self, monkeypatch):
        conn, mock = zendesk_conn(monkeypatch, payload={"tickets": [{"id": 1}, {"id": 2}]})
        r = await conn.list_tickets("t", status="open")
        assert r["success"] is True
        assert r["data"]["total"] == 2
        assert mock.call_args.kwargs["params"] == {"status": "open"}

    @pytest.mark.asyncio
    async def test_list_tickets_empty_on_failure(self, monkeypatch):
        conn, _ = zendesk_conn(monkeypatch, payload=None)
        r = await conn.list_tickets("t")
        assert r["success"] is True
        assert r["data"]["tickets"] == []
        assert r["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_get_health(self, monkeypatch):
        conn, _ = zendesk_conn(monkeypatch, payload=None, status=200)
        r = await conn.get_health()
        assert r["success"] is True
        assert r["data"]["status"] == "healthy"

        conn2, _ = zendesk_conn(monkeypatch, payload=None, status=503)
        r2 = await conn2.get_health()
        assert r2["success"] is False
        assert "503" in r2["error"]

        req = httpx.Request("GET", "http://x")
        conn3, _ = zendesk_conn(monkeypatch, exc=httpx.RequestError("down", request=req))
        r3 = await conn3.get_health()
        assert r3["success"] is False

    @pytest.mark.asyncio
    async def test_close(self, monkeypatch):
        conn, _ = zendesk_conn(monkeypatch, payload={})
        aclose = AsyncMock()
        monkeypatch.setattr(conn._client, "aclose", aclose)
        await conn.close()
        aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# ServiceNowConnector
# ---------------------------------------------------------------------------


class TestServiceNow:
    def test_init_normalizes_instance(self, monkeypatch):
        conn = ServiceNowConnector(
            "t", {"instance": "acme.service-now.com/", "username": "u", "password": "p"}
        )
        assert conn.instance == "acme.service-now.com"
        assert conn.provider == "servicenow"

    def test_request_http_error(self, monkeypatch):
        req = httpx.Request("GET", "http://x")
        conn, _ = servicenow_conn(
            monkeypatch,
            exc=httpx.HTTPStatusError("boom", request=req, response=httpx.Response(400, request=req)),
        )
        assert _run(conn._request("GET", "/x")) is None

    def test_request_request_error(self, monkeypatch):
        req = httpx.Request("GET", "http://x")
        conn, _ = servicenow_conn(monkeypatch, exc=httpx.RequestError("down", request=req))
        assert _run(conn._request("GET", "/x")) is None

    @pytest.mark.asyncio
    async def test_create_ticket_success(self, monkeypatch):
        conn, mock = servicenow_conn(
            monkeypatch, payload={"result": {"sys_id": "S1", "number": "INC001"}}
        )
        r = await conn.create_ticket(
            {"subject": "broken", "description": "it broke", "priority": "high", "status": "open", "customer_id": "C1", "call_id": "CALL-1"}
        )
        assert r["success"] is True
        assert r["data"]["sys_id"] == "S1"
        assert r["data"]["number"] == "INC001"
        body = mock.call_args.kwargs["json"]
        assert body["short_description"] == "broken"
        assert body["priority"] == 1
        assert body["state"] == 2
        assert body["u_call_id"] == "CALL-1"

    @pytest.mark.asyncio
    async def test_create_ticket_failure(self, monkeypatch):
        conn, _ = servicenow_conn(monkeypatch, payload=None)
        r = await conn.create_ticket({"subject": "S"})
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_get_ticket_success_and_failure(self, monkeypatch):
        conn, _ = servicenow_conn(monkeypatch, payload={"result": {"sys_id": "S1"}})
        r = await conn.get_ticket("S1")
        assert r["success"] is True
        assert r["data"]["sys_id"] == "S1"

        conn2, _ = servicenow_conn(monkeypatch, payload=None)
        r2 = await conn2.get_ticket("nope")
        assert r2["success"] is False
        assert "not found" in r2["error"]

    @pytest.mark.asyncio
    async def test_update_ticket_maps_fields(self, monkeypatch):
        conn, mock = servicenow_conn(monkeypatch, payload={"result": {"sys_id": "S1"}})
        r = await conn.update_ticket(
            "S1",
            {"subject": "new", "description": "d", "priority": "urgent", "status": "closed", "comment": "note"},
        )
        assert r["success"] is True
        body = mock.call_args.kwargs["json"]
        assert body["short_description"] == "new"
        assert body["priority"] == 1
        assert body["state"] == 7
        assert body["work_notes"] == "note"

    @pytest.mark.asyncio
    async def test_update_ticket_failure(self, monkeypatch):
        conn, _ = servicenow_conn(monkeypatch, payload=None)
        r = await conn.update_ticket("S1", {"status": "closed"})
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_list_tickets_with_status(self, monkeypatch):
        conn, mock = servicenow_conn(monkeypatch, payload={"result": [{"sys_id": "S1"}]})
        r = await conn.list_tickets("t", status="open")
        assert r["success"] is True
        assert r["data"]["total"] == 1
        assert mock.call_args.kwargs["params"]["sysparm_query"] == "state=2"

    @pytest.mark.asyncio
    async def test_list_tickets_failure_returns_empty(self, monkeypatch):
        conn, _ = servicenow_conn(monkeypatch, payload=None)
        r = await conn.list_tickets("t")
        assert r["success"] is True
        assert r["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_get_health(self, monkeypatch):
        conn, _ = servicenow_conn(monkeypatch, payload=None, status=200)
        r = await conn.get_health()
        assert r["success"] is True

        conn2, _ = servicenow_conn(monkeypatch, payload=None, status=500)
        r2 = await conn2.get_health()
        assert r2["success"] is False

        req = httpx.Request("GET", "http://x")
        conn3, _ = servicenow_conn(monkeypatch, exc=httpx.RequestError("down", request=req))
        r3 = await conn3.get_health()
        assert r3["success"] is False

    def test_map_priority(self):
        conn = ServiceNowConnector("t", {"instance": "x", "username": "u", "password": "p"})
        assert conn._map_priority("low") == 3
        assert conn._map_priority("normal") == 2
        assert conn._map_priority("high") == 1
        assert conn._map_priority("urgent") == 1
        assert conn._map_priority("bogus") == 2

    def test_map_status(self):
        conn = ServiceNowConnector("t", {"instance": "x", "username": "u", "password": "p"})
        assert conn._map_status("new") == 1
        assert conn._map_status("open") == 2
        assert conn._map_status("pending") == 3
        assert conn._map_status("solved") == 6
        assert conn._map_status("closed") == 7
        assert conn._map_status("bogus") == 1

    @pytest.mark.asyncio
    async def test_close(self, monkeypatch):
        conn, _ = servicenow_conn(monkeypatch, payload={})
        aclose = AsyncMock()
        monkeypatch.setattr(conn._client, "aclose", aclose)
        await conn.close()
        aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# TicketingService
# ---------------------------------------------------------------------------


class TestTicketingService:
    @pytest.fixture
    def connector(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_create(self, connector):
        connector.create_ticket = AsyncMock(return_value={"success": True})
        svc = TicketingService(connector)
        r = await svc.create_ticket({"subject": "S"})
        assert r == {"success": True}
        connector.create_ticket.assert_awaited_once_with({"subject": "S"})

    @pytest.mark.asyncio
    async def test_get(self, connector):
        connector.get_ticket = AsyncMock(return_value={"success": True})
        r = await TicketingService(connector).get_ticket("T1")
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_update(self, connector):
        connector.update_ticket = AsyncMock(return_value={"success": True})
        r = await TicketingService(connector).update_ticket("T1", {"status": "open"})
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_list(self, connector):
        connector.list_tickets = AsyncMock(return_value={"success": True})
        r = await TicketingService(connector).list_tickets("t", status="open")
        connector.list_tickets.assert_awaited_once_with("t", "open")
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_sync_from_call(self, connector):
        connector.create_ticket = AsyncMock(return_value={"success": True})
        r = await TicketingService(connector).sync_from_call(
            {
                "caller_number": "+15550001111",
                "ai_summary": "Customer wants a refund",
                "call_id": "CA123",
            }
        )
        assert r["success"] is True
        data = connector.create_ticket.call_args.args[0]
        assert data["subject"] == "+15550001111"
        assert data["description"] == "Customer wants a refund"
        assert data["customer_id"] == "+15550001111"
        assert data["call_id"] == "CA123"
        assert data["priority"] == "normal"

    @pytest.mark.asyncio
    async def test_sync_from_call_defaults(self, connector):
        connector.create_ticket = AsyncMock(return_value={"success": True})
        await TicketingService(connector).sync_from_call({})
        data = connector.create_ticket.call_args.args[0]
        assert data["subject"] == "Unknown"
        assert data["description"] == "Ticket from call sync"

    @pytest.mark.asyncio
    async def test_get_health(self, connector):
        connector.get_health = AsyncMock(return_value={"success": True})
        r = await TicketingService(connector).get_health()
        assert r["success"] is True

    def test_is_connector(self, connector):
        assert isinstance(TicketingService(connector).connector, MagicMock)


# ---------------------------------------------------------------------------
# TicketingFactory
# ---------------------------------------------------------------------------


class TestTicketingFactory:
    def test_get_connector_known(self):
        conn = TicketingFactory.get_connector("t", "zendesk", {"subdomain": "x"})
        assert isinstance(conn, ZendeskConnector)
        conn2 = TicketingFactory.get_connector("t", "servicenow", {"instance": "x"})
        assert isinstance(conn2, ServiceNowConnector)

    def test_get_connector_unknown(self):
        with pytest.raises(ValueError, match="Unsupported ticketing provider"):
            TicketingFactory.get_connector("t", "freshdesk", {})

    @pytest.mark.asyncio
    async def test_from_tenant_found(self):
        async def fake_list(tenant_id, integration_type=None):
            return [
                {"provider": "zendesk", "config_json": {"subdomain": "acme"}},
                {"provider": "servicenow", "config_json": {"instance": "sn"}},
            ]

        with patch("api.services.ticketing.list_integration_configs_db", new=fake_list):
            conn = await TicketingFactory.from_tenant("t", "servicenow")
        assert isinstance(conn, ServiceNowConnector)

    @pytest.mark.asyncio
    async def test_from_tenant_missing_config(self):
        async def fake_list(tenant_id, integration_type=None):
            return [{"provider": "zendesk", "config_json": {}}]

        with patch("api.services.ticketing.list_integration_configs_db", new=fake_list):
            with pytest.raises(ValueError, match="No ticketing config"):
                await TicketingFactory.from_tenant("t", "servicenow")

    @pytest.mark.asyncio
    async def test_from_tenant_no_configs(self):
        async def fake_list(tenant_id, integration_type=None):
            return []

        with patch("api.services.ticketing.list_integration_configs_db", new=fake_list):
            with pytest.raises(ValueError, match="No ticketing config"):
                await TicketingFactory.from_tenant("t", "zendesk")
