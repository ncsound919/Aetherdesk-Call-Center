"""Debug tenant creation - inline server."""
import os, sys, time, httpx, json, traceback

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
os.environ["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
os.environ["JWT_SECRET"] = "test-websocket-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"

# Remove old DB for clean test
db_path = r"C:\Users\User\Desktop\aetherdesk_scaffold\aetherdesk.db"
if os.path.exists(db_path):
    os.remove(db_path)

# Start server inline
import threading
import uvicorn

def run_server():
    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000, log_level="info")

t = threading.Thread(target=run_server, daemon=True)
t.start()
time.sleep(8)

# Login
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print(f"LOGIN: {login.status_code}")
if login.status_code == 200:
    token = login.json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    # Create tenant
    print("\nCreating tenant...")
    try:
        r = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
            "name": "Acme Corp", "email": "acme@test.com",
            "phone": "+15551234567", "gdpr_consent": True
        }, headers=h, timeout=10)
        print(f"STATUS: {r.status_code}")
        print(f"BODY: {r.text[:1000]}")
    except Exception as e:
        print(f"EXCEPTION: {e}")
        traceback.print_exc()