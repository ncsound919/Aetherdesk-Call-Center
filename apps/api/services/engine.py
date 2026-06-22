
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class VMState:
    protocol_id: str
    node: str
    fields: dict[str, Any]
    transcript: list
    route_key: str | None = None
    prompt: str | None = None
    audio_prompt: bytes | None = None

class ProtocolVM:
    def __init__(self, loader, validators, actions):
        self.loader = loader
        self.validators = validators
        self.actions = actions

    async def step(self, state: VMState, user_input: str) -> VMState:
        if user_input.strip().lower() in ["0","agent","help","operator"]:
            return self._advance(state, "agent_handoff", "escape_hatch")

        proto = self.loader.load(state.protocol_id)
        if not proto:
            return self._advance(state, "agent_handoff", "protocol_not_found")

        nodes = proto.get("nodes", {})
        node = nodes.get(state.node)
        if not node:
            return self._advance(state, "agent_handoff", "node_not_found")

        if "field" in node:
            rule = node.get("validate")
            if rule and not self.validators.validate(rule, user_input):
                return self._repeat(state, "validation_failed")
            state.fields[node["field"]] = user_input
            nxt = node.get("next","agent_handoff")
            return self._advance(state, nxt, f"field_set:{node['field']}")

        if "options" in node:
            target = self._resolve(node["options"], user_input)
            if not target:
                return self._repeat(state, "invalid_option")
            return self._advance(state, target, f"option_selected:{user_input}")

        if "action" in node:
            result = await self.actions.run(node["action"], state.fields)
            nxt = node.get("on_ok" if result.get("success") else "on_fail", "agent_handoff")
            return self._advance(state, nxt, f"action:{node['action']}")

        return self._advance(state, "agent_handoff", "no_rule")

    def _resolve(self, options, user_input):
        for opt in options:
            if ":" in opt:
                k, t = opt.split(":",1)
                if k.strip().lower() == user_input.strip().lower():
                    return t
        return None

    def _render_prompt(self, prompt: str, fields: dict[str, Any]) -> str:
        if not prompt:
            return ""

        def replacer(match):
            key = match.group(1).strip()
            return str(fields.get(key, ""))

        return re.sub(r"\{\{\s*(\w+)\s*\}\}", replacer, prompt)

    def get_prompt(self, state: VMState) -> str:
        proto = self.loader.load(state.protocol_id)
        if not proto:
            return ""
        node = proto.get("nodes", {}).get(state.node, {})
        return self._render_prompt(node.get("prompt", ""), state.fields)

    def _advance(self, state: VMState, nxt: str, reason: str) -> VMState:
        state.transcript.append({"from":state.node,"to":nxt,"reason":reason,"fields":dict(state.fields)})
        state.node = nxt
        return state

    def _repeat(self, state: VMState, reason: str) -> VMState:
        state.transcript.append({"from":state.node,"to":state.node,"reason":reason,"fields":dict(state.fields)})
        return state
