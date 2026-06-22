import html
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class SanitizationResult:
    is_valid: bool
    sanitized_value: Any
    errors: list[str]


class InputSanitizer:
    MAX_STRING_LENGTH = 10000
    MAX_FIELD_COUNT = 100
    MAX_NESTING_DEPTH = 5

    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'on\w+\s*=',
        r'\$\{.*\}',
        r'\{\{.*\}\}',
    ]

    @classmethod
    def sanitize_string(cls, value: str, field_name: str = "field") -> SanitizationResult:
        errors = []

        if not isinstance(value, str):
            return SanitizationResult(False, None, [f"{field_name} must be a string"])

        if len(value) > cls.MAX_STRING_LENGTH:
            errors.append(f"{field_name} exceeds maximum length of {cls.MAX_STRING_LENGTH}")

        sanitized = value[:cls.MAX_STRING_LENGTH]

        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, sanitized, re.IGNORECASE):
                errors.append(f"{field_name} contains dangerous pattern")
                break

        sanitized = html.escape(sanitized)

        return SanitizationResult(
            is_valid=len(errors) == 0,
            sanitized_value=sanitized.strip(),
            errors=errors
        )

    @classmethod
    def sanitize_dict(cls, data: dict[str, Any], max_depth: int = 0) -> dict[str, Any]:
        if max_depth > cls.MAX_NESTING_DEPTH:
            return {}

        sanitized = {}
        for key, value in data.items():
            if not isinstance(key, str):
                continue

            sanitized_key = html.escape(key.strip())[:200]

            if isinstance(value, str):
                result = cls.sanitize_string(value, sanitized_key)
                sanitized[sanitized_key] = result.sanitized_value
            elif isinstance(value, dict):
                sanitized[sanitized_key] = cls.sanitize_dict(value, max_depth + 1)
            elif isinstance(value, list):
                sanitized[sanitized_key] = [
                    cls.sanitize_string(v, f"{sanitized_key}[{i}]").sanitized_value
                    if isinstance(v, str) else v
                    for i, v in enumerate(value[:100])
                ]
            else:
                sanitized[sanitized_key] = value

        return sanitized

    @classmethod
    def sanitize_transcript(cls, transcript: list[str]) -> list[str]:
        return [
            cls.sanitize_string(text, f"transcript[{i}]").sanitized_value
            for i, text in enumerate(transcript[:cls.MAX_TRANSCRIPT_LENGTH])
            if isinstance(text, str)
        ]

    @classmethod
    def sanitize_protocol_fields(cls, fields: dict[str, Any], required_fields: list[str]) -> SanitizationResult:
        errors = []
        sanitized = {}

        if len(fields) > cls.MAX_FIELD_COUNT:
            errors.append(f"Too many fields: {len(fields)}")
            return SanitizationResult(False, None, errors)

        for field_name in required_fields:
            if field_name not in fields:
                errors.append(f"Required field missing: {field_name}")
                continue

            value = fields[field_name]
            result = cls.sanitize_string(str(value), field_name)

            if result.is_valid:
                sanitized[field_name] = result.sanitized_value
            else:
                errors.extend(result.errors)

        for key, value in fields.items():
            if key in required_fields:
                continue
            if isinstance(value, str):
                result = cls.sanitize_string(value, key)
                sanitized[key] = result.sanitized_value
            else:
                sanitized[key] = value

        return SanitizationResult(
            is_valid=len(errors) == 0,
            sanitized_value=sanitized,
            errors=errors
        )


def sanitize_user_input(data: dict[str, Any]) -> dict[str, Any]:
    return InputSanitizer.sanitize_dict(data)
