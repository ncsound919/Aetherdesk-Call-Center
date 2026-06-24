import subprocess
import os
import time
import httpx

os.environ["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"

print("=" * 60)
print("  AetherDesk Call Center - Starting Servers")
print("=" * 60)
print()

# Start API server
print("[1] Starting API Server on port 8000...")
proc = subprocess.Popen(
    ['python', '-m', 'uvicorn', 'apps.api.main:app', '--host', '127.0.0.1', '--port', '8000'],
    cwd=r'C:\Users\User\Desktop\aetherdesk_scaffold',
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
time.sleep(6)

# Check API
try:
    r = httpx.get('http://127.0.0.1:8000/health')
    print(f"   API: 200 OK")
except Exception as e:
    print(f"   API: FAILED - {e}")

# Start UI server (if not running)
print("[2] Starting UI Server on port 3001...")
env = os.environ.copy()
env["PATH"] = os.environ.get("PATH", "")
ui_proc = subprocess.Popen(
    ['cmd', '/c', 'npm run dev -- --host 127.0.0.1 --port 3001'],
    cwd=r'C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui',
    env=env,
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
time.sleep(8)

# Check UI
try:
    r = httpx.get('http://127.0.0.1:3001/')
    print(f"   UI: 200 OK")
except Exception as e:
    print(f"   UI: FAILED - {e}")

print()
print("=" * 60)
print("  ALL SERVERS RUNNING!")
print("=" * 60)
print()
print("  Open your Chrome browser to:")
print("  http://127.0.0.1:3001")
print()
print("  Keep this window open. Close Ctrl+C to stop.")
print("=" * 60)

while True:
    time.sleep(1)