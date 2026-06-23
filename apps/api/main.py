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


load_dotenv()

from fastapi.responses import JSONResponse

from apps.api.middleware.audit import AuditMiddleware
from apps.api.middleware.security import SecurityHeadersMiddleware
from apps.api.services.connection_pool import http_pool
from apps.api.routers import (
    agent,
    agents,
    auth,
    billing,
    campaign,
    engine,
    health,
    leads,
    onboarding,
    protocols,
    realtime,
    saas,
    scripts,
    tenants,
    voice,
    voice_cloning,
    webhooks_twilio,
)
from apps.api.routers.agent import agent_cache
from apps.api.services.auth import (
    WebSocketAuthMiddleware,
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
    app.state.fonster_client = fonster_client
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
app.include_router(agents.router, prefix="/api/v1")
app.include_router(tenants.router)
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
app.include_router(health.router)


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

from apps.api.models.dto import (
    AgentCreate,
    AgentResponse,
    AgentStatusUpdate,
    CallAction,
    CallCreate,
    CallResponse,
    UsageResponse,
    WebhookConfig,
)



# =============================================================================
# Security
# =============================================================================


def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token signed with RS256."""
    from apps.api.services.jwt_utils import create_access_token as _create_rs256_token
    return _create_rs256_token(data, expires_delta)



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
