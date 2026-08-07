"""Tests for src/api/services/db_tenants.py — SQLite-backed CRUD for tenants,
agents, users, subscription/usage, leads, and scripts."""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from api.services.database import init_sqlite_schema  # noqa: E402
from api.services.db_pool import _get_sqlite_conn  # noqa: E402

import api.services.db_tenants as m  # noqa: E402

TENANT = "tenant-big"

TENANT_TABLES = [
    "agent_activity",
    "agent_profiles",
    "agents",
    "billing_records",
    "leads",
    "scripts",
    "tenant_settings",
    "users",
]


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module", autouse=True)
def _fresh_db(tmp_path_factory):
    """Point SQLite at a fresh temp DB built from the translated canonical
    schema, so stale aetherdesk.db definitions don't interfere."""
    import api.services.db_config as cfg
    import api.services.db_pool as pool

    db_path = str(tmp_path_factory.mktemp("tenants_db") / "test.db")
    cfg.SQLITE_PATH = db_path
    pool.SQLITE_PATH = db_path
    conn = _get_sqlite_conn()
    try:
        from api.services.db_schema import SCHEMA_SQL
        from api.services.db_sqlite_transform import postgres_to_sqlite

        conn.executescript(postgres_to_sqlite(SCHEMA_SQL))
        # Canonical SCHEMA_SQL is missing these two tables / a column used by db_tenants.
        conn.executescript(
            """
            ALTER TABLE tenants ADD COLUMN api_key TEXT;
            CREATE TABLE IF NOT EXISTS tenant_settings (
                tenant_id TEXT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
                api_feeds TEXT DEFAULT '[]',
                auto_mode_enabled INTEGER DEFAULT 0,
                redact_pii INTEGER DEFAULT 1,
                require_consent INTEGER DEFAULT 1,
                sync_dnc INTEGER DEFAULT 0,
                mcp_servers TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                company_name TEXT, contact_name TEXT, first_name TEXT, last_name TEXT,
                phone TEXT NOT NULL, email TEXT, industry TEXT, notes TEXT,
                priority INTEGER DEFAULT 5, status TEXT DEFAULT 'new', score REAL DEFAULT 0.0,
                source TEXT, imported_at TIMESTAMP, last_called_at TIMESTAMP,
                custom_fields TEXT DEFAULT '{}', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _db(_fresh_db):
    conn = _get_sqlite_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO tenants (id, name, slug, email) VALUES (?, 'Big', 'big', ?)",
            (TENANT, f"{TENANT}@test.com"),
        )
        conn.commit()
    finally:
        conn.close()
    yield
    conn = _get_sqlite_conn()
    try:
        for t in TENANT_TABLES:
            try:
                conn.execute(f"DELETE FROM {t} WHERE tenant_id = ?", (TENANT,))
            except Exception:
                pass
        try:
            conn.execute("DELETE FROM script_templates")
        except Exception:
            pass
        conn.execute("DELETE FROM tenants WHERE id = ?", (TENANT,))
        conn.commit()
    finally:
        conn.close()


# --- Tenants ---


def test_create_and_get_tenant():
    t = run(m.create_tenant("BigCo", "big@co.com", "bigco"))
    assert t is not None
    tid = t["id"]
    got = run(m.get_tenant_db(tid))
    assert got is not None
    assert run(m.get_tenant_db("nope")) is None
    tenants = run(m.list_tenants_db())
    assert any(x["id"] == tid for x in tenants)
    by_key = run(m.get_tenant_by_api_key(t["api_key"]))
    assert by_key is not None
    assert run(m.get_tenant_by_api_key("bad")) is None
    assert run(m.verify_tenant_api_key(tid, t["api_key"])) is True
    assert run(m.verify_tenant_api_key(tid, "bad")) is False


def test_create_tenant_with_gdpr():
    t = run(m.create_tenant("Co", "c@c.com", "co", gdpr_consent=True, settings={"k": 1}))
    assert t is not None
    assert t["gdpr_consent"] in (1, True)


# --- Agents ---


def test_agents_crud():
    a = run(
        m.create_agent(
            TENANT, "AgentA", "Agent A", skills=["support"], config={"k": 1}
        )
    )
    assert a is not None
    aid = a["id"]
    assert run(m.get_agent_db(aid)) is not None
    assert run(m.get_agent_db("nope")) is None
    assert len(run(m.list_agents(TENANT))) == 1

    st = run(m.update_agent_status(aid, "busy", session_ref="s1"))
    assert st["success"] is True
    assert st["new_status"] == "busy"

    up = run(
        m.update_agent_db(
            aid,
            TENANT,
            name="AgentB",
            display_name="Agent B",
            agent_type="human",
            skills=["billing"],
            config={"x": 1},
        )
    )
    assert up is not None
    assert up["name"] == "AgentB"

    assert run(m.delete_agent_db(aid, TENANT)) is True
    assert run(m.delete_agent_db(aid, TENANT)) is False


def test_parse_skills():
    assert m._parse_skills(None) == []
    assert m._parse_skills(["a"]) == ["a"]
    assert m._parse_skills('["a", "b"]') == ["a", "b"]
    assert m._parse_skills("notjson") == []
    assert m._parse_skills(123) == []


def test_get_available_agents():
    a = run(m.create_agent(TENANT, "FreeAgent", "Free", skills=["support"]))
    run(m.update_agent_status(a["id"], "available"))
    run(m.create_agent(TENANT, "BusyAgent", "Busy", skills=["support"]))
    agents = run(m.get_available_agents(TENANT))
    assert len(agents) == 1
    filtered = run(m.get_available_agents(TENANT, skills=["support"]))
    assert len(filtered) == 1
    no_match = run(m.get_available_agents(TENANT, skills=["nope"]))
    assert len(no_match) == 0


def test_create_agent_profile():
    run(m.create_agent_profile_db("prof-1", TENANT, "P1", "prompt", {"k": 1}))
    conn = _get_sqlite_conn()
    try:
        row = conn.execute(
            "SELECT * FROM agent_profiles WHERE id = 'prof-1'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None


# --- Tenant settings ---


def test_tenant_settings():
    run(
        m.update_tenant_settings_db(
            TENANT, {"api_feeds": [1], "auto_mode_enabled": 1}
        )
    )
    got = run(m.get_tenant_settings_db(TENANT))
    assert got is not None
    assert run(m.get_tenant_settings_db("nope")) is None


# --- Users ---


def test_users_flow():
    u = run(m.create_user_db("user@co.com", "hash", "U", tenant_id=TENANT))
    assert u["id"]
    assert run(m.get_user_by_email_db("user@co.com")) is not None
    assert run(m.get_user_by_email_db("missing@co.com")) is None
    by_id = run(m.get_user_by_id_db(u["id"]))
    assert by_id is not None
    assert run(m.get_user_by_id_db("nope")) is None

    assert run(m.verify_user_email_db(u["verification_token"])) == u["id"]
    assert run(m.verify_user_email_db(u["verification_token"])) is None

    uid, token = run(m.set_password_reset_token_db("user@co.com"))
    assert uid == u["id"] and token
    assert run(m.set_password_reset_token_db("missing@co.com")) == (None, None)

    assert run(m.reset_password_db(token, "newhash")) == u["id"]

    run(m.update_user_onboarding_db(u["id"], 3, completed=True))
    by_id2 = run(m.get_user_by_id_db(u["id"]))
    assert by_id2["onboarding_completed"] in (1, True)


# --- Subscription / usage ---


def test_subscription_and_usage():
    run(m.update_tenant_subscription_db(TENANT, stripe_customer_id="cus_1", plan_id="p1"))
    assert run(m.get_tenant_by_stripe_customer_db("cus_1")) is not None
    assert run(m.get_tenant_by_stripe_customer_db("nope")) is None

    run(m.record_usage_db(TENANT, "agent_minutes", 10.5, "2026-01-01", "2026-01-31"))
    assert run(m.get_tenant_plan_db(TENANT)) is not None
    assert run(m.count_active_agents_db(TENANT)) == 0
    assert run(m.count_active_calls_db(TENANT)) == 0


# --- Leads ---


def test_leads_crud():
    lead = run(
        m.create_lead_db(
            TENANT, "555-0100", company_name="ACME", custom_fields={"c": 1}
        )
    )
    assert lead["id"]
    lid = lead["id"]
    assert run(m.get_lead_db(lid, TENANT)) is not None
    assert run(m.get_lead_db("nope", TENANT)) is None
    assert len(run(m.list_leads_db(TENANT))) == 1
    assert len(run(m.list_leads_db(TENANT, status="new"))) == 1
    assert len(run(m.list_leads_db(TENANT, status="closed"))) == 0

    updated = run(
        m.update_lead_db(
            lid, TENANT, {"status": "qualified", "custom_fields": {"c2": 2}}
        )
    )
    assert updated is not None
    updated_empty = run(m.update_lead_db(lid, TENANT, {}))
    assert updated_empty is not None

    assert run(m.delete_lead_db(lid, TENANT)) is True
    assert run(m.delete_lead_db(lid, TENANT)) is False


def test_bulk_leads():
    l1 = run(m.create_lead_db(TENANT, "111"))
    l2 = run(m.create_lead_db(TENANT, "222"))
    assert run(m.bulk_update_leads_db(TENANT, [], {})) == 0
    assert run(m.bulk_delete_leads_db(TENANT, [])) == 0
    n = run(m.bulk_update_leads_db(TENANT, [l1["id"], l2["id"]], {"status": "qualified"}))
    assert n == 2
    n = run(m.bulk_update_leads_db(TENANT, [l1["id"]], {"custom_fields": {"tag": "vip"}}))
    assert n == 1
    n = run(m.bulk_delete_leads_db(TENANT, [l1["id"], l2["id"]]))
    assert n == 2


# --- Scripts ---


def test_scripts_crud():
    s = run(
        m.create_script_db(
            TENANT, "Intro", {"opening": "Hi"}, variables=[{"name": "x"}]
        )
    )
    assert s["id"]
    sid = s["id"]
    got = run(m.get_script_db(sid, TENANT))
    assert got is not None
    assert got["content"] == {"opening": "Hi"}
    assert run(m.get_script_db("nope", TENANT)) is None
    assert len(run(m.list_scripts_db(TENANT))) == 1
    assert len(run(m.list_scripts_db(TENANT, is_active=False))) == 1

    updated = run(
        m.update_script_db(
            sid,
            TENANT,
            {"name": "Intro2", "content": {"o": "2"}, "variables": [{"n": "y"}], "is_active": False},
        )
    )
    assert updated is not None
    updated_empty = run(m.update_script_db(sid, TENANT, {}))
    assert updated_empty is not None

    # Updating a non-existent script returns None in SQLite mode.
    assert run(m.update_script_db("nope", TENANT, {"name": "X"})) is None

    assert run(m.delete_script_db(sid, TENANT)) is True
    assert run(m.delete_script_db(sid, TENANT)) is False


def test_script_templates():
    t = run(
        m.create_script_template_db(
            "Cold Call", "desc", "insurance", {"q": 1}, [{"n": "x"}]
        )
    )
    assert t["id"]
    tid = t["id"]
    assert run(m.get_script_template_db(tid)) is not None
    assert run(m.get_script_template_db("nope")) is None
    assert len(run(m.list_script_templates_db())) >= 1
    assert len(run(m.list_script_templates_db(industry="insur"))) >= 1
    assert run(m.delete_script_template_db(tid)) is True
    assert run(m.delete_script_template_db(tid)) is False


# --- Postgres branches ---


class _FakeRow(dict):
    def __init__(self, **kw):
        defaults = {
            "id": "1",
            "tenant_id": TENANT,
            "name": "x",
            "content": "{}",
            "variables": "[]",
            "custom_fields": "{}",
            "api_key": "k",
        }
        defaults.update(kw)
        super().__init__(defaults)


class _FakePool:
    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def fetch(self, query, *params):
        return [_FakeRow()]

    async def fetchrow(self, query, *params):
        return _FakeRow()

    async def fetchval(self, query, *params):
        return '{"ok": true}'

    async def execute(self, query, *params):
        return "UPDATE 1"


def test_postgres_branches(monkeypatch):
    monkeypatch.setattr(m, "USE_POSTGRES", True)
    monkeypatch.setattr(m, "get_pg_pool", AsyncMock(return_value=_FakePool()))

    assert run(m.create_tenant("X", "x@x.com", "x")) is not None
    assert run(m.get_tenant_db("1")) is not None
    assert run(m.list_tenants_db()) is not None
    assert run(m.get_tenant_by_api_key("k")) is not None
    assert run(m.verify_tenant_api_key("1", "k")) is True
    assert run(m.create_agent(TENANT, "A", "A")) is not None
    assert run(m.get_agent_db("1")) is not None
    assert run(m.list_agents(TENANT)) is not None
    assert run(m.update_agent_status("1", "busy")) is not None
    assert run(m.update_agent_db("1", TENANT, name="B")) is not None
    assert run(
        m.update_agent_db(
            "1",
            TENANT,
            name="B",
            display_name="B",
            agent_type="human",
            skills=["s"],
            config={"k": 1},
        )
    ) is not None
    assert run(m.delete_agent_db("1", TENANT)) is True
    assert run(m.get_available_agents(TENANT)) is not None
    assert run(m.get_available_agents(TENANT, skills=["s"])) is not None
    run(m.create_agent_profile_db("p1", TENANT, "P", "prompt", {}))
    assert run(m.get_tenant_settings_db(TENANT)) is not None
    run(m.update_tenant_settings_db(TENANT, {"api_feeds": []}))
    assert run(m.get_user_by_email_db("e@e.com")) is not None
    assert run(m.create_user_db("e@e.com", "h", "U"))["id"]
    assert run(m.get_user_by_id_db("1")) is not None
    assert run(m.verify_user_email_db("tok")) is not None
    assert run(m.set_password_reset_token_db("e@e.com")) is not None
    assert run(m.reset_password_db("tok", "h")) is not None
    run(m.update_user_onboarding_db("1", 1, True))
    run(m.update_tenant_subscription_db(TENANT, stripe_customer_id="c"))
    assert run(m.get_tenant_by_stripe_customer_db("c")) is not None
    run(m.record_usage_db(TENANT, "m", 1.0, "s", "e"))
    assert run(m.get_tenant_plan_db(TENANT)) is not None
    assert run(m.count_active_agents_db(TENANT)) is not None
    assert run(m.count_active_calls_db(TENANT)) is not None
    assert run(m.create_lead_db(TENANT, "555"))["id"]
    assert run(m.get_lead_db("1", TENANT)) is not None
    assert run(m.list_leads_db(TENANT)) is not None
    assert run(m.list_leads_db(TENANT, status="new", industry="fin")) is not None
    assert run(m.update_lead_db("1", TENANT, {"status": "x"})) is not None
    assert run(m.delete_lead_db("1", TENANT)) is True
    assert run(m.bulk_update_leads_db(TENANT, ["1"], {"status": "x"})) == 1
    assert run(m.bulk_delete_leads_db(TENANT, ["1"])) == 1
    assert run(m.create_script_db(TENANT, "S", {"a": 1}))["id"]
    assert run(m.get_script_db("1", TENANT)) is not None
    assert run(m.list_scripts_db(TENANT)) is not None
    assert run(m.list_scripts_db(TENANT, is_active=True, limit=5, offset=0)) is not None
    assert run(m.update_script_db("1", TENANT, {"name": "N"})) is not None
    assert run(m.update_script_db("1", TENANT, {"content": {"a": 2}, "variables": [{"n": "x"}]})) is not None
    assert run(m.delete_script_db("1", TENANT)) is True
    assert run(m.get_script_template_db("1")) is not None
    assert run(m.list_script_templates_db()) is not None
    assert run(m.list_script_templates_db(industry="ins")) is not None
    assert run(m.create_script_template_db("N", "d", "i", {}, []))["id"]
    assert run(m.delete_script_template_db("1")) is True


def test_postgres_no_pool(monkeypatch):
    monkeypatch.setattr(m, "USE_POSTGRES", True)
    monkeypatch.setattr(m, "get_pg_pool", AsyncMock(return_value=None))

    assert run(m.create_tenant("X", "x@x.com", "x")) is None
    assert run(m.get_tenant_db("1")) is None
    assert run(m.list_tenants_db()) is None
    assert run(m.get_tenant_by_api_key("k")) is None
    assert run(m.verify_tenant_api_key("1", "k")) is False
    assert run(m.create_agent(TENANT, "A", "A")) is None
    assert run(m.get_agent_db("1")) is None
    assert run(m.list_agents(TENANT)) is None
    assert run(m.update_agent_status("1", "busy")) is None
    assert run(m.update_agent_db("1", TENANT, name="B")) is None
    assert run(m.delete_agent_db("1", TENANT)) is None
    assert run(m.get_available_agents(TENANT)) is None
    run(m.create_agent_profile_db("p1", TENANT, "P", "prompt", {}))
    assert run(m.get_tenant_settings_db(TENANT)) is None
    run(m.update_tenant_settings_db(TENANT, {"api_feeds": []}))
    assert run(m.get_user_by_email_db("e@e.com")) is None
