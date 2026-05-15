import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import agentops
import httpx
import structlog

from apps.api.services.actions import Actions
from apps.api.services.security_guard import detect_prompt_injection, redact_pii

# Initialize AgentOps for Observability (Checklist Section 5)
AGENTOPS_API_KEY = os.getenv("AGENTOPS_API_KEY")
if AGENTOPS_API_KEY:
    agentops.init(AGENTOPS_API_KEY, default_tags=["aetherdesk-saas"])


@dataclass
class AgentResponse:
    text: str
    sources: list[str]
    needs_agent: bool = False
    action_taken: str | None = None
    sentiment: str = "neutral"
    latency_ms: float = 0.0


logger = structlog.get_logger()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
OLLAMA_SUPERVISOR_MODEL = os.getenv("OLLAMA_SUPERVISOR_MODEL", OLLAMA_MODEL)


def sanitize_user_input(text: str, max_length: int = 2000) -> str:
    """Truncate and strip injection attempts from user input using NLP guards."""
    text = text[:max_length].strip()
    is_injection, confidence = detect_prompt_injection(text)

    if is_injection:
        logger.warning("prompt_injection_detected", input_preview=text[:100], confidence=confidence)
        return "[Customer asked a question]"
    return text


# Base ReAct Agent
class ReActAgent:
    def __init__(self, name: str, system_prompt: str, tools: list[str], actions: Actions):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.actions = actions
        self.model = OLLAMA_MODEL
        self.host = OLLAMA_HOST

    async def _execute_tool(self, tool_name: str, tool_input: str, tenant_id: str) -> str:
        # Optimization: Track tool execution in AgentOps
        tool_event = agentops.ToolEvent(name=tool_name, params={"input": tool_input})

        if tool_name not in self.tools:
            return f"Tool {tool_name} not permitted for agent {self.name}."

        if tool_name == "lookup_invoice":
            res = await self.actions.run("lookup_invoice", {"invoice_id": tool_input}, tenant_id=tenant_id)
            agentops.record(tool_event)
            if res.get("success"):
                data = res.get("data", {})
                return f"Invoice {tool_input} found. Status: {data.get('status', 'Unknown')}, Amount: {data.get('amount', '$0.00')}, Due: {data.get('due_date', 'Unknown')}"
            return f"Could not find invoice {tool_input}"
        elif tool_name == "get_order_status":
            res = await self.actions.run("get_order_status", {"order_id": tool_input}, tenant_id=tenant_id)
            agentops.record(tool_event)
            if res.get("success"):
                data = res.get("data", {})
                return f"Order {tool_input} found. Status: {data.get('status', 'Unknown')}, Expected Delivery: {data.get('expected_delivery', 'Unknown')}"
            return f"Could not find order {tool_input}"
        elif tool_name == "search_knowledge_base":
            from apps.api.services.rag import rag_service
            results = await rag_service.query(tool_input, k=2)
            agentops.record(tool_event)
            if not results:
                return "No information found."
            return "\n".join([f"- {r['content']}" for r in results])
        elif tool_name == "handoff_to_human":
            await self.actions.run("handoff", {"queue": "general", "reason": tool_input}, tenant_id=tenant_id)
            agentops.record(tool_event)
            return "Handoff initiated."
        elif tool_name == "escalate_to_supervisor":
            agentops.record(tool_event)
            return "Escalated back to supervisor."
        elif tool_name.startswith("mcp_"):
            from apps.api.services.mcp_client import mcp_manager
            result = await mcp_manager.execute_tool(tenant_id, tool_name, tool_input)
            agentops.record(tool_event)  # Log completion
            return result
        else:
            agentops.record(tool_event)  # Log completion
            return f"Unknown tool: {tool_name}"

    async def step(self, history: list[dict[str, str]], user_input: str, tenant_id: str) -> AgentResponse:
        start_ts = time.time()

        # Start AgentOps Session for this specific interaction
        ao_session = agentops.start_session(tags=[tenant_id, self.name])

        try:
            # Load profile for settings
            from apps.api.services.database import db_context, USE_POSTGRES

            async with db_context() as conn:
                if USE_POSTGRES:
                    profile = await conn.fetchrow("SELECT * FROM agent_profiles WHERE name = $1", self.name)
                else:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM agent_profiles WHERE name = ?", (self.name,))
                    profile = cursor.fetchone()
            params = json.loads(profile["parameters"] or "{}") if profile else {}
            require_approval = params.get("require_approval_on", [])

            # Long-term Memory Injection (Optimization: Mem0 concept)
            from apps.api.services.memory_service import memory_service
            customer_id = history[0].get("customer_id", "unknown") if history else "unknown"
            memories = await memory_service.get_memories(tenant_id, customer_id)

            system_content = self.system_prompt
            if memories:
                memory_context = "\n".join([f"- {m}" for m in memories])
                system_content += f"\n\nLONG-TERM CUSTOMER MEMORIES:\n{memory_context}"

            messages = [{"role": "system", "content": system_content}]
            for msg in history:
                role = "user" if msg["from"] == "customer" else "assistant"
                content = msg["text"]
                if role == "assistant":
                    content = json.dumps({"thought": "continuing", "response": content})
                messages.append({"role": role, "content": content})

            messages.append({"role": "user", "content": user_input})

            needs_agent = False
            action_taken = None

            async with httpx.AsyncClient(timeout=60.0) as client:
                for attempt in range(2):  # Self-healing retry loop
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
                        ai_msg = response.json().get("message", {}).get("content", "")

                        try:
                            parsed = json.loads(ai_msg)
                        except json.JSONDecodeError:
                            # SELF-HEALING: Prompt the model to fix its JSON
                            logger.warning("self_healing_triggered", reason="json_decode_error")
                            messages.append({"role": "assistant", "content": ai_msg})
                            messages.append({"role": "user", "content": "Your previous response was not valid JSON. Please respond with ONLY JSON."})
                            continue

                        if "response" in parsed:
                            latency = (time.time() - start_ts) * 1000
                            ao_session.end_session(end_state="Success")
                            return AgentResponse(
                                text=parsed["response"],
                                sources=[],
                                needs_agent=needs_agent,
                                action_taken=action_taken,
                                sentiment="neutral",
                                latency_ms=latency
                            )

                        if "tool" in parsed:
                            tool_name = parsed["tool"]
                            tool_input = str(parsed.get("tool_input", ""))

                            # SUPERVISION CHECK
                            if tool_name in require_approval:
                                logger.info("supervision_required", action=tool_name)
                                # Create approval request in DB
                                from apps.api.services.database import USE_POSTGRES
                                approval_id = f"APP-{uuid.uuid4().hex[:6].upper()}"
                                async with db_context() as conn:
                                    if USE_POSTGRES:
                                        await conn.execute(
                                            "INSERT INTO action_approvals (id, tenant_id, session_id, agent_id, action, params) VALUES ($1, $2, $3, $4, $5, $6)",
                                            approval_id, tenant_id, "SESS-LIVE", self.name, tool_name, tool_input
                                        )
                                    else:
                                        cursor = conn.cursor()
                                        cursor.execute(
                                            "INSERT INTO action_approvals (id, tenant_id, session_id, agent_id, action, params) VALUES (?, ?, ?, ?, ?, ?)",
                                            (approval_id, tenant_id, "SESS-LIVE", self.name, tool_name, tool_input)
                                        )
                                        conn.commit()
                                return AgentResponse(text=f"I need supervisor approval to perform '{tool_name}'. Please wait.", sources=[], needs_agent=False, action_taken="pending_approval")

                            action_taken = tool_name
                            tool_result = await self._execute_tool(tool_name, tool_input, tenant_id)
                            # Push real-time alert if handoff is happening
                            if tool_name in ("handoff_to_human", "escalate_to_supervisor"):
                                from apps.api.routers.campaign import push_escalation_alert
                                asyncio.create_task(push_escalation_alert(
                                    call_sid="LIVE", reason=f"Agent requested {tool_name}: {tool_input}", agent_name=self.name
                                ))

                            messages.append({"role": "assistant", "content": ai_msg})
                            messages.append({"role": "user", "content": f"Tool '{tool_name}' returned: {tool_result}"})
                            continue

                    except Exception as e:
                        logger.error("agent_step_error", error=str(e))
                        if attempt == 0:
                            continue
                        # Push escalation for crash recovery
                        from apps.api.routers.campaign import push_escalation_alert
                        asyncio.create_task(push_escalation_alert(
                            call_sid="LIVE", reason=f"Agent crash: {str(e)[:100]}", agent_name=self.name
                        ))
                        return AgentResponse(text="I'm having trouble processing that right now.", sources=[], needs_agent=True)

            # Max steps exhausted - push alert
            from apps.api.routers.campaign import push_escalation_alert
            asyncio.create_task(push_escalation_alert(
                call_sid="LIVE", reason="Agent max reasoning steps exhausted", agent_name=self.name
            ))
            return AgentResponse(text="I need to transfer you to an agent as this is taking too long.", sources=[], needs_agent=True)
        finally:
            # Ensure AgentOps session is ended
            try:
                ao_session.end_session(end_state="Success")
            except Exception:
                pass

    async def record_session(self, session_id: str, history: list[dict], tenant_id: str):
        # Quality Assurance & Benchmarking
        import uuid

        from apps.api.services.database import db_context, USE_POSTGRES

        async with db_context() as conn:
            if USE_POSTGRES:
                settings_row = await conn.fetchrow(
                    "SELECT redact_pii FROM tenant_settings WHERE tenant_id = $1",
                    tenant_id
                )
            else:
                cursor = conn.cursor()
                cursor.execute("SELECT redact_pii FROM tenant_settings WHERE tenant_id = ?", (tenant_id,))
                settings_row = cursor.fetchone()
            redact = bool(settings_row["redact_pii"]) if settings_row else True

            transcript_lines = []
            for m in history:
                text = m['text']
                if redact:
                    # Advanced NLP PII Redaction via Presidio
                    text = redact_pii(text)
                transcript_lines.append(f"{m['from']}: {text}")

            transcript = "\n".join(transcript_lines)
            # Mock QA Scoring
            score = 0.85 if "thank" in transcript.lower() else 0.5
            feedback = "Great empathy" if score > 0.8 else "Needs more engagement"

            rec_id = f"REC-{uuid.uuid4().hex[:6].upper()}"
            if USE_POSTGRES:
                await conn.execute(
                    "INSERT INTO session_recordings (id, tenant_id, session_id, transcript, qa_score, qa_feedback) VALUES ($1, $2, $3, $4, $5, $6)",
                    rec_id, tenant_id, session_id, transcript, score, feedback
                )
            else:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO session_recordings (id, tenant_id, session_id, transcript, qa_score, qa_feedback) VALUES (?, ?, ?, ?, ?, ?)",
                    (rec_id, tenant_id, session_id, transcript, score, feedback)
                )
                conn.commit()

        # Optimization: Persist long-term facts (Mem0 concept)
        from apps.api.services.memory_service import memory_service
        # In production, we'd pass a real customer_id here
        asyncio.create_task(memory_service.add_memories(tenant_id, "CUST-DEFAULT", transcript))


