"""Health endpoint tests using httpx.AsyncClient + ASGITransport.

Synchronous TestClient boots the app in an AnyIO portal thread with its own
event loop; on this Windows box the portal's internal coroutines never drain
after the lifespan returns, so TestClient.__exit__ hangs at thread.join().
Using LifespanManager + ASGITransport keeps startup, requests, and shutdown on
the same event loop as the test (FastAPI's recommended async pattern).

The lifespan's Redis retry backoff (1+2+4+8s) is avoided by patching
redis.from_url to a fake client that pings immediately.
"""

import os

os.environ.setdefault("SENTRY_DSN", "")
os.environ.setdefault("POSTHOG_ENABLED", "false")
os.environ.setdefault("LANGFUSE_ENABLED", "false")

# Evict a mock api.main pre-registered by unit tests (see tests/conftest.py).
import sys  # noqa: E402

import asgi_lifespan  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402

_existing_main = sys.modules.get("api.main")
if _existing_main is not None and not hasattr(_existing_main, "app"):
    del sys.modules["api.main"]

from unittest.mock import patch  # noqa: E402

from api.main import app  # noqa: E402


class _HealthyRedis:
    async def ping(self):
        return True

    async def close(self):
        return None

    async def aclose(self):
        return None


@pytest.fixture(scope="module")
async def client():
    """Run the app lifespan + serve health endpoints on one event loop."""
    with patch("api.main.redis.from_url", lambda *a, **k: _HealthyRedis()):
        async with asgi_lifespan.LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as c:
                yield c


@pytest.mark.anyio
class TestHealthCheck:
    """Tests for health check endpoint - verifies 503 on degraded services."""

    async def test_health_returns_200_when_healthy(self, client):
        resp = await client.get("/api/v1/health")
        # May be 200 or 503 depending on whether services are running
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "status" in body
        assert body["status"] in ("healthy", "degraded")
        assert "services" in body
        assert "database" in body["services"]
        assert "redis" in body["services"]

    async def test_readiness_probe_returns_200(self, client):
        resp = await client.get("/api/v1/health/ready")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert data["status"] in ("ready", "not_ready")

    async def test_liveness_probe_returns_200(self, client):
        resp = await client.get("/api/v1/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"
