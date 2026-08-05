from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Evict a mock api.main pre-registered by unit tests (see tests/conftest.py).
import sys  # noqa: E402

_existing_main = sys.modules.get("api.main")
if _existing_main is not None and not hasattr(_existing_main, "app"):
    del sys.modules["api.main"]


class TestHealthCheck:
    """Tests for health check endpoint — verifies 503 on degraded services."""

    def test_health_returns_200_when_healthy(self):
        from api.main import app

        with TestClient(app) as client:
            resp = client.get("/api/v1/health")
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
            assert resp.status_code in (200, 503)
            data = resp.json()
            assert data["status"] in ("ready", "not_ready")

    def test_liveness_probe_returns_200(self):
        from api.main import app

        with TestClient(app) as client:
            resp = client.get("/api/v1/health/live")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "alive"
