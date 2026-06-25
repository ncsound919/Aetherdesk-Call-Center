"""Unit tests for health router endpoints.

Tests the 3 health endpoints using TestClient with a minimal FastAPI app
that includes only the health router. Dependencies (fonster_client, redis,
USE_POSTGRES, get_pg_pool) are mocked to isolate the router logic.
"""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def app():
    """Create a minimal FastAPI app with just the health router."""
    from api.routers.health import router

    application = FastAPI()
    application.include_router(router)

    # Mock app.state dependencies
    fonster_mock = AsyncMock()
    fonster_mock.health_check = AsyncMock(return_value={"healthy": True})
    application.state.fonster_client = fonster_mock
    application.state.redis = AsyncMock()

    return application


@pytest.fixture
def client(app):
    """TestClient bound to the minimal health app."""
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    """Tests for GET /health and GET /api/v1/health."""

    def test_health_returns_200_when_healthy(self, client):
        """Both /health and /api/v1/health return 200 when all services are healthy.

        Patching USE_POSTGRES to True so the DB check runs and succeeds.
        """
        with patch("api.routers.health.USE_POSTGRES", True), \
             patch("api.routers.health.get_pg_pool", new_callable=AsyncMock) as mock_get_pool:

            mock_pool = AsyncMock()
            mock_pool.fetchval = AsyncMock(return_value=1)
            mock_get_pool.return_value = mock_pool

            for path in ("/health", "/api/v1/health"):
                resp = client.get(path)
                assert resp.status_code == 200, f"{path} should return 200"
                body = resp.json()
                assert body["status"] == "healthy"
                assert body["services"]["fonster"] == "healthy"
                assert body["services"]["database"] == "connected"
                assert body["fonster_connected"] is True
                assert body["database_connected"] is True
                assert "timestamp" in body
                assert body["version"] == "1.0.0"

    def test_health_fonster_unhealthy(self, app, client):
        """Health returns degraded when fonster reports unhealthy."""
        app.state.fonster_client.health_check = AsyncMock(return_value={"healthy": False})
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["services"]["fonster"] == "unhealthy"

    def test_health_fonster_disconnected(self, app, client):
        """Health returns degraded when fonster health_check raises."""
        app.state.fonster_client.health_check = AsyncMock(side_effect=Exception("Connection refused"))
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["services"]["fonster"] == "disconnected"

    def test_health_no_fonster_client(self, client):
        """Health handles missing fonster_client gracefully."""
        # Create a fresh app without fonster_client
        from api.routers.health import router

        app_no_fonster = FastAPI()
        app_no_fonster.include_router(router)
        app_no_fonster.state.redis = AsyncMock()
        # Deliberately NOT setting fonster_client

        with TestClient(app_no_fonster) as test_client:
            resp = test_client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["services"]["fonster"] == "unknown"
            assert body["status"] == "degraded"

    def test_health_db_disconnected_when_use_postgres(self, client):
        """Health returns degraded when PostgreSQL SELECT 1 fails."""
        with patch("api.routers.health.USE_POSTGRES", True), \
             patch("api.routers.health.get_pg_pool", new_callable=AsyncMock) as mock_get_pool:

            mock_pool = AsyncMock()
            mock_pool.fetchval = AsyncMock(side_effect=Exception("Connection refused"))
            mock_get_pool.return_value = mock_pool

            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["services"]["database"] == "disconnected"
            assert body["status"] == "degraded"
            assert body["database_connected"] is False

    def test_health_db_connected_when_use_postgres(self, client):
        """Health returns healthy when PostgreSQL pool is available."""
        with patch("api.routers.health.USE_POSTGRES", True), \
             patch("api.routers.health.get_pg_pool", new_callable=AsyncMock) as mock_get_pool:

            mock_pool = AsyncMock()
            mock_pool.fetchval = AsyncMock(return_value=1)
            mock_get_pool.return_value = mock_pool

            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["services"]["database"] == "connected"
            assert body["database_connected"] is True
            assert body["fonster_connected"] is True
            assert body["status"] == "healthy"

    def test_health_db_disconnected_no_pool(self, client):
        """Health returns disconnected when get_pg_pool returns None."""
        with patch("api.routers.health.USE_POSTGRES", True), \
             patch("api.routers.health.get_pg_pool", new_callable=AsyncMock) as mock_get_pool:

            mock_get_pool.return_value = None

            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["services"]["database"] == "disconnected"

    def test_health_redis_disconnected(self, app, client):
        """Health reports redis as disconnected when no redis client."""
        app.state.redis = None
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["services"]["redis"] == "disconnected"

    def test_health_returns_json_content_type(self, client):
        """Health endpoint returns JSON content type."""
        resp = client.get("/health")
        assert resp.headers["content-type"] == "application/json"


class TestReadinessProbe:
    """Tests for GET /api/v1/health/ready."""

    def test_readiness_returns_200(self, client):
        """Readiness probe returns 200 with ready status."""
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ready"}

    def test_readiness_returns_json(self, client):
        """Readiness probe returns JSON."""
        resp = client.get("/api/v1/health/ready")
        assert resp.headers["content-type"] == "application/json"


class TestLivenessProbe:
    """Tests for GET /api/v1/health/live."""

    def test_liveness_returns_200(self, client):
        """Liveness probe returns 200 with alive status."""
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "alive"}

    def test_liveness_returns_json(self, client):
        """Liveness probe returns JSON."""
        resp = client.get("/api/v1/health/live")
        assert resp.headers["content-type"] == "application/json"
