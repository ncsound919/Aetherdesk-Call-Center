
import re
from typing import Any


class Validators:
    def validate(self, rule: str | dict[str, Any], value: str) -> bool:
        if isinstance(rule, str):
            # Use fullmatch so patterns are implicitly anchored at both
            # ends, preventing partial matches from being treated as valid
            # (e.g. a rule of r"\d+" matching "abc123" via re.match).
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
        # Default-deny: an unrecognized/unsupported rule type or shape
        # must never be silently treated as valid.
        return False

validators = Validators()


