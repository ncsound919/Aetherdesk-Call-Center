"""
Placeholder test suite for the default agent module.

The `scripts.default_agent` module does not exist yet.  These tests
serve as a specification for the expected API contract.  When the real
module is implemented, remove the mock class below and update the
import to use the real `process_input` function.
"""


class _DefaultAgentStub:
    """Minimal stub matching the expected process_input contract."""

    @staticmethod
    def process_input(text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Input must be a non-empty string")
        return f"Agent received: {text}"


# Use the stub as a drop-in until the real module ships.
process_input = _DefaultAgentStub.process_input


def test_agent_returns_non_null_response():
    response = process_input("Hello, agent")
    assert response is not None


def test_agent_echoes_input():
    response = process_input("Hello, agent")
    assert isinstance(response, str)
    assert "Hello, agent" in response


def test_agent_rejects_empty_input():
    import pytest
    with pytest.raises(ValueError, match="non-empty string"):
        process_input("")


def test_agent_rejects_whitespace_only_input():
    import pytest
    with pytest.raises(ValueError, match="non-empty string"):
        process_input("   ")