class TenantAgent(ReActAgent):
    def __init__(self, tenant_id: str, profile_id: str, actions: Actions):
        self.tenant_id = tenant_id
        self.profile_id = profile_id
        self._initialized = False
        self._name = None
        self._system_prompt = None
        self._tools = None
        self._actions = actions
        super().__init__(name="lazy", system_prompt="", tools=[], actions=actions)

    async def _ensure_initialized(self):
        if self._initialized:
            return
        from apps.api.services.database import db_context, USE_POSTGRES

        async with db_context() as conn:
            if USE_POSTGRES:
                row = await conn.fetchrow("SELECT * FROM agent_profiles WHERE id = $1 AND tenant_id = $2", self.profile_id, self.tenant_id)
            else:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM agent_profiles WHERE id = ? AND tenant_id = ?", (self.profile_id, self.tenant_id))
                row = cursor.fetchone()

            if not row:
                raise ValueError(f"Profile {self.profile_id} not found for tenant {self.tenant_id}")

            params = json.loads(row["parameters"] or "{}")
            agent_tools = params.get("tools", ["search_knowledge_base", "handoff_to_human"])

            if USE_POSTGRES:
                settings_row = await conn.fetchrow("SELECT mcp_servers FROM tenant_settings WHERE tenant_id = $1", self.tenant_id)
            else:
                cursor = conn.cursor()
                cursor.execute("SELECT mcp_servers FROM tenant_settings WHERE tenant_id = ?", (self.tenant_id,))
                settings_row = cursor.fetchone()

        if settings_row and settings_row["mcp_servers"]:
            try:
                from apps.api.services.mcp_client import mcp_manager
                asyncio.create_task(mcp_manager.initialize_tenant_servers(self.tenant_id, settings_row["mcp_servers"]))
                mcp_tools = mcp_manager.get_available_tools(self.tenant_id)
                for t in mcp_tools:
                    agent_tools.append(t["name"])
            except Exception as e:
                logger.warning("mcp_init_skipped", error=str(e))

        self._name = row["name"]
        self._system_prompt = row["prompt"]
        self._tools = agent_tools
        self.name = self._name
        self.system_prompt = self._system_prompt
        self.tools = self._tools
        self._initialized = True

    @property
    def name(self):
        return self._name or "TenantAgent"

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def system_prompt(self):
        return self._system_prompt or ""

    @system_prompt.setter
    def system_prompt(self, value):
        self._system_prompt = value

    @property
    def tools(self):
        return self._tools or []

    @tools.setter
    def tools(self, value):
        self._tools = value


