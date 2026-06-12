skip_reason = "Requires full app import chain"
import pytest


@pytest.mark.skip(reason=skip_reason)
class TestApiHealth:
    pass
