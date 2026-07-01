import pytest
from api.services.validators import Validators, validators


class TestValidatorsTypedMethods:
    def setup_method(self):
        self.v = Validators()

    def test_validate_phone_valid(self):
        assert self.v.validate_phone("+14155551234") is True
        assert self.v.validate_phone("14155551234") is True
        assert self.v.validate_phone("4155551234") is True

    def test_validate_phone_invalid(self):
        assert self.v.validate_phone("") is False
        assert self.v.validate_phone("not-a-phone") is False
        assert self.v.validate_phone("+") is False
        assert self.v.validate_phone("123") is False
        assert self.v.validate_phone("+" * 20) is False

    def test_validate_email_valid(self):
        assert self.v.validate_email("user@example.com") is True
        assert self.v.validate_email("test.user+tag@domain.co.uk") is True
        assert self.v.validate_email("x@y.co") is True

    def test_validate_email_invalid(self):
        assert self.v.validate_email("") is False
        assert self.v.validate_email("not-an-email") is False
        assert self.v.validate_email("@missing-username.com") is False
        assert self.v.validate_email("user@") is False
        assert self.v.validate_email("user@.com") is False

    def test_validate_zip_valid(self):
        assert self.v.validate_zip("12345") is True
        assert self.v.validate_zip("12345-6789") is True

    def test_validate_zip_invalid(self):
        assert self.v.validate_zip("") is False
        assert self.v.validate_zip("1234") is False
        assert self.v.validate_zip("123456") is False
        assert self.v.validate_zip("ABCDE") is False
        assert self.v.validate_zip("12345-678") is False

    def test_validate_rx_number_valid(self):
        assert self.v.validate_rx_number("123456") is True
        assert self.v.validate_rx_number("999999999999") is True

    def test_validate_rx_number_invalid(self):
        assert self.v.validate_rx_number("") is False
        assert self.v.validate_rx_number("12345") is False
        assert self.v.validate_rx_number("1234567") is True
        assert self.v.validate_rx_number("abc123") is False

    def test_validate_uuid_valid(self):
        assert self.v.validate_uuid("550e8400-e29b-41d4-a716-446655440000") is True
        assert self.v.validate_uuid("f47ac10b-58cc-4372-a567-0e02b2c3d479") is True

    def test_validate_uuid_invalid(self):
        assert self.v.validate_uuid("") is False
        assert self.v.validate_uuid("not-a-uuid") is False
        assert self.v.validate_uuid("550e8400-e29b-41d4-a716-44665544000") is False
        assert self.v.validate_uuid("550e8400-e29b-41d4-a716-4466554400000") is False
        assert self.v.validate_uuid("gggggggg-eeee-eeee-eeee-ffffffffffff") is False

    def test_singleton_module_level(self):
        assert isinstance(validators, Validators)
