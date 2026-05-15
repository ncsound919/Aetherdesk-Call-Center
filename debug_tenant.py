"""Debug tenant creation 500 error."""
import os, sys, time, httpx, json

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
os.environ["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
os.environ["JWT_SECRET"] = "test-websocket-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"
os.environ["DEEPGRAM_API_KEY"] = "6d7905409a8d2384ab88de756a671b7fe5be7fa3"
os.environ["GROQ_API_KEY"] = "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"

# Start server
print("Starting server...")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "debug"],
    stdout=sys.stdout, stderr=sys.stderr
)
time.sleep(10)

# Login
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print(f"LOGIN: {login.status_code}")
if login.status_code != 200:
    print("Login failed:", login.text)
    sys.exit(1)

token = login.json()["token"]
h = {"Authorization": "Bearer " + token}

# Create tenant with extra logging
print("\nCreating tenant...")
t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
    "name": "Acme Corp", "email": "admin@acmecorp.com",
    "phone": "+15551234567", "gdpr_consent": True
}, headers=h)
print(f"TENANT: status={t.status_code}")
if t.status_code != 201:
    print("Error body:", t.text[:1000])
    # Check server log output
else:
    print("Tenant created:", t.json())

sys.exit(0)