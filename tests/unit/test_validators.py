import pytest
from api.services.validators import Validators


class TestValidators:
    def setup_method(self):
        self.v = Validators()

    def test_regex_match(self):
        assert self.v.validate(r"^\d{3}-\d{2}-\d{4}$", "123-45-6789") is True

    def test_regex_no_match(self):
        assert self.v.validate(r"^\d{3}$", "abcd") is False

    def test_regex_empty_string(self):
        assert self.v.validate(r"^\d+$", "") is False

    def test_enum_match(self):
        assert self.v.validate({"enum": ["red", "green", "blue"]}, "red") is True

    def test_enum_no_match(self):
        assert self.v.validate({"enum": ["red", "green"]}, "yellow") is False

    def test_range_valid(self):
        assert self.v.validate({"min": 1, "max": 100}, "50") is True

    def test_range_below_min(self):
        assert self.v.validate({"min": 10, "max": 20}, "5") is False

    def test_range_above_max(self):
        assert self.v.validate({"min": 10, "max": 20}, "25") is False

    def test_range_at_boundary(self):
        assert self.v.validate({"min": 10, "max": 20}, "10") is True
        assert self.v.validate({"min": 10, "max": 20}, "20") is True

    def test_range_non_numeric(self):
        assert self.v.validate({"min": 1, "max": 10}, "abc") is False

    def test_unknown_rule_default_true(self):
        assert self.v.validate({}, "anything") is True
