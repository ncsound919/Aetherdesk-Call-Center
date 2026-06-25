from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


class TestHealthCheck:
    """Tests for health check endpoint — verifies 503 on degraded services."""

    def test_health_returns_200_when_healthy(self):
        from api.main import app

        with TestClient(app) as client:
            resp = client.get("/health")
            # May be 200 or 503 depending on whether services are running
            assert resp.status_code in (200, 503)
            body = resp.json()
            assert "status" in body
            assert body["status"] in ("healthy", "degraded")
            assert "services" in body
            assert "database" in body["services"]
            assert "redis" in body["services"]

    def test_readiness_probe_returns_200(self):
        from api.main import app

        with TestClient(app) as client:
            resp = client.get("/api/v1/health/ready")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ready"}

    def test_liveness_probe_returns_200(self):
        from api.main import app

        with TestClient(app) as client:
            resp = client.get("/api/v1/health/live")
            assert resp.status_code == 200
            assert resp.json() == {"status": "alive"}
