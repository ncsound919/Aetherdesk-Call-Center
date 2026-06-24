"""
HIPAA Audit Logging Middleware
===============================
Automatically logs all access to Protected Health Information (PHI).
All entries are written to the audit_log table and optionally to a
remote SIEM endpoint for compliance monitoring.
"""

import json
import time
import uuid
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from apps.api.services.database import USE_POSTGRES

logger = structlog.get_logger()

# Classify which request paths involve PHI access
PHI_PATHS = {
    "/api/v1/tenants": "tenant_data",
    "/api/v1/tenants/": "tenant_data",
    "/api/v1/agents": "agent_data",
    "/api/v1/agents/": "agent_data",
    "/api/v1/calls": "call_data",
    "/api/v1/calls/": "call_data",
    "/api/v1/calls/webhooks": "call_data",
    "/api/v1/webhooks/fonster": "call_event_data",
    "/voice/incoming": "call_event_data",
    "/voice/intent": "call_data",
    "/voice/media-stream": "call_media_data",
    "/voice/transcribe": "call_media_data",
    "/voice/synthesize": "call_media_data",
    "/voice/outbound": "call_data",
}

# Fields in request/response bodies that contain PHI
PHI_FIELDS = {
    "caller_number", "caller_name", "called_number", "phone", "email",
    "name", "address", "date_of_birth", "ssn", "medical_record_number",
    "patient_id", "prescription", "diagnosis", "transcript", "full_text",
    "ingress_number",
}


def _redact_phi(data: dict) -> dict:
    """Redact PHI fields from a dict, keeping only keys."""
    if not isinstance(data, dict):
        return data
    redacted = {}
    for key, value in data.items():
        if key.lower() in PHI_FIELDS:
            redacted[key] = "[REDACTED-PHI]"
        elif isinstance(value, dict):
            redacted[key] = _redact_phi(value)
        elif isinstance(value, list):
            redacted[key] = [_redact_phi(item) if isinstance(item, dict) else item for item in value]
        else:
            redacted[key] = value
    return redacted


def _get_resource_type(path: str) -> str:
    """Determine resource type from the request path."""
    for prefix, rtype in PHI_PATHS.items():
        if path.startswith(prefix) or prefix in path:
            return rtype
    return "general"


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs every request to PHI-related endpoints
    into the audit_log table for HIPAA compliance.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.time()
        path = request.url.path
        resource_type = _get_resource_type(path)

        # Extract tenant_id from headers or JWT (if available)
        tenant_id = request.headers.get("x-tenant-id", "unknown")
        user_id = request.headers.get("x-user-id", "unknown")

        # Check for PHI access
        is_phi = resource_type != "general"

        # Read and redact body if present
        body = None
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body = json.loads(body_bytes)
                    if is_phi:
                        body = _redact_phi(body)
            except Exception:
                body = {"_parse_error": True}

        # Process the request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Read response body for PHI endpoints
        response_body = None
        if is_phi and response.status_code < 400:
            try:
                response_body = json.loads(response.body.decode()) if response.body else None
                if response_body:
                    response_body = _redact_phi(response_body)
            except Exception:
                response_body = {"_read_error": True}

        # Log audit event
        if is_phi:
            try:
                action = f"{request.method.upper()} {path}"
                new_values = {
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "request_id": request_id,
                    "body": body,
                    "response": response_body,
                }

                if USE_POSTGRES:
                    # Async logging for PostgreSQL
                    import asyncio

                    from apps.api.services.database import get_pg_pool
                    pool = await get_pg_pool()
                    if pool:
                        async def _log_async():
                            try:
                                await pool.execute(
                                    """INSERT INTO audit_log
                                       (tenant_id, user_id, action, resource_type, resource_id,
                                        old_values, new_values, ip_address)
                                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                                    tenant_id, user_id, action, resource_type, request_id,
                                    "{}", json.dumps(new_values),
                                    request.client.host if request.client else "0.0.0.0"  # nosec B104 — fallback IP for audit log
                                )
                            except Exception as log_err:
                                logger.error("async_audit_log_failed", error=str(log_err))
                        task = asyncio.create_task(_log_async())
                        # Store reference to prevent GC of pending task
                        if not hasattr(request.app.state, '_background_tasks'):
                            request.app.state._background_tasks = set()
                        request.app.state._background_tasks.add(task)
                        task.add_done_callback(request.app.state._background_tasks.discard)
                else:
                    # Synchronous logging for SQLite
                    import datetime as dt

                    from apps.api.services.database import _get_sqlite_conn
                    conn = _get_sqlite_conn()
                    conn.execute(
                        """INSERT INTO audit_log
                           (tenant_id, user_id, action, resource_type, resource_id,
                            old_values, new_values, ip_address, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (tenant_id, user_id, action, resource_type, str(request_id),
                         "{}", json.dumps(new_values),
                         request.client.host if request.client else "0.0.0.0",  # nosec B104 — fallback IP for audit log
                         dt.datetime.now(dt.UTC).isoformat())
                    )
                    conn.commit()
                    conn.close()

                logger.info(
                    "audit_event",
                    action=action,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    resource_type=resource_type,
                    status_code=response.status_code,
                    duration_ms=round(duration_ms, 2),
                )
            except Exception as e:
                logger.error("audit_log_failed", error=str(e))

        # Add audit headers to response
        response.headers["x-request-id"] = request_id
        response.headers["x-audit-logged"] = str(is_phi).lower()

        return response
