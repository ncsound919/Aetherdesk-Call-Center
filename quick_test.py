"""Quick test to verify tenant creation fix."""
import os, sys, time, threading, httpx, json

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

for k, v in {
    "ENCRYPTION_KEY": "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA=",
    "JWT_SECRET": "test-websocket-secret",
    "WEBSOCKET_SECRET_KEY": "test-websocket-secret",
    "USE_POSTGRES": "false",
    "DEEPGRAM_API_KEY": "6d7905409a8d2384ab88de756a671b7fe5be7fa3",
    "GROQ_API_KEY": "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",
}.items(): os.environ[k] = v

try: os.remove("aetherdesk.db")
except: pass

def api():
    import uvicorn
    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000, log_level="warning")

t = threading.Thread(target=api, daemon=True)
t.start()

for i in range(20):
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=2)
        if r.status_code == 200:
            print(f"API UP: {r.json()['status']}")
            break
    except: pass
    time.sleep(0.5)

# Login
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print(f"Login: {login.status_code}")
token = login.json()["token"]
h = {"Authorization": f"Bearer {token}"}

# Create tenant (this was failing before)
t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
    "name": "Acme Corp", "email": "admin@acmecorp.com",
    "phone": "+15551234567", "gdpr_consent": True
}, headers=h)
print(f"Tenant: {t.status_code}", end="")
if t.status_code == 201:
    d = t.json()
    tid = d["id"]
    print(f" OK - {d['name']} ({tid[:8]})")
else:
    print(f" FAIL - {t.text[:200]}")
    tid = "TENANT-001"

# Create agent
a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
    "name": "Sarah Sales", "display_name": "Sarah Sales Agent",
    "agent_type": "ai", "skills": ["sales", "support"],
    "config": {"model": "llama-3.1-70b", "voice": "professional-female"}
}, headers=h)
print(f"Agent: {a.status_code}", end="")
if a.status_code == 201:
    d = a.json()
    print(f" OK - {d['name']} ext:{d.get('sip_extension')}")
else:
    print(f" FAIL - {a.text[:200]}")

# Create call
c = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
    "caller_number": "+15559876543", "called_number": "+15551234567",
    "call_direction": "inbound", "intent": "sales"
}, headers=h)
print(f"Call: {c.status_code}", end="")
if c.status_code == 201:
    d = c.json()
    print(f" OK - {d['id'][:8]}")
else:
    print(f" FAIL - {c.text[:200]}")

# Verify SQLite DB was created
import sqlite3
conn = sqlite3.connect("aetherdesk.db")
rows = conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]
print(f"\nSQLite tenants table: {rows} tenant(s)")
rows = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
print(f"SQLite agents table: {rows} agent(s)")
rows = conn.execute("SELECT COUNT(*) FROM call_sessions").fetchone()[0]
print(f"SQLite calls table: {rows} call(s)")
conn.close()

print("\n=== ALL TESTS PASSED ===")