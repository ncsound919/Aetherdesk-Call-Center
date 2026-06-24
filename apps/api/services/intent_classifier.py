import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from apps.api.middleware.metrics import track_llm_latency
from apps.api.services.connection_pool import get_http_client
from apps.api.services.memory import memory_service
from apps.api.services.retry import retry_ollama

logger = structlog.get_logger()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

INTENT_SCHEMA = {
    "intent": "string - one of: pharmacy_refill, pharmacy_refill_doc, billing_invoice, billing_refund, order_status, tech_support_password, generalInquiry, agent_handoff",
    "entities": "object - extracted key-value pairs from the transcript",
    "confidence": "float - confidence score between 0 and 1",
    "reasoning": "string - brief explanation of the classification"
}

SYSTEM_PROMPT = f"""You are an intent classifier for a call center IVR system.
Your task is to classify customer utterances into one of the following intents:

- pharmacy_refill: Customer wants to refill a prescription
- pharmacy_refill_doc: Customer wants doctor callback for prescription
- billing_invoice: Customer wants invoice information
- billing_refund: Customer wants refund for order
- order_status: Customer wants status of an order
- tech_support_password: Customer needs password reset help
- generalInquiry: General questions not matching specific categories
- agent_handoff: Customer explicitly wants to speak to agent

Extract any entities mentioned (like order numbers, prescription numbers, etc).

Respond with JSON only, following this schema:
{json.dumps(INTENT_SCHEMA, indent=2)}

Example input: "I need to refill my prescription number 12345"
Example output: {{"intent": "pharmacy_refill", "entities": {{"rx_number": "12345"}}, "confidence": 0.95, "reasoning": "Customer explicitly mentioned refill and provided Rx number"}}
"""


@dataclass
class IntentResult:
    intent: str
    entities: dict[str, Any]
    confidence: float
    reasoning: str


class IntentClassifier:
    KEYWORD_INTENTS = [
        ("refund", "billing_refund"),
        ("invoice", "billing_invoice"),
        ("order status", "order_status"),
        ("password", "tech_support_password"),
        ("prescription", "pharmacy_refill"),
        ("refill", "pharmacy_refill"),
        ("doctor", "pharmacy_refill_doc"),
        ("help", "generalInquiry"),
        ("agent", "agent_handoff"),
        ("representative", "agent_handoff"),
        ("human", "agent_handoff"),
    ]

    def __init__(self, model: str = None, host: str = None):
        self.model = model or OLLAMA_MODEL
        self.host = host or OLLAMA_HOST
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client from connection pool"""
        return get_http_client()

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _keyword_fallback(self, transcript: str) -> IntentResult:
        lower = transcript.lower()
        for keyword, intent in self.KEYWORD_INTENTS:
            if keyword in lower:
                return IntentResult(
                    intent=intent,
                    entities={},
                    confidence=0.5,
                    reasoning=f"Keyword fallback matched '{keyword}'"
                )

        return IntentResult(
            intent="generalInquiry",
            entities={},
            confidence=0.2,
            reasoning="No strong keyword match found"
        )

    async def _call_ollama(self, transcript: str, session_id: str = None) -> dict[str, Any]:
        # Build context from memory if session_id provided
        context = ""
        if session_id:
            try:
                memories = await memory_service.search_memories(
                    query=transcript,
                    session_id=session_id,
                    k=3
                )
                if memories:
                    context = "Relevant context from conversation history:\n"
                    for mem in memories:
                        context += f"- {mem['content']}\n"
                    context += "\n"
            except Exception as e:
                logger.warning("memory_search_failed", error=str(e))

        prompt = f"{context}Current utterance: {transcript}"

        async with get_http_client() as client:
            response = await client.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    "format": "json",
                    "temperature": 0.1,
                    "num_predict": 50,
                    "stream": False,
                }
            )
            response.raise_for_status()
            return response.json()

    async def classify(self, transcript: str) -> IntentResult:
        start_time = time.time()
        if not transcript or not transcript.strip():
            return IntentResult(
                intent="generalInquiry",
                entities={},
                confidence=0.0,
                reasoning="Empty transcript"
            )

        try:
            data = await retry_ollama.execute(self._call_ollama, transcript)
            content = data.get("message", {}).get("content", "{}")

            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                result = {}

            if not result.get("intent"):
                return await self._keyword_fallback(transcript)

            return IntentResult(
                intent=result.get("intent", "agent_handoff"),
                entities=result.get("entities", {}),
                confidence=result.get("confidence", 0.5),
                reasoning=result.get("reasoning", "")
            )
        except Exception as e:
            logger.error("intent_classification_error", error=str(e))
            return await self._keyword_fallback(transcript)
        finally:
            duration = time.time() - start_time
            track_llm_latency(duration, model="ollama")

    async def classify_with_retry(self, transcript: str, max_retries: int = 3) -> IntentResult:
        last_error = None
        for attempt in range(max_retries):
            try:
                return await self.classify(transcript)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        return IntentResult(
            intent="agent_handoff",
            entities={},
            confidence=0.0,
            reasoning=f"Failed after {max_retries} attempts: {str(last_error)}"
        )

    async def classify_with_fallback(self, transcript: str, fallback_intent: str = "generalInquiry") -> IntentResult:
        result = await self.classify(transcript)

        if result.confidence < 0.5:
            return IntentResult(
                intent=fallback_intent,
                entities=result.entities,
                confidence=0.5,
                reasoning=f"Low confidence ({result.confidence}), defaulting to {fallback_intent}"
            )

        return result


classifier = IntentClassifier()


