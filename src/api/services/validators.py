
import re
from typing import Any


class Validators:
    def validate(self, rule: str | dict[str, Any], value: str) -> bool:
        if isinstance(rule, str):
            return bool(re.match(rule, value))
        if isinstance(rule, dict):
            if 'enum' in rule:
                return value in rule['enum']
            if 'min' in rule and 'max' in rule:
                try:
                    x = float(value)
                    return rule['min'] <= x <= rule['max']
                except ValueError:
                    return False
        return True

validators = Validators()


