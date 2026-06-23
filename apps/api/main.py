"""
AetherDesk Call Center SaaS Platform - FastAPI Application
============================================================
Digital call center with agent rental, privacy-focused, HIPAA/GDPR compliant.
Uses Fonoster + FreeSWITCH instead of Twilio for cost efficiency.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

load_dotenv()

from fastapi.responses import JSONResponse

from apps.api.middleware.audit import AuditMiddleware
from apps.api.middleware.security import SecurityHeadersMiddleware
from apps.api.services.connection_pool import http_pool
from apps.api.routers import (
    agent,
    auth,
    billing,
    campaign,
    engine,
    leads,
    onboarding,
    protocols,
    realtime,
    saas,
    scripts,
    voice,
    voice_cloning,
    webhooks_twilio,
)
from apps.api.routers.agent import agent_cache
from apps.api.services.auth import (
    WebSocketAuthMiddleware,
    verify_api_key,
    verify_tenant_access,
)
from apps.api.services.database import (
    USE_POSTGRES,
    close_pg_pool,
    create_call_session,
    delete_agent_db,
    enqueue_call,
    get_agent_db,
    get_available_agents,
    get_billing_summary,
    get_call_session,
    get_pg_pool,
    get_tenant_db,
    get_usage_stats,
    init_pg_schema,
    log_audit_event,
    update_agent_db,
    update_agent_status,
)
from apps.api.services.database import (
    create_agent as create_agent_db,
)
from apps.api.services.database import (
    create_tenant as create_tenant_db,
)
from apps.api.services.database import (
    list_agents as list_agents_db,
)
from apps.api.services.database import (
    list_calls as list_calls_db,
)
from apps.api.services.database import (
    update_call_status as db_update_call_status,
)
from apps.api.services.db_errors import (
    DatabaseError,
    NotFoundError,
    PoolNotAvailableError,
)
from apps.api.services.rate_limit import RateLimitMiddleware

# =============================================================================
# Fonster HTTP Client (replaces SDK)
# =============================================================================


def get_voice_client() -> Any | None:
    """Create the best available voice client.

    Preference order:
      1. Fonoster (Docker/FreeSWITCH) — production
      2. Twilio (cloud API, no Docker needed) — dev/staging
      3. MockVoiceClient — last resort, logs calls (dev/demo)
    """
    fonster_key = os.getenv("FONOSTER_API_KEY", "")
    if fonster_key and fonster_key != "your-fonoster-api-key":
        try:
            from apps.api.fonoster_client import FonosterHTTPClient as FC
            fonster_url = os.getenv("FONOSTER_URL", "http://aetherdesk-fonoster:50062")
            fonster_secret = os.getenv("FONOSTER_API_SECRET", "")
            client = FC(base_url=fonster_url, api_key=fonster_key, api_secret=fonster_secret)
            logging.info("Using Fonoster voice client")
            return client
        except Exception as e:
            logging.debug(f"Fonoster client failed: {e}")

    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    if twilio_sid:
        try:
            from apps.api.twilio_client import TwilioVoiceClient
            client = TwilioVoiceClient()
            logging.info("Using Twilio voice client")
            return client
        except Exception as e:
            logging.error(f"Twilio client failed: {e}")

    try:
        from apps.api.mock_voice_client import MockVoiceClient
        logging.warning("No real voice client — MockVoiceClient active (calls logged, not placed)")
        return MockVoiceClient()
    except Exception:
        logging.error("Failed to create MockVoiceClient")
        return None


# =============================================================================
# Configuration
# =============================================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    None
)
if not DATABASE_URL:
    if os.getenv("USE_POSTGRES", "false").lower() == "true":
        raise RuntimeError("DATABASE_URL environment variable must be set for production.")
    else:
        logger.warning("database_url_not_set_using_sqlite")
REDIS_URL = os.getenv("REDIS_URL", "redis://aetherdesk-redis:6379")
FONOSTER_URL = os.getenv("FONOSTER_URL", "http://aetherdesk-fonoster:50062")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    if os.getenv("USE_POSTGRES", "false").lower() == "true":
        raise RuntimeError("ENCRYPTION_KEY environment variable must be set for production.")
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    if os.getenv("USE_POSTGRES", "false").lower() == "true":
        raise RuntimeError("JWT_SECRET environment variable must be set for production.")
SALT_ROUNDS = int(os.getenv("SALT_ROUNDS", "12"))

# =============================================================================
# Logging (HIPAA-compliant - no PHI in logs)
# =============================================================================
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

if LOG_FORMAT == "json":
    import structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        handlers=[logging.StreamHandler()],
    )
else:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()],
    )
logger = logging.getLogger(__name__)

# =============================================================================
# Lifespan Manager
# =============================================================================
fonster_client = None
redis_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global fonster_client, redis_client

    logger.info("Initializing AetherDesk services...")

    # Initialize database schema (PostgreSQL or SQLite)
    try:
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                await init_pg_schema(pool)
                logger.info("PostgreSQL schema ready")
        else:
            from apps.api.services.database import init_sqlite_schema
            init_sqlite_schema()
            logger.info("SQLite schema ready")
    except Exception as e:
        logger.error(f"Database init failed: {e}")

    # Redis
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        app.state.redis = redis_client
        max_retries = 5
        for attempt in range(max_retries):
            try:
                await redis_client.ping()
                logger.info("Redis connected")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(f"Redis connection attempt {attempt+1} failed, retrying in {wait}s: {e}")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Redis connection failed after {max_retries} attempts: {e}")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")

    # Voice Client (Fonoster > Twilio > Mock)
    fonster_client = get_voice_client()
    if fonster_client:
        logger.info("Voice client initialized")
    else:
        logger.warning("Voice client not available - running in dev mode")

    # Agent cache cleanup background task
    cleanup_task = asyncio.create_task(agent_cache.start_cleanup_loop())

    # DI service initialization — single shared instances
    from apps.api.services.transcript_store import TranscriptStore
    from apps.api.services.voice_profile_store import VoiceProfileStore

    app.state.transcript_store = TranscriptStore()
    app.state.voice_profile_store = VoiceProfileStore()

    # Wire DI instances into router modules (replaces module-level singletons)
    from apps.api.routers import realtime as realtime_router
    realtime_router._default_store = app.state.transcript_store
    realtime_router.manager._store = app.state.transcript_store

    from apps.api.routers import voice_cloning as vc_router
    vc_router._profile_store = app.state.voice_profile_store

    # Start stale transcript cleanup
    transcript_cleanup_task = asyncio.create_task(app.state.transcript_store.cleanup_stale_loop())

    # Start data retention cleanup (GDPR compliance — purge expired recordings, sessions)
    async def _retention_cleanup_loop():
        while True:
            await asyncio.sleep(3600)
            try:
                retention_days = int(os.getenv("CALL_RECORDING_RETENTION_DAYS", "365"))
                if USE_POSTGRES:
                    pool = await get_pg_pool()
                    if pool:
                        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
                        await pool.execute(
                            "UPDATE recordings SET pii_redacted = TRUE, retention_until = NOW() WHERE created_at < $1 AND pii_redacted = FALSE",
                            cutoff
                        )
                        logger.info("retention_cleanup_completed", purged_before=cutoff.isoformat())
                else:
                    import datetime as dt

                    from apps.api.services.database import _get_sqlite_conn
                    conn = _get_sqlite_conn()
                    try:
                        cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(days=retention_days)).isoformat()
                        conn.execute(
                            "UPDATE recordings SET pii_redacted = 1, retention_until = ? WHERE created_at < ? AND pii_redacted = 0",
                            (dt.datetime.now(dt.UTC).isoformat(), cutoff)
                        )
                        conn.commit()
                        logger.info("retention_cleanup_completed")
                    finally:
                        conn.close()
            except Exception as e:
                logger.error("retention_cleanup_failed", error=str(e))

    retention_task = asyncio.create_task(_retention_cleanup_loop())

    yield

    logger.info("Shutting down AetherDesk services...")
    for bg_task in [cleanup_task, transcript_cleanup_task, retention_task]:
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
    if fonster_client:
        await fonster_client.close()
    if redis_client:
        await redis_client.close()
    await http_pool.close()
    await close_pg_pool()


async def safe_redis_publish(channel: str, message: str) -> bool:
    """Publish to Redis with automatic reconnection on failure."""
    global redis_client
    try:
        if not redis_client:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            app.state.redis = redis_client
        await redis_client.publish(channel, message)
        return True
    except Exception as e:
        logger.warning(f"redis_publish_failed_attempting_reconnect: channel={channel} error={e}")
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            app.state.redis = redis_client
            await redis_client.ping()
            await redis_client.publish(channel, message)
            logger.info("redis_reconnected")
            return True
        except Exception as ex:
            logger.error(f"redis_reconnect_failed: {ex}")
            return False


# =============================================================================
# FastAPI Application
# =============================================================================
app = FastAPI(
    title="AetherDesk Call Center API",
    description=(
        "Digital call center SaaS platform with AI-powered agents. "
        "Uses Fonoster + FreeSWITCH instead of Twilio for privacy and cost efficiency."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

@app.exception_handler(NotFoundError)
async def not_found_handler(request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"success": False, "error": exc.message, "code": "not_found"},
    )


@app.exception_handler(PoolNotAvailableError)
async def pool_error_handler(request, exc: PoolNotAvailableError):
    return JSONResponse(
        status_code=503,
        content={"success": False, "error": exc.message, "code": "service_unavailable"},
    )


@app.exception_handler(DatabaseError)
async def database_error_handler(request, exc: DatabaseError):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": exc.message, "code": "database_error"},
    )


cors_origin_env = os.getenv("CORS_ORIGIN", "http://127.0.0.1:3001,http://localhost:3001,https://app.aetherdesk.com")
cors_origins = [origin.strip() for origin in cors_origin_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice.router, prefix="/api/v1")
app.include_router(voice_cloning.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(realtime.router)
app.include_router(engine.router)
app.include_router(saas.router, prefix="/api/v1")
app.include_router(protocols.router)
app.include_router(campaign.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")
app.include_router(onboarding.router, prefix="/api/v1")
app.include_router(leads.router, prefix="/api/v1")
app.include_router(scripts.router, prefix="/api/v1")
app.include_router(webhooks_twilio.router)


# =============================================================================
# Auth Routes (must be after CORS, before middleware)
# =============================================================================

# =============================================================================
# Middleware (HIPAA/GDPR Compliance)
# =============================================================================

# Rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# HIPAA Audit Logging - must be after CORS, before routes
app.add_middleware(AuditMiddleware)

# WebSocket Authentication - must be after CORS, before routes
app.add_middleware(WebSocketAuthMiddleware)

# Security Headers - must be after CORS, before routes
app.add_middleware(SecurityHeadersMiddleware)

# =============================================================================
# Pydantic Models
# =============================================================================


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


# =============================================================================
# Security
# =============================================================================
security = HTTPBearer()


def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token signed with RS256."""
    from apps.api.services.jwt_utils import create_access_token as _create_rs256_token
    return _create_rs256_token(data, expires_delta)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Verify JWT token and return user payload"""
    from apps.api.services.jwt_utils import verify_access_token as _verify_rs256_token
    payload = _verify_rs256_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


# =============================================================================
# Health Check
# =============================================================================
@app.get("/api/v1/health", response_model=HealthCheck)
@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint with service status"""
    fonster_status = "unknown"
    db_status = "disconnected"

    if fonster_client:
        try:
            hc = await fonster_client.health_check()
            fonster_status = "healthy" if hc.get("healthy") else "unhealthy"
        except Exception:
            fonster_status = "disconnected"  # Health check — expected if Fonster is down

    try:
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                await pool.fetchval("SELECT 1")
                db_status = "connected"
    except Exception:
        db_status = "disconnected"  # Health check — expected if DB is unavailable

    overall = "healthy" if fonster_status == "healthy" and db_status == "connected" else "degraded"

    return HealthCheck(
        status=overall,
        timestamp=datetime.now(UTC),
        version="1.0.0",
        services={
            "fonster": fonster_status,
            "freeswitch": "connected",
            "redis": "connected" if redis_client else "disconnected",
            "database": db_status,
        },
        fonster_connected=fonster_status == "healthy",
        database_connected=db_status == "connected",
    )


