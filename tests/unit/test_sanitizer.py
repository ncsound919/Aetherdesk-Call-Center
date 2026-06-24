import pytest
from apps.api.services.sanitizer import InputSanitizer, SanitizationResult


class TestInputSanitizer:
    def test_sanitize_string_clean(self):
        result = InputSanitizer.sanitize_string("hello world", "greeting")
        assert result.is_valid is True
        assert result.errors == []

    def test_sanitize_string_html_escaped(self):
        result = InputSanitizer.sanitize_string("<b>bold</b>", "html")
        assert "&lt;b&gt;bold&lt;/b&gt;" in result.sanitized_value
        assert "<b>" not in result.sanitized_value

    def test_sanitize_string_strips_whitespace(self):
        result = InputSanitizer.sanitize_string("  spaced  ", "field")
        assert result.sanitized_value == "spaced"

    def test_sanitize_string_non_string(self):
        result = InputSanitizer.sanitize_string(123, "number")
        assert result.is_valid is False
        assert "must be a string" in result.errors[0]

    def test_sanitize_string_too_long(self):
        long_str = "a" * 20000
        result = InputSanitizer.sanitize_string(long_str, "long")
        assert result.is_valid is False
        assert "exceeds maximum length" in result.errors[0]
        assert len(result.sanitized_value) == 10000

    def test_sanitize_string_script_tag(self):
        result = InputSanitizer.sanitize_string("<script>alert('xss')</script>", "input")
        assert result.is_valid is False
        assert "dangerous pattern" in result.errors[0]

    def test_sanitize_string_javascript_protocol(self):
        result = InputSanitizer.sanitize_string("javascript:alert(1)", "link")
        assert result.is_valid is False

    def test_sanitize_string_event_handler(self):
        result = InputSanitizer.sanitize_string('onclick="evil()"', "attr")
        assert result.is_valid is False

    def test_sanitize_string_expression(self):
        result = InputSanitizer.sanitize_string("${process.env.SECRET}", "tmpl")
        assert result.is_valid is False

    def test_sanitize_dict_non_string_key(self):
        data = {1: "value", 2: "other"}
        result = InputSanitizer.sanitize_dict(data)
        assert 1 not in result
        assert 2 not in result

    def test_sanitize_transcript(self):
        transcript = ["hello", "<script>alert(1)</script>", "world"]
        result = InputSanitizer.sanitize_transcript(transcript)
        assert len(result) == 3
        assert result[0] == "hello"
        assert "&lt;script&gt;" in result[1]
        assert result[2] == "world"

    def test_sanitize_transcript_filters_non_strings(self):
        transcript = ["hello", 123, "world"]
        result = InputSanitizer.sanitize_transcript(transcript)
        assert len(result) == 2
        assert result[0] == "hello"
        assert result[1] == "world"

    def test_sanitize_protocol_fields_required_field_validation_fails(self):
        fields = {"name": "<script>alert(1)</script>"}
        result = InputSanitizer.sanitize_protocol_fields(fields, ["name"])
        assert result.is_valid is False
        assert any("dangerous pattern" in e for e in result.errors)

    def test_sanitize_protocol_fields_optional_non_string(self):
        fields = {"required_field": "valid", "optional_num": 42}
        result = InputSanitizer.sanitize_protocol_fields(fields, ["required_field"])
        assert result.is_valid is True
        assert result.sanitized_value["optional_num"] == 42
        assert result.sanitized_value["required_field"] == "valid"

    def test_sanitize_user_input_function(self):
        from apps.api.services.sanitizer import sanitize_user_input
        data = {"name": "Alice", "age": 30}
        result = sanitize_user_input(data)
        assert result["name"] == "Alice"
        assert result["age"] == 30

    def test_sanitize_dict_simple(self):
        data = {"name": "Alice", "age": 30}
        result = InputSanitizer.sanitize_dict(data)
        assert result["name"] == "Alice"
        assert result["age"] == 30

    def test_sanitize_dict_nested(self):
        data = {"level1": {"level2": {"key": "value"}}}
        result = InputSanitizer.sanitize_dict(data)
        assert result["level1"]["level2"]["key"] == "value"

    def test_sanitize_dict_max_depth(self):
        deep = {}
        d = deep
        for _ in range(7):
            d["nested"] = {}
            d = d["nested"]
        result = InputSanitizer.sanitize_dict({"a": deep})
        assert result["a"]["nested"]["nested"]["nested"]["nested"]["nested"] == {}

    def test_sanitize_dict_html_in_keys(self):
        data = {"<script>": "value"}
        result = InputSanitizer.sanitize_dict(data)
        assert "&lt;script&gt;" in result
        assert result["&lt;script&gt;"] == "value"

    def test_sanitize_dict_list_values(self):
        data = {"items": ["a", "<b>", "c"]}
        result = InputSanitizer.sanitize_dict(data)
        assert result["items"][1] == "&lt;b&gt;"

    def test_sanitize_protocol_fields_missing_required(self):
        result = InputSanitizer.sanitize_protocol_fields({"optional": "x"}, ["required_field"])
        assert result.is_valid is False
        assert any("required_field" in e for e in result.errors)

    def test_sanitize_protocol_fields_valid(self):
        fields = {"name": "Alice", "age": "30"}
        result = InputSanitizer.sanitize_protocol_fields(fields, ["name"])
        assert result.is_valid is True
        assert result.sanitized_value["name"] == "Alice"

    def test_sanitize_protocol_fields_too_many(self):
        fields = {str(i): str(i) for i in range(150)}
        result = InputSanitizer.sanitize_protocol_fields(fields, [])
        assert result.is_valid is False
        assert "Too many fields" in result.errors[0]
