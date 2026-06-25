import pytest
import sys
from pathlib import Path

# Ensure src/ is on sys.path for test imports
_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


@pytest.fixture(scope="session", autouse=True)
def reset_rate_limiter():
    from api.services.rate_limit import reset_rate_limiter
    reset_rate_limiter()
    yield
    reset_rate_limiter()