# =============================================================================
# Tenant Management
# =============================================================================
@app.post("/api/v1/tenants", response_model=TenantResponse, status_code=201)
async def create_tenant_endpoint(tenant: TenantCreate, _=Depends(verify_api_key)):
    """Create a new tenant account with full setup"""
    import re
    slug = re.sub(r"[^a-z0-9-]", "", tenant.name.lower().replace(" ", "-"))[:50]

    # Create in database
    db_tenant = await create_tenant_db(
        name=tenant.name, slug=slug, email=tenant.email,
        phone=tenant.phone, plan_id=tenant.plan_id,
        settings={"maxConcurrentCalls": 10, "recordingRetention": 365,
                  "language": "en-US", "timezone": "America/New_York"},
        gdpr_consent=tenant.gdpr_consent,
    )
    actual_tenant_id = db_tenant["id"] if db_tenant else str(uuid.uuid4())

    # Create Fonster Voice Application for tenant
    if fonster_client:
        try:
            await fonster_client.create_application({
                "name": f"{tenant.name} Voice App",
                "type": "EXTERNAL",
                "endpoint": "tcp://aetherdesk-voice:50061",
                "speechToText": {
                    "productRef": "stt.deepgram",
                    "config": {"model": "nova-2", "languageCode": "en-US", "enablePunctuations": True}
                },
                "textToSpeech": {
                    "productRef": "tts.chatterbox",
                    "config": {"voice": "default", "emotion": "neutral"}
                },
                "intelligence": {
                    "productRef": "llm.groq",
                    "config": {"model": "llama-3.1-70b-versatile", "temperature": 0.7}
                },
            })
        except Exception as e:
            logger.warning(f"Fonster app creation failed (non-fatal): {e}")

    # Fetch plan name
    plan_name = "Starter"
    if db_tenant and db_tenant.get("plan_id"):
        pool = await get_pg_pool()
        if pool:
            try:
                plan = await pool.fetchrow("SELECT name FROM plans WHERE id = $1", db_tenant["plan_id"])
                if plan:
                    plan_name = plan["name"]
            except Exception:
                pass  # Best-effort plan name lookup, defaults to "Starter"

    return TenantResponse(
        id=actual_tenant_id,
        name=tenant.name,
        email=tenant.email,
        phone=tenant.phone,
        plan_name=plan_name,
        status="active",
        settings={
            "maxConcurrentCalls": 10,
            "recordingRetention": 365,
            "language": "en-US",
            "timezone": "America/New_York",
        },
        gdpr_consent=tenant.gdpr_consent,
        created_at=datetime.now(UTC),
    )


