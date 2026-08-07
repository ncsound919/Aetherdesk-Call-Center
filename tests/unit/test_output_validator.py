"""Unit tests for api.services.output_validator."""

from unittest.mock import patch

import pytest

from api.services.output_validator import (
    VALIDATION_SCHEMAS,
    OutputValidator,
    validator,
)


class TestValidateJSONOutput:
    def test_valid_json_no_errors(self):
        result = validator.validate_json_output(
            '{"intent": "billing_invoice", "confidence": 0.9}', VALIDATION_SCHEMAS["intent_classification"]
        )
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["fixed"] is None

    def test_valid_json_with_schema_error(self):
        result = validator.validate_json_output(
            '{"intent": 123, "confidence": 0.9}', VALIDATION_SCHEMAS["intent_classification"]
        )
        assert result["valid"] is False
        assert any("should be string" in e for e in result["errors"])
        assert result["fixed"] == '{"intent": 123, "confidence": 0.9}'

    def test_invalid_json_auto_fixed(self):
        with patch("api.services.output_validator.logger.info") as mock_info:
            result = validator.validate_json_output(
                "{'intent': 'billing_invoice', 'confidence': 0.9}",
                VALIDATION_SCHEMAS["intent_classification"],
            )

        # The original parse error is kept in the errors list, so valid is False,
        # but the auto-fixed (normalized) JSON is returned in "fixed".
        assert result["valid"] is False
        assert "JSON parse error" in result["errors"][0]
        assert result["fixed"] == '{"intent": "billing_invoice", "confidence": 0.9}'
        mock_info.assert_called_once_with("json_fixed_automatically")

    def test_invalid_json_unfixable_returns_original(self):
        result = validator.validate_json_output("not json at all", {})
        assert result["valid"] is False
        assert "JSON parse error" in result["errors"][0]
        assert result["fixed"] is None

    def test_invalid_json_fix_failed(self):
        result = validator.validate_json_output("{'a': }", {})
        assert result["valid"] is False
        assert "Could not auto-fix JSON" in result["errors"]
        assert result["fixed"] == '{"a": }'


