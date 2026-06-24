import logging
import os
import re
import time
from functools import wraps
from typing import Any

import psutil
import structlog

from apps.api.services.connection_pool import http_pool

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

PII_PATTERNS = [
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), 'XXX-XX-XXXX'),  # SSN
    (re.compile(r'\b[\w\.-]+@[\w\.-]+\.\w+\b'), '[REDACTED_EMAIL]'), # Email
    (re.compile(r'\b(?:\+\d{1,2}\s)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b'), '[REDACTED_PHONE]') # Phone
]
SENSITIVE_KEYS = {"email", "phone", "ssn", "password", "customer_name", "credit_card", "address", "shipping_address"}

def redact_pii_processor(logger, log_method, event_dict):
    """Redacts PII from log event dicts."""
    for key, value in list(event_dict.items()):
        if key in SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
        elif isinstance(value, str):
            for pattern, replacement in PII_PATTERNS:
                value = pattern.sub(replacement, value)
            event_dict[key] = value
    return event_dict

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_pii_processor,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLogger().level),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()

initialized_services = {
    "redis": False,
    "asr": False,
    "ollama": False,
}


def mark_initialized(service: str):
    initialized_services[service] = True


def log_call(endpoint: str = "unknown"):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            logger.info(
                "api_call_start",
                endpoint=endpoint,
                function=func.__name__,
                args_len=len(args)
            )
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start
                logger.info(
                    "api_call_end",
                    endpoint=endpoint,
                    function=func.__name__,
                    duration_ms=int(duration * 1000),
                    status="success"
                )
                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(
                    "api_call_error",
                    endpoint=endpoint,
                    function=func.__name__,
                    duration_ms=int(duration * 1000),
                    error=str(e),
                    status="error"
                )
                raise
        return wrapper
    return decorator


class CallLogger:
    def __init__(self):
        self.active_calls: dict[str, dict[str, Any]] = {}

    def start_call(self, call_sid: str, metadata: dict[str, Any] = None):
        self.active_calls[call_sid] = {
            "started_at": time.time(),
            "metadata": metadata or {},
            "events": []
        }
        logger.info(
            "call_started",
            call_sid=call_sid,
            **self.active_calls[call_sid]["metadata"]
        )

    def log_event(self, call_sid: str, event: str, data: dict[str, Any] = None):
        if call_sid in self.active_calls:
            self.active_calls[call_sid]["events"].append({
                "event": event,
                "timestamp": time.time(),
                "data": data or {}
            })
            logger.info(
                "call_event",
                call_sid=call_sid,
                event=event,
                **(data or {})
            )

    def end_call(self, call_sid: str, status: str = "completed"):
        if call_sid in self.active_calls:
            duration = time.time() - self.active_calls[call_sid]["started_at"]
            logger.info(
                "call_ended",
                call_sid=call_sid,
                duration_sec=int(duration),
                status=status,
                events_count=len(self.active_calls[call_sid]["events"])
            )
            del self.active_calls[call_sid]


call_logger = CallLogger()


class MetricsCollector:
    def __init__(self):
        self.counters: dict[str, int] = {}
        self.timers: dict[str, list] = {}

    def increment(self, metric: str, value: int = 1):
        key = f"counter_{metric}"
        self.counters[key] = self.counters.get(key, 0) + value

    def record_time(self, metric: str, duration_ms: int):
        key = f"timer_{metric}"
        if key not in self.timers:
            self.timers[key] = []
        self.timers[key].append(duration_ms)

    def get_metrics(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "timers": {
                k: {
                    "count": len(v),
                    "avg_ms": sum(v) // len(v) if v else 0,
                    "min_ms": min(v) if v else 0,
                    "max_ms": max(v) if v else 0
                }
                for k, v in self.timers.items()
            }
        }

    def reset(self):
        self.counters.clear()
        self.timers.clear()


metrics = MetricsCollector()


async def check_redis_health() -> bool:
    try:
        from apps.api.main import app
        if hasattr(app, 'state') and hasattr(app.state, 'redis'):
            app.state.redis.ping()
            return True
    except Exception:
        pass  # Best-effort health check
    return False


async def check_asr_health() -> bool:
    try:
        from apps.api.services.asr import asr_service
        if asr_service._model is not None:
            return True
    except Exception:
        pass  # Best-effort health check
    return False


async def check_ollama_health() -> bool:
    try:
        client = await http_pool.get_client()
        response = await client.get("http://localhost:11434/api/tags")
        return response.status_code == 200
    except Exception:
        return False


HEALTH_CHECKS = {
    "redis": check_redis_health,
    "ollama": check_ollama_health,
    "asr": check_asr_health,
}


async def get_health_status() -> dict[str, Any]:
    results = {}
    all_healthy = True

    for name, check_fn in HEALTH_CHECKS.items():
        try:
            healthy = await check_fn()
            results[name] = {"status": "healthy" if healthy else "unhealthy", "initialized": initialized_services.get(name, False)}
            if not healthy:
                all_healthy = False
        except Exception as e:
            results[name] = {"status": "error", "error": str(e), "initialized": initialized_services.get(name, False)}
            all_healthy = False

    # System Metrics (Checklist Section 7)
    system_metrics = {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_available_mb": psutil.virtual_memory().available // (1024 * 1024)
    }

    return {
        "status": "healthy" if all_healthy else "degraded",
        "services": results,
        "system_metrics": system_metrics,
        "metrics": metrics.get_metrics()
    }


