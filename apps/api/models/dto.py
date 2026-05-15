
from typing import Any

from pydantic import BaseModel, Field


class HandoffContext(BaseModel):
    session_id: str
    protocol_id: str
    fields: dict[str, Any] = {}
    route_key: str | None = None

class Disposition(BaseModel):
    session_id: str
    code: str = Field(..., description="resolved|callback|escalated|abandoned")
    notes: str | None = None
