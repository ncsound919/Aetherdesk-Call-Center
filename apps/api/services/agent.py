import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

SYSTEM_PROMPT = """You are a helpful call center agent. Use the provided context from the knowledge base to answer customer questions.
If the context doesn't contain enough information to answer the question, provide a helpful response and suggest connecting to an agent.
Keep responses concise and natural for voice interaction.

Context from knowledge base:
{context}

Conversation history:
{history}

Customer: {question}
Agent:"""


@dataclass
class AgentResponse:
    text: str
    sources: list[str]
    needs_agent: bool
    action_taken: str | None = None


class AgentService:
    def __init__(
        self,
        model: str = None,
        host: str = None
    ):
        self.model = model or OLLAMA_MODEL
        self.host = host or OLLAMA_HOST
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=60.0,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def answer(
        self,
        question: str,
        context_results: list[dict[str, Any]],
        history: list[dict[str, str]] = None
    ) -> AgentResponse:
        if not context_results:
            return AgentResponse(
                text="I don't have enough information to answer that. Would you like to speak with an agent?",
                sources=[],
                needs_agent=True
            )

        context = "\n\n".join([
            f"- {r['content']}" for r in context_results
        ])

        history_text = "No previous conversation"
        if history:
            history_text = "\n".join([
                f"Customer: {h.get('customer', '')}\nAgent: {h.get('agent', '')}"
                for h in history[-3:]
            ])

        prompt = SYSTEM_PROMPT.format(
            context=context,
            history=history_text,
            question=question
        )

        client = self._get_client()

        try:
            response = await client.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": question}
                    ],
                    "temperature": 0.7,
                    "stream": False
                }
            )
            response.raise_for_status()
            data = response.json()

            answer_text = data.get("message", {}).get("content", "")
            sources = [r.get("metadata", {}).get("source", "unknown") for r in context_results]

            needs_agent = any(
                keyword in answer_text.lower()
                for keyword in ["i don't know", "can't help", "speak with an agent", "transfer"]
            )

            return AgentResponse(
                text=answer_text,
                sources=sources,
                needs_agent=needs_agent
            )

        except Exception as e:
            logger.error("agent_response_error", error=str(e))
            return AgentResponse(
                text="I'm having trouble processing that request. Please hold while I connect you to an agent.",
                sources=[],
                needs_agent=True
            )

    async def answer_with_rag(
        self,
        question: str,
        history: list[dict[str, str]] = None,
        use_rag: bool = True
    ) -> AgentResponse:
        from apps.api.services.rag import rag_service

        if use_rag:
            context_results = await rag_service.query(question, k=3)
        else:
            context_results = []

        return await self.answer(question, context_results, history)

agent_service = AgentService()


class DynamicAgent:
    def __init__(self, actions, model: str = None, host: str = None):
        self.model = model or OLLAMA_MODEL
        self.host = host or OLLAMA_HOST
        self._client: httpx.AsyncClient | None = None
        self.actions = actions

        self.system_prompt = """You are Aether, an autonomous AI call center agent.
You have access to the following tools:
- lookup_invoice(invoice_id): Returns the status and amount of an invoice.
- get_order_status(order_id): Returns the status of an order.
- search_knowledge_base(query): Searches the company knowledge base for policy information.
- handoff_to_human(reason): Transfers the call to a human agent.

To use a tool, you MUST output exactly this JSON format and nothing else:
{"thought": "reasoning here", "tool": "tool_name", "tool_input": "input"}

If you want to respond to the user, output exactly this JSON format and nothing else:
{"thought": "reasoning here", "response": "what to say to the user"}

Keep your responses natural, conversational, and concise for voice interaction.
"""

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def _execute_tool(self, tool_name: str, tool_input: str) -> str:
        from apps.api.services.rag import rag_service

        if tool_name == "lookup_invoice":
            res = self.actions.run("lookup_invoice", {"invoice_id": tool_input})
            if res.get("success"):
                return f"Invoice {tool_input} found. Status: Paid, Amount: $42.00"
            return f"Could not find invoice {tool_input}"
        elif tool_name == "get_order_status":
            return f"Order {tool_input} is currently processing and will ship tomorrow."
        elif tool_name == "search_knowledge_base":
            results = await rag_service.query(tool_input, k=2)
            if not results:
                return "No information found."
            return "\n".join([f"- {r['content']}" for r in results])
        elif tool_name == "handoff_to_human":
            self.actions.run("handoff", {"queue": "general", "reason": tool_input})
            return "Handoff initiated."
        else:
            return f"Unknown tool: {tool_name}"

    async def step(self, history: list[dict[str, str]], user_input: str) -> AgentResponse:
        client = self._get_client()

        messages = [{"role": "system", "content": self.system_prompt}]
        for msg in history:
            role = "user" if msg["from"] == "customer" else "assistant"
            content = msg["text"]
            if role == "assistant":
                content = json.dumps({"thought": "continuing conversation", "response": content})
            messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_input})

        max_steps = 3
        needs_agent = False
        action_taken = None

        for _step_idx in range(max_steps):
            for attempt in range(2): # SELF-HEALING LOOP
                try:
                    response = await client.post(
                        f"{self.host}/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": 0.1,
                            "stream": False,
                            "format": "json"
                        }
                    )
                    response.raise_for_status()
                    data = response.json()
                    ai_msg = data.get("message", {}).get("content", "")

                    try:
                        parsed = json.loads(ai_msg)
                        break # Success, exit retry loop
                    except json.JSONDecodeError:
                        logger.warning("agent_json_parse_error", raw=ai_msg)
                        if attempt == 0:
                            messages.append({"role": "assistant", "content": ai_msg})
                            messages.append({"role": "user", "content": "Your response was not valid JSON. Please repeat but ensure valid JSON format."})
                            continue
                        return AgentResponse(text="I'm sorry, I encountered an error processing that.", sources=[], needs_agent=True)
                except Exception as e:
                    logger.error("agent_step_error", error=str(e))
                    return AgentResponse(text="I'm having trouble processing that request right now.", sources=[], needs_agent=True)

            if "response" in parsed:
                if parsed.get("thought"):
                    logger.info("agent_thought", thought=parsed["thought"])
                return AgentResponse(
                    text=parsed["response"],
                    sources=[],
                    needs_agent=needs_agent,
                    action_taken=action_taken
                )

            if "tool" in parsed:
                tool_name = parsed["tool"]
                tool_input = str(parsed.get("tool_input", ""))
                logger.info("agent_tool_call", tool=tool_name, input=tool_input, thought=parsed.get("thought"))

                # SUPERVISION CHECK
                if tool_name == "handoff_to_human":
                    needs_agent = True

                tool_result = await self._execute_tool(tool_name, tool_input)
                logger.info("agent_tool_result", result=tool_result)

                messages.append({"role": "assistant", "content": ai_msg})
                messages.append({"role": "user", "content": f"Tool '{tool_name}' returned: {tool_result}"})
                continue

        return AgentResponse(text="I need to transfer you to an agent as this is taking too long.", sources=[], needs_agent=True)
