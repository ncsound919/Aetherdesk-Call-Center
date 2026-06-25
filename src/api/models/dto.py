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


class ShiftCreate(BaseModel):
    agent_id: str
    start_time: str
    end_time: str
    shift_type: str = "regular"
    notes: str | None = None


class QAScoreCreate(BaseModel):
    call_id: str
    agent_id: str
    rubric_id: str
    scores_per_criterion: dict[str, int]
    notes: str | None = None


class QARubricCreate(BaseModel):
    name: str
    description: str | None = None
    criteria: list[dict]


class IntegrationConfigCreate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=100)
    integration_type: str = Field(..., pattern=r"^(crm|ticketing)$")
    config: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"


class TicketCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|urgent)$")
    status: str = Field(default="new", pattern=r"^(new|open|pending|solved|closed)$")
    customer_id: str | None = None
    call_id: str | None = None


class AIExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    model_a: str
    model_b: str
    traffic_split: float = Field(default=0.5, ge=0.0, le=1.0)


class AIEvaluationCreate(BaseModel):
    experiment_id: str | None = None
    call_id: str | None = None
    predicted_intent: str
    actual_intent: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    model_used: str | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)


class PenTestScanCreate(BaseModel):
    target_url: str
    severity: str = "medium"


class PenTestScanResponse(BaseModel):
    id: str
    tenant_id: str
    target_url: str
    status: str
    findings_json: list | dict
    severity: str
    started_at: datetime | None
    completed_at: datetime | None


class WAFRuleUpdate(BaseModel):
    action: str = Field(..., pattern=r"^(enable|disable|block|log|captcha)$")


class DataClassifyRequest(BaseModel):
    table: str
    column: str
    sensitivity: str = Field(..., pattern=r"^(public|internal|confidential|restricted)$")
    description: str | None = None


class DataClassifyResponse(BaseModel):
    id: str
    tenant_id: str
    schema_name: str
    table_name: str
    column_name: str
    sensitivity: str
    description: str | None


class RBACAuditEntry(BaseModel):
    role: str
    resource: str
    action: str
    expected: bool
    actual: bool
    passed: bool


class RBACAuditResponse(BaseModel):
    total_tests: int
    results: list[RBACAuditEntry]


class CredentialAuditResponse(BaseModel):
    total_users: int
    critical: int
    warning: int
    ok: int
    users: list[dict]


class DRTestResponse(BaseModel):
    test_type: str
    success: bool
    duration_seconds: float
    details: str


class DRStatusResponse(BaseModel):
    dr_ready: bool
    rto_seconds: int
    rpo_seconds: int
    backup_enabled: bool
    failover_enabled: bool


class CacheStatsResponse(BaseModel):
    hits: int
    misses: int
    hit_rate_pct: float
    miss_rate_pct: float
    total_requests: int
    local_cache_size: int


class CircuitBreakerState(BaseModel):
    name: str
    state: str
    failure_count: int
    success_count: int
    threshold: int
    total_calls: int
    is_open: bool


class VoiceQualityMetricCreate(BaseModel):
    call_id: str
    agent_id: str | None = None
    mos: float = Field(ge=1.0, le=5.0)
    jitter_ms: float = Field(ge=0.0)
    packet_loss_pct: float = Field(ge=0.0, le=100.0)
    latency_ms: float = Field(ge=0.0)
    rtt_samples: list[float] = Field(default_factory=list)
    codec: str = "opus"


class VoiceQualityMetricResponse(BaseModel):
    id: str
    tenant_id: str
    call_id: str
    agent_id: str | None
    mos: float
    jitter_ms: float
    packet_loss_pct: float
    latency_ms: float
    codec: str
    quality_rating: str
    created_at: datetime


class CSATSurveyCreate(BaseModel):
    call_id: str | None = None
    customer_id: str | None = None
    rating: int = Field(..., ge=1, le=5)
    feedback: str | None = None
    channel: str = "voice"


class CustomerInteractionCreate(BaseModel):
    customer_id: str
    interaction_type: str
    channel: str = "voice"
    call_id: str | None = None
    agent_id: str | None = None
    sentiment: str = "neutral"
    summary: str | None = None
    duration_seconds: int = 0


class ValidateOutputRequest(BaseModel):
    output: str
    schema_name: str = "intent_classification"


class SuggestionRequest(BaseModel):
    call_id: str | None = None
    transcript_segment: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSnippetCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    category: str = "general"


class NextBestActionRequest(BaseModel):
    call_id: str
    call_duration_seconds: int = 0
    current_intent: str | None = None
    sentiment: str = "neutral"
    agent_id: str | None = None


class LineageEntryCreate(BaseModel):
    source_table: str = Field(..., max_length=100)
    source_id: str = Field(..., max_length=100)
    target_table: str = Field(..., max_length=100)
    target_id: str = Field(..., max_length=100)
    operation: str = Field(default="transform", max_length=50)
    column_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LineageQuery(BaseModel):
    table: str
    record_id: str


class SMSSendRequest(BaseModel):
    to_number: str = Field(..., min_length=1, max_length=20)
    message: str = Field(..., min_length=1, max_length=1600)
    template_id: str | None = None


class SMSTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    body: str = Field(..., min_length=1, max_length=1600)


class ChatSessionCreate(BaseModel):
    visitor_id: str
    visitor_name: str | None = None
    visitor_email: str | None = None
    initial_message: str | None = None


class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    sender_type: str = Field(default="visitor", pattern=r"^(visitor|agent|system)$")
    sender_name: str | None = None


# ── Enterprise Polish DTOs ────────────────────────────────────────

class FailoverTestResult(BaseModel):
    id: str
    primary: str
    secondary: str
    failover_success: bool
    failover_time_ms: float
    fallback_success: bool
    total_test_time_ms: float
    timestamp: str


class FailoverStatus(BaseModel):
    primary_provider: str
    secondary_provider: str
    primary_healthy: bool
    secondary_healthy: bool
    last_test_at: str | None
    auto_test_enabled: bool


class ConversationQualityResult(BaseModel):
    rubric_name: str
    criteria_scores: dict[str, int]
    total_score: int
    max_possible: int
    percentage: float
    rating: str


class QualityScoreResponse(BaseModel):
    id: str
    tenant_id: str
    agent_id: str | None
    call_id: str | None
    transcript_hash: str | None
    rubric_name: str
    total_score: float
    criteria_scores: dict
    created_at: datetime


class APIVersionResponse(BaseModel):
    version: str
    status: str
    release_date: str
    sunset_date: str | None
    changelog: str | None
    migration_notes: str | None


class MigrationGuideResponse(BaseModel):
    from_version: str
    to_version: str
    from_status: str
    to_status: str
    migration_notes: str
    breaking_changes: list[str]


class CustomerPortalData(BaseModel):
    customer_id: str
    call_history: list[dict]
    invoices: list[dict]
    csat_scores: list[dict]
    average_csat: float
    preferences: dict


class ComplaintCreate(BaseModel):
    customer_id: str
    subject: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1)


class ComplaintResponse(BaseModel):
    id: str
    customer_id: str
    subject: str
    description: str
    status: str
    created_at: str


class CallbackSchedule(BaseModel):
    customer_id: str
    preferred_time: str
    reason: str


class CallbackResponse(BaseModel):
    id: str
    customer_id: str
    preferred_time: str
    reason: str
    status: str
    created_at: str


# ── WFM Metrics DTOs ─────────────────────────────────────────────

class AHTTrackRequest(BaseModel):
    call_id: str
    agent_id: str
    duration_seconds: int


class FCRTrackRequest(BaseModel):
    call_id: str
    customer_id: str
    resolved: bool
    follow_up_call_id: str | None = None


class CSATTrackRequest(BaseModel):
    call_id: str
    customer_id: str
    rating: int = Field(..., ge=1, le=5)


class NPSTrackRequest(BaseModel):
    call_id: str
    customer_id: str
    score: int = Field(..., ge=0, le=10)


class CourseCreateRequest(BaseModel):
    title: str
    description: str | None = None
    modules: list[dict] = []
    duration_hours: float = 0


class CoachingCreateRequest(BaseModel):
    agent_id: str
    coach_id: str
    focus_area: str
    notes: str | None = None


# ── Business Continuity DTOs ─────────────────────────────────────

class FailoverTestRequest(BaseModel):
    service: str


class ChaosRunRequest(BaseModel):
    target: str
    fault_type: str
    duration_seconds: int = 30


class ContractCreateRequest(BaseModel):
    vendor: str
    terms: str
    renewal_date: str
    cost: float | None = None


class BackupChannelCreateRequest(BaseModel):
    channel_type: str
    config: dict


# ── Platform Ops DTOs ─────────────────────────────────────────────

class BrandingConfig(BaseModel):
    company_name: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    favicon_url: str | None = None


class BrandingResponse(BaseModel):
    id: str
    tenant_id: str
    company_name: str | None
    logo_url: str | None
    primary_color: str
    secondary_color: str
    favicon_url: str | None
    created_at: datetime
    updated_at: datetime


class CustomDomainResponse(BaseModel):
    id: str
    tenant_id: str
    domain: str
    ssl_status: str
    verified: bool
    created_at: datetime


class OnboardingProgressResponse(BaseModel):
    tenant_id: str
    steps_completed: list[str]
    current_step: str
    completed: bool


class SetupProgressResponse(BaseModel):
    percent_complete: int
    completed_steps: list[str]
    current_step: str
    remaining_steps: list[str]
    onboarding_complete: bool


class QuickstartStep(BaseModel):
    id: str
    label: str
    done: bool
    link: str


class QuickstartGuideResponse(BaseModel):
    tenant_id: str
    steps: list[QuickstartStep]


class HealthCheckResponse(BaseModel):
    tenant_id: str
    overall_status: str
    checks: dict[str, dict]


class ProvisionNumberResponse(BaseModel):
    phone_number: str
    area_code: str
    status: str
    message: str


class SignupResponse(BaseModel):
    tenant_id: str
    api_key: str
    slug: str
    company_name: str
    email: str


# ── AI Platform DTOs ───────────────────────────────────────────────

