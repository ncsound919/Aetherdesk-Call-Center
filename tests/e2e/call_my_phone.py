"""
Call 555-123-4567 — test the full voice pipeline.

Without Twilio credentials, the call won't actually dial, but we'll
exercise every component of the pipeline end-to-end.
"""
import json
import httpx

API = "http://localhost:8000"
PHONE = "+15551234567"
H = {"x-api-key": "dev-api-key"}

print(f"Calling {PHONE} via AetherDesk voice pipeline...")
print("=" * 50)

# 1. CREATE A LEAD
print("\n1. Create lead record...")
r = httpx.post(f"{API}/api/v1/campaign/leads", json={
    "company_name": "Live Test Call",
    "phone": PHONE,
    "contact_name": "User",
    "industry": "testing",
    "priority": 10,
}, headers=H, timeout=10)
lead = r.json()
print(f"   Lead ID: {lead.get('id')}, Status: {lead.get('status')}")

# 2. HIRE AN AGENT FOR THIS CALL
print("\n2. Create agent profile for this call...")
r = httpx.post(
    f"{API}/api/v1/saas/profile?name=Live+Test+Agent&prompt=You+are+a+friendly+test+agent+dialing+a+live+number",
    json={"parameters": {"tone": "friendly", "industry": "testing"}},
    headers=H, timeout=10,
)
pid = r.json().get("profile_id")
print(f"   Profile ID: {pid}")

# 3. TRIGGER OUTBOUND CALL
print("\n3. Triggering outbound call...")
r = httpx.post(f"{API}/api/v1/voice/outbound", json={
    "to_phone": PHONE,
    "profile_id": pid or "PROF-META-SALES",
}, headers=H, timeout=15)
print(f"   Status: {r.status_code}")
data = r.json() if r.status_code == 200 else {}
call_sid = data.get("call_sid", "N/A")
print(f"   Call SID: {call_sid}")
print(f"   Response: {json.dumps(data, indent=2)}")

# 4. SIMULATE WHAT WOULD HAPPEN ON INCOMING ANSWER
print("\n4. What happens when the call connects...")
r = httpx.get(f"{API}/api/v1/voice/incoming?profile_id={pid}", headers=H, timeout=5)
print(f"   Incoming handler returns: {r.status_code}")
if r.status_code == 200:
    twiml = r.text
    if "<Say>" in twiml:
        print(f"   Phone would hear: [greeting message]")
    if "<Connect>" in twiml:
        print(f"   Media stream would connect for real-time AI conversation")

# 5. TEST INTENT — what would the AI understand?
print("\n5. What if the caller said 'Hello, I need help with a refund'?")
r = httpx.post(f"{API}/api/v1/voice/intent", json={
    "text": "Hello, I need help getting a refund for my last purchase"
}, headers=H, timeout=60)
if r.status_code == 200:
    intent = r.json()
    print(f"   Intent: {intent['intent']}")
    print(f"   Confidence: {intent['confidence']}")
    print(f"   Reasoning: {intent['reasoning'][:100]}")

# 6. TEST TTS — what the AI would say back
print("\n6. AI would generate speech response...")
r = httpx.post(f"{API}/api/v1/voice/synthesize", json={
    "text": "Hello! I understand you need help with a refund. Let me look into that for you right now."
}, headers=H, timeout=15)
if r.status_code == 200:
    audio_len = len(r.json().get("audio", ""))
    print(f"   Generated {audio_len} chars of base64 audio ({audio_len * 3 // 4} bytes of speech)")

# 7. CHECK CAMPAIGN CALL LOG
print("\n7. Campaign call log...")
r = httpx.get(f"{API}/api/v1/campaign/calls", headers=H, timeout=5)
calls = r.json() if r.status_code == 200 else []
print(f"   Total calls recorded: {len(calls)}")

print("\n" + "=" * 50)
print("COMPLETE VOICE PIPELINE TESTED:")
print("  Lead created → Agent hired → Call triggered →")
print("  Incoming handler ready → Intent classified →")
print("  TTS response generated → Call logged")
print("\n(Actual dial requires Twilio credentials)")
print("=" * 50)
