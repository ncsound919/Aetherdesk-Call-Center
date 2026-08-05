import os
import sys

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("USE_POSTGRES", "false")
os.environ.setdefault("ENCRYPTION_KEY", "0KbqB9reCq9pLKXpQcAY_GLYSf5m5aLKIwgymbAg6Fg=")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("INTERNAL_API_KEY", "dev-api-key")
os.environ.setdefault("ENABLE_DEV_USERS", "true")
os.environ.setdefault("DEV_ADMIN_PASSWORD", "admin123")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")

import pytest
from fastapi.testclient import TestClient

# Evict a mock api.main pre-registered by unit tests (see tests/conftest.py).
_existing_main = sys.modules.get("api.main")
if _existing_main is not None and not hasattr(_existing_main, "app"):
    del sys.modules["api.main"]

from api.main import app  # noqa: E402
from api.services.rate_limit import reset_rate_limiter  # noqa: E402

reset_rate_limiter()

_client = TestClient(app)


@pytest.fixture
def client():
    return _client
