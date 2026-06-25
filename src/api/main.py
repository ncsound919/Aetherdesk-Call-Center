"""
AetherDesk Call Center SaaS Platform - FastAPI Application
============================================================
Digital call center with agent rental, privacy-focused, HIPAA/GDPR compliant.
Uses Fonoster + FreeSWITCH instead of Twilio for cost efficiency.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path so 'from api.xxx import yyy' works
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import (
    FastAPI,
)
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from fastapi.responses import JSONResponse

from api.middleware.audit import AuditMiddleware
from api.middleware.rbac import RBACMiddleware
from api.middleware.security import SecurityHeadersMiddleware
from api.routers import (
    agent,
    agents,
    ai_assist,
    ai_ops,
    ai_platform,
    auth,
    billing,
    business_continuity,
    calls,
    campaign,
    cdp,
    cx,
    data_governance,
    developer,
    engine,
    enterprise_polish,
    health,
    integrations,
    leads,
    metabase,
    omnichannel,
    onboarding,
    platform_ops,
    protocols,
    realtime,
    reliability,
    saas,
    scripts,
    security,
    security_hardening,
    tenants,
    usage,
    verticals,
    voice,
    voice_cloning,
    voice_quality,
    webhooks_fonster,
    webhooks_twilio,
    wfm,
    wfm_final,
)
from api.routers.agent import agent_cache
from api.services.auth import (
    WebSocketAuthMiddleware,
)
from api.services.connection_pool import http_pool
from api.services.database import (
    USE_POSTGRES,
    close_pg_pool,
    get_pg_pool,
    init_pg_schema,
)
from api.services.db_errors import (
    DatabaseError,
    NotFoundError,
    PoolNotAvailableError,
)
from api.services.rate_limit import RateLimitMiddleware

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
            from api.fonoster_client import FonosterHTTPClient as FC
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
            from api.twilio_client import TwilioVoiceClient
            client = TwilioVoiceClient()
            logging.info("Using Twilio voice client")
            return client
        except Exception as e:
            logging.error(f"Twilio client failed: {e}")

    try:
        from api.mock_voice_client import MockVoiceClient
        logging.warning("No real voice client — MockVoiceClient active (calls logged, not placed)")
        return MockVoiceClient()
    except Exception:
        logging.error("Failed to create MockVoiceClient")
        return None


# =============================================================================
# Configuration
# =============================================================================
logger = logging.getLogger(__name__)

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
            from api.services.database import init_sqlite_schema
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
        logger.info(f"Voice client initialized: {type(fonster_client).__name__}")
    else:
        logger.warning("Voice client not available - running in dev mode")

    # Agent cache cleanup background task
    cleanup_task = asyncio.create_task(agent_cache.start_cleanup_loop())

    # DI service initialization — single shared instances
    from api.services.transcript_store import TranscriptStore
    from api.services.voice_profile_store import VoiceProfileStore

    app.state.transcript_store = TranscriptStore()
    app.state.voice_profile_store = VoiceProfileStore()

    # Wire DI instances into router modules (replaces module-level singletons)
    from api.routers import realtime as realtime_router
    realtime_router._default_store = app.state.transcript_store
    realtime_router.manager._store = app.state.transcript_store

    from api.routers import voice_cloning as vc_router
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

                    from api.services.database import _get_sqlite_conn
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

    # Flush observability backends before shutdown
    try:
        from api.services.langfuse_client import flush as langfuse_flush
        langfuse_flush()
    except Exception:
        pass

    try:
        import sentry_sdk
        sentry_sdk.flush()
    except Exception:
        pass

    try:
        from api.services.analytics_client import shutdown as posthog_shutdown
        posthog_shutdown()
    except Exception:
        pass


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

# Attach Sentry FastAPI integration (must be after app creation)
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        sentry_sdk.setup_integrations(
            [FastApiIntegration(
                app=app,
                failed_request_status_codes={400, 401, 403, 404, 500},
            )],
            raise_server_exceptions=False,
        )
    except Exception as e:
        logger.warning("sentry_fastapi_integration_failed", error=str(e))

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
app.include_router(tenants.router, prefix="/api/v1")
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
app.include_router(webhooks_fonster.router)
app.include_router(calls.router, prefix="/api/v1")
app.include_router(health.router)
app.include_router(usage.router, prefix="/api/v1")
app.include_router(metabase.router)
app.include_router(wfm.router, prefix="/api/v1")
app.include_router(security.router, prefix="/api/v1")
app.include_router(voice_quality.router, prefix="/api/v1")
app.include_router(ai_ops.router, prefix="/api/v1")
app.include_router(cx.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
app.include_router(omnichannel.router, prefix="/api/v1")
app.include_router(ai_assist.router, prefix="/api/v1")
app.include_router(data_governance.router, prefix="/api/v1")
app.include_router(wfm_final.router, prefix="/api/v1")
app.include_router(business_continuity.router, prefix="/api/v1")
app.include_router(security_hardening.router, prefix="/api/v1")
app.include_router(reliability.router, prefix="/api/v1")
app.include_router(enterprise_polish.router, prefix="/api/v1")
app.include_router(ai_platform.router, prefix="/api/v1")
app.include_router(developer.router, prefix="/api/v1")
app.include_router(cdp.router, prefix="/api/v1")
app.include_router(verticals.router, prefix="/api/v1")
app.include_router(platform_ops.router, prefix="/api/v1")

# Overlay 365 public signup (no prefix - already has /api/v1/signup)
from api.routers.signup_overlay365 import router as signup_overlay365_router
app.include_router(signup_overlay365_router)

# Overlay 365 Blocklabor integration (no prefix - already has /api/v1/blocklabor)
from api.routers.blocklabor_overlay365 import router as blocklabor_overlay365_router
app.include_router(blocklabor_overlay365_router)


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

# RBAC - role-based access control (must be after auth middleware)
app.add_middleware(RBACMiddleware)

# =============================================================================
# Pydantic Models
# =============================================================================




# =============================================================================
# Security
# =============================================================================


def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token signed with RS256."""
    from api.services.jwt_utils import create_access_token as _create_rs256_token
    return _create_rs256_token(data, expires_delta)



# =============================================================================













# =============================================================================
# Utility Endpoints
# =============================================================================


# Sentry initialization — full FastAPI integration
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_integrations = [
            LoggingIntegration(level="error", event_level="error"),
        ]

        # FastAPI integration added after app is created (see below)
        sentry_sdk.init(
            dsn=sentry_dsn,
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
            environment=os.getenv("APP_ENV", "development"),
            release=f"aetherdesk@{os.getenv('APP_VERSION', '1.0.0')}",
            integrations=sentry_integrations,
            send_default_pii=False,
        )
        logger.info("sentry_initialized", environment=os.getenv("APP_ENV", "development"))
    except Exception as e:
        logger.warning("sentry_init_failed", error=str(e))
