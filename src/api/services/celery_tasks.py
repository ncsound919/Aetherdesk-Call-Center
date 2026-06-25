import asyncio
import json
import os
import time

import structlog
from celery import shared_task

logger = structlog.get_logger()

QUEUE_PREFIX = "aetherdesk:queue:"
SESSION_PREFIX = "aetherdesk:session:"


@shared_task(bind=True, max_retries=3)
def process_rag_query(self, query: str, k: int = 3, tenant_id: str = "default"):
    try:
        from api.services.rag import rag_service
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(rag_service.query(query, k))
        loop.close()
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5) from exc


@shared_task(bind=True, max_retries=3)
def process_intent_classify(self, transcript: str, tenant_id: str = "default"):
    try:
        from api.services.intent_classifier import classifier
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(classifier.classify(transcript))
        loop.close()
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5) from exc


@shared_task(bind=True, max_retries=3)
def process_agent_response(self, question: str, context: list = None, history: list = None, tenant_id: str = "default"):
    try:
        from api.services.agent import agent_service
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(agent_service.answer(question, context or [], history or []))
        loop.close()
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5) from exc


@shared_task(ignore_result=True)
def enqueue_item(queue_name: str, item_json: str):
    import redis as sync_redis
    r = sync_redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    key = f"{QUEUE_PREFIX}{queue_name}"
    r.lpush(key, item_json)


@shared_task(ignore_result=True)
def log_session_event(session_id: str, event_json: str):
    import redis as sync_redis
    r = sync_redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    key = f"{QUEUE_PREFIX}log:{session_id}"
    r.rpush(key, event_json)


@shared_task(ignore_result=True)
def process_handoff(queue_name: str, item_json: str, agent_id: str = None):
    item = json.loads(item_json)
    if agent_id:
        item["claimed_by"] = agent_id
        item["claimed_ts"] = time.time()
    logger.info("handoff_processed", queue=queue_name, agent=agent_id, session=item.get("session_id"))


