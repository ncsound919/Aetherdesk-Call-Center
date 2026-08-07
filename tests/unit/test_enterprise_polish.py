"""Unit tests for api.routers.enterprise_polish."""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The api.routers package __init__ pulls in api.services.asr, which imports
# faster_whisper -> ctranslate2 -> torch at module level. Stub it out so the
# router imports stay fast and hermetic (no real model/torch loading).
_faster_whisper = types.ModuleType("faster_whisper")
_faster_whisper.WhisperModel = MagicMock
sys.modules.setdefault("faster_whisper", _faster_whisper)

from api.routers.enterprise_polish import router
from api.services.auth import verify_tenant_access


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)

    async def _override_tenant():
        return "TENANT-001"

    application.dependency_overrides[verify_tenant_access] = _override_tenant
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestFailover:
    def test_run_failover_test(self, client):
        with patch(
            "api.routers.enterprise_polish.failover_service.test_telephony_failover",
            new_callable=AsyncMock,
            return_value={"id": "fo-1", "failover_success": True},
        ) as mock_fo:
            resp = client.post("/enterprise/failover/test")
        assert resp.status_code == 200
        assert resp.json()["failover_success"] is True
        mock_fo.assert_awaited_once()

    def test_get_failover_status(self, client):
        with patch(
            "api.routers.enterprise_polish.failover_service.get_failover_status",
            new_callable=AsyncMock,
            return_value={"primary_provider": "twilio"},
        ):
            resp = client.get("/enterprise/failover/status")
        assert resp.status_code == 200
        assert resp.json()["primary_provider"] == "twilio"

    def test_get_failover_history(self, client):
        with patch(
            "api.routers.enterprise_polish.failover_service.get_failover_history",
            new_callable=AsyncMock,
            return_value=[{"id": "fo-1"}],
        ) as mock_history:
            resp = client.get("/enterprise/failover/history", params={"limit": 5})
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        mock_history.assert_awaited_once_with(limit=5)

    def test_get_failover_history_validation(self, client):
        resp = client.get("/enterprise/failover/history", params={"limit": 0})
        assert resp.status_code == 422
        resp = client.get("/enterprise/failover/history", params={"limit": 101})
        assert resp.status_code == 422

    def test_get_failover_config(self, client):
        with patch(
            "api.routers.enterprise_polish.failover_service.get_failover_config",
            new_callable=AsyncMock,
            return_value={"auto_test_interval_hours": 24},
        ):
            resp = client.get("/enterprise/failover/config")
        assert resp.status_code == 200
        assert resp.json()["auto_test_interval_hours"] == 24


class TestConversationQuality:
    def test_score_conversation(self, client):
        with patch(
            "api.routers.enterprise_polish.conversation_quality_service.score_conversation",
            return_value={"percentage": 95.0, "rating": "excellent"},
        ) as mock_score:
            resp = client.post(
                "/enterprise/conversation-quality/score",
                params={"transcript": "hello", "rubric_name": "standard"},
            )
        assert resp.status_code == 200
        assert resp.json()["rating"] == "excellent"
        mock_score.assert_called_once_with("hello", "standard")

    def test_score_conversation_default_rubric(self, client):
        with patch(
            "api.routers.enterprise_polish.conversation_quality_service.score_conversation",
            return_value={},
        ) as mock_score:
            resp = client.post(
                "/enterprise/conversation-quality/score", params={"transcript": "hi"}
            )
        assert resp.status_code == 200
        mock_score.assert_called_once_with("hi", "standard")

    def test_get_quality_scores(self, client):
        with patch(
            "api.routers.enterprise_polish.conversation_quality_service.get_quality_scores",
            new_callable=AsyncMock,
            return_value=[{"percentage": 80.0}],
        ) as mock_scores:
            resp = client.get(
                "/enterprise/conversation-quality/scores",
                params={"agent_id": "a1", "period": "7d"},
            )
        assert resp.status_code == 200
        mock_scores.assert_awaited_once_with("TENANT-001", "a1", "7d")

    def test_get_quality_trends(self, client):
        with patch(
            "api.routers.enterprise_polish.conversation_quality_service.get_quality_trends",
            new_callable=AsyncMock,
            return_value={"avg_percentage": 80.0},
        ) as mock_trends:
            resp = client.get("/enterprise/conversation-quality/trends")
        assert resp.status_code == 200
        mock_trends.assert_awaited_once_with("TENANT-001", "30d")

    def test_get_coaching_opportunities(self, client):
        with patch(
            "api.routers.enterprise_polish.conversation_quality_service.identify_coaching_opportunities",
            new_callable=AsyncMock,
            return_value=[{"criterion": "empathy", "gap": 4.0}],
        ) as mock_coaching:
            resp = client.get(
                "/enterprise/conversation-quality/coaching",
                params={"agent_id": "a1"},
            )
        assert resp.status_code == 200
        mock_coaching.assert_awaited_once_with("a1", "30d")


