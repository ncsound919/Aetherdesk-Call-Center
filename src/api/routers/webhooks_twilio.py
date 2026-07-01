"""Twilio webhook handlers for voice calls and SMS."""

import html
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from twilio.request_validator import RequestValidator

router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])

async def validate_twilio_request(request: Request, x_twilio_signature: str = Header(default=None)):
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    is_dev = os.getenv("APP_ENV", "development") == "development"

    if is_dev and not auth_token:
        # Pure local-dev convenience: no token configured at all and we're
        # explicitly in dev mode. If a token IS configured, we still
        # validate below even in dev — this closes the gap where
        # APP_ENV=development silently skipped validation despite having
        # a real TWILIO_AUTH_TOKEN set.
        return True

    if not x_twilio_signature:
        raise HTTPException(status_code=403, detail="Missing Twilio Signature")

    if not auth_token:
        # Non-dev environment without a configured token: we cannot
        # validate the signature, so fail closed rather than silently
        # accepting the request.
        raise HTTPException(status_code=503, detail="TWILIO_AUTH_TOKEN not configured")

    validator = RequestValidator(auth_token)

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
    raw_call_sid = form.get("CallSid", "unknown")
    # Escape for safe use as a URL path segment and then again for the XML
    # attribute context, since CallSid originates from an external request.
    from urllib.parse import quote
    call_sid = quote(str(raw_call_sid), safe="")

    # Avoid hardcoded port 8000, construct stream URL robustly from TWILIO_WEBHOOK_BASE
    webhook_base = os.getenv("TWILIO_WEBHOOK_BASE")
    if webhook_base:
        from urllib.parse import urlparse
        parsed = urlparse(webhook_base)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = f"{ws_scheme}://{parsed.netloc}/realtime/call/{call_sid}"
    else:
        ws_scheme = "wss" if request.url.scheme == "https" else "ws"
        safe_netloc = html.escape(request.url.netloc)
        ws_url = f"{ws_scheme}://{safe_netloc}/realtime/call/{call_sid}"

    response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">
        Hello. You have reached AetherDesk AI. Please hold while I connect you.
    </Say>
    <Connect>
        <Stream url="{html.escape(ws_url, quote=True)}"/>
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

    from api.services.security_guard import mask_phone
    logger = get_logger()
    logger.info(
        "twilio_call_status",
        call_sid=call_sid,
        status=call_status,
        from_number=mask_phone(from_number),
        to_number=mask_phone(to_number),
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
    # Redact potentially sensitive DTMF/speech content: log only length and
    # a short, truncated preview rather than the raw value.
    digits_redacted = f"***len={len(digits)}" if digits else ""
    speech_redacted = (speech[:20] + "…") if len(speech) > 20 else speech
    logger.info(
        "twilio_gather",
        call_sid=call_sid,
        digits_len=len(digits),
        digits_redacted=digits_redacted,
        speech_preview=speech_redacted,
    )

    response = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Thank you. Your input has been received.</Say>
</Response>"""
    return HTMLResponse(content=response, media_type="application/xml")
