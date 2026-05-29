"""Centralized database error types."""
from typing import Optional

class DatabaseError(Exception):
    def __init__(self, message: str, detail: Optional[dict] = None):
        self.message = message
        self.detail = detail or {}
        super().__init__(self.message)

class NotFoundError(DatabaseError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} not found: {resource_id}", {"resource": resource, "id": resource_id})

class PoolNotAvailableError(DatabaseError):
    def __init__(self):
        super().__init__("Database pool not available")
