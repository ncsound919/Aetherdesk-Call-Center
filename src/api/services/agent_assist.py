from datetime import UTC, datetime

import structlog

from api.services.db_ai_assist import (
    create_knowledge_snippet_db,
    delete_knowledge_snippet_db,
    search_knowledge_snippets_db,
)
from api.services.output_validator import validator

logger = structlog.get_logger()

SUGGESTED_ACTIONS = [
    {"action": "transfer_to_billing", "label": "Transfer to Billing", "confidence": 0.0},
    {"action": "transfer_to_support", "label": "Transfer to Technical Support", "confidence": 0.0},
    {"action": "escalate_to_supervisor", "label": "Escalate to Supervisor", "confidence": 0.0},
    {"action": "offer_discount", "label": "Offer 10% Discount", "confidence": 0.0},
    {"action": "schedule_callback", "label": "Schedule Callback", "confidence": 0.0},
    {"action": "send_email_summary", "label": "Send Email Summary", "confidence": 0.0},
]

SCRIPT_SNIPPETS = {
    "greeting": "Thank you for calling. My name is {agent_name}. How can I assist you today?",
    "apology": "I sincerely apologize for the inconvenience you've experienced.",
    "callback": "I'll make sure someone calls you back within the next {timeframe} hours.",
    "discount": "As a gesture of goodwill, I can offer you a {percent}% discount on your next purchase.",
    "closing": "Is there anything else I can help you with today?",
    "transfer": "Let me transfer you to the right department who can better assist with this.",
}

_KB_STORE: dict[str, dict] = {}
_NEXT_ID = 1


