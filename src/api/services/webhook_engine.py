import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime

import httpx
import structlog

from api.services.db_developer import (
    create_webhook_delivery_log_db,
    get_active_webhooks_for_event_db,
    get_webhook_by_id_db,
    get_webhook_delivery_log_by_id_db,
    get_webhook_delivery_logs_db,
    list_webhooks_db,
    register_webhook_db,
    unregister_webhook_db,
    update_webhook_delivery_log_db,
)

logger = structlog.get_logger()

EVENT_CATALOG = {
    "call.completed": {
        "description": "A call has completed",
        "schema": {
            "call_id": "string",
            "tenant_id": "string",
            "duration_seconds": "number",
            "status": "string",
            "timestamp": "string",
        },
    },
    "call.failed": {
        "description": "A call has failed",
        "schema": {
            "call_id": "string",
            "tenant_id": "string",
            "error": "string",
            "timestamp": "string",
        },
    },
    "agent.status_changed": {
        "description": "An agent's status has changed",
        "schema": {
            "agent_id": "string",
            "tenant_id": "string",
            "status_before": "string",
            "status_after": "string",
            "timestamp": "string",
        },
    },
    "intent.classified": {
        "description": "Call intent has been classified",
        "schema": {
            "call_id": "string",
            "tenant_id": "string",
            "intent": "string",
            "confidence": "number",
            "timestamp": "string",
        },
    },
    "qa.score_created": {
        "description": "A QA score has been created",
        "schema": {
            "score_id": "string",
            "call_id": "string",
            "agent_id": "string",
            "total_score": "number",
            "timestamp": "string",
        },
    },
    "csat.submitted": {
        "description": "A CSAT survey has been submitted",
        "schema": {
            "survey_id": "string",
            "call_id": "string",
            "rating": "number",
            "feedback": "string",
            "timestamp": "string",
        },
    },
    "transcription.ready": {
        "description": "Transcription is ready for a call",
        "schema": {
            "call_id": "string",
            "tenant_id": "string",
            "transcription_id": "string",
            "language": "string",
            "timestamp": "string",
        },
    },
}

DELIVERY_TIMEOUT = 10
MAX_RETRIES = 3
BACKOFF_BASE = 2.0


def _sign_payload(payload: str, secret: str) -> str:
    return hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


async def _deliver_webhook(url: str, payload: dict, secret: str | None,
                           log_id: str, tenant_id: str, webhook_id: str) -> bool:
    payload_str = json.dumps(payload, default=str)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AetherDesk-Webhook/1.0",
    }
    if secret:
        signature = _sign_payload(payload_str, secret)
        headers["X-AetherDesk-Signature"] = f"sha256={signature}"
        headers["X-AetherDesk-Timestamp"] = str(int(time.time()))

    error_message = None
    response_status = None
    response_body = None

    try:
        async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT) as client:
            resp = await client.post(url, content=payload_str, headers=headers)
            response_status = resp.status_code
            response_body = resp.text[:2000]
            if 200 <= resp.status_code < 300:
                await update_webhook_delivery_log_db(
                    log_id, "delivered",
                    response_status=response_status,
                    response_body=response_body,
                )
                return True
            error_message = f"HTTP {resp.status_code}"
    except httpx.TimeoutException:
        error_message = "Timeout"
        response_status = 0
    except Exception as e:
        error_message = str(e)[:500]
        response_status = 0

    await update_webhook_delivery_log_db(
        log_id, status="failed" if error_message else "failed",
        response_status=response_status,
        response_body=response_body,
        error_message=error_message,
        retry_count=0,
    )
    return False


class WebhookEngine:
    def __init__(self):
        self._dispatch_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    def start(self):
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            self._worker_task = None

    async def register_webhook(self, tenant_id: str, url: str, events: list[str],
                               secret: str | None = None) -> dict:
        if not secret:
            secret = uuid.uuid4().hex
        return await register_webhook_db(tenant_id, url, events, secret)

    async def unregister_webhook(self, tenant_id: str, webhook_id: str) -> bool:
        return await unregister_webhook_db(tenant_id, webhook_id)

    async def list_webhooks(self, tenant_id: str) -> list[dict]:
        return await list_webhooks_db(tenant_id)

    async def get_webhook(self, tenant_id: str, webhook_id: str) -> dict | None:
        return await get_webhook_by_id_db(tenant_id, webhook_id)

    def get_event_catalog(self) -> dict:
        return EVENT_CATALOG

    async def dispatch_event(self, tenant_id: str, event_type: str, payload: dict):
        if event_type not in EVENT_CATALOG:
            logger.warning("unknown_event_type", event_type=event_type)
            return

        webhooks = await get_active_webhooks_for_event_db(tenant_id, event_type)
        if not webhooks:
            return

        event_payload = {
            "event_type": event_type,
            "event_id": uuid.uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "data": payload,
        }

        for wh in webhooks:
            await self._dispatch_queue.put((wh, event_payload))

    async def get_delivery_logs(self, tenant_id: str, webhook_id: str,
                                limit: int = 50) -> list[dict]:
        return await get_webhook_delivery_logs_db(tenant_id, webhook_id, limit)

    async def retry_delivery(self, tenant_id: str, log_id: str) -> bool:
        log_entry = await get_webhook_delivery_log_by_id_db(log_id)
        if not log_entry:
            return False

        webhook = await get_webhook_by_id_db(log_entry["tenant_id"], log_entry["webhook_id"])
        if not webhook:
            return False

        request_body = log_entry.get("request_body", "{}")
        if isinstance(request_body, str):
            payload = json.loads(request_body)
        else:
            payload = request_body

        await update_webhook_delivery_log_db(
            log_id, "retrying",
            retry_count=(log_entry.get("retry_count", 0) or 0) + 1,
        )

        success = await _deliver_webhook(
            webhook["url"], payload,
            webhook.get("secret"),
            log_id, log_entry["tenant_id"], webhook["id"],
        )
        return success

    async def _worker_loop(self):
        while True:
            try:
                webhook, payload = await self._dispatch_queue.get()
                asyncio.create_task(self._deliver_with_retry(webhook, payload))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("dispatch_worker_error", error=str(e))

    async def _deliver_with_retry(self, webhook: dict, payload: dict):
        log_entry = await create_webhook_delivery_log_db(
            webhook["tenant_id"], webhook["id"],
            payload["event_type"], json.dumps(payload, default=str),
        )
        if not log_entry:
            return
        log_id = log_entry["id"]

        for attempt in range(MAX_RETRIES):
            success = await _deliver_webhook(
                webhook["url"], payload,
                webhook.get("secret"),
                log_id, webhook["tenant_id"], webhook["id"],
            )
            if success:
                return

            if attempt < MAX_RETRIES - 1:
                backoff = BACKOFF_BASE ** attempt
                await asyncio.sleep(backoff)
                await update_webhook_delivery_log_db(
                    log_id, "retrying",
                    retry_count=attempt + 1,
                )

        await update_webhook_delivery_log_db(
            log_id, "dead_letter",
            error_message="Max retries exceeded",
            retry_count=MAX_RETRIES,
        )
        logger.warning("webhook_dead_letter",
                       webhook_id=webhook["id"],
                       event_type=payload.get("event_type"))


webhook_engine = WebhookEngine()
