"""Unit tests for api.error_handlers."""

from api.error_handlers import create_api_error


def test_create_api_error_without_details():
    result = create_api_error("NOT_FOUND", "Resource missing")
    assert result == {
        "error": {"code": "NOT_FOUND", "message": "Resource missing", "details": None}
    }


def test_create_api_error_with_details():
    result = create_api_error("VALIDATION", "Bad input", "field 'x' is required")
    assert result["error"]["code"] == "VALIDATION"
    assert result["error"]["message"] == "Bad input"
    assert result["error"]["details"] == "field 'x' is required"


def test_create_api_error_returns_dict_never_none():
    result = create_api_error("", "")
    assert isinstance(result, dict)
    assert result["error"]["details"] is None
