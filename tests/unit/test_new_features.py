import pytest
from pydantic import ValidationError
from unittest.mock import patch
from src.validators import UserCreateSchema
from src.services.logger import log_error, logger

def test_user_create_schema_valid():
    schema = UserCreateSchema(username="john_doe", email="john@example.com", age=30)
    assert schema.username == "john_doe"
    assert schema.email == "john@example.com"
    assert schema.age == 30

def test_user_create_schema_invalid_username():
    with pytest.raises(ValidationError):
        UserCreateSchema(username="jo", email="john@example.com", age=30)

def test_user_create_schema_invalid_email():
    with pytest.raises(ValidationError):
        UserCreateSchema(username="john_doe", email="invalid-email", age=30)

def test_user_create_schema_invalid_age_too_low():
    with pytest.raises(ValidationError):
        UserCreateSchema(username="john_doe", email="john@example.com", age=0)

def test_user_create_schema_invalid_age_too_high():
    with pytest.raises(ValidationError):
        UserCreateSchema(username="john_doe", email="john@example.com", age=121)

def test_log_error_calls_logger_error():
    with patch.object(logger, 'error') as mock_error:
        log_error("Test error message", exc_info=True)
        mock_error.assert_called_once_with("Test error message", exc_info=True)
