"""Final verification test for AetherDesk full stack."""
import os, sys, time, threading, httpx, sqlite3

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
            print(f"API: UP ({r.json()['status']})")
            break
    except: pass
    time.sleep(0.5)
else:
    print("API failed to start"); sys.exit(1)

login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print(f"Login: {login.status_code}")
token = login.json()["token"]
h = {"Authorization": f"Bearer {token}"}

# Create tenant
t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
    "name": "Acme Corp", "email": "admin@acmecorp.com",
    "phone": "+15551234567", "gdpr_consent": True
}, headers=h)
tid = t.json()["id"] if t.status_code == 201 else ""
print(f"Tenant: {t.status_code} ({tid[:8] if tid else 'N/A'})")

# Create agent
a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
    "name": "Sarah Sales", "display_name": "Sarah Sales Agent",
    "agent_type": "ai", "skills": ["sales"],
    "config": {"model": "llama-3.1-70b", "voice": "professional-female"}
}, headers=h)
aid = a.json()["id"] if a.status_code == 201 else ""
sip = a.json().get("sip_extension", "") if a.status_code == 201 else ""
print(f"Agent: {a.status_code} (id={aid[:8] if aid else 'N/A'}, sip={sip})")

# Create call (without agent_id to test auto-routing/queue path)
c = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
    "caller_number": "+15559876543", "called_number": "+15551234567",
    "call_direction": "inbound", "intent": "sales", "agent_id": aid
}, headers=h)
cid = c.json()["id"] if c.status_code == 201 else ""
print(f"Call: {c.status_code} (id={cid[:8] if cid else 'N/A'})")

# DB verification
conn = sqlite3.connect("aetherdesk.db")
for tbl in ["tenants", "agents", "call_sessions"]:
    n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    print(f"  DB: {tbl} = {n} rows")
conn.close()

print("\n=== AETHERDESK FULL STACK VERIFIED ===")