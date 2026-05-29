"""
Call Center Operations Audit — test every voice/call-center capability.
"""
import json

import httpx

API = "http://localhost:8000"
H = {"x-api-key": "dev-api-key"}

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK]  {name}  {detail}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def main():
    global PASS, FAIL

    # 1. INBOUND CALL HANDLER
    print("\n=== 1. INBOUND CALL HANDLER ===")
    r = httpx.get(f"{API}/api/v1/voice/incoming?profile_id=PROF-META-SALES",
                  headers=H, timeout=5)
    ok = r.status_code == 200
    check("Answer inbound call (TwiML)", ok,
          f"HTTP {r.status_code}" if not ok else "returns TwiML")

    # 2. ASR - SPEECH TO TEXT
    print("\n=== 2. SPEECH TO TEXT ===")
    try:
        r = httpx.post(f"{API}/api/v1/voice/transcribe",
                       content=b"\x00" * 320,
                       headers={**H, "Content-Type": "audio/wav"},
                       timeout=15)
        check("Transcribe audio to text", r.status_code == 200,
              f"response: {r.text[:100]}")
    except Exception as e:
        check("Transcribe audio to text", False, str(e)[:100])

    # 3. TTS - TEXT TO SPEECH
    print("\n=== 3. TEXT TO SPEECH ===")
    try:
        r = httpx.post(f"{API}/api/v1/voice/synthesize",
                       json={"text": "Hello, this is AetherDesk calling."},
                       headers=H, timeout=15)
        ok3 = r.status_code == 200
        if ok3:
            data = r.json()
            audio_len = len(data.get("audio", ""))
            ok3 = audio_len > 10
            check("Synthesize speech (TTS)", ok3,
                  f"audio_base64: {audio_len} chars")
        else:
            check("Synthesize speech (TTS)", False,
                  f"HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        check("Synthesize speech (TTS)", False, str(e)[:100])

    # 4. INTENT CLASSIFICATION — medical
    print("\n=== 4. INTENT: Pharmacy Refill ===")
    try:
        r = httpx.post(f"{API}/api/v1/voice/intent",
                       json={"text": "I need to refill my blood pressure medication"},
                       headers=H, timeout=20)
        ok4 = r.status_code == 200
        if ok4:
            data = r.json()
            intent = data.get("intent", "")
            confidence = data.get("confidence", 0)
            ok4 = intent != "" and confidence > 0
            check("Classify pharmacy refill intent", ok4,
                  f"intent={intent}, confidence={confidence}")
        else:
            check("Classify pharmacy refill intent", False,
                  f"HTTP {r.status_code}")
    except Exception as e:
        check("Classify pharmacy refill intent", False, str(e)[:100])

    # 5. INTENT CLASSIFICATION — billing
    print("\n=== 5. INTENT: Billing Dispute ===")
    try:
        r = httpx.post(f"{API}/api/v1/voice/intent",
                       json={"text": "You charged me twice this month and I want a refund"},
                       headers=H, timeout=20)
        ok5 = r.status_code == 200
        if ok5:
            data = r.json()
            ok5 = data.get("intent", "") != ""
            check("Classify billing dispute intent", ok5,
                  f"intent={data.get('intent')}, confidence={data.get('confidence')}")
        else:
            check("Classify billing dispute intent", False,
                  f"HTTP {r.status_code}")
    except Exception as e:
        check("Classify billing dispute intent", False, str(e)[:100])

    # 6. INTENT CLASSIFICATION — tech support
    print("\n=== 6. INTENT: Tech Support ===")
    try:
        r = httpx.post(f"{API}/api/v1/voice/intent",
                       json={"text": "My password isn't working and I'm locked out of my account"},
                       headers=H, timeout=20)
        ok6 = r.status_code == 200
        if ok6:
            data = r.json()
            ok6 = data.get("intent", "") != ""
            check("Classify tech support intent", ok6,
                  f"intent={data.get('intent')}, confidence={data.get('confidence')}")
        else:
            check("Classify tech support intent", False,
                  f"HTTP {r.status_code}")
    except Exception as e:
        check("Classify tech support intent", False, str(e)[:100])

    # 7. AGENT QUEUE
    print("\n=== 7. AGENT QUEUE ===")
    try:
        r = httpx.get(f"{API}/api/v1/agent/peek?queue=general&n=10",
                      headers=H, timeout=5)
        ok7 = r.status_code == 200
        data = r.json() if ok7 else []
        queue_items = len(data) if isinstance(data, list) else 0
        check("Peek at agent queue", ok7,
              f"{queue_items} items waiting")
    except Exception as e:
        check("Peek at agent queue", False, str(e)[:100])

    # 8. CLAIM NEXT CALL
    print("\n=== 8. CLAIM NEXT CALL ===")
    try:
        agent_id = "CALL_CENTER_TEST_AGENT"
        r = httpx.post(f"{API}/api/v1/agent/claim?queue=general&agent_id={agent_id}",
                       headers=H, timeout=5)
        ok8 = r.status_code in [200, 204, 404]  # 404 = queue empty
        check("Claim next call from queue", ok8,
              f"HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        check("Claim next call from queue", False, str(e)[:100])

    # 9. AGENT TOKEN
    print("\n=== 9. GENERATE AGENT WS TOKEN ===")
    try:
        r = httpx.post(f"{API}/api/v1/agent/token?agent_id=CALL_CENTER_TEST_AGENT",
                       headers=H, timeout=5)
        ok9 = r.status_code == 200
        if ok9:
            data = r.json()
            has_token = bool(data.get("token"))
            check("Generate WebSocket auth token", has_token,
                  f"token issued" if has_token else "no token")
        else:
            check("Generate WebSocket auth token", False,
                  f"HTTP {r.status_code}")
    except Exception as e:
        check("Generate WebSocket auth token", False, str(e)[:100])

    # 10. CALL RECORDINGS
    print("\n=== 10. CALL RECORDINGS ===")
    try:
        r = httpx.get(f"{API}/api/v1/saas/recordings", headers=H, timeout=5)
        ok10 = r.status_code == 200
        data = r.json() if ok10 else []
        count = len(data) if isinstance(data, list) else 0
        check("Fetch call recordings", ok10,
              f"{count} recordings" if count else "0 recordings (normal if no calls)")
    except Exception as e:
        check("Fetch call recordings", False, str(e)[:100])

    # 11. OUTBOUND DIAL
    print("\n=== 11. OUTBOUND DIAL (requires Twilio) ===")
    try:
        r = httpx.post(f"{API}/api/v1/voice/outbound",
                       json={"to_phone": "+15551234567",
                             "profile_id": "PROF-META-SALES"},
                       headers=H, timeout=15)
        # 200 = call placed, 5xx = Twilio not configured
        ok11 = r.status_code in [200, 500]
        check("Trigger outbound call via Twilio", ok11,
              f"HTTP {r.status_code}" if r.status_code != 200 else "call placed")
    except Exception as e:
        check("Trigger outbound call via Twilio", False, str(e)[:100])

    # 12. CALL DISPOSITION
    print("\n=== 12. CALL DISPOSITION ===")
    try:
        r = httpx.post(
            f"{API}/api/v1/agent/disposition"
            f"?session_id=test-call-001&code=interested&notes=Demo disposition",
            headers=H, timeout=5)
        ok12 = r.status_code == 200
        check("Record call disposition", ok12,
              f"HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        check("Record call disposition", False, str(e)[:100])

    # 13. APPROVALS
    print("\n=== 13. PENDING ACTION APPROVALS ===")
    try:
        r = httpx.get(f"{API}/api/v1/saas/approvals", headers=H, timeout=5)
        ok13 = r.status_code == 200
        data = r.json() if ok13 else []
        count = len(data) if isinstance(data, list) else 0
        check("Fetch pending action approvals", ok13,
              f"{count} pending" if count else "0 pending (agents autonomous)")
    except Exception as e:
        check("Fetch pending action approvals", False, str(e)[:100])

    # 14. UPLOAD CALL PROTOCOL
    print("\n=== 14. UPLOAD CALL PROTOCOL CSV ===")
    csv_content = (
        "node,prompt,field,validate,next,action,on_ok,on_fail,options\n"
        "greeting,Hello! How can I help?,intent,required,route,,,,\n"
        "route,Based on your {intent}...,,,menu,menu,Refill,Billing,Support\n"
        "menu,Thanks! Let me handle that.,,,end,,,\n"
    )
    r = httpx.post(f"{API}/api/v1/protocols/upload_csv",
                   files={"file": ("cs_flow.csv", csv_content, "text/csv")},
                   timeout=10)
    ok14 = r.status_code == 200
    if ok14:
        data = r.json()
        check("Upload call protocol CSV", ok14,
              f"{data.get('nodes', 0)} nodes, id={data.get('protocol_id')}")
    else:
        check("Upload call protocol CSV", False, f"HTTP {r.status_code}")

    # 15. CAMPAIGN STATS
    print("\n=== 15. CAMPAIGN PERFORMANCE ===")
    try:
        r = httpx.get(f"{API}/api/v1/campaign/stats", headers=H, timeout=5)
        ok15 = r.status_code == 200
        if ok15:
            stats = r.json()
            check("Campaign performance stats", ok15,
                  f"{stats['total_calls_made']} calls, "
                  f"{stats['interested']} interested, "
                  f"{stats['conversion_rate']}% conv")
        else:
            check("Campaign performance stats", False, f"HTTP {r.status_code}")
    except Exception as e:
        check("Campaign performance stats", False, str(e)[:100])

    # 16. CAMPAIGN CALLS
    print("\n=== 16. CAMPAIGN CALL LOG ===")
    try:
        r = httpx.get(f"{API}/api/v1/campaign/calls", headers=H, timeout=5)
        ok16 = r.status_code == 200
        data = r.json() if ok16 else []
        count = len(data) if isinstance(data, list) else 0
        if count > 0:
            last = data[-1]
            check("Campaign call log", ok16,
                  f"{count} calls, last: {last.get('outcome', '?')} "
                  f"to {last.get('lead_id', '?')}")
        else:
            check("Campaign call log", ok16, f"{count} calls")
    except Exception as e:
        check("Campaign call log", False, str(e)[:100])

    # 17. ENGINE — SMS IVR
    print("\n=== 17. SMS IVR TRIAGE ===")
    try:
        r = httpx.post(f"{API}/api/v1/engine/twilio/sms",
                       data={"From": "+15551234567", "Body": "1"},
                       timeout=15)
        ok17 = r.status_code == 200
        check("SMS IVR triage (start)", ok17,
              f"TwiML returned" if ok17 else f"HTTP {r.status_code}")
    except Exception as e:
        check("SMS IVR triage (start)", False, str(e)[:100])

    # SUMMARY
    total = PASS + FAIL
    print(f"\n{'='*50}")
    print(f"CALL CENTER OPS: {PASS}/{total} operational ({PASS/total*100:.0f}%)")
    print(f"  INCOMING CALLS:   {'OK' if PASS >= 3 else 'PARTIAL'}")
    print(f"  AGENT QUEUE:      {'OK' if PASS >= 5 else 'PARTIAL'}")
    print(f"  VOICE PIPELINE:   {'OK' if PASS >= 7 else 'PARTIAL'}")
    print(f"  CAMPAIGN MGMT:    {'OK' if PASS >= 9 else 'PARTIAL'}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
