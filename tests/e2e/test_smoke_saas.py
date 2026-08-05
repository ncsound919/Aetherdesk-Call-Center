import os
import sys

import pytest

os.environ["APP_ENV"] = "development"
os.environ["USE_POSTGRES"] = "false"
os.environ["ENCRYPTION_KEY"] = "0KbqB9reCq9pLKXpQcAY_GLYSf5m5aLKIwgymbAg6Fg="
os.environ["JWT_SECRET"] = "test-jwt-secret"
os.environ["INTERNAL_API_KEY"] = "dev-api-key"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret-for-testing-only"

# Evict a mock api.main pre-registered by unit tests (see tests/conftest.py).
_existing_main = sys.modules.get("api.main")
if _existing_main is not None and not hasattr(_existing_main, "app"):
    del sys.modules["api.main"]

from api.main import app  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health endpoint works."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test root endpoint returns OpenAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "info" in data


@pytest.mark.asyncio
async def test_app_routes_loaded():
    """Test that routes are loaded."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs")
        assert response.status_code == 200