"""Langfuse LLM observability client.

Provides tracing for AI agent conversations — LLM costs, prompt quality,
intent classification accuracy, and token usage per call.

Graceful no-op when LANGFUSE_PUBLIC_KEY is not configured.
"""

import os
from typing import Any

import structlog

logger = structlog.get_logger()

_langfuse = None
_tried = False


def get_langfuse() -> Any | None:
    """Return the Langfuse client singleton, or None if not configured."""
    global _langfuse, _tried
    if _tried:
        return _langfuse if _langfuse else None

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        _tried = True
        return None

    try:
        from langfuse import Langfuse

        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        _langfuse = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        _tried = True
        logger.info("langfuse_initialized", host=host)
    except ImportError:
        logger.debug("langfuse_not_installed")
        _tried = True
    except Exception as e:
        logger.warning("langfuse_init_failed", error=str(e))
        _tried = True

    return _langfuse


def flush():
    """Flush buffered events to Langfuse. Call on shutdown."""
    lf = get_langfuse()
    if lf and hasattr(lf, "flush"):
        try:
            lf.flush()
        except Exception:
            pass


def score_call(call_sid: str, name: str, value: float, **kwargs: Any):
    """Score a call trace (e.g. satisfaction, intent_confidence)."""
    lf = get_langfuse()
    if not lf:
        return
    try:
        lf.score(name=name, value=value, comment=kwargs.get("comment"), metadata=kwargs)
    except Exception:
        pass