@app.get("/api/v1/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, _=Depends(verify_tenant_access)):
    """Get tenant details"""
    db_tenant = await get_tenant_db(tenant_id)
    if not db_tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return TenantResponse(
        id=db_tenant["id"],
        name=db_tenant["name"],
        email=db_tenant["email"],
        phone=db_tenant.get("phone"),
        plan_name="Starter",
        status="active" if db_tenant.get("is_active") else "inactive",
        settings=db_tenant.get("settings") or {},
        gdpr_consent=db_tenant.get("gdpr_consent", False),
        created_at=db_tenant.get("created_at") or datetime.now(UTC),
    )


# =============================================================================
# Agent Management
# =============================================================================
@app.post("/api/v1/tenants/{tenant_id}/agents", response_model=AgentResponse, status_code=201)
async def create_agent(tenant_id: str, agent: AgentCreate, _=Depends(verify_tenant_access)):
    """Create a new agent with SIP extension and Fonster integration"""
    db_agent = await create_agent_db(
        tenant_id=tenant_id,
        name=agent.name,
        display_name=agent.display_name,
        agent_type=agent.agent_type,
        skills=agent.skills,
        config=agent.config,
    )
    agent_id = db_agent["id"]
    sip_extension = db_agent["sip_extension"]

    # Create Fonster Voice Application for agent
    if fonster_client:
        try:
            await fonster_client.create_application({
                "name": f"Agent-{agent.name}",
                "type": "EXTERNAL",
                "endpoint": "tcp://aetherdesk-voice:50061",
                "speechToText": {
                    "productRef": "stt.deepgram",
                    "config": {"languageCode": "en-US"}
                },
                "textToSpeech": {
                    "productRef": "tts.chatterbox",
                    "config": {"voice": "default", "emotion": "neutral"}
                },
            })
        except Exception as e:
            logger.warning(f"Fonster agent app creation failed (non-fatal): {e}")

    return AgentResponse(
        id=agent_id,
        tenant_id=tenant_id,
        name=agent.name,
        display_name=agent.display_name or agent.name,
        agent_type=agent.agent_type,
        status="offline",
        skills=agent.skills,
        sip_extension=sip_extension,
        total_calls=0,
        total_talk_time_seconds=0,
        avg_rating=0.0,
        created_at=datetime.now(UTC),
    )


@app.get("/api/v1/tenants/{tenant_id}/agents")
async def list_agents(tenant_id: str, _=Depends(verify_tenant_access)):
    """List all agents for a tenant with status"""
    agents = await list_agents_db(tenant_id)
    result = []
    for a in agents:
        skills_raw = a.get("skills", "[]")
        if isinstance(skills_raw, str):
            try:
                skills_parsed = json.loads(skills_raw)
            except json.JSONDecodeError:
                skills_parsed = []
        else:
            skills_parsed = skills_raw or []

        result.append(AgentResponse(
            id=a["id"],
            tenant_id=a["tenant_id"],
            name=a["name"],
            display_name=a.get("display_name") or a["name"],
            agent_type=a.get("agent_type", "ai"),
            status=a.get("status", "offline"),
            skills=skills_parsed,
            sip_extension=a.get("sip_extension"),
            total_calls=a.get("total_calls", 0) or 0,
            total_talk_time_seconds=a.get("total_talk_time_seconds", 0) or 0,
            avg_rating=float(a.get("avg_rating", 0) or 0),
            created_at=a.get("created_at") or datetime.now(UTC),
        ))
    return result


@app.get("/api/v1/tenants/{tenant_id}/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(tenant_id: str, agent_id: str, _=Depends(verify_tenant_access)):
    """Get agent details"""
    agent = await get_agent_db(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    skills_raw = agent.get("skills", "[]")
    if isinstance(skills_raw, str):
        try:
            skills_parsed = json.loads(skills_raw)
        except json.JSONDecodeError:
            skills_parsed = []
    else:
        skills_parsed = skills_raw or []

    return AgentResponse(
        id=agent["id"],
        tenant_id=agent["tenant_id"],
        name=agent["name"],
        display_name=agent.get("display_name") or agent["name"],
        agent_type=agent.get("agent_type", "ai"),
        status=agent.get("status", "offline"),
        skills=skills_parsed,
        sip_extension=agent.get("sip_extension"),
        total_calls=agent.get("total_calls", 0) or 0,
        total_talk_time_seconds=agent.get("total_talk_time_seconds", 0) or 0,
        avg_rating=float(agent.get("avg_rating", 0) or 0),
        created_at=agent.get("created_at") or datetime.now(UTC),
    )


@app.put("/api/v1/tenants/{tenant_id}/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(tenant_id: str, agent_id: str, agent: AgentCreate, _=Depends(verify_tenant_access)):
    """Update an agent's configuration"""
    updated = await update_agent_db(
        agent_id=agent_id, tenant_id=tenant_id,
        name=agent.name, display_name=agent.display_name,
        agent_type=agent.agent_type, skills=agent.skills,
        config=agent.config,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Agent not found")

    skills_raw = updated.get("skills", "[]")
    if isinstance(skills_raw, str):
        try:
            skills_parsed = json.loads(skills_raw)
        except json.JSONDecodeError:
            skills_parsed = []
    else:
        skills_parsed = skills_raw or []

    return AgentResponse(
        id=updated["id"], tenant_id=updated["tenant_id"],
        name=updated["name"],
        display_name=updated.get("display_name") or updated["name"],
        agent_type=updated.get("agent_type", "ai"),
        status=updated.get("status", "offline"),
        skills=skills_parsed,
        sip_extension=updated.get("sip_extension"),
        total_calls=updated.get("total_calls", 0) or 0,
        total_talk_time_seconds=updated.get("total_talk_time_seconds", 0) or 0,
        avg_rating=float(updated.get("avg_rating", 0) or 0),
        created_at=updated.get("created_at") or datetime.now(UTC),
    )


@app.delete("/api/v1/tenants/{tenant_id}/agents/{agent_id}")
async def delete_agent(tenant_id: str, agent_id: str, _=Depends(verify_tenant_access)):
    """Delete an agent"""
    deleted = await delete_agent_db(agent_id, tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"success": True, "agent_id": agent_id}


@app.patch("/api/v1/agents/{agent_id}/status")
async def handle_update_agent_status(
    agent_id: str,
    status: AgentStatusUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update agent status with real-time WebSocket notification"""
    result = await update_agent_status(agent_id, status.status, status.session_ref)

    # Ownership check: agent must belong to the token's tenant
    agent = await get_agent_db(agent_id)
    if agent and agent.get("tenant_id") != current_user.get("tenant_id"):
        raise HTTPException(
            status_code=403,
            detail="Access denied: agent does not belong to this tenant",
        )

    # Publish status change to Redis for real-time updates
    await safe_redis_publish(
        f"agent:{agent_id}:status",
        json.dumps({
            "agent_id": agent_id,
            "status": status.status,
            "session_ref": status.session_ref,
            "timestamp": datetime.now(UTC).isoformat(),
        })
    )

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Agent not found"))

    return result


# =============================================================================
# Call Management with Fonster Integration
# =============================================================================
@app.post("/api/v1/calls", response_model=CallResponse, status_code=201)
async def create_call(call: CallCreate, tenant_id: str = Depends(verify_tenant_access)):
    """Create and initiate a call via Fonster"""
    call_id = str(uuid.uuid4())

    # Find available agent or queue
    agent_id = call.agent_id

    if agent_id:
        agent = await get_agent_db(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent.get("sip_extension", "30001")
        await create_call_session(
            tenant_id=tenant_id,
            agent_id=agent_id,
            caller_number=call.caller_number,
            called_number=call.called_number or call.caller_number,
            call_direction=call.call_direction,
            intent_detected=call.intent,
            sip_call_id=call_id,
        )
    else:
        # Auto-route: find available agent by intent
        skills = [call.intent] if call.intent else None
        available = await get_available_agents(tenant_id, skills)
        if available:
            agent_id = available[0]["id"]
            await create_call_session(
                tenant_id=tenant_id,
                agent_id=agent_id,
                caller_number=call.caller_number,
                called_number=call.called_number or call.caller_number,
                call_direction=call.call_direction,
                intent_detected=call.intent,
                sip_call_id=call_id,
            )
        else:
            # No agents available, enqueue
            await enqueue_call(tenant_id, call.caller_number, call.intent)
            await create_call_session(
                tenant_id=tenant_id,
                agent_id=None,
                caller_number=call.caller_number,
                called_number=call.called_number or call.caller_number,
                call_direction=call.call_direction,
                intent_detected=call.intent,
                sip_call_id=call_id,
            )

    # Create voice application in Fonster
    if fonster_client:
        try:
            await fonster_client.create_application({
                "name": f"Call-{call_id}",
                "type": "EXTERNAL",
                "endpoint": "tcp://aetherdesk-voice:50061",
            })
        except Exception as e:
            logger.warning(f"Fonster call app creation failed: {e}")

    return CallResponse(
        id=call_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        caller_number=call.caller_number,
        call_direction=call.call_direction,
        call_status="initiated",
        duration_seconds=0,
        cost=0.0,
        sip_call_id=call_id,
        intent_detected=call.intent,
        created_at=datetime.now(UTC),
    )


@app.post("/api/v1/calls/{call_id}/action")
async def call_action(
    call_id: str,
    action: CallAction,
    tenant_id: str = Depends(verify_tenant_access),
):
    """Perform call action via Fonster"""
    call_session = await get_call_session(call_id)
    if not call_session:
        raise HTTPException(status_code=404, detail="Call not found")

    # IDOR protection: confirm call belongs to requesting tenant
    if call_session.get("tenant_id") != tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: call does not belong to this tenant",
        )

    await log_audit_event(
        tenant_id=call_session.get("tenant_id", ""),
        user_id="system",
        action=f"call_{action.action}",
        resource_type="call",
        resource_id=call_id,
        new_values={"action": action.action, "target": action.target},
    )

    if not fonster_client:
        return {"success": True, "action": action.action, "note": "Fonster not connected (dev mode)"}

    if action.action == "answer":
        result = await fonster_client.answer_call(call_id)
    elif action.action == "hangup":
        result = await fonster_client.hangup_call(call_id)
    elif action.action == "mute":
        result = await fonster_client.mute_call(call_id)
    elif action.action == "hold":
        result = await fonster_client.hold_call(call_id)
    elif action.action == "unmute":
        result = await fonster_client.unmute_call(call_id)
    elif action.action == "unhold":
        result = await fonster_client.unhold_call(call_id)
    elif action.action == "transfer":
        if not action.target:
            raise HTTPException(status_code=400, detail="Transfer target required")
        result = await fonster_client.transfer_call(call_id, action.target)
    elif action.action == "gather":
        hints = action.data.get("hints", ["sales", "support", "billing", "technical"]) if action.data else []
        result = await fonster_client.gather_speech(call_id, hints=hints, language="en-US")
    elif action.action == "say":
        text = action.data.get("text", "") if action.data else ""
        result = await fonster_client.say_text(call_id, text)
    elif action.action == "play":
        url = action.data.get("url", "") if action.data else ""
        result = await fonster_client.play_audio(call_id, url)
    elif action.action == "record":
        record_action = action.data.get("action", "start") if action.data else "start"
        result = await fonster_client.record_call(call_id, record_action)
    elif action.action == "dtmf":
        digits = action.data.get("digits", "") if action.data else ""
        result = await fonster_client.send_dtmf(call_id, digits)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    return result


@app.get("/api/v1/calls/{call_id}", response_model=CallResponse)
async def get_call(call_id: str, tenant_id: str = Depends(verify_tenant_access)):
    """Get call details"""
    call = await get_call_session(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    return CallResponse(
        id=call["id"],
        tenant_id=call["tenant_id"],
        agent_id=call.get("agent_id"),
        caller_number=call["caller_number"],
        call_direction=call.get("call_direction", "inbound"),
        call_status=call.get("call_status", "initiated"),
        duration_seconds=call.get("duration_seconds", 0) or 0,
        cost=float(call.get("total_cost", 0) or 0),
        sip_call_id=call.get("sip_call_id"),
        intent_detected=call.get("intent_detected"),
        created_at=call.get("created_at") or datetime.now(UTC),
    )


@app.get("/api/v1/calls")
async def list_calls(
    tenant_id: str = Depends(verify_tenant_access),
    status: str | None = None,
):
    """List calls for a tenant"""
    calls = await list_calls_db(tenant_id, status)
    return [
        CallResponse(
            id=c["id"],
            tenant_id=c["tenant_id"],
            agent_id=c.get("agent_id"),
            caller_number=c["caller_number"],
            call_direction=c.get("call_direction", "inbound"),
            call_status=c["call_status"],
            duration_seconds=c.get("duration_seconds", 0) or 0,
            cost=float(c.get("total_cost", 0) or 0),
            sip_call_id=c.get("sip_call_id"),
            intent_detected=c.get("intent_detected"),
            created_at=c.get("created_at") or datetime.now(UTC),
        )
        for c in calls
    ]


# =============================================================================
# Webhook Handler for Fonster Events
# =============================================================================
@app.post("/api/v1/webhooks/fonster")
async def fonster_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_fonoster_signature: str = Header(default=None),
):
    """Handle Fonster call events (call.answered, call.completed, call.failed)"""
    # HMAC signature verification
    fonster_webhook_secret = os.getenv("FONOSTER_WEBHOOK_SECRET")
    if fonster_webhook_secret and x_fonoster_signature:
        raw_body = await request.body()
        expected_sig = hmac.new(
            fonster_webhook_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, x_fonoster_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    elif fonster_webhook_secret and not x_fonoster_signature:
        # Secret is configured but no signature sent — reject in non-dev mode
        if os.getenv("APP_ENV", "development") == "production":
            raise HTTPException(status_code=401, detail="Missing webhook signature")

    payload = await request.json()
    event_type = payload.get("event_type")
    call_id = payload.get("call_id")
    session_ref = payload.get("session_ref")

    logger.info(f"Fonster webhook: {event_type} for call {call_id}")

    if event_type == "call.answered":
        background_tasks.add_task(handle_fonster_webhook, call_id, "active", session_ref)
    elif event_type == "call.completed":
        background_tasks.add_task(handle_fonster_webhook, call_id, "completed")
    elif event_type == "call.failed":
        background_tasks.add_task(handle_fonster_webhook, call_id, "failed")

    return {"status": "ok"}


async def handle_fonster_webhook(call_id: str, status: str, session_ref: str = None):
    """Update call status in DB and notify via WebSocket/Redis"""
    logger.info(f"Call {call_id} status updated to {status}")

    try:
        await db_update_call_status(call_id, status)
    except Exception as e:
        logger.error(f"Call status DB update failed: {e}")

    await safe_redis_publish(
        f"call:{call_id}:status",
        json.dumps({
            "call_id": call_id,
            "status": status,
            "session_ref": session_ref,
            "timestamp": datetime.now(UTC).isoformat(),
        })
    )


# =============================================================================
# Usage Analytics
# =============================================================================
@app.get("/api/v1/usage", response_model=UsageResponse)
async def get_usage(
    tenant_id: str = Query(default="TENANT-001", description="Tenant ID"),
    x_api_key: str = Header(default="dev-api-key"),
    period_start: datetime = Query(default=None),
    period_end: datetime = Query(default=None),
    _=Depends(verify_tenant_access),
):
    """Get usage analytics for a tenant"""
    # Use verify_tenant_access for authorization

    # Default to last 7 days if not specified
    now = datetime.now(UTC)
    if period_start is None:
        period_start = now - timedelta(days=7)
    if period_end is None:
        period_end = now

    stats = await get_usage_stats(tenant_id)

    # Guard against division by zero
    active = stats.get("active_agents", 0) or 0
    avg_duration = (
        round(stats["total_minutes"] / active, 2)
        if active > 0 else 0.0
    )

    pool = await get_pg_pool()
    queue_depth = 0
    if pool:
        queue_depth = await pool.fetchval(
            "SELECT COUNT(*) FROM call_queue WHERE tenant_id = $1 AND status = 'waiting'",
            tenant_id
        )

    return UsageResponse(
        total_agents=stats["total_agents"],
        active_agents=stats["active_agents"],
        total_calls=stats["total_calls"],
        active_calls=stats["active_calls"],
        total_minutes=stats["total_minutes"],
        avg_call_duration=avg_duration,
        queue_depth=queue_depth,
        total_cost=stats["total_minutes"] * 0.015,
        by_agent=[],
        by_day=[],
    )


# =============================================================================
# Billing
# =============================================================================
@app.get("/api/v1/billing")
async def get_billing(
    tenant_id: str = Query(default="TENANT-001", description="Tenant ID"),
    x_api_key: str = Header(default="dev-api-key"),
    period_start: datetime = Query(default=None),
    period_end: datetime = Query(default=None),
    _=Depends(verify_tenant_access),
):
    """Get billing summary"""
    # Use verify_tenant_access for authorization

    # Default to last 7 days if not specified
    now = datetime.now(UTC)
    if period_start is None:
        period_start = now - timedelta(days=7)
    if period_end is None:
        period_end = now

    summary = await get_billing_summary(tenant_id, period_start, period_end)
    return {
        "total_calls": summary["total_calls"],
        "total_minutes": summary["total_minutes"],
        "total_cost": summary["total_cost"],
        "currency": summary["currency"],
        "breakdown": {
            "per_minute": 0.015,
            "ai_minutes": summary["total_minutes"] * 0.5,
            "standard_minutes": summary["total_minutes"] * 0.5,
        },
    }


# =============================================================================
# Real-Time WebSocket
# =============================================================================
@app.websocket("/ws/calls/{tenant_id}")
async def websocket_calls(websocket: WebSocket, tenant_id: str, _=Depends(verify_tenant_access)):
    """WebSocket for real-time call status updates"""
    await websocket.accept()
    pubsub = None

    try:
        if redis_client:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(f"calls:{tenant_id}")

        while True:
            if pubsub:
                message = await pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    await websocket.send_json(json.loads(message["data"]))
            else:
                await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for tenant {tenant_id}")
    finally:
        if pubsub:
            await pubsub.unsubscribe(f"calls:{tenant_id}")


# =============================================================================
# Agent WebSocket
# =============================================================================
@app.websocket("/ws/agent/{agent_id}")
async def websocket_agent(websocket: WebSocket, agent_id: str):
    """WebSocket for agents to receive call assignments"""
    await websocket.accept()

    pubsub = None
    try:
        if redis_client:
            await redis_client.sadd("online_agents", agent_id)
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(f"agent:{agent_id}:assignments")

        while True:
            if pubsub:
                try:
                    message = await pubsub.get_message(timeout=30.0)

                    if message and message["type"] == "message":
                        call_data = json.loads(message["data"])
                        await websocket.send_json({
                            "type": "call_assignment",
                            **call_data
                        })
                except TimeoutError:
                    continue
            else:
                await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info(f"Agent {agent_id} disconnected")
    finally:
        if redis_client:
            await redis_client.srem("online_agents", agent_id)
        if pubsub:
            try:
                await pubsub.unsubscribe(f"agent:{agent_id}:assignments")
                await pubsub.close()
            except Exception:
                pass


# =============================================================================
# Utility Endpoints
# =============================================================================

# Sentry initialization
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.1)
        logger.info("Sentry initialized")
    except Exception as e:
        logger.warning(f"Sentry init failed: {e}")


@app.get("/api/v1/health/ready")
async def readiness_probe():
    """Kubernetes readiness probe"""
    return {"status": "ready"}


@app.get("/api/v1/health/live")
async def liveness_probe():
    """Kubernetes liveness probe"""
    return {"status": "alive"}


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    from apps.api.middleware.metrics import metrics_endpoint as metrics_handler
    return await metrics_handler()
