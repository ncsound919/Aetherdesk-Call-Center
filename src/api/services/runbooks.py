import time
import uuid

import structlog

logger = structlog.get_logger()

# Active incidents store
_active_incidents: dict[str, dict] = {}

# Predefined runbooks
RUNBOOKS = {
    "telephony_outage": {
        "name": "Telephony Outage",
        "severity": "critical",
        "description": "Complete or partial loss of telephony connectivity",
        "steps": [
            {"order": 1, "action": "check_provider_status", "description": "Check Twilio/Fonoster status page", "timeout_seconds": 60},
            {"order": 2, "action": "test_sip_connectivity", "description": "Test SIP trunk reachability", "timeout_seconds": 30},
            {"order": 3, "action": "check_freeswitch_status", "description": "Check FreeSWITCH process status", "timeout_seconds": 15},
            {"order": 4, "action": "enable_failover", "description": "Enable secondary telephony provider", "timeout_seconds": 30},
            {"order": 5, "action": "notify_escalation", "description": "Notify on-call engineer and escalation contacts", "timeout_seconds": 60},
        ],
        "escalation_paths": [
            {"level": 1, "contacts": ["on-call-engineer"], "timeout_minutes": 15},
            {"level": 2, "contacts": ["engineering-lead", "ops-manager"], "timeout_minutes": 30},
            {"level": 3, "contacts": ["vp-engineering", "cto"], "timeout_minutes": 60},
        ],
    },
    "database_failure": {
        "name": "Database Failure",
        "severity": "critical",
        "description": "PostgreSQL or SQLite database unavailable",
        "steps": [
            {"order": 1, "action": "check_db_process", "description": "Verify database process is running", "timeout_seconds": 30},
            {"order": 2, "action": "check_connections", "description": "Check connection pool and active connections", "timeout_seconds": 30},
            {"order": 3, "action": "check_disk_space", "description": "Verify disk space for WAL and data", "timeout_seconds": 15},
            {"order": 4, "action": "attempt_restart", "description": "Restart database service", "timeout_seconds": 60},
            {"order": 5, "action": "activate_readonly_mode", "description": "Enable read-only mode if write fails", "timeout_seconds": 30},
        ],
        "escalation_paths": [
            {"level": 1, "contacts": ["dba-on-call"], "timeout_minutes": 10},
            {"level": 2, "contacts": ["dba-lead", "engineering-lead"], "timeout_minutes": 20},
        ],
    },
    "llm_degradation": {
        "name": "LLM Service Degradation",
        "severity": "high",
        "description": "Groq/Ollama LLM response times degraded or failing",
        "steps": [
            {"order": 1, "action": "check_llm_health", "description": "Check Groq/Ollama endpoint health", "timeout_seconds": 30},
            {"order": 2, "action": "check_rate_limits", "description": "Verify API rate limits not exceeded", "timeout_seconds": 15},
            {"order": 3, "action": "switch_fallback_model", "description": "Switch to fallback LLM model", "timeout_seconds": 30},
            {"order": 4, "action": "enable_cached_responses", "description": "Enable cached response mode for common intents", "timeout_seconds": 60},
        ],
        "escalation_paths": [
            {"level": 1, "contacts": ["ai-team-lead"], "timeout_minutes": 20},
            {"level": 2, "contacts": ["engineering-lead"], "timeout_minutes": 45},
        ],
    },
    "security_incident": {
        "name": "Security Incident",
        "severity": "critical",
        "description": "Potential unauthorized access, data breach, or security compromise",
        "steps": [
            {"order": 1, "action": "isolate_system", "description": "Isolate affected systems, revoke compromised credentials", "timeout_seconds": 60},
            {"order": 2, "action": "preserve_evidence", "description": "Preserve logs and audit trails", "timeout_seconds": 30},
            {"order": 3, "action": "assess_scope", "description": "Assess scope and impact of the incident", "timeout_seconds": 300},
            {"order": 4, "action": "notify_legal", "description": "Notify legal and compliance teams if data breach", "timeout_seconds": 600},
            {"order": 5, "action": "notify_customers", "description": "Notify affected customers per regulatory requirements", "timeout_seconds": 3600},
        ],
        "escalation_paths": [
            {"level": 1, "contacts": ["security-lead"], "timeout_minutes": 5},
            {"level": 2, "contacts": ["cto", "legal"], "timeout_minutes": 15},
            {"level": 3, "contacts": ["ceo", "board"], "timeout_minutes": 60},
        ],
    },
    "provider_degradation": {
        "name": "Third-Party Provider Degradation",
        "severity": "medium",
        "description": "Deepgram, Chatterbox, or other provider degraded",
        "steps": [
            {"order": 1, "action": "check_provider_status", "description": "Check provider status page and API health", "timeout_seconds": 30},
            {"order": 2, "action": "switch_to_fallback", "description": "Switch to fallback provider (e.g., Deepgram→alternate STT)", "timeout_seconds": 60},
            {"order": 3, "action": "notify_provider_support", "description": "Open support ticket with provider", "timeout_seconds": 300},
            {"order": 4, "action": "enable_degraded_mode", "description": "Enable degraded service mode", "timeout_seconds": 60},
        ],
        "escalation_paths": [
            {"level": 1, "contacts": ["ops-on-call"], "timeout_minutes": 30},
            {"level": 2, "contacts": ["engineering-lead"], "timeout_minutes": 60},
        ],
    },
}

