"""Tests for src/api/routers/integrations.py — CRM + ticketing + config router."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.routers.integrations as mod  # noqa: E402
from api.services.auth import verify_tenant_access  # noqa: E402


@pytest.fixture
def ctx(monkeypatch):
    crm = MagicMock()
    crm.create_contact = AsyncMock(return_value={"ok": True, "id": "c1"})
    crm.search_contacts = AsyncMock(return_value={"data": {"contacts": [], "total": 0}})
    crm.get_contact = AsyncMock(return_value={"ok": True, "id": "c1"})
    crm.update_contact = AsyncMock(return_value={"ok": True, "id": "c1"})
    crm.sync_contacts = AsyncMock(return_value={"ok": True, "timestamp": "2026-01-01"})
    crm.get_health = AsyncMock(return_value={"success": True, "data": {"status": "healthy"}})

    tick_conn = MagicMock()
    tick_svc = MagicMock()
    tick_svc.create_ticket = AsyncMock(
        return_value={"success": True, "data": {"id": "t1"}}
    )
    tick_svc.list_tickets = AsyncMock(
        return_value={"success": True, "data": {"tickets": [], "total": 0}}
    )
    tick_svc.get_ticket = AsyncMock(return_value={"success": True, "data": {"id": "t1"}})
    tick_svc.update_ticket = AsyncMock(return_value={"success": True})
    tick_svc.sync_from_call = AsyncMock(
        return_value={"success": True, "data": {"id": "t2"}}
    )
    tick_svc.get_health = AsyncMock(return_value={"success": True, "data": {"status": "ok"}})

    connector_factory = MagicMock()
    connector_factory.get_connector = MagicMock(return_value=crm)

    ticketing_factory = MagicMock()
    ticketing_factory.get_connector = MagicMock(return_value=tick_conn)

    service_cls = MagicMock()
    service_cls.return_value = tick_svc

    monkeypatch.setattr(mod, "CRMConnectorFactory", connector_factory)
    monkeypatch.setattr(mod, "TicketingFactory", ticketing_factory)
    monkeypatch.setattr(mod, "TicketingService", service_cls)

    list_configs = AsyncMock(return_value=[])
    get_config = AsyncMock(return_value=None)
    create_config = AsyncMock(return_value={"ok": True})
    update_config = AsyncMock(return_value={"ok": True})
    create_sync_log = AsyncMock(return_value={"id": "log-1"})

    monkeypatch.setattr(mod, "list_integration_configs_db", list_configs)
    monkeypatch.setattr(mod, "get_integration_config_db", get_config)
    monkeypatch.setattr(mod, "create_integration_config_db", create_config)
    monkeypatch.setattr(mod, "update_integration_config_db", update_config)
    monkeypatch.setattr(mod, "create_ticket_sync_log_db", create_sync_log)

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[verify_tenant_access] = lambda: "tenant-1"
    client = TestClient(app)

    yield client, crm, tick_svc, list_configs, get_config
    client.close()


def test_crm_endpoints_without_config(ctx):
    client, _, _, list_configs, _ = ctx
    list_configs.return_value = []  # no CRM config
    assert client.post("/integrations/crm/contacts", json={"name": "x"}).status_code == 400
    assert client.get("/integrations/crm/contacts").status_code == 200  # returns empty
    assert client.get("/integrations/crm/contacts/c1").status_code == 400
    assert client.put("/integrations/crm/contacts/c1", json={"name": "x"}).status_code == 400
    assert client.post("/integrations/crm/sync").status_code == 400
    assert client.get("/integrations/crm/health").status_code == 200  # not_configured


def test_crm_endpoints_with_config(ctx):
    client, crm, _, list_configs, _ = ctx
    list_configs.return_value = [
        {"provider": "hubspot", "integration_type": "crm", "config_json": "{}"}
    ]

    r = client.post("/integrations/crm/contacts", json={"name": "x"})
    assert r.status_code == 200
    crm.create_contact.assert_awaited_once()

    assert client.get("/integrations/crm/contacts").status_code == 200
    assert client.get("/integrations/crm/contacts/c1").status_code == 200
    assert client.put("/integrations/crm/contacts/c1", json={"name": "x"}).status_code == 200

    sync = client.post("/integrations/crm/sync")
    assert sync.status_code == 200
    crm.sync_contacts.assert_awaited_once()

    assert client.get("/integrations/crm/health").status_code == 200


def test_ticketing_endpoints_without_config(ctx):
    client, _, _, list_configs, _ = ctx
    list_configs.return_value = []
    assert client.post("/integrations/ticketing/tickets", json={"subject": "x"}).status_code == 400
    assert client.get("/integrations/ticketing/tickets").status_code == 200  # empty
    assert client.get("/integrations/ticketing/tickets/t1").status_code == 400
    assert client.put("/integrations/ticketing/tickets/t1", json={"subject": "x"}).status_code == 400
    assert client.post("/integrations/ticketing/sync-from-call", json={"call_id": "c1"}).status_code == 400
    assert client.get("/integrations/ticketing/health").status_code == 200  # not_configured


def test_ticketing_endpoints_with_config(ctx):
    client, _, tick_svc, list_configs, _ = ctx
    list_configs.return_value = [
        {"provider": "zendesk", "integration_type": "ticketing", "config_json": "{}"}
    ]

    r = client.post("/integrations/ticketing/tickets", json={"subject": "Ticket"})
    assert r.status_code == 200
    tick_svc.create_ticket.assert_awaited_once()

    assert client.get("/integrations/ticketing/tickets").status_code == 200
    assert client.get("/integrations/ticketing/tickets/t1").status_code == 200
    assert client.put("/integrations/ticketing/tickets/t1", json={"subject": "x"}).status_code == 200
    assert client.post("/integrations/ticketing/sync-from-call", json={"call_id": "c1"}).status_code == 200
    assert client.get("/integrations/ticketing/health").status_code == 200


def test_configs_list(ctx):
    client, _, _, list_configs, _ = ctx
    list_configs.return_value = [{"provider": "hubspot"}]
    r = client.get("/integrations/configs")
    assert r.status_code == 200
    assert r.json()["configs"] == [{"provider": "hubspot"}]


def test_create_or_update_config_existing(ctx):
    client, _, _, _, get_config = ctx
    get_config.return_value = {"provider": "hubspot"}  # existing -> update
    r = client.post(
        "/integrations/configs",
        json={"provider": "hubspot", "integration_type": "crm", "config": {}, "status": "active"},
    )
    assert r.status_code == 200


def test_create_or_update_config_new(ctx):
    client, _, _, _, get_config = ctx
    get_config.return_value = None  # new -> create
    r = client.post(
        "/integrations/configs",
        json={"provider": "salesforce", "integration_type": "crm", "config": {}, "status": "active"},
    )
    assert r.status_code == 200


def test_create_or_update_config_failure(ctx):
    client, _, _, _, get_config = ctx
    get_config.return_value = None
    mod.create_integration_config_db.return_value = None
    r = client.post(
        "/integrations/configs",
        json={"provider": "salesforce", "integration_type": "crm", "config": {}, "status": "active"},
    )
    assert r.status_code == 400


def test_all_health(ctx):
    client, crm, tick_svc, list_configs, _ = ctx
    list_configs.return_value = [
        {"provider": "hubspot", "integration_type": "crm", "config_json": "{}"},
        {"provider": "zendesk", "integration_type": "ticketing", "config_json": "{}"},
        {"provider": "other", "integration_type": "unknown", "config_json": "{}"},
    ]
    r = client.get("/integrations/health")
    assert r.status_code == 200
    body = r.json()
    assert "hubspot" in body["health"]
    assert "zendesk" in body["health"]
    assert body["health"]["other"]["data"]["status"] == "unknown_type"
    crm.get_health.assert_awaited()
    tick_svc.get_health.assert_awaited()


def test_all_health_catches_errors(ctx):
    client, crm, _, list_configs, _ = ctx
    crm.get_health.side_effect = RuntimeError("boom")
    list_configs.return_value = [
        {"provider": "hubspot", "integration_type": "crm", "config_json": "{}"}
    ]
    r = client.get("/integrations/health")
    assert r.status_code == 200
    assert r.json()["health"]["hubspot"]["data"]["status"] == "error"


def test_crm_sync_persists_last_sync(ctx):
    client, crm, _, list_configs, _ = ctx
    list_configs.return_value = [
        {"provider": "hubspot", "integration_type": "crm", "config_json": "{}"}
    ]
    crm.sync_contacts = AsyncMock(return_value={"ok": True, "timestamp": "2026-02-02"})
    r = client.post("/integrations/crm/sync")
    assert r.status_code == 200
    assert mod.update_integration_config_db.await_count == 1
    call_args = mod.update_integration_config_db.call_args
    assert call_args.args[0] == "tenant-1"
    assert call_args.args[1] == "hubspot"
    assert call_args.kwargs["last_sync_at"] == "2026-02-02"
    assert call_args.kwargs["status"] == "active"


def test_create_ticket_writes_sync_log(ctx):
    client, _, tick_svc, list_configs, _ = ctx
    list_configs.return_value = [
        {"provider": "zendesk", "integration_type": "ticketing", "config_json": "{}"}
    ]
    tick_svc.create_ticket = AsyncMock(
        return_value={"success": True, "data": {"id": "tkt-9"}}
    )
    r = client.post(
        "/integrations/ticketing/tickets",
        json={"subject": "Ticket", "call_id": "CA-100"},
    )
    assert r.status_code == 200
    assert mod.create_ticket_sync_log_db.await_count == 1
    call_args = mod.create_ticket_sync_log_db.call_args
    assert call_args.args[1] == "tkt-9"
    assert call_args.kwargs["call_id"] == "CA-100"
    assert call_args.kwargs["direction"] == "outbound"
    assert call_args.kwargs["status"] == "success"


def test_sync_from_call_writes_sync_log(ctx):
    client, _, tick_svc, list_configs, _ = ctx
    list_configs.return_value = [
        {"provider": "zendesk", "integration_type": "ticketing", "config_json": "{}"}
    ]
    tick_svc.sync_from_call = AsyncMock(
        return_value={"success": True, "data": {"id": "tkt-22"}}
    )
    r = client.post(
        "/integrations/ticketing/sync-from-call", json={"call_id": "CA-200"}
    )
    assert r.status_code == 200
    assert mod.create_ticket_sync_log_db.await_count == 1
    assert mod.create_ticket_sync_log_db.call_args.kwargs["call_id"] == "CA-200"


def test_create_or_update_config_existing_uses_update(ctx):
    client, _, _, _, get_config = ctx
    get_config.return_value = {"provider": "hubspot"}
    r = client.post(
        "/integrations/configs",
        json={
            "provider": "hubspot",
            "integration_type": "crm",
            "config": {"api_key": "x"},
            "status": "active",
        },
    )
    assert r.status_code == 200
    assert mod.create_integration_config_db.await_count == 0
    assert mod.update_integration_config_db.await_count == 1
    call_args = mod.update_integration_config_db.call_args
    assert call_args.kwargs["config_json"] == {"api_key": "x"}
    assert call_args.kwargs["status"] == "active"


def test_crm_contact_uses_configured_provider(ctx):
    client, crm, _, list_configs, _ = ctx
    list_configs.return_value = [
        {"provider": "salesforce", "integration_type": "crm", "config_json": "{}"}
    ]
    r = client.post("/integrations/crm/contacts", json={"name": "x"})
    assert r.status_code == 200
    assert mod.CRMConnectorFactory.get_connector.call_args[0][1] == "salesforce"

