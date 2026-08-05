import os
import pytest
import sys
from pathlib import Path

# Ensure src/ is on sys.path for test imports
_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Set test env defaults BEFORE any api.* import. api.main's module-level env
# check sys.exit()s when required vars are missing, which caches a partial
# `api.main` in sys.modules and breaks later `from api.main import app`
# (e2e conftests) depending on test-directory ordering.
#
# INTERNAL_API_KEY is set to "dev-api-key" — the same value auth.py falls back
# to in APP_ENV=dev — so unit tests like test_dev_bypass are unaffected while
# top-level tests that import api.main don't hit the FATAL env guard.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("USE_POSTGRES", "false")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("INTERNAL_API_KEY", "dev-api-key")
os.environ.setdefault("ENCRYPTION_KEY", "0KbqB9reCq9pLKXpQcAY_GLYSf5m5aLKIwgymbAg6Fg=")


def ensure_real_api_main() -> None:
    """Drop a mock `api.main` from sys.modules so the real app module loads.

    Several unit tests pre-register `types.ModuleType("api.main")` in
    sys.modules to avoid importing the heavy FastAPI module. When unit tests
    run before e2e in the same pytest invocation, `from api.main import app`
    in the e2e conftests then hits the mock (which has no `app`), raising
    `ImportError: cannot import name 'app' from 'api.main' (unknown location)`.
    This helper evicts any mock that lacks an `app` attribute.
    """
    import sys

    existing = sys.modules.get("api.main")
    if existing is not None and not hasattr(existing, "app"):
        del sys.modules["api.main"]


@pytest.fixture(scope="session", autouse=True)
def reset_rate_limiter():
    from api.services.rate_limit import reset_rate_limiter
    reset_rate_limiter()
    yield
    reset_rate_limiter()
