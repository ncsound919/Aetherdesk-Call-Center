"""Twilio webhook handlers for voice calls and SMS."""

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from twilio.request_validator import RequestValidator

router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])

async def validate_twilio_request(request: Request, x_twilio_signature: str = Header(default=None)):
    if os.getenv("APP_ENV", "development") == "development":
        return True

    if not x_twilio_signature:
        raise HTTPException(status_code=403, detail="Missing Twilio Signature")

    validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN", ""))

    # Reconstruct the URL using TWILIO_WEBHOOK_BASE if set, to handle reverse proxy setups correctly
    webhook_base = os.getenv("TWILIO_WEBHOOK_BASE")
    if webhook_base:
        from urllib.parse import urlparse
        parsed_base = urlparse(webhook_base)
        parsed_url = urlparse(str(request.url))
        url = parsed_url._replace(scheme=parsed_base.scheme, netloc=parsed_base.netloc).geturl()
    else:
        url = str(request.url)

    # Fastapi request.form() must be awaited and can only be consumed once unless using request.form() again because it caches.
    form_data = await request.form()
    params = {k: v for k, v in form_data.items()}

    if not validator.validate(url, params, x_twilio_signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio Signature")
    return True



@router.get("/ping")
def ping():
    return {"ok": True}


@router.post("/voice", dependencies=[Depends(validate_twilio_request)])
async def handle_incoming_voice(request: Request):
    """Twilio voice webhook — returns TwiML to handle incoming calls.

    When Twilio receives an incoming call to our number, it POSTs here.
    We return TwiML that connects the call to our AI agent via Media Streams.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")

    # Avoid hardcoded port 8000, construct stream URL robustly from TWILIO_WEBHOOK_BASE
    webhook_base = os.getenv("TWILIO_WEBHOOK_BASE")
    if webhook_base:
        from urllib.parse import urlparse
        parsed = urlparse(webhook_base)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = f"{ws_scheme}://{parsed.netloc}/realtime/call/{call_sid}"
    else:
        ws_scheme = "wss" if request.url.scheme == "https" else "ws"
        import html
        safe_netloc = html.escape(request.url.netloc)
        ws_url = f"{ws_scheme}://{safe_netloc}/realtime/call/{call_sid}"

    response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">
        Hello. You have reached AetherDesk AI. Please hold while I connect you.
    </Say>
    <Connect>
        <Stream url="{ws_url}"/>
    </Connect>
</Response>"""
    return HTMLResponse(content=response, media_type="application/xml")


@router.post("/call-status", dependencies=[Depends(validate_twilio_request)])
async def handle_call_status(request: Request):
    """Twilio call status webhook — receives call state changes."""
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    call_status = form.get("CallStatus", "unknown")
    from_number = form.get("From", "unknown")
    to_number = form.get("To", "unknown")

    from structlog import get_logger
    logger = get_logger()
    logger.info(
        "twilio_call_status",
        call_sid=call_sid,
        status=call_status,
        from_number=from_number,
        to_number=to_number,
    )

    # Forward every completed call status to BlockLabor so the
    # verification-webhook edge function can match it against
    # call_sessions (intent_detected = 'verification:...') and update
    # the relevant verification_status column.
    if call_status in ("completed", "failed", "no-answer", "busy", "canceled"):
        try:
            import httpx
            blocklabor_url = os.getenv("BLOCKLABOR_URL", "")
            blocklabor_key = os.getenv("BLOCKLABOR_API_KEY", "")
            if blocklabor_url and blocklabor_key:
                payload = {
                    "twilio_call_sid": call_sid,
                    "call_status": call_status,
                    "from_number": from_number,
                    "to_number": to_number,
                    "duration": form.get("CallDuration", "0"),
                    "recording_url": form.get("RecordingUrl", ""),
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{blocklabor_url}/functions/v1/verification-webhook",
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {blocklabor_key}",
                        },
                    )
        except Exception:
            # Never let a webhook failure break the Twilio flow.
            pass

    return JSONResponse({"ok": True})


@router.post("/gather", dependencies=[Depends(validate_twilio_request)])
async def handle_gather(request: Request):
    """Twilio Gather webhook — receives DTMF or speech input."""
    form = await request.form()
    digits = form.get("Digits", "")
    speech = form.get("SpeechResult", "")
    call_sid = form.get("CallSid", "unknown")

    from structlog import get_logger
    logger = get_logger()
    logger.info("twilio_gather", call_sid=call_sid, digits=digits, speech=speech)

    response = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Thank you. Your input has been received.</Say>
</Response>"""
    return HTMLResponse(content=response, media_type="application/xml")
