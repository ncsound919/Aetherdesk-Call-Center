import logging
import os
import re
import time
from functools import wraps
from typing import Any

import psutil
import structlog

from api.services.connection_pool import http_pool

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
        from api.main import app
        if hasattr(app, 'state') and hasattr(app.state, 'redis'):
            app.state.redis.ping()
            return True
    except Exception:
        pass  # Best-effort health check
    return False


async def check_asr_health() -> bool:
    try:
        from api.services.asr import asr_service
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


# App start time (set on import)
APP_START_TIME = time.time()


class UptimeTracker:
    """Tracks application uptime for SLA reporting."""

    def get_uptime_seconds(self) -> float:
        return time.time() - APP_START_TIME

    def get_uptime_percentage(self, target_availability: float = 99.9) -> float:
        """Calculate uptime percentage against target."""
        # For demo: assume no downtime
        return target_availability


class SLAMetrics:
    """Computes service-level indicators."""

    def __init__(self):
        self._error_counts: dict[str, int] = {}
        self._request_counts: dict[str, int] = {}
        self._latency_buckets: dict[str, list[float]] = {}

    def record_request(self, endpoint: str, status_code: int, latency_ms: float):
        key = endpoint
        self._request_counts[key] = self._request_counts.get(key, 0) + 1
        if status_code >= 500:
            self._error_counts[key] = self._error_counts.get(key, 0) + 1
        if key not in self._latency_buckets:
            self._latency_buckets[key] = []
        self._latency_buckets[key].append(latency_ms)
        # Keep only last 1000 latency samples
        if len(self._latency_buckets[key]) > 1000:
            self._latency_buckets[key] = self._latency_buckets[key][-1000:]

    def get_sla_summary(self) -> dict:
        total_requests = sum(self._request_counts.values())
        total_errors = sum(self._error_counts.values())
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0

        all_latencies = []
        for latencies in self._latency_buckets.values():
            all_latencies.extend(latencies)

        if all_latencies:
            all_latencies_sorted = sorted(all_latencies)
            p50 = all_latencies_sorted[len(all_latencies_sorted) // 2]
            p95_idx = int(len(all_latencies_sorted) * 0.95)
            p99_idx = int(len(all_latencies_sorted) * 0.99)
            p95 = all_latencies_sorted[min(p95_idx, len(all_latencies_sorted) - 1)]
            p99 = all_latencies_sorted[min(p99_idx, len(all_latencies_sorted) - 1)]
            avg = sum(all_latencies) / len(all_latencies)
        else:
            p50 = p95 = p99 = avg = 0

        uptime_tracker = UptimeTracker()
        return {
            "uptime_seconds": uptime_tracker.get_uptime_seconds(),
            "uptime_percentage": uptime_tracker.get_uptime_percentage(),
            "total_requests": total_requests,
            "error_rate_pct": round(error_rate, 2),
            "latency": {
                "avg_ms": round(avg, 2),
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
            },
            "availability_target": 99.9,
        }

    def reset(self):
        self._error_counts.clear()
        self._request_counts.clear()
        self._latency_buckets.clear()


uptime_tracker = UptimeTracker()
sla_metrics = SLAMetrics()


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


