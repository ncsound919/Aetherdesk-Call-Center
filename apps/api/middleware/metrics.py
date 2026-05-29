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

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path

        # Skip metrics endpoint
        if endpoint == '/metrics':
            return await call_next(request)

        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            logger.error(f"Request failed: {e}", exc_info=True)
            raise e
        finally:
            duration = time.time() - start_time

            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status=status_code
            ).inc()

            REQUEST_LATENCY.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)

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
