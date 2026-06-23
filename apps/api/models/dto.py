from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=255, description="Business name")
    email: str = Field(..., max_length=255, description="Business email")
    phone: str | None = Field(None, max_length=20, description="Business phone")
    plan_id: str | None = Field(None, description="Subscription plan ID")
    gdpr_consent: bool = Field(default=False, description="GDPR consent status")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Acme Corp",
                "email": "admin@acmecorp.com",
                "phone": "+15551234567",
                "gdpr_consent": True,
            }
        }
    )


class TenantResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None
    plan_name: str
    status: str
    settings: dict
    gdpr_consent: bool
    created_at: datetime


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Agent display name")
    display_name: str | None = Field(None, description="Public-facing name")
    agent_type: str = Field(default="ai", pattern=r"^(ai|human|hybrid)$", description="Agent type")
    skills: list[str] = Field(default_factory=list, description="Agent skills for routing")
    config: dict[str, Any] = Field(default_factory=dict, description="AI model and behavior config")

    @field_validator("skills", mode="before")
    @classmethod
    def validate_skills(cls, v):
        allowed_skills = ["sales", "support", "technical", "billing", "accounting"]
        if isinstance(v, list):
            return [skill for skill in v if skill in allowed_skills]
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Sales Agent",
                "agent_type": "ai",
                "skills": ["sales", "support"],
                "config": {"model": "llama-3.1-70b", "temperature": 0.7, "voice": "professional-male"},
            }
        }
    )


class AgentResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    display_name: str
    agent_type: str
    status: str
    skills: list[str]
    sip_extension: str | None
    total_calls: int
    total_talk_time_seconds: int
    avg_rating: float
    created_at: datetime


class AgentStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(offline|online|available|busy|on_call|paused|training)$", description="New status")
    session_ref: str | None = Field(None, description="Fonoster session reference")


class CallCreate(BaseModel):
    agent_id: str | None = Field(None, description="Target agent ID")
    caller_number: str = Field(..., description="Caller phone number")
    called_number: str | None = Field(None, description="Called number")
    call_direction: str = Field(default="inbound", pattern=r"^(inbound|outbound)$", description="Call direction")
    intent: str | None = Field(None, description="Detected caller intent")


class CallAction(BaseModel):
    action: str = Field(..., pattern=r"^(answer|hangup|mute|unmute|hold|unhold|transfer|record|gather|say|play|dtmf)$", description="Action to perform")
    target: str | None = Field(None, description="Target for transfer or dial")
    data: dict[str, Any] | None = Field(None, description="Additional data for the action")


class CallResponse(BaseModel):
    id: str
    tenant_id: str
    agent_id: str | None
    caller_number: str
    call_direction: str
    call_status: str
    duration_seconds: int
    cost: float
    sip_call_id: str | None
    intent_detected: str | None
    created_at: datetime


class UsageResponse(BaseModel):
    total_agents: int
    active_agents: int
    total_calls: int
    active_calls: int
    total_minutes: float
    avg_call_duration: float
    queue_depth: int
    total_cost: float
    by_agent: list[dict]
    by_day: list[dict]


class HealthCheck(BaseModel):
    status: str
    timestamp: datetime
    version: str
    services: dict[str, str]
    fonster_connected: bool
    database_connected: bool


class WebhookConfig(BaseModel):
    tenant_id: str
    url: str
    events: list[str]
    secret: str
    active: bool = True
