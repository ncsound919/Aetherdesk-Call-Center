"""Lago usage-based billing client.

Replaces/complements stripe_service.py for metering and plan management.
When LAGO_API_KEY is not set, all functions return mock data (dev/test mode).

Lago handles: usage metering, subscription plans, invoicing, Stripe sync.
"""

import os
from typing import Any

import structlog

logger = structlog.get_logger()

_client = None
_enabled = False


def _get_client() -> Any | None:
    """Return the Lago client singleton, or None if not configured."""
    global _client, _enabled
    if _client is not None:
        return _client

    api_key = os.getenv("LAGO_API_KEY")
    if not api_key:
        _enabled = False
        return None

    try:
        from lago_python_client import LagoClient

        _client = LagoClient(api_key=api_key)
        # Override base URL for self-hosted Lago
        if os.getenv("LAGO_API_URL"):
            _client.base_url = os.getenv("LAGO_API_URL")
        _enabled = True
        logger.info("lago_initialized")
    except ImportError:
        logger.debug("lago_not_installed")
        _enabled = False
    except Exception as e:
        logger.warning("lago_init_failed", error=str(e))
        _enabled = False

    return _client


def is_lago_enabled() -> bool:
    """Return True if Lago SDK is configured."""
    return _enabled and _get_client() is not None


# ---------------------------------------------------------------------------
# Event metering
# ---------------------------------------------------------------------------

def track_call_usage(
    tenant_id: str,
    call_sid: str,
    duration_seconds: int,
    call_type: str = "inbound",
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Meter a completed call for billing."""
    if not is_lago_enabled():
        return {"mock": True, "event_code": "call_completed", "tenant_id": tenant_id}

    client = _get_client()
    try:
        client.events().create({
            "event_code": "call_completed",
            "customer_id": tenant_id,
            "properties": {
                "call_sid": call_sid,
                "duration_seconds": duration_seconds,
                "call_type": call_type,
                **(metadata or {}),
            },
        })
        logger.info("lago_usage_tracked", tenant_id=tenant_id, call_sid=call_sid, duration=duration_seconds)
        return {"recorded": True, "tenant_id": tenant_id}
    except Exception as e:
        logger.error("lago_usage_track_failed", error=str(e))
        return {"recorded": False, "error": str(e)}


def track_ai_usage(
    tenant_id: str,
    session_id: str,
    tokens_used: int,
    model: str = "default",
) -> dict[str, Any]:
    """Meter AI/LLM usage for billing."""
    if not is_lago_enabled():
        return {"mock": True, "event_code": "ai_usage", "tenant_id": tenant_id}

    client = _get_client()
    try:
        client.events().create({
            "event_code": "ai_usage",
            "customer_id": tenant_id,
            "properties": {
                "session_id": session_id,
                "tokens_used": tokens_used,
                "model": model,
            },
        })
        return {"recorded": True}
    except Exception as e:
        logger.error("lago_ai_usage_track_failed", error=str(e))
        return {"recorded": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Subscription / plan management
# ---------------------------------------------------------------------------

def get_customer_usage(tenant_id: str, period_start: str, period_end: str) -> dict[str, Any]:
    """Get usage summary for a tenant in a billing period."""
    if not is_lago_enabled():
        return {
            "mock": True,
            "customer_id": tenant_id,
            "period_start": period_start,
            "period_end": period_end,
            "usage": [
                {"billable_metric": "call_minutes", "units": 0, "amount_cents": 0},
                {"billable_metric": "ai_tokens", "units": 0, "amount_cents": 0},
            ],
            "total_amount_cents": 0,
        }

    client = _get_client()
    try:
        invoice = client.invoices().find_draft_invoice(tenant_id)
        return {
            "customer_id": tenant_id,
            "invoice_id": invoice.id if invoice else None,
            "amount_cents": invoice.amount_cents if invoice else 0,
            "status": invoice.status if invoice else "draft",
        }
    except Exception as e:
        logger.error("lago_usage_query_failed", error=str(e))
        return {"error": str(e)}


def create_customer(
    tenant_id: str,
    email: str,
    name: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Create a Lago customer (synced to Stripe automatically)."""
    if not is_lago_enabled():
        return {"mock": True, "customer_id": tenant_id, "email": email}

    client = _get_client()
    try:
        from lago_python_client.models import Customer

        customer = Customer(
            external_id=tenant_id,
            email=email,
            name=name or tenant_id,
            metadata=metadata or {},
        )
        result = client.customers().create(customer)
        return {"customer_id": result.id, "external_id": tenant_id}
    except Exception as e:
        logger.error("lago_customer_create_failed", error=str(e))
        return {"error": str(e)}


def getinvoices(tenant_id: str) -> list[dict[str, Any]]:
    """Get all invoices for a tenant."""
    if not is_lago_enabled():
        return []

    client = _get_client()
    try:
        invoices = client.invoices().find_all({"external_customer_id": tenant_id})
        return [
            {
                "id": inv.id,
                "status": inv.status,
                "amount_cents": inv.amount_cents,
                "created_at": inv.created_at,
            }
            for inv in (invoices or [])
        ]
    except Exception as e:
        logger.error("lago_invoices_query_failed", error=str(e))
        return []
