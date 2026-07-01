"""
Core E2E conftest — sets env vars early and provides TestClient.
No ML-heavy imports should happen here.
"""
import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("USE_POSTGRES", "false")
os.environ.setdefault("ENCRYPTION_KEY", "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE=")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-api-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.services.rate_limit import reset_rate_limiter

# Strip env vars that the .env file may have injected and that would
# interfere with unit-test isolation (e.g. Twilio validation in dev mode).
for _key in ("TWILIO_AUTH_TOKEN", "TWILIO_ACCOUNT_SID", "TWILIO_FROM_NUMBER"):
    os.environ.pop(_key, None)

reset_rate_limiter()

_client = TestClient(app)


@pytest.fixture
def client():
    return _client
