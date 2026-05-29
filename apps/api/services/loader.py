
import json
import os
from typing import Any


class FileLoader:
    def __init__(self, base_path: str | None = None):
        if base_path is None:
            base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "config", "protocols")
        self.base_path = base_path

    def load(self, protocol_id: str) -> dict[str, Any] | None:
        path = os.path.join(self.base_path, f"{protocol_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

loader = FileLoader()
