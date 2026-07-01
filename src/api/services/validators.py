
import re
from typing import Any


_PHONE_RE = re.compile(r"^\+?1?\d{10,15}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
_RX_NUMBER_RE = re.compile(r"^\d{6,12}$")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class Validators:
    def validate(self, rule: str | dict[str, Any], value: str) -> bool:
        if isinstance(rule, str):
            return bool(re.fullmatch(rule, value))
        if isinstance(rule, dict):
            if 'enum' in rule:
                return value in rule['enum']
            if 'min' in rule and 'max' in rule:
                try:
                    x = float(value)
                    return rule['min'] <= x <= rule['max']
                except ValueError:
                    return False
        return False

    def validate_phone(self, value: str) -> bool:
        return bool(_PHONE_RE.match(value))

    def validate_email(self, value: str) -> bool:
        return bool(_EMAIL_RE.match(value))

    def validate_zip(self, value: str) -> bool:
        return bool(_ZIP_RE.match(value))

    def validate_rx_number(self, value: str) -> bool:
        return bool(_RX_NUMBER_RE.match(value))

    def validate_uuid(self, value: str) -> bool:
        return bool(_UUID_RE.match(value))


validators = Validators()

