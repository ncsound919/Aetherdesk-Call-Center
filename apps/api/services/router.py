import json
import os
from typing import TypedDict


class RouteInfo(TypedDict):
    protocol_id: str
    queue: str
    fields: list[str]

INTENT_TO_PROTOCOL = {
    "pharmacy_refill": ("pharmacy_refill_v1", "rx", ["rx_number"]),
    "pharmacy_refill_doc": ("pharmacy_refill_doc_v1", "rx", ["patient_dob", "doctor_name"]),
    "billing_invoice": ("billing_invoice_v1", "billing", ["invoice_id"]),
    "billing_refund": ("billing_refund_v1", "billing", ["order_id", "reason_code"]),
    "order_status": ("order_status_v1", "ops", ["order_id", "zip"]),
    "tech_support_password": ("reset_v1", "support", ["customer_id"]),
    "generalInquiry": ("general_inquiry_v1", "general", []),
    "agent_handoff": ("agent_handoff_v1", "general", []),
    "retry": ("triage_v1", "general", []),
}


class TwoQuestionRouter:
    def __init__(self, table: dict[str, RouteInfo]):
        self.table = table

    def route(self, q1: str, q2: str) -> RouteInfo:
        key = f"{q1}:{q2}"
        info = self.table.get(key)
        if not info:
            return {"protocol_id":"fallback_handoff_v1","queue":"general","fields":[]}
        return info


class LLMIntentRouter:
    def __init__(self):
        self._classifier = None

    def _get_classifier(self):
        from apps.api.services.intent_classifier import classifier
        return classifier

    def route(self, intent: str, entities: dict) -> RouteInfo:
        protocol_id, queue, fields = INTENT_TO_PROTOCOL.get(
            intent,
            ("fallback_handoff_v1", "general", [])
        )

        return {
            "protocol_id": protocol_id,
            "queue": queue,
            "fields": fields,
            "entities": entities,
            "intent": intent
        }

    async def route_from_transcript(self, transcript: str) -> RouteInfo:
        classifier = self._get_classifier()
        result = await classifier.classify_with_fallback(transcript)
        return self.route(result.intent, result.entities)


routes_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "config", "routes.json")
try:
    with open(routes_path) as f:
        route_table = json.load(f)
except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
    import structlog
    structlog.get_logger().warning("route_table_load_failed_using_empty", error=str(e), path=routes_path)
    route_table = {}

two_question_router = TwoQuestionRouter(route_table)
llm_router = LLMIntentRouter()

def get_router():
    use_llm = os.getenv("USE_LLM_ROUTING", "false").lower() == "true"
    if use_llm:
        return llm_router
    return two_question_router

router = get_router()
