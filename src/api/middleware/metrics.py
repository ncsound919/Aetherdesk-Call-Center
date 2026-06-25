import logging
import time

from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# HTTP metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP Requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

# Voice-specific metrics
VOICE_REQUEST_COUNT = Counter(
    'voice_requests_total',
    'Total voice requests',
    ['intent', 'protocol_id']
)

ASR_LATENCY = Histogram(
    'asr_processing_seconds',
    'ASR processing time',
    ['engine']
)

TTS_LATENCY = Histogram(
    'tts_processing_seconds',
    'TTS processing time',
    ['engine']
)

LLM_LATENCY = Histogram(
    'llm_processing_seconds',
    'LLM processing time',
    ['model']
)

# Resource metrics
ACTIVE_SESSIONS = Gauge(
    'active_voice_sessions',
    'Number of active voice sessions'
)

WEBSOCKET_CONNECTIONS = Gauge(
    'websocket_connections',
    'Number of active WebSocket connections'
)

REDIS_CONNECTIONS = Gauge(
    'redis_connections',
    'Number of Redis connections'
)

# Additional metrics
UPTIME_GAUGE = Gauge(
    'app_uptime_seconds',
    'Application uptime in seconds'
)

DB_POOL_SIZE = Gauge(
    'db_connection_pool_size',
    'Database connection pool size'
)

DB_POOL_USED = Gauge(
    'db_connection_pool_used',
    'Database connections currently in use'
)

DB_QUERY_LATENCY = Histogram(
    'db_query_duration_seconds',
    'Database query execution time',
    ['query_name']
)

CACHE_HITS = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['cache_type']
)

CACHE_MISSES = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['cache_type']
)

CALL_QUEUE_DEPTH = Gauge(
    'call_queue_depth',
    'Number of calls waiting in queue',
    ['tenant_id']
)

ACTIVE_VOICE_CHANNELS = Gauge(
    'active_voice_channels',
    'Number of active voice channels/call legs'
)

VENDOR_HEALTH = Gauge(
    'vendor_health_status',
    'Vendor health status (1=healthy, 0=unhealthy)',
    ['vendor']
)


def track_db_query(query_name: str, duration: float):
    DB_QUERY_LATENCY.labels(query_name=query_name).observe(duration)


def record_cache_hit(cache_type: str):
    CACHE_HITS.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str):
    CACHE_MISSES.labels(cache_type=cache_type).inc()


def update_call_queue_depth(tenant_id: str, depth: int):
    CALL_QUEUE_DEPTH.labels(tenant_id=tenant_id).set(depth)


def update_vendor_health(vendor: str, healthy: bool):
    VENDOR_HEALTH.labels(vendor=vendor).set(1 if healthy else 0)


def update_db_pool_stats(size: int, used: int):
    DB_POOL_SIZE.set(size)
    DB_POOL_USED.set(used)


def update_active_voice_channels(count: int):
    ACTIVE_VOICE_CHANNELS.set(count)


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._start_time = time.time()

    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path

        if endpoint == '/metrics':
            return await call_next(request)

        start_time = time.time()
        UPTIME_GAUGE.set(time.time() - self._start_time)

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            logger.error(f"Request failed: {e}", exc_info=True)
            raise e
        finally:
            duration = time.time() - start_time
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status_code).inc()
            REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

        return response

def track_voice_request(session_id: str, intent: str, protocol_id: str):
    """Track a voice request"""
    logger.info("voice_request_tracked", session_id=session_id, intent=intent, protocol_id=protocol_id)
    VOICE_REQUEST_COUNT.labels(
        intent=intent,
        protocol_id=protocol_id
    ).inc()

def track_asr_latency(duration: float, engine: str = "faster-whisper"):
    """Track ASR processing latency"""
    ASR_LATENCY.labels(engine=engine).observe(duration)

def track_tts_latency(duration: float, engine: str = "edge"):
    """Track TTS processing latency"""
    TTS_LATENCY.labels(engine=engine).observe(duration)

def track_llm_latency(duration: float, model: str = "ollama"):
    """Track LLM processing latency"""
    LLM_LATENCY.labels(model=model).observe(duration)

def update_active_sessions(count: int):
    """Update active sessions gauge"""
    ACTIVE_SESSIONS.set(count)

def update_websocket_connections(count: int):
    """Update WebSocket connections gauge"""
    WEBSOCKET_CONNECTIONS.set(count)

def update_redis_connections(count: int):
    """Update Redis connections gauge"""
    REDIS_CONNECTIONS.set(count)

async def metrics_endpoint():
    """Metrics endpoint handler"""
    return Response(generate_latest(), media_type="text/plain")
