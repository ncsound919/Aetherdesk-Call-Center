"""Tests for src/api/services/db_integrations.py — SQLite-backed CRUD for
integration configs and ticket sync logs."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from api.services.database import init_sqlite_schema  # noqa: E402
from api.services.db_pool import _get_sqlite_conn  # noqa: E402

import api.services.db_integrations as m  # noqa: E402

TENANT = "tenant-int"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _schema_and_cleanup():
    init_sqlite_schema()
    conn = _get_sqlite_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO tenants (id, name, slug) VALUES (?, 'Test', 'test')",
            (TENANT,),
        )
        conn.commit()
    finally:
        conn.close()
    yield
    conn = _get_sqlite_conn()
    try:
        for table in ["integration_configs", "ticket_sync_log"]:
            try:
                conn.execute(f"DELETE FROM {table} WHERE tenant_id = ?", (TENANT,))
            except Exception:
                pass
        conn.execute("DELETE FROM tenants WHERE id = ?", (TENANT,))
        conn.commit()
    finally:
        conn.close()


def test_create_and_get_config():
    cfg = run(
        m.create_integration_config_db(
            TENANT, "hubspot", "crm", {"api_key": "k"}, status="active"
        )
    )
    assert cfg and cfg["provider"] == "hubspot"

    got = run(m.get_integration_config_db(TENANT, "hubspot"))
    assert got and got["provider"] == "hubspot"
    assert run(m.get_integration_config_db(TENANT, "nope")) is None


def test_list_configs():
    run(m.create_integration_config_db(TENANT, "hubspot", "crm", "{}"))
    run(m.create_integration_config_db(TENANT, "zendesk", "ticketing", "{}"))
    all_cfgs = run(m.list_integration_configs_db(TENANT))
    assert len(all_cfgs) == 2
    crm_cfgs = run(m.list_integration_configs_db(TENANT, integration_type="crm"))
    assert len(crm_cfgs) == 1
    assert crm_cfgs[0]["provider"] == "hubspot"


def test_update_config():
    run(m.create_integration_config_db(TENANT, "hubspot", "crm", "{}"))
    updated = run(
        m.update_integration_config_db(
            TENANT,
            "hubspot",
            config_json={"api_key": "new"},
            status="error",
            last_sync_at="2026-01-01",
            error_message="oops",
        )
    )
    assert updated is not None
    assert updated["status"] == "error"
    assert "new" in updated["config_json"]

    no_updates = run(m.update_integration_config_db(TENANT, "hubspot"))
    assert no_updates is None


def test_create_and_list_ticket_sync_logs():
    log = run(
        m.create_ticket_sync_log_db(
            TENANT,
            "ticket-1",
            call_id=None,
            direction="outbound",
            status="success",
            payload_json={"subject": "x"},
            response_json={"id": "ticket-1"},
        )
    )
    assert log and log["id"]
    assert log["payload_json"] is not None
    assert log["response_json"] is not None

    logs = run(m.list_ticket_sync_logs_db(TENANT))
    assert any(l["id"] == log["id"] for l in logs)
    success_logs = run(m.list_ticket_sync_logs_db(TENANT, status="success"))
    assert any(l["id"] == log["id"] for l in success_logs)
    failed_logs = run(m.list_ticket_sync_logs_db(TENANT, status="failed"))
    assert all(l["id"] != log["id"] for l in failed_logs)


def test_ticket_sync_log_with_strings():
    log = run(
        m.create_ticket_sync_log_db(
            TENANT,
            "ticket-2",
            payload_json="raw",
            response_json="raw2",
        )
    )
    assert log is not None


class _FakeRow(dict):
    pass


class _FakePool:
    async def fetch(self, query, *params):
        return [_FakeRow({"id": "1", "tenant_id": TENANT, "provider": "hubspot"})]

    async def fetchrow(self, query, *params):
        return _FakeRow({"id": "1", "tenant_id": TENANT, "provider": "hubspot"})

    async def execute(self, query, *params):
        return None


def test_postgres_branches(monkeypatch):
    monkeypatch.setattr(m, "USE_POSTGRES", True)
    monkeypatch.setattr(m, "get_pg_pool", AsyncMock(return_value=_FakePool()))

    assert run(
        m.create_integration_config_db(TENANT, "hubspot", "crm", {"k": "v"})
    ) is not None
    assert run(m.create_integration_config_db(TENANT, "hs", "crm", "raw")) is not None
    assert run(m.list_integration_configs_db(TENANT)) is not None
    assert run(m.list_integration_configs_db(TENANT, integration_type="crm")) is not None
    assert run(m.get_integration_config_db(TENANT, "hubspot")) is not None
    assert run(
        m.update_integration_config_db(
            TENANT,
            "hubspot",
            config_json={"k": "v"},
            status="active",
            last_sync_at="2026-01-01",
            error_message="x",
        )
    ) is not None
    assert run(m.update_integration_config_db(TENANT, "hubspot", config_json={})) is not None
    assert run(m.create_ticket_sync_log_db(TENANT, "t1", payload_json={"a": 1})) is not None
    assert run(m.list_ticket_sync_logs_db(TENANT)) is not None
    assert run(m.list_ticket_sync_logs_db(TENANT, status="success", limit=5, offset=1)) is not None


def test_postgres_no_pool_fallback(monkeypatch):
    monkeypatch.setattr(m, "USE_POSTGRES", True)
    monkeypatch.setattr(m, "get_pg_pool", AsyncMock(return_value=None))

    assert run(m.create_integration_config_db(TENANT, "hubspot", "crm", "{}")) is None
    assert run(m.list_integration_configs_db(TENANT)) is None
    assert run(m.get_integration_config_db(TENANT, "hubspot")) is None
    assert run(
        m.update_integration_config_db(TENANT, "hubspot", status="active")
    ) is None
    assert run(m.create_ticket_sync_log_db(TENANT, "t1")) is None
    assert run(m.list_ticket_sync_logs_db(TENANT)) is None
