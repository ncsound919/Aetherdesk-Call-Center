import json
import re

import structlog

logger = structlog.get_logger()

VALIDATION_SCHEMAS = {
    "intent_classification": {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "entities": {"type": "object"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasoning": {"type": "string"},
        },
        "required": ["intent", "confidence"],
    },
    "entity_extraction": {
        "type": "object",
        "properties": {
            "entities": {"type": "object"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["entities"],
    },
    "sentiment_analysis": {
        "type": "object",
        "properties": {
            "sentiment": {
                "type": "string",
                "enum": ["positive", "negative", "neutral", "mixed"],
            },
            "score": {"type": "number", "minimum": -1, "maximum": 1},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["sentiment", "score"],
    },
}

COMMON_JSON_ERRORS = [
    (r"(?<!\")'", '"'),
    (r"(?<!\w)True(?!\w)", "true"),
    (r"(?<!\w)False(?!\w)", "false"),
    (r"(?<!\w)None(?!\w)", "null"),
]


class OutputValidator:
    def validate_json_output(self, llm_output: str, schema: dict) -> dict:
        parsed = None
        errors = []

        try:
            parsed = json.loads(llm_output)
        except json.JSONDecodeError as e:
            errors.append(f"JSON parse error: {e.msg}")
            fixed = self.fix_common_json_errors(llm_output)
            if fixed != llm_output:
                try:
                    parsed = json.loads(fixed)
                    logger.info("json_fixed_automatically")
                except json.JSONDecodeError:
                    errors.append("Could not auto-fix JSON")
                    return {"valid": False, "errors": errors, "fixed": fixed}

        if parsed is None:
            return {"valid": False, "errors": errors, "fixed": None}

        schema_errors = self._validate_against_schema(parsed, schema)
        errors.extend(schema_errors)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "fixed": json.dumps(parsed) if errors else None,
        }

    def fix_common_json_errors(self, text: str) -> str:
        fixed = text.strip().strip("```json").strip("```").strip()

        for pattern, replacement in COMMON_JSON_ERRORS:
            fixed = re.sub(pattern, replacement, fixed)

        fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
        fixed = re.sub(r",\s*$", "", fixed, flags=re.MULTILINE)

        open_braces = fixed.count("{")
        close_braces = fixed.count("}")
        if open_braces > close_braces:
            fixed += "}" * (open_braces - close_braces)

        open_brackets = fixed.count("[")
        close_brackets = fixed.count("]")
        if open_brackets > close_brackets:
            fixed += "]" * (open_brackets - close_brackets)

        if not fixed.startswith("{"):
            for idx, c in enumerate(fixed):
                if c == "{":
                    fixed = fixed[idx:]
                    break

        return fixed

    def _validate_against_schema(self, data: dict, schema: dict) -> list[str]:
        errors = []
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for field in required:
            if field not in data or data[field] is None:
                errors.append(f"Missing required field: '{field}'")
                continue
            field_schema = properties.get(field, {})
            field_type = field_schema.get("type", "")
            value = data[field]

            if field_type == "string" and not isinstance(value, str):
                errors.append(f"Field '{field}' should be string, got {type(value).__name__}")
            elif field_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"Field '{field}' should be number, got {type(value).__name__}")
            elif field_type == "object" and not isinstance(value, dict):
                errors.append(f"Field '{field}' should be object, got {type(value).__name__}")

            if "minimum" in field_schema and isinstance(value, (int, float)):
                if value < field_schema["minimum"]:
                    errors.append(f"Field '{field}' below minimum ({field_schema['minimum']})")
            if "maximum" in field_schema and isinstance(value, (int, float)):
                if value > field_schema["maximum"]:
                    errors.append(f"Field '{field}' above maximum ({field_schema['maximum']})")

            if "enum" in field_schema and isinstance(value, str):
                if value not in field_schema["enum"]:
                    errors.append(f"Field '{field}' value '{value}' not in allowed values: {field_schema['enum']}")

        for key in data:
            if key not in properties:
                continue
            field_schema = properties[key]
            if "type" in field_schema and not self._type_check(data[key], field_schema["type"]):
                errors.append(f"Field '{key}' type mismatch")

        return errors

    def _type_check(self, value, expected_type: str) -> bool:
        mapping = {
            "string": str,
            "number": (int, float),
            "object": dict,
            "array": list,
            "boolean": bool,
        }
        py_type = mapping.get(expected_type)
        return isinstance(value, py_type) if py_type else True

    def validate_intent_result(self, result: dict, allowed_intents: list) -> dict:
        errors = []
        intent = result.get("intent", "")

        if not intent:
            errors.append("Missing 'intent' field")
            return {"valid": False, "errors": errors, "intent": intent}

        if intent not in allowed_intents:
            errors.append(f"Intent '{intent}' not in allowed list: {allowed_intents}")
            return {"valid": False, "errors": errors, "intent": intent}

        confidence = result.get("confidence", 0)
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            errors.append(f"Invalid confidence value: {confidence}")

        return {"valid": len(errors) == 0, "errors": errors, "intent": intent}

    def validate_entity_extraction(self, entities: dict, required_fields: list) -> dict:
        errors = []
        missing = [f for f in required_fields if f not in entities]
        if missing:
            errors.append(f"Missing required entity fields: {missing}")

        return {"valid": len(errors) == 0, "errors": errors, "entities": entities}

    def get_validation_schema(self, schema_name: str) -> dict | None:
        return VALIDATION_SCHEMAS.get(schema_name)

    def list_schemas(self) -> list[str]:
        return list(VALIDATION_SCHEMAS.keys())

    def repair_with_llm_fallback(self, invalid_output: str, error: str) -> str:
        logger.info("repair_attempt", error_preview=error[:100])

        fixed = self.fix_common_json_errors(invalid_output)

        try:
            json.loads(fixed)
            logger.info("repair_successful_via_regex")
            return fixed
        except json.JSONDecodeError:
            pass

        brace_match = re.search(r"\{.*\}", fixed, re.DOTALL)
        if brace_match:
            candidate = brace_match.group(0)
            try:
                json.loads(candidate)
                logger.info("repair_successful_via_brace_extraction")
                return candidate
            except json.JSONDecodeError:
                pass

        logger.warning("repair_failed")
        return invalid_output


validator = OutputValidator()