class RunbookEngine:
    def trigger_runbook(self, incident_type: str, context: dict = None) -> dict:
        """Trigger a runbook for an incident type."""
        if incident_type not in RUNBOOKS:
            return {"success": False, "error": f"Unknown incident type: {incident_type}"}

        incident_id = str(uuid.uuid4())
        runbook = RUNBOOKS[incident_type]
        incident = {
            "id": incident_id,
            "type": incident_type,
            "name": runbook["name"],
            "severity": runbook["severity"],
            "status": "in_progress",
            "current_step": 1,
            "steps": runbook["steps"],
            "escalation_level": 0,
            "escalation_paths": runbook["escalation_paths"],
            "context": context or {},
            "created_at": time.time(),
            "updated_at": time.time(),
            "log": [{"timestamp": time.time(), "event": "runbook_triggered", "details": f"Runbook '{runbook['name']}' triggered"}]
        }
        _active_incidents[incident_id] = incident
        logger.warning("runbook_triggered", incident_id=incident_id, type=incident_type, severity=runbook["severity"])
        return {"success": True, "incident": incident}

    def get_active_incidents(self, tenant_id: str = None) -> list:
        """Get all active incidents."""
        incidents = list(_active_incidents.values())
        if tenant_id:
            incidents = [i for i in incidents if i["context"].get("tenant_id") == tenant_id]
        return sorted(incidents, key=lambda x: x["created_at"], reverse=True)

    def get_incident(self, incident_id: str) -> dict | None:
        return _active_incidents.get(incident_id)

    def advance_step(self, incident_id: str, result: str = None) -> dict:
        """Advance to next step in the runbook."""
        incident = _active_incidents.get(incident_id)
        if not incident:
            return {"success": False, "error": "Incident not found"}

        step_idx = incident["current_step"] - 1
        if step_idx < len(incident["steps"]):
            incident["log"].append({
                "timestamp": time.time(),
                "event": "step_completed",
                "step": incident["current_step"],
                "result": result
            })

        incident["current_step"] += 1
        if incident["current_step"] > len(incident["steps"]):
            incident["status"] = "resolved"
            incident["log"].append({"timestamp": time.time(), "event": "runbook_resolved"})
        incident["updated_at"] = time.time()
        return {"success": True, "incident": incident}

    def escalate(self, incident_id: str) -> dict:
        """Escalate the incident to the next level."""
        incident = _active_incidents.get(incident_id)
        if not incident:
            return {"success": False, "error": "Incident not found"}

        max_level = len(incident["escalation_paths"])
        if incident["escalation_level"] >= max_level:
            return {"success": False, "error": "Already at maximum escalation level"}

        incident["escalation_level"] += 1
        path = incident["escalation_paths"][incident["escalation_level"] - 1]
        incident["log"].append({
            "timestamp": time.time(),
            "event": "escalated",
            "level": incident["escalation_level"],
            "contacts": path["contacts"]
        })
        incident["updated_at"] = time.time()
        logger.warning("incident_escalated", incident_id=incident_id, level=incident["escalation_level"])
        return {"success": True, "incident": incident}

    def get_runbook_list(self) -> list:
        return [{"id": k, "name": v["name"], "severity": v["severity"], "description": v["description"]} for k, v in RUNBOOKS.items()]

runbook_engine = RunbookEngine()