class TestFixCommonJSONErrors:
    def test_code_fence(self):
        assert validator.fix_common_json_errors('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_code_fence_plain(self):
        assert validator.fix_common_json_errors('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_single_quotes_and_bool_none(self):
        fixed = validator.fix_common_json_errors("{'a': True, 'b': None, 'c': False,}")
        assert fixed == '{"a": true, "b": null, "c": false}'

    def test_missing_closing_brace(self):
        assert validator.fix_common_json_errors('{"a": 1') == '{"a": 1}'

    def test_missing_closing_bracket(self):
        assert validator.fix_common_json_errors("[1, 2") == "[1, 2]"

    def test_leading_text_extracts_braces(self):
        # Only the leading text is trimmed; trailing text after the closing brace remains
        assert validator.fix_common_json_errors('prefix {"a": 1} suffix') == '{"a": 1} suffix'

    def test_multiline_trailing_commas(self):
        fixed = validator.fix_common_json_errors('{\n  "a": 1,\n  "b": 2,\n}')
        assert fixed == '{\n  "a": 1\n  "b": 2}'

    def test_plain_valid_json_unchanged(self):
        assert validator.fix_common_json_errors('{"a": 1}') == '{"a": 1}'


class TestValidateAgainstSchema:
    def test_missing_required_field(self):
        errors = validator._validate_against_schema(
            {"confidence": 0.5}, VALIDATION_SCHEMAS["intent_classification"]
        )
        assert "Missing required field: 'intent'" in errors

    def test_required_field_none(self):
        errors = validator._validate_against_schema(
            {"intent": None, "confidence": 0.5},
            VALIDATION_SCHEMAS["intent_classification"],
        )
        assert "Missing required field: 'intent'" in errors

    def test_string_type_mismatch(self):
        errors = validator._validate_against_schema(
            {"intent": 42, "confidence": 0.5},
            VALIDATION_SCHEMAS["intent_classification"],
        )
        assert any("'intent' should be string, got int" in e for e in errors)

    def test_number_type_mismatch(self):
        errors = validator._validate_against_schema(
            {"intent": "x", "confidence": "high"},
            VALIDATION_SCHEMAS["intent_classification"],
        )
        assert any("'confidence' should be number, got str" in e for e in errors)

    def test_object_type_mismatch(self):
        errors = validator._validate_against_schema(
            {"intent": "x", "confidence": 0.5, "entities": []},
            VALIDATION_SCHEMAS["intent_classification"],
        )
        assert any("'entities' type mismatch" in e for e in errors)

    def test_required_object_field_wrong_type(self):
        errors = validator._validate_against_schema(
            {"entities": [], "confidence": 0.5}, VALIDATION_SCHEMAS["entity_extraction"]
        )
        assert any("'entities' should be object, got list" in e for e in errors)

    def test_unknown_key_is_skipped(self):
        errors = validator._validate_against_schema(
            {"entities": {"order": "1"}, "confidence": 0.5, "unexpected": "x"},
            VALIDATION_SCHEMAS["entity_extraction"],
        )
        assert errors == []

    def test_below_minimum(self):
        errors = validator._validate_against_schema(
            {"intent": "x", "confidence": -0.1},
            VALIDATION_SCHEMAS["intent_classification"],
        )
        assert any("'confidence' below minimum (0)" in e for e in errors)

    def test_above_maximum(self):
        errors = validator._validate_against_schema(
            {"intent": "x", "confidence": 1.5},
            VALIDATION_SCHEMAS["intent_classification"],
        )
        assert any("'confidence' above maximum (1)" in e for e in errors)

    def test_enum_mismatch(self):
        errors = validator._validate_against_schema(
            {"sentiment": "angry", "score": 0.5}, VALIDATION_SCHEMAS["sentiment_analysis"]
        )
        assert any("not in allowed values" in e for e in errors)

    def test_unknown_property_type_mismatch(self):
        errors = validator._validate_against_schema(
            {"sentiment": "positive", "score": 0.5, "confidence": "not-a-number"},
            VALIDATION_SCHEMAS["sentiment_analysis"],
        )
        assert any("'confidence' type mismatch" in e for e in errors)

    def test_clean_schema_pass(self):
        errors = validator._validate_against_schema(
            {"entities": {"order": "123"}, "confidence": 0.8},
            VALIDATION_SCHEMAS["entity_extraction"],
        )
        assert errors == []


class TestTypeCheck:
    @pytest.mark.parametrize(
        "value,expected,result",
        [
            ("abc", "string", True),
            (42, "string", False),
            (1, "number", True),
            (1.5, "number", True),
            ("x", "number", False),
            ({"a": 1}, "object", True),
            ([], "object", False),
            ([1, 2], "array", True),
            ({"a": 1}, "array", False),
            (True, "boolean", True),
            (1, "boolean", False),
            (object(), "unknown_type", True),
        ],
    )
    def test_type_check(self, value, expected, result):
        assert validator._type_check(value, expected) is result


class TestValidateIntentResult:
    def test_missing_intent(self):
        result = validator.validate_intent_result({}, ["generalInquiry"])
        assert result["valid"] is False
        assert "Missing 'intent' field" in result["errors"]

    def test_intent_not_allowed(self):
        result = validator.validate_intent_result(
            {"intent": "nope", "confidence": 0.9}, ["generalInquiry"]
        )
        assert result["valid"] is False
        assert "not in allowed list" in result["errors"][0]

    def test_invalid_confidence_string(self):
        result = validator.validate_intent_result(
            {"intent": "generalInquiry", "confidence": "high"}, ["generalInquiry"]
        )
        assert result["valid"] is False
        assert "Invalid confidence value: high" in result["errors"]

    def test_invalid_confidence_range(self):
        result = validator.validate_intent_result(
            {"intent": "generalInquiry", "confidence": 1.5}, ["generalInquiry"]
        )
        assert result["valid"] is False
        assert "Invalid confidence value: 1.5" in result["errors"]

    def test_valid(self):
        result = validator.validate_intent_result(
            {"intent": "generalInquiry", "confidence": 0.5}, ["generalInquiry"]
        )
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["intent"] == "generalInquiry"

    def test_default_confidence_accepted(self):
        result = validator.validate_intent_result({"intent": "generalInquiry"}, ["generalInquiry"])
        assert result["valid"] is True


class TestValidateEntityExtraction:
    def test_missing_fields(self):
        result = validator.validate_entity_extraction({"order_id": "123"}, ["customer_id"])
        assert result["valid"] is False
        assert "Missing required entity fields: ['customer_id']" in result["errors"]

    def test_all_present(self):
        result = validator.validate_entity_extraction(
            {"order_id": "123", "customer_id": "456"}, ["order_id", "customer_id"]
        )
        assert result["valid"] is True
        assert result["errors"] == []


class TestSchemaIntrospection:
    def test_get_validation_schema(self):
        assert validator.get_validation_schema("intent_classification") == VALIDATION_SCHEMAS[
            "intent_classification"
        ]

    def test_get_validation_schema_missing(self):
        assert validator.get_validation_schema("unknown") is None

    def test_list_schemas(self):
        assert set(validator.list_schemas()) == set(VALIDATION_SCHEMAS.keys())


class TestRepairWithLLMFallback:
    def test_regex_repair_success(self):
        with patch("api.services.output_validator.logger.info") as mock_info:
            out = validator.repair_with_llm_fallback("{'a': 1}", "some error")

        assert out == '{"a": 1}'
        mock_info.assert_any_call("repair_successful_via_regex")

    def test_brace_extraction_success(self):
        with patch("api.services.output_validator.logger.info") as mock_info:
            out = validator.repair_with_llm_fallback("text { 'a': 1 } trailing", "error")

        assert out == '{ "a": 1 }'
        mock_info.assert_any_call("repair_successful_via_brace_extraction")

    def test_repair_failed_returns_original(self):
        with patch("api.services.output_validator.logger.warning") as mock_warn:
            out = validator.repair_with_llm_fallback("complete garbage", "error")

        assert out == "complete garbage"
        mock_warn.assert_called_once_with("repair_failed")

    def test_brace_extraction_candidate_invalid(self):
        # brace_match found, but candidate still fails to parse -> falls through
        with patch("api.services.output_validator.logger.warning") as mock_warn:
            out = validator.repair_with_llm_fallback("text { not json } more", "error")

        assert out == "text { not json } more"
        mock_warn.assert_called_once_with("repair_failed")
