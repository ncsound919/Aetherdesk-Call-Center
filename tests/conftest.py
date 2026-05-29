import pytest


@pytest.fixture(scope="session", autouse=True)
def reset_rate_limiter():
    from apps.api.services.rate_limit import reset_rate_limiter
    reset_rate_limiter()
    yield
    reset_rate_limiter()