class TestAPIVersioning:
    def test_list_api_versions(self, client):
        with patch(
            "api.routers.enterprise_polish.api_versioning_service.get_api_versions",
            new_callable=AsyncMock,
            return_value=[{"version": "v1"}],
        ):
            resp = client.get("/enterprise/api-versions")
        assert resp.status_code == 200
        assert resp.json()[0]["version"] == "v1"

    def test_deprecate_version_success(self, client):
        with patch(
            "api.routers.enterprise_polish.api_versioning_service.deprecate_version",
            new_callable=AsyncMock,
            return_value={"success": True, "version": "v3", "status": "deprecated"},
        ) as mock_dep:
            resp = client.post(
                "/enterprise/api-versions/v3/deprecate",
                params={"sunset_date": "2026-01-01"},
            )
        assert resp.status_code == 200
        mock_dep.assert_awaited_once_with("v3", "2026-01-01")

    def test_deprecate_version_not_found(self, client):
        with patch(
            "api.routers.enterprise_polish.api_versioning_service.deprecate_version",
            new_callable=AsyncMock,
            return_value={"success": False, "error": "Version v9 not found"},
        ):
            resp = client.post(
                "/enterprise/api-versions/v9/deprecate",
                params={"sunset_date": "2026-01-01"},
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Version v9 not found"

    def test_deprecate_version_missing_sunset_date(self, client):
        resp = client.post("/enterprise/api-versions/v3/deprecate")
        assert resp.status_code == 422

    def test_get_migration_guide(self, client):
        with patch(
            "api.routers.enterprise_polish.api_versioning_service.get_migration_guide",
            new_callable=AsyncMock,
            return_value={"from_version": "v2", "to_version": "v3"},
        ) as mock_guide:
            resp = client.get(
                "/enterprise/api-versions/migration-guide",
                params={"from_version": "v2", "to_version": "v3"},
            )
        assert resp.status_code == 200
        mock_guide.assert_awaited_once_with("v2", "v3")

    def test_get_changelog_with_version(self, client):
        with patch(
            "api.routers.enterprise_polish.api_versioning_service.get_changelog",
            new_callable=AsyncMock,
            return_value=[{"version": "v1"}],
        ) as mock_log:
            resp = client.get("/enterprise/api-versions/changelog", params={"version": "v1"})
        assert resp.status_code == 200
        mock_log.assert_awaited_once_with("v1")

    def test_get_changelog_all(self, client):
        with patch(
            "api.routers.enterprise_polish.api_versioning_service.get_changelog",
            new_callable=AsyncMock,
            return_value=[{"version": "v1"}, {"version": "v2"}],
        ) as mock_log:
            resp = client.get("/enterprise/api-versions/changelog")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
        mock_log.assert_awaited_once_with(None)

    def test_get_api_usage_stats_with_version(self, client):
        with patch(
            "api.routers.enterprise_polish.api_versioning_service.get_usage_stats",
            new_callable=AsyncMock,
            return_value={"v1": {"total_requests": 1}},
        ) as mock_stats:
            resp = client.get("/enterprise/api-versions/usage-stats", params={"version": "v1"})
        assert resp.status_code == 200
        mock_stats.assert_awaited_once_with("v1")

    def test_get_api_usage_stats_all(self, client):
        with patch(
            "api.routers.enterprise_polish.api_versioning_service.get_usage_stats",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_stats:
            resp = client.get("/enterprise/api-versions/usage-stats")
        assert resp.status_code == 200
        mock_stats.assert_awaited_once_with(None)


class TestSelfServicePortal:
    def test_get_customer_portal(self, client):
        with patch(
            "api.routers.enterprise_polish.self_service_portal_service.get_customer_portal_data",
            new_callable=AsyncMock,
            return_value={"customer_id": "c1", "average_csat": 4.5},
        ) as mock_portal:
            resp = client.get("/enterprise/customer-portal/c1")
        assert resp.status_code == 200
        mock_portal.assert_awaited_once_with("c1")
        assert resp.json()["average_csat"] == 4.5

    def test_submit_complaint(self, client):
        with patch(
            "api.routers.enterprise_polish.self_service_portal_service.submit_complaint",
            new_callable=AsyncMock,
            return_value={"id": "cmp-1", "status": "open"},
        ) as mock_complaint:
            resp = client.post(
                "/enterprise/customer-portal/complaint",
                params={
                    "customer_id": "c1",
                    "subject": "Late delivery",
                    "description": "My order arrived late",
                },
            )
        assert resp.status_code == 200
        mock_complaint.assert_awaited_once_with(
            "c1", "Late delivery", "My order arrived late"
        )

    def test_schedule_callback(self, client):
        with patch(
            "api.routers.enterprise_polish.self_service_portal_service.schedule_call_back",
            new_callable=AsyncMock,
            return_value={"id": "cb-1", "status": "scheduled"},
        ) as mock_cb:
            resp = client.post(
                "/enterprise/customer-portal/callback",
                params={
                    "customer_id": "c1",
                    "preferred_time": "2025-07-01T10:00:00Z",
                    "reason": "billing",
                },
            )
        assert resp.status_code == 200
        mock_cb.assert_awaited_once_with(
            "c1", "2025-07-01T10:00:00Z", "billing"
        )

    def test_update_customer_preferences(self, client):
        with patch(
            "api.routers.enterprise_polish.self_service_portal_service.update_preferences",
            new_callable=AsyncMock,
            return_value={"customer_id": "c1", "preferences": {"timezone": "UTC"}},
        ) as mock_prefs:
            resp = client.put(
                "/enterprise/customer-portal/c1/preferences",
                json={"timezone": "UTC", "marketing_emails": False},
            )
        assert resp.status_code == 200
        mock_prefs.assert_awaited_once_with(
            "c1", {"timezone": "UTC", "marketing_emails": False}
        )
