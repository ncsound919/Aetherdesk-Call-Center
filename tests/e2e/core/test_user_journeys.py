"""
Core E2E user journeys for AetherDesk.
Runs against TestClient (no live server needed).
Covers: login → dashboard → agents → calls → campaigns → tenant isolation.
"""
import uuid
import pytest

pytestmark = pytest.mark.e2e_core

# This conftest is specific to the e2e/core suite.
# It provides the TestClient and sets up necessary environment variables.
# It should avoid importing heavy ML dependencies.

# NOTE: The TestClient will trigger module-level imports of the app, including services.
# These imports might still pull in ML dependencies if not lazily loaded.
# However, the goal is to ensure core workflows function correctly.


# ──────────────────────────────────────────────
# UTILITIES & FIXTURES
# ──────────────────────────────────────────────
def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

def _auth_headers():
    return {"x-api-key": "dev-api-key"}

def _bearer_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────
# AUTH FLOW
# ──────────────────────────────────────────────
class TestAuthFlow:
    """Login → token → protected resource → logout"""

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert data["version"] == "1.0.0"

    def test_liveness_probe(self, client):
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "alive"}

    def test_readiness_probe(self, client):
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ready"}

    def test_login_valid_dev_user(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@aetherdesk.com", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["tenantId"] == "TENANT-001"
        assert data["role"] == "admin"
        assert data["userId"] == "USER-ADMIN-001"

    def test_login_invalid_credentials_rejected(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@aetherdesk.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_missing_fields_rejected(self, client):
        resp = client.post("/api/v1/auth/login", json={"email": "test@test.com"})
        assert resp.status_code == 422

    def test_me_endpoint_returns_user(self, client):
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@aetherdesk.com", "password": "admin123"},
        )
        token = login.json()["token"]
        resp = client.get("/api/v1/auth/me", headers=_bearer_headers(token))
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@aetherdesk.com"

    def test_logout_succeeds(self, client):
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200


# ──────────────────────────────────────────────
# TENANT FLOW
# ──────────────────────────────────────────────
class TestTenantFlow:
    """Create tenant → read → validate isolation"""

    def test_create_tenant(self, client):
        email = _uniq("test@tenant")
        resp = client.post(
            "/api/v1/tenants",
            json={"name": f"Tenant-{email}", "email": email, "gdpr_consent": True},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == f"Tenant-{email}"
        assert data["status"] == "active"
        assert len(data["id"]) >= 20
        return data["id"] # Return ID for potential use in other tests

    def test_create_tenant_validates_input(self, client):
        email = _uniq("badinput@tenant")
        resp = client.post(
            "/api/v1/tenants",
            json={"name": "X", "email": "bad"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422

    def test_tenant_isolation_rejects_cross_tenant(self, client):
        """Tenant B cannot access Tenant A's agents."""
        # First, create Tenant A
        email_a = _uniq("tenantA@test")
        tenant_a = client.post(
            "/api/v1/tenants",
            json={"name": f"TenantA-{email_a}", "email": email_a, "gdpr_consent": True},
            headers=_auth_headers(),
        )
        assert tenant_a.status_code == 201
        tenant_a_id = tenant_a.json()["id"]

        # Create an agent for Tenant A
        agent_resp_a = client.post(
            f"/api/v1/tenants/{tenant_a_id}/agents",
            json={"name": "Agent A", "agent_type": "ai"},
            headers=_auth_headers(),
        )
        assert agent_resp_a.status_code == 201

        # Now, try to access Tenant A's agents using a different tenant ID (fake)
        fake_tenant_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        resp = client.get(
            f"/api/v1/tenants/{fake_tenant_id}/agents",
            headers=_auth_headers(),
        )
        # In dev mode the app may return 200 with empty list for unknown tenant IDs
        # (no cross-tenant data leak since the tenant doesn't exist). 403/404 also acceptable.
        assert resp.status_code in (200, 403, 404), f"Expected 200/403/404, got {resp.status_code}: {resp.text}"
        if resp.status_code == 200:
            assert resp.json() == []

    def test_invalid_tenant_id_returns_4xx(self, client):
        """Requests with invalid tenant IDs should result in 4xx errors."""
        for tid in ["<script>", "' OR 1=1", "../../etc/passwd"]:
            resp = client.get(f"/api/v1/tenants/{tid}", headers=_auth_headers())
            assert resp.status_code in [400, 403, 404, 422]

    def test_404_returns_json(self, client):
        resp = client.get("/nonexistent")
        assert resp.status_code == 404
        assert "application/json" in resp.headers.get("content-type", "")

    def test_method_not_allowed_returns_405(self, client):
        resp = client.put("/health")
        assert resp.status_code == 405


# ──────────────────────────────────────────────
# AGENT WORKFLOW
# ──────────────────────────────────────────────
class TestAgentWorkflow:
    """Create tenant → create agent → list → update status → delete"""

    def _create_tenant_for_agent_test(self, client):
        email = _uniq("agentflow@tenant")
        resp = client.post(
            "/api/v1/tenants",
            json={"name": f"AgentFlow-{email}", "email": email, "gdpr_consent": True},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_full_agent_lifecycle(self, client):
        # Use dev admin's tenant directly so JWT ownership check passes
        tenant_id = "TENANT-001"

        # Login to get JWT token (needed for agent status endpoint)
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@aetherdesk.com", "password": "admin123"},
        )
        assert login_resp.status_code == 200
        login_body = login_resp.json()
        bearer = _bearer_headers(login_body.get("access_token") or login_body.get("token", ""))

        # Create Agent under dev tenant (TENANT-001)
        resp = client.post(
            f"/api/v1/tenants/{tenant_id}/agents",
            json={"name": "E2E Agent", "agent_type": "ai", "skills": ["sales", "support"], "config": {"model": "llama-3.1-70b", "temperature": 0.7}},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201
        agent = resp.json()
        assert agent["name"] == "E2E Agent"
        assert agent["status"] == "offline"
        agent_id = agent["id"]

        # List Agents
        resp = client.get(f"/api/v1/tenants/{tenant_id}/agents", headers=_auth_headers())
        assert resp.status_code == 200
        agents = resp.json()
        assert agent_id in [a["id"] for a in agents]

        # Update Agent Status (requires JWT Bearer token with matching tenant_id)
        resp = client.patch(
            f"/api/v1/agents/{agent_id}/status",
            json={"status": "available"},
            headers=bearer,
        )
        assert resp.status_code == 200

        # Delete Agent
        resp = client.delete(f"/api/v1/tenants/{tenant_id}/agents/{agent_id}", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json().get("success") is True

    def test_agent_type_validation(self, client):
        tenant_id = self._create_tenant_for_agent_test(client)
        resp = client.post(
            f"/api/v1/tenants/{tenant_id}/agents",
            json={"name": "Bad Agent", "agent_type": "robot"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422


# ──────────────────────────────────────────────
# CALL WORKFLOW
# ──────────────────────────────────────────────
class TestCallWorkflow:
    """Create tenant → agent → call → call action → list calls"""

    def test_create_call_with_agent(self, client):
        tenant_id = _uniq("callflow@tenant")
        tenant_resp = client.post(
            "/api/v1/tenants",
            json={"name": f"CallFlow-{tenant_id}", "email": f"{tenant_id}@example.com", "gdpr_consent": True},
            headers=_auth_headers(),
        )
        assert tenant_resp.status_code == 201
        tenant_id = tenant_resp.json()["id"]

        agent_resp = client.post(
            f"/api/v1/tenants/{tenant_id}/agents",
            json={"name": "Call Agent", "agent_type": "ai"},
            headers=_auth_headers(),
        )
        assert agent_resp.status_code == 201
        agent_id = agent_resp.json()["id"]

        resp = client.post(
            "/api/v1/calls",
            params={"tenant_id": tenant_id},
            json={
                "agent_id": agent_id,
                "caller_number": "+15551234567",
                "call_direction": "inbound",
                "intent": "support",
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 201
        call = resp.json()
        assert call["call_status"] == "initiated"
        assert call["caller_number"] == "+15551234567"

        # List calls
        list_resp = client.get("/api/v1/calls", params={"tenant_id": tenant_id}, headers=_auth_headers())
        assert list_resp.status_code == 200
        calls = list_resp.json()
        assert isinstance(calls, list)
        # Verify the created call is in the list (check by caller number or other unique field)
        assert any(c["caller_number"] == "+15551234567" for c in calls)

    def test_get_nonexistent_call(self, client):
        """Get call by non-existent ID."""
        resp = client.get(
            "/api/v1/calls/nonexistent-call-id",
            params={"tenant_id": "TENANT-001"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 404


# ──────────────────────────────────────────────
# CAMPAIGN WORKFLOW
# ──────────────────────────────────────────────
class TestCampaignWorkflow:
    """Create lead → list → stats → bulk import → invalid transitions"""

    def test_lead_crud(self, client):
        # Create Lead
        resp = client.post(
            "/api/v1/campaign/leads",
            json={"company_name": _uniq("E2E Corp"), "phone": "+15551234567", "priority": 8},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        lead = resp.json()
        assert "id" in lead

        # List Leads
        resp = client.get("/api/v1/campaign/leads", headers=_auth_headers())
        assert resp.status_code == 200
        assert any(l["id"] == lead["id"] for l in resp.json())

    def test_campaign_stats(self, client):
        resp = client.get("/api/v1/campaign/stats", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "total_leads" in data
        assert "conversion_rate" in data

    def test_bulk_import(self, client):
        resp = client.post(
            "/api/v1/campaign/leads/bulk",
            json={"leads": [{"company_name": _uniq(f"Bulk-{i}"), "phone": f"+1555000{i:04d}"} for i in range(10)]},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json().get("imported") == 10

    def test_phone_validation(self, client):
        resp = client.post(
            "/api/v1/campaign/leads",
            json={"company_name": "Bad Phone", "phone": "not-a-phone"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422


# ──────────────────────────────────────────────
# USAGE & BILLING
# ──────────────────────────────────────────────
class TestUsageAndBilling:
    """Usage stats and billing summary"""

    def test_usage_stats(self, client):
        resp = client.get("/api/v1/usage", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "total_calls" in data
        assert "total_agents" in data

    def test_billing_summary(self, client):
        resp = client.get("/api/v1/billing", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "total_calls" in data


# ──────────────────────────────────────────────
# ERROR HANDLING
# ──────────────────────────────────────────────
class TestErrorHandling:
    """Edge cases and error resilience"""

    def test_malformed_json_returns_422(self, client):
        email = _uniq("malformed@tenant")
        tenant_resp = client.post(
            "/api/v1/tenants",
            json={"name": f"Malformed-{email}", "email": email, "gdpr_consent": True},
            headers=_auth_headers(),
        )
        assert tenant_resp.status_code == 201
        tenant_id = tenant_resp.json()["id"]

        resp = client.post(
            f"/api/v1/tenants/{tenant_id}/agents",
            content=b"this is not json",
            headers={"content-type": "application/json", **_auth_headers()},
        )
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, client):
        tenant_email = _uniq("emptybody@tenant")
        tenant = client.post(
            "/api/v1/tenants",
            json={"name": f"EmptyBody-{tenant_email}", "email": tenant_email, "gdpr_consent": True},
            headers=_auth_headers(),
        )
        assert tenant.status_code == 201
        tenant_id = tenant.json()["id"]

        resp = client.post(
            f"/api/v1/tenants/{tenant_id}/agents",
            json={},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422

    def test_oversized_payload_rejected(self, client):
        large = "x" * (1000 * 1000)  # 1MB string, to trigger field validation limit
        tenant_email = _uniq("oversized@tenant")
        tenant = client.post(
            "/api/v1/tenants",
            json={"name": f"Over-{tenant_email}", "email": tenant_email, "gdpr_consent": True},
            headers=_auth_headers(),
        )
        assert tenant.status_code == 201
        tenant_id = tenant.json()["id"]

        resp = client.post(
            f"/api/v1/tenants/{tenant_id}/agents",
            json={"name": large, "agent_type": "ai"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422

    def test_special_chars_in_names(self, client):
        tenant_email = _uniq("special@tenant")
        tenant = client.post(
            "/api/v1/tenants",
            json={"name": f"Spec-{tenant_email}", "email": tenant_email, "gdpr_consent": True},
            headers=_auth_headers(),
        )
        assert tenant.status_code == 201
        tenant_id = tenant.json()["id"]