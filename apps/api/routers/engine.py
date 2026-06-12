import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response

from apps.api.services import loader, validators
from apps.api.services.actions import Actions
from apps.api.services.engine import ProtocolVM, VMState
from apps.api.services.router import router as route_resolver


def build_xml_response(message: str) -> str:
    """Build a simple XML response for Fonoster (replaces Twilio MessagingResponse)."""
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{message}</Message></Response>'


router = APIRouter(prefix="/engine", tags=["engine"])


def prompt_for(state: VMState) -> str:
    n = state.node
    if n == "ask_q1":
        return "What's this about?\n1 Refill\n2 Billing\n3 Order Status\n4 Tech Support\n9 Other"
    if n == "ask_q2_refill":
        return "Refill:\n1 Using Rx ID\n2 Doctor Callback\n3 Pharmacy Transfer"
    if n == "ask_q2_billing":
        return "Billing:\n1 Invoice\n2 Refund\n3 Copay\n4 Past-due Balance"
    if n == "ask_q2_status":
        return "Status:\n1 Order\n2 Shipment\n3 Backorder"
    if n == "ask_q2_tech":
        return "Tech Support:\n1 Password\n2 App Error\n3 Pairing"
    if n == "agent_handoff":
        return "Transferring to an agent. Please wait..."
    return "..."


@router.post("/twilio/sms")
async def inbound_sms(request: Request, From: str = Form(...), Body: str = Form(...)):
    try:
        r = request.app.state.redis
        sid = f"sms:{From}"
        raw = r.get(f"session:{sid}")
        if raw:
            state = VMState(**json.loads(raw))
        else:
            state = VMState(protocol_id="bootstrap_q1", node="ask_q1", fields={"phone": From, "session_id": sid}, transcript=[])
    except Exception:
        sid = f"sms:{From}"
        state = VMState(protocol_id="bootstrap_q1", node="ask_q1", fields={"phone": From, "session_id": sid}, transcript=[])

    actions = Actions(request.app.state.redis)
    vm = ProtocolVM(loader, validators, actions)

    if state.protocol_id == "bootstrap_q1":
        if state.node == "ask_q1":
            mapping = {"1": "refill", "2": "billing", "3": "status", "4": "tech-support", "9": "other"}
            sel = mapping.get(Body.strip())
            if not sel:
                prompt = prompt_for(state)
            else:
                state.fields["q1"] = sel
                next_node = "ask_q2_" + ("tech" if sel == "tech-support" else sel)
                state.node = next_node
                prompt = prompt_for(state)
        elif state.node.startswith("ask_q2_"):
            q1 = state.fields.get("q1")
            m = {
                "billing": {"1": "invoice", "2": "refund", "3": "copay", "4": "balance"},
                "refill": {"1": "id_lookup", "2": "doctor_callback", "3": "pharmacy_transfer"},
                "status": {"1": "order", "2": "shipment", "3": "backorder"},
                "tech": {"1": "password", "2": "app_error", "3": "pairing"},
                "other": {"1": "agent", "2": "voicemail", "3": "faq"}
            }
            key = "tech" if q1 == "tech-support" else q1
            sel = m.get(key, {}).get(Body.strip())
            if not sel:
                prompt = prompt_for(state)
            else:
                info = route_resolver.route(q1, sel)
                state.route_key = f"{q1}:{sel}"
                state.protocol_id = info["protocol_id"]
                state.node = "start"
                state.fields.update({"queue": info["queue"], "protocol_id": info["protocol_id"]})
                prompt = "Starting your flow..."
        else:
            prompt = "..."
    else:
        state = vm.step(state, Body.strip())
        prompt = prompt_for(state)

    try:
        r.setex(f"session:{sid}", 1800, json.dumps(state.__dict__))
    except Exception:
        pass

    return Response(content=build_xml_response(prompt), media_type="application/xml")
