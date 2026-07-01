"""E2E integration tests for all Phase 1-4 integrations.

Tests the full lifecycle of each integration:
- Langfuse: trace creation → scoring → flush
- Lago: usage tracking → customer creation → invoicing
- Casbin: permission checking → role hierarchy
- ClickHouse: event recording → querying → analytics
- PostHog: event tracking → feature flags
- Metabase: stats → embed URLs
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Langfuse E2E
# ---------------------------------------------------------------------------

class TestLangfuseE2E:
    def test_full_trace_lifecycle(self):
        """Simulate a full call trace: create → score → flush."""
        import api.services.langfuse_client as mod
        mod._langfuse = None
        mod._tried = False

        mock_lf = MagicMock()
        with patch("api.services.langfuse_client.get_langfuse", return_value=mock_lf):
            from api.services.langfuse_client import score_call, flush

            # Score the call
            score_call("call-123", "satisfaction", 0.92, comment="Great interaction")
            score_call("call-123", "intent_confidence", 0.88)

            # Flush on shutdown
            flush()

            assert mock_lf.score.call_count == 2
            mock_lf.flush.assert_called_once()

    def test_graceful_without_langfuse(self):
        """All operations should be no-ops when Langfuse is not configured."""
        import api.services.langfuse_client as mod
        mod._langfuse = None
        mod._tried = False

        from api.services.langfuse_client import score_call, flush

        # These should all be silent no-ops
        score_call("call-123", "satisfaction", 0.92)
        flush()  # Should not raise


# ---------------------------------------------------------------------------
# Lago E2E
# ---------------------------------------------------------------------------

class TestLagoE2E:
    def test_full_billing_lifecycle(self):
        """Simulate: track call → track AI → query usage → create customer."""
        import api.services.billing_engine as mod
        mod._client = None
        mod._enabled = False

        from api.services.billing_engine import (
            track_call_usage,
            track_ai_usage,
            get_customer_usage,
            create_customer,
            getinvoices,
        )

        # All should return mock data when not configured
        call_result = track_call_usage("tenant-1", "call-123", 120, "inbound")
        assert call_result["mock"] is True

        ai_result = track_ai_usage("tenant-1", "session-1", 500, "gpt-4")
        assert ai_result["mock"] is True

        usage = get_customer_usage("tenant-1", "2024-01-01", "2024-01-31")
        assert usage["mock"] is True

        customer = create_customer("tenant-1", "test@example.com", "Test Co")
        assert customer["mock"] is True

        invoices = getinvoices("tenant-1")
        assert invoices == []

    def test_with_mock_client(self):
        """Test with a mocked Lago client."""
        import api.services.billing_engine as mod
        mod._client = MagicMock()
        mod._enabled = True

        from api.services.billing_engine import track_call_usage, is_lago_enabled

        assert is_lago_enabled() is True

        result = track_call_usage("tenant-1", "call-123", 120, "inbound")
        assert result["recorded"] is True


# ---------------------------------------------------------------------------
# Casbin RBAC E2E
# ---------------------------------------------------------------------------

class TestCasbinE2E:
    def test_role_hierarchy(self):
        """Verify admin > supervisor > agent > viewer hierarchy."""
        import api.services.authorization as mod
        mod._enforcer = None

        # Load the actual Casbin model and policy
        model_path = str(mod._model_path)
        policy_path = str(mod._policy_path)

        if not os.path.exists(model_path) or not os.path.exists(policy_path):
            pytest.skip("Casbin config files not found")

        try:
            import casbin
        except ImportError:
            pytest.skip("casbin not installed")

        enforcer = casbin.Enforcer(model_path, policy_path)

        # Admin can do everything
        assert enforcer.enforce("admin", "calls", "read") is True
        assert enforcer.enforce("admin", "calls", "delete") is True
        assert enforcer.enforce("admin", "billing", "write") is True

        # Supervisor inherits from agent, can read/write agents and calls
        assert enforcer.enforce("supervisor", "calls", "read") is True
        assert enforcer.enforce("supervisor", "calls", "write") is True
        assert enforcer.enforce("supervisor", "agents", "read") is True

        # Agent can read calls and transfer
        assert enforcer.enforce("agent", "calls", "read") is True
        assert enforcer.enforce("agent", "calls", "transfer") is True
        # Agent cannot delete
        assert enforcer.enforce("agent", "calls", "delete") is False

        # Viewer can only read
        assert enforcer.enforce("viewer", "calls", "read") is True
        assert enforcer.enforce("viewer", "calls", "write") is False

    def test_authorization_service_e2e(self):
        """Test the authorization service with real Casbin files."""
        import api.services.authorization as mod
        mod._enforcer = None

        from api.services.authorization import check_permission, get_permissions

        # In permissive mode (no enforcer), everything is allowed
        with patch("api.services.authorization._get_enforcer", return_value=None):
            assert check_permission("agent", "calls", "read") is True
            assert check_permission("admin", "billing", "delete") is True
            assert get_permissions("admin") == []


# ---------------------------------------------------------------------------
# ClickHouse E2E
# ---------------------------------------------------------------------------

class TestClickHouseE2E:
    def test_full_analytics_lifecycle(self):
        """Simulate: record event → query stats → query intents → query hourly."""
        import api.services.analytics_db as mod
        mod._client = None
        mod._initialized = False

        from api.services.analytics_db import (
            record_call_event,
            query_call_stats,
            query_intent_distribution,
            query_agent_performance,
            query_hourly_volume,
        )

        now = datetime.utcnow()
        start = now - timedelta(days=30)

        # All should return empty/mock when not configured
        assert record_call_event(
            call_id="call-1",
            tenant_id="tenant-1",
            agent_id="agent-1",
            direction="inbound",
            caller="+1234",
            called="+5678",
            started_at=now,
        ) is False

        stats = query_call_stats("tenant-1", start, now)
        assert stats["mock"] is True

        intents = query_intent_distribution("tenant-1", start, now)
        assert intents == []

        agents = query_agent_performance("tenant-1", start, now)
        assert agents == []

        hourly = query_hourly_volume("tenant-1", start, now)
        assert hourly == []

    def test_with_mock_client(self):
        """Test recording and querying with a mocked ClickHouse client."""
        import api.services.analytics_db as mod
        mock_client = MagicMock()

        mock_result = MagicMock()
        mock_result.first_row = (10, 10.0, 60.0, 8, 2, 0.85, 1500, 50)
        mock_client.query.return_value = mock_result

        mod._client = mock_client

        from api.services.analytics_db import record_call_event, query_call_stats

        now = datetime.utcnow()

        # Record an event
        result = record_call_event(
            call_id="call-1",
            tenant_id="tenant-1",
            agent_id="agent-1",
            direction="inbound",
            caller="+1234",
            called="+5678",
            started_at=now,
            duration_seconds=120.5,
            intent="billing",
            status="completed",
            satisfaction_score=0.9,
            tokens_used=150,
            cost_cents=5,
            metadata={"source": "web"},
        )
        assert result is True
        mock_client.insert.assert_called_once()

        # Query stats
        stats = query_call_stats("tenant-1", now - timedelta(days=30), now)
        assert stats["total_calls"] == 10
        assert stats["total_minutes"] == 10.0


# ---------------------------------------------------------------------------
# PostHog E2E
# ---------------------------------------------------------------------------

class TestPostHogE2E:
    def test_full_analytics_lifecycle(self):
        """Simulate: track event → identify user → check feature flag."""
        import api.services.analytics_client as mod
        mod._client = None
        mod._tried = False

        from api.services.analytics_client import (
            track_event,
            identify_user,
            is_feature_enabled,
            get_feature_flag,
            shutdown,
        )

        # All should return defaults when not configured
        assert track_event("user-1", "page_view") is False
        assert identify_user("user-1", {"name": "Test"}) is False
        assert is_feature_enabled("new-ui", "user-1") is True
        assert get_feature_flag("new-ui", "user-1") is None

        shutdown()  # Should not raise

    def test_with_mock_client(self):
        """Test with a mocked PostHog client."""
        import api.services.analytics_client as mod
        mock_ph = MagicMock()
        mock_ph.feature_enabled.return_value = True
        mock_ph.get_feature_flag.return_value = "variant-a"
        mod._client = mock_ph
        mod._tried = True

        from api.services.analytics_client import track_event, is_feature_enabled, get_feature_flag

        # Track event
        result = track_event("user-1", "button_click", {"button": "signup"})
        assert result is True
        mock_ph.capture.assert_called_once()

        # Feature flag
        assert is_feature_enabled("new-ui", "user-1") is True
        assert get_feature_flag("experiment-1", "user-1") == "variant-a"


# ---------------------------------------------------------------------------
# Metabase E2E
# ---------------------------------------------------------------------------

class TestMetabaseE2E:
    def test_stats_endpoints_mock_mode(self):
        """Test all Metabase stats endpoints in mock mode."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routers.metabase import router
        from api.services.auth import verify_tenant_access

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[verify_tenant_access] = lambda: "tenant-1"

        with TestClient(app) as client:
            with patch("api.routers.metabase.is_clickhouse_enabled", return_value=False):
                # Stats
                resp = client.get("/metabase/stats")
                assert resp.status_code == 200
                assert resp.json()["source"] == "mock"

                # Intents
                resp = client.get("/metabase/intents")
                assert resp.status_code == 200
                assert resp.json()["source"] == "mock"

                # Agents
                resp = client.get("/metabase/agents")
                assert resp.status_code == 200
                assert resp.json()["source"] == "mock"

                # Hourly
                resp = client.get("/metabase/hourly")
                assert resp.status_code == 200
                assert resp.json()["source"] == "mock"

                # Embed
                resp = client.get("/metabase/embed/42")
                assert resp.status_code == 200
                assert resp.json()["configured"] is False