class Orchestrator:
    def __init__(self, actions: Actions):
        self.actions = actions
        self.agents = {}  # Cache or registry

    async def get_agent(self, tenant_id: str, profile_id: str):
        key = f"{tenant_id}:{profile_id}"
        if key not in self.agents:
            self.agents[key] = TenantAgent(tenant_id, profile_id, self.actions)
        return self.agents[key]

    async def route_to_agent(self, history: list[dict[str, str]], user_input: str) -> str:
        """Supervisor routing logic to determine the correct department."""
        messages = [
            {"role": "system", "content": "You are a supervisor. Route the customer to 'billing', 'ops', or 'human'. Respond ONLY with JSON like {'thought': '...', 'route_to': '...'}"},
        ]
        for msg in history:
            messages.append({"role": "user" if msg["from"] == "customer" else "assistant", "content": msg["text"]})
        messages.append({"role": "user", "content": user_input})

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{OLLAMA_HOST}/api/chat",
                    json={
                        "model": OLLAMA_SUPERVISOR_MODEL,
                        "messages": messages,
                        "temperature": 0.0,
                        "format": "json",
                        "stream": False
                    }
                )
                response.raise_for_status()
                content = response.json().get("message", {}).get("content", "{}")
                parsed = json.loads(content)
                route = parsed.get("route_to", "human")

                # Validation
                if route not in ["billing", "ops", "human"]:
                    return "human"
                return route
        except Exception as e:
            logger.error("supervisor_routing_error", error=str(e))
            return "human"

    async def step(self, session_state: dict[str, Any], history: list[dict[str, str]], user_input: str, tenant_id: str, profile_id: str = "PROF-001") -> AgentResponse:
        user_input = sanitize_user_input(user_input)

        try:
            # ENFORCEMENT: Check active rentals
            from apps.api.services.database import db_context, USE_POSTGRES

            rental = None
            async with db_context() as conn:
                if USE_POSTGRES:
                    result = await conn.fetchval(
                        "SELECT id FROM rentals WHERE profile_id = $1 AND status = 'active'",
                        profile_id
                    )
                    if result:
                        rental = {"id": result}
                else:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM rentals WHERE profile_id = ? AND status = 'active'", (profile_id,))
                    row = cursor.fetchone()
                    if row:
                        rental = {"id": row["id"]}

            if not rental:
                logger.warning("no_active_rental", tenant=tenant_id, profile=profile_id)
                return AgentResponse(text="This AI Agent is currently offline (No active rental).", sources=[], needs_agent=True)

            agent = await self.get_agent(tenant_id, profile_id)
            response = await agent.step(history, user_input, tenant_id=tenant_id)

            # Update session state based on agent response
            if response.needs_agent:
                session_state["active_agent"] = None
            elif response.action_taken == "escalate":
                session_state["active_agent"] = None
                response.text = "Let me check with another department."
            else:
                session_state["active_agent"] = profile_id

            return response
        except Exception as e:
            logger.error("orchestrator_error", error=str(e))
            return AgentResponse(text="I'm sorry, I'm having trouble connecting to my brain right now.", sources=[], needs_agent=True)
