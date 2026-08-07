"""Unit tests for api.services.runbooks.RunbookEngine."""

import pytest

import api.services.runbooks as runbooks_module
from api.services.runbooks import RUNBOOKS, runbook_engine


@pytest.fixture(autouse=True)
def clean_incidents():
    runbooks_module._active_incidents.clear()
    yield
    runbooks_module._active_incidents.clear()


def _trigger(incident_type="telephony_outage", tenant_id="t1"):
    return runbook_engine.trigger_runbook(incident_type, {"tenant_id": tenant_id})


class TestRunbookEngine:
    def test_trigger_unknown_type(self):
        result = runbook_engine.trigger_runbook("banana")
        assert result["success"] is False
        assert "Unknown incident type" in result["error"]

    def test_trigger_success(self):
        result = _trigger()
        assert result["success"] is True
        incident = result["incident"]
        assert incident["id"]
        assert incident["type"] == "telephony_outage"
        assert incident["status"] == "in_progress"
        assert incident["current_step"] == 1
        assert incident["escalation_level"] == 0
        assert incident["context"] == {"tenant_id": "t1"}
        assert incident["log"][0]["event"] == "runbook_triggered"
        assert len(incident["steps"]) == 5
        assert runbooks_module._active_incidents[incident["id"]] is incident

    def test_trigger_without_context(self):
        result = runbook_engine.trigger_runbook("database_failure")
        assert result["incident"]["context"] == {}

    def test_get_active_incidents(self):
        _trigger("telephony_outage", "t1")
        _trigger("database_failure", "t2")
        incidents = runbook_engine.get_active_incidents()
        assert len(incidents) == 2

    def test_get_active_incidents_filtered_by_tenant(self):
        _trigger("telephony_outage", "t1")
        _trigger("database_failure", "t2")
        incidents = runbook_engine.get_active_incidents("t1")
        assert len(incidents) == 1
        assert incidents[0]["context"]["tenant_id"] == "t1"

    def test_get_active_incidents_sorted_by_created_at(self, monkeypatch):
        counter = {"value": 100.0}

        def _tick():
            counter["value"] += 1.0
            return counter["value"]

        monkeypatch.setattr(runbooks_module.time, "time", _tick)
        _trigger("telephony_outage", "t1")
        _trigger("database_failure", "t1")
        incidents = runbook_engine.get_active_incidents("t1")
        assert incidents[0]["type"] == "database_failure"  # newest first

    def test_get_incident_found(self):
        incident = _trigger()["incident"]
        assert runbook_engine.get_incident(incident["id"]) == incident

    def test_get_incident_missing(self):
        assert runbook_engine.get_incident("nope") is None

    def test_advance_step_not_found(self):
        result = runbook_engine.advance_step("nope")
        assert result == {"success": False, "error": "Incident not found"}

    def test_advance_step_normal(self):
        incident = _trigger()["incident"]
        result = runbook_engine.advance_step(incident["id"], result="ok")
        assert result["success"] is True
        assert incident["current_step"] == 2
        assert incident["log"][-1]["event"] == "step_completed"
        assert incident["log"][-1]["result"] == "ok"

    def test_advance_step_resolves(self):
        incident = _trigger()["incident"]
        num_steps = len(incident["steps"])
        for _ in range(num_steps):
            runbook_engine.advance_step(incident["id"])
        assert incident["current_step"] == num_steps + 1
        assert incident["status"] == "resolved"
        assert incident["log"][-1]["event"] == "runbook_resolved"

    def test_advance_step_past_end(self):
        incident = _trigger()["incident"]
        for _ in range(len(incident["steps"]) + 2):
            runbook_engine.advance_step(incident["id"])
        assert incident["status"] == "resolved"

    def test_escalate_not_found(self):
        result = runbook_engine.escalate("nope")
        assert result == {"success": False, "error": "Incident not found"}

    def test_escalate_max_level(self):
        incident = _trigger()["incident"]
        max_level = len(incident["escalation_paths"])
        for _ in range(max_level):
            assert runbook_engine.escalate(incident["id"])["success"] is True
        result = runbook_engine.escalate(incident["id"])
        assert result == {
            "success": False,
            "error": "Already at maximum escalation level",
        }

    def test_escalate_success(self):
        incident = _trigger()["incident"]
        result = runbook_engine.escalate(incident["id"])
        assert result["success"] is True
        assert incident["escalation_level"] == 1
        assert incident["log"][-1]["event"] == "escalated"
        assert incident["log"][-1]["contacts"] == incident["escalation_paths"][0][
            "contacts"
        ]

    def test_get_runbook_list(self):
        result = runbook_engine.get_runbook_list()
        assert len(result) == len(RUNBOOKS)
        for entry in result:
            assert set(entry.keys()) == {"id", "name", "severity", "description"}