class TrainingJobCreate(BaseModel):
    name: str
    model_base: str = "llama-3.1-8b"
    hyperparams: dict[str, Any] = Field(default_factory=lambda: {"epochs": 3, "learning_rate": 2e-4, "batch_size": 8})


class ModelRegister(BaseModel):
    name: str
    version: str
    model_type: str = "intent"
    config: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class VoiceProfileCreate(BaseModel):
    speaker_name: str
    features: dict[str, Any] = Field(default_factory=dict)


class EmotionDetectRequest(BaseModel):
    call_id: str | None = None
    audio_features: dict[str, Any] = Field(default_factory=dict)


class DatasetCreate(BaseModel):
    name: str
    recipe_type: str = "dialogue"
    source_start_date: str | None = None
    source_end_date: str | None = None


class TurnLabel(BaseModel):
    turn_id: str
    label_type: str = "intent"
    label_value: str
    confidence: float = 1.0
    notes: str | None = None


class ExternalJobSubmit(BaseModel):
    dataset_id: str
    model_name: str
    hyperparams: dict[str, Any] = Field(default_factory=dict)
    provider: str = "modal"


class EvalMetricsIngest(BaseModel):
    model_id: str
    version: str
    metrics: dict[str, Any]


# ── CDP DTOs ─────────────────────────────────────────────────────

class CustomerUnifyRequest(BaseModel):
    phone: str | None = None
    email: str | None = None
    external_id: str | None = None
    name: str | None = None
    metadata: dict = {}


class CustomerProfileResponse(BaseModel):
    id: str
    tenant_id: str
    external_id: str | None
    phone: str | None
    email: str | None
    name: str | None
    tags: list = []
    first_seen_at: str | None
    last_seen_at: str | None
    created_at: str | None


class TagRequest(BaseModel):
    tags: list[str]


class SegmentCreateRequest(BaseModel):
    name: str
    criteria: dict


class SegmentResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    criteria: dict
    member_count: int
    created_at: str


class RFMResponse(BaseModel):
    recency_days: int
    frequency: int
    monetary_seconds: int
    r_score: int
    f_score: int
    m_score: int
    rfm_segment: str


class TimelineEntry(BaseModel):
    type: str
    timestamp: str | None
    channel: str | None = None
    interaction_type: str | None = None
    sentiment: str | None = None
    summary: str | None = None
    rating: int | None = None
    feedback: str | None = None


class CohortAnalysisResponse(BaseModel):
    cohort_period: str
    metric: str
    cohorts: list[dict]


class ChurnRiskResponse(BaseModel):
    customer_id: str
    churn_risk: str
    churn_probability: float
    factors: list[str]
    days_since_last_interaction: int | None = None
    interaction_frequency: float | None = None
    negative_sentiment_ratio: float | None = None


class LTVResponse(BaseModel):
    customer_id: str
    estimated_ltv: float
    total_interactions: int
    total_minutes: float
    estimated_revenue: float
    monthly_value: float


class AggregateMetricsResponse(BaseModel):
    period: str
    total_customers: int
    active_customers: int
    new_customers: int
    returning_customers: int
    avg_lifetime_calls: float
    total_lifetime_calls: int


# ── Vertical Templates DTOs ──────────────────────────────────────

class VerticalTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    compliance: list[str]
    intent_count: int
    script_count: int


class VerticalConfigResponse(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    compliance: list[str]
    intents: list[str]
    script_templates: list[str]
    compliance_rules: dict
    routing_config: dict
    required_integrations: list[str]


class VerticalComplianceResponse(BaseModel):
    vertical_id: str
    name: str
    compliance_standards: list[str]
    compliance_rules: dict


class VerticalScriptsResponse(BaseModel):
    vertical_id: str
    name: str
    script_templates: list[str]
    intents: list[str]


# ── Developer Platform DTOs ─────────────────────────────────────

class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: ["all"])
    expires_in_days: int = Field(default=365, ge=1, le=3650)


class APIKeyResponse(BaseModel):
    id: str
    name: str
    masked_key: str
    scopes: list[str]
    created_at: str | None = None
    last_used_at: str | None = None
    expires_at: str | None = None
    is_active: bool = True


class APIKeyCreatedResponse(APIKeyResponse):
    full_key: str


class APIKeyUsageResponse(BaseModel):
    key_id: str
    name: str
    created_at: str | None = None
    last_used_at: str | None = None
    is_active: bool
    period: str
    call_count: int = 0


class WebhookRegisterRequest(BaseModel):
    url: str = Field(..., max_length=2000)
    events: list[str] = Field(..., min_length=1)
    secret: str | None = None


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    secret: str | None = None
    is_active: bool
    created_at: str | None = None


class WebhookDeliveryLogResponse(BaseModel):
    id: str
    webhook_id: str
    event_type: str
    status: str
    request_body: str | None = None
    response_status: int | None = None
    response_body: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    created_at: str | None = None


class EventCatalogEntry(BaseModel):
    description: str
    schema: dict[str, str]


class EventCatalogResponse(BaseModel):
    events: dict[str, EventCatalogEntry]