class AgentAssistService:
    def __init__(self):
        self._call_stats: dict[str, dict] = {}

    async def get_suggestions(self, call_id: str | None, transcript_segment: str | None, context: dict) -> list[dict]:
        suggestions = []
        intents = [
            "pharmacy_refill", "pharmacy_refill_doc", "billing_invoice",
            "billing_refund", "order_status", "tech_support_password",
            "generalInquiry", "agent_handoff",
        ]

        detected_intent = "generalInquiry"
        if transcript_segment:
            try:
                from api.services.intent_classifier import classifier
                result = await classifier.classify(transcript_segment)
                validated = validator.validate_intent_result(
                    {"intent": result.intent, "confidence": result.confidence},
                    intents,
                )
                if validated["valid"]:
                    detected_intent = result.intent
            except Exception as e:
                logger.warning("suggestion_intent_failed", error=str(e))

        kb_snippets = []
        if transcript_segment:
            try:
                kb_snippets = await self.get_knowledge_snippets(
                    context.get("tenant_id", "default"),
                    transcript_segment,
                    limit=3,
                )
            except Exception as e:
                logger.warning("kb_search_failed", error=str(e))

        for kb in kb_snippets:
            suggestions.append({
                "type": "knowledge_article",
                "title": kb.get("title", "Knowledge Article"),
                "content": kb.get("content", ""),
                "id": kb.get("id", ""),
                "confidence": 0.85,
            })

        actions = list(SUGGESTED_ACTIONS)
        intent_action_map = {
            "billing_invoice": "transfer_to_billing",
            "billing_refund": "transfer_to_billing",
            "tech_support_password": "transfer_to_support",
            "order_status": "transfer_to_support",
            "agent_handoff": "transfer_to_support",
        }
        preferred = intent_action_map.get(detected_intent)
        for action in actions:
            if action["action"] == preferred:
                action["confidence"] = 0.9
            elif preferred and "transfer" in action["action"]:
                action["confidence"] = 0.3
            else:
                action["confidence"] = 0.5

        suggestions.append({
            "type": "detected_intent",
            "intent": detected_intent,
            "confidence": 0.85,
        })

        for action in actions:
            suggestions.append({
                "type": "action",
                "action": action["action"],
                "label": action["label"],
                "confidence": action["confidence"],
            })

        script_key = self._pick_script(detected_intent)
        if script_key:
            suggestions.append({
                "type": "script",
                "key": script_key,
                "text": SCRIPT_SNIPPETS.get(script_key, ""),
                "confidence": 0.75,
            })

        return suggestions

    def _pick_script(self, intent: str) -> str | None:
        mapping = {
            "billing_invoice": "apology",
            "billing_refund": "apology",
            "tech_support_password": "apology",
            "generalInquiry": "greeting",
            "order_status": "greeting",
            "agent_handoff": "transfer",
        }
        return mapping.get(intent)

    async def get_knowledge_snippets(self, tenant_id: str, query: str, limit: int = 5) -> list[dict]:
        try:
            results = await search_knowledge_snippets_db(tenant_id, query, limit)
            if results:
                return results
        except Exception as e:
            logger.debug("kb_db_search_failed", error=str(e))

        results = []
        query_lower = query.lower()
        for sid, snippet in list(_KB_STORE.items()):
            if snippet.get("tenant_id") != tenant_id:
                continue
            if query_lower in snippet.get("title", "").lower() or query_lower in snippet.get("content", "").lower():
                results.append(snippet)
                if len(results) >= limit:
                    break
        return results

    async def create_knowledge_snippet(
        self, tenant_id: str, title: str, content: str,
        tags: list[str] | None = None, category: str = "general",
    ) -> dict:
        global _NEXT_ID
        try:
            result = await create_knowledge_snippet_db(tenant_id, title, content, tags or [], category)
            if result:
                return result
        except Exception as e:
            logger.debug("kb_db_create_failed, using memory store", error=str(e))

        sid = str(_NEXT_ID)
        _NEXT_ID += 1
        now = datetime.now(UTC).isoformat()
        snippet = {
            "id": sid,
            "tenant_id": tenant_id,
            "title": title,
            "content": content,
            "tags": tags or [],
            "category": category,
            "created_at": now,
            "updated_at": now,
        }
        _KB_STORE[sid] = snippet
        return snippet

    async def delete_knowledge_snippet(self, tenant_id: str, snippet_id: str) -> bool:
        try:
            deleted = await delete_knowledge_snippet_db(tenant_id, snippet_id)
            if deleted:
                return True
        except Exception as e:
            logger.debug("kb_db_delete_failed, trying memory store", error=str(e))

        if snippet_id in _KB_STORE and _KB_STORE[snippet_id].get("tenant_id") == tenant_id:
            del _KB_STORE[snippet_id]
            return True
        return False

    async def get_next_best_action(self, call_context: dict, agent_performance: dict | None = None) -> dict:
        intent = call_context.get("current_intent", "generalInquiry")
        sentiment = call_context.get("sentiment", "neutral")
        duration = call_context.get("call_duration_seconds", 0)

        nba = {"action": "continue_monitoring", "reason": "Call in progress", "confidence": 0.5}

        if sentiment == "negative" and duration > 300:
            nba = {
                "action": "escalate_to_supervisor",
                "reason": "Negative sentiment with long duration",
                "confidence": 0.85,
            }
        elif intent in ("billing_refund", "billing_invoice"):
            nba = {
                "action": "offer_discount",
                "reason": "Billing-related call — consider goodwill gesture",
                "confidence": 0.7,
            }
        elif sentiment == "negative":
            nba = {
                "action": "send_email_summary",
                "reason": "Negative sentiment detected — follow up with summary",
                "confidence": 0.6,
            }

        if agent_performance:
            avg_score = agent_performance.get("avg_score", 0.5)
            if avg_score < 0.6 and sentiment == "negative":
                nba = {
                    "action": "escalate_to_supervisor",
                    "reason": "Low agent performance score + negative sentiment",
                    "confidence": 0.9,
                }

        return nba

    async def get_realtime_stats(self, call_id: str) -> dict:
        if call_id not in self._call_stats:
            import random
            self._call_stats[call_id] = {
                "call_id": call_id,
                "duration_seconds": 0,
                "sentiment": "neutral",
                "sentiment_trend": ["neutral"],
                "keywords": [],
                "talk_ratio": 0.5,
                "interruptions": 0,
            }

        stats = self._call_stats[call_id]
        stats["duration_seconds"] += 15

        import random
        sentiment_shift = random.choice(["positive", "neutral", "negative"])
        if random.random() < 0.3:
            stats["sentiment"] = sentiment_shift
        stats["sentiment_trend"].append(stats["sentiment"])
        if len(stats["sentiment_trend"]) > 20:
            stats["sentiment_trend"] = stats["sentiment_trend"][-20:]

        return stats


agent_assist_service = AgentAssistService()
