"""Unit tests for usage router endpoints.

Tests GET /api/v1/usage using TestClient with a minimal FastAPI app
that includes only the usage router. Dependencies (verify_tenant_access,
get_usage_stats, get_pg_pool) are mocked to isolate the router logic.
"""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.services.auth import verify_tenant_access


@pytest.fixture
def app():
    """Create a minimal FastAPI app with just the usage router."""
    from api.routers.usage import router

    application = FastAPI()
    application.include_router(router, prefix="/api/v1")

    # Override the auth dependency to skip real verification
    application.dependency_overrides[verify_tenant_access] = lambda: "TENANT-001"

    return application


@pytest.fixture
def client(app):
    """TestClient bound to the minimal usage app."""
    with TestClient(app) as c:
        yield c


class TestGetUsage:
    """Tests for GET /api/v1/usage."""

    def test_get_usage_returns_200(self, client):
        """Returns 200 with full usage data when all dependencies succeed."""
        mock_stats = {
            "total_agents": 10,
            "active_agents": 5,
            "total_calls": 100,
            "active_calls": 3,
            "total_minutes": 450.0,
        }

        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=2)

        with patch("api.routers.usage.get_usage_stats", new_callable=AsyncMock) as mock_get_stats, \
             patch("api.routers.usage.get_pg_pool", new_callable=AsyncMock) as mock_get_pool:

            mock_get_stats.return_value = mock_stats
            mock_get_pool.return_value = mock_pool

            resp = client.get("/api/v1/usage")

            assert resp.status_code == 200
            body = resp.json()
            assert body["total_agents"] == 10
            assert body["active_agents"] == 5
            assert body["total_calls"] == 100
            assert body["active_calls"] == 3
            assert body["total_minutes"] == 450.0
            assert body["avg_call_duration"] == 90.0  # 450 / 5
            assert body["queue_depth"] == 2
            assert body["total_cost"] == 6.75  # 450 * 0.015
            assert body["by_agent"] == []
            assert body["by_day"] == []

    def test_get_usage_with_default_tenant(self, client):
        """Uses default TENANT-001 when no tenant_id is provided."""
        mock_stats = {
            "total_agents": 1,
            "active_agents": 0,
            "total_calls": 5,
            "active_calls": 0,
            "total_minutes": 0.0,
        }

        with patch("api.routers.usage.get_usage_stats", new_callable=AsyncMock) as mock_get_stats, \
             patch("api.routers.usage.get_pg_pool", new_callable=AsyncMock) as mock_get_pool:

            mock_get_stats.return_value = mock_stats
            mock_get_pool.return_value = None  # no pool

            resp = client.get("/api/v1/usage")
            assert resp.status_code == 200

    def test_get_usage_avg_duration_zero_when_no_active_agents(self, client):
        """avg_call_duration is 0.0 when active_agents is 0 (avoids div by zero)."""
        mock_stats = {
            "total_agents": 0,
            "active_agents": 0,
            "total_calls": 0,
            "active_calls": 0,
            "total_minutes": 0.0,
        }

        with patch("api.routers.usage.get_usage_stats", new_callable=AsyncMock) as mock_get_stats, \
             patch("api.routers.usage.get_pg_pool", new_callable=AsyncMock) as mock_get_pool:

            mock_get_stats.return_value = mock_stats
            mock_get_pool.return_value = None

            resp = client.get("/api/v1/usage")
            assert resp.status_code == 200
            body = resp.json()
            assert body["avg_call_duration"] == 0.0
            assert body["total_cost"] == 0.0

    def test_get_usage_queue_depth_zero_when_no_pool(self, client):
        """queue_depth defaults to 0 when get_pg_pool returns None."""
        mock_stats = {
            "total_agents": 5,
            "active_agents": 2,
            "total_calls": 20,
            "active_calls": 1,
            "total_minutes": 120.0,
        }

        with patch("api.routers.usage.get_usage_stats", new_callable=AsyncMock) as mock_get_stats, \
             patch("api.routers.usage.get_pg_pool", new_callable=AsyncMock) as mock_get_pool:

            mock_get_stats.return_value = mock_stats
            mock_get_pool.return_value = None

            resp = client.get("/api/v1/usage")
            assert resp.status_code == 200
            body = resp.json()
            assert body["queue_depth"] == 0
            assert body["avg_call_duration"] == 60.0  # 120 / 2

    def test_get_usage_returns_json_content_type(self, client):
        """Usage endpoint returns JSON."""
        with patch("api.routers.usage.get_usage_stats", new_callable=AsyncMock) as mock_get_stats, \
             patch("api.routers.usage.get_pg_pool", new_callable=AsyncMock) as mock_get_pool:

            mock_get_stats.return_value = {
                "total_agents": 1, "active_agents": 1,
                "total_calls": 1, "active_calls": 1,
                "total_minutes": 10.0,
            }
            mock_get_pool.return_value = None

            resp = client.get("/api/v1/usage")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/json"
