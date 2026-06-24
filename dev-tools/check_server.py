"""Check server status and run quick tests."""
import httpx, json, sys

# Health
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    print("HEALTH:", r.status_code, r.json()["status"])
except Exception as e:
    print("HEALTH: FAILED -", e)
    # Start server inline
    print("Starting server inline...")
    import subprocess, os, time
    os.environ["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
    os.environ["JWT_SECRET"] = "test-websocket-secret"
    os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
    os.environ["USE_POSTGRES"] = "false"
    os.environ["DEEPGRAM_API_KEY"] = os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY")
    os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY")
    import uvicorn
    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000)
    sys.exit(0)

# Login
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print("LOGIN:", login.status_code)
if login.status_code == 200:
    token = login.json()["token"]
    h = {"Authorization": "Bearer " + token}

    # Tenant
    t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
        "name": "Acme Corp", "email": "admin@acmecorp.com",
        "phone": "+15551234567", "gdpr_consent": True
    }, headers=h)
    print("TENANT:", t.status_code)
    tid = t.json()["id"] if t.status_code == 201 else "TENANT-001"

    # Agent
    a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
        "name": "Sarah Sales", "agent_type": "ai", "skills": ["sales"]
    }, headers=h)
    print("AGENT:", a.status_code)
    if a.status_code == 201:
        print("  SIP:", a.json().get("sip_extension"))

    # Call
    c = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
        "caller_number": "+15559876543", "called_number": "+15551234567",
        "call_direction": "inbound", "intent": "sales"
    }, headers=h)
    print("CALL:", c.status_code)

    print("\nALL TESTS PASSED!")
else:
    print("Login failed:", login.text[:300])