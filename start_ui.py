import subprocess
import os
import sys
import time
import httpx

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui")

env = os.environ.copy()
env["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
env["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"

NPX = r"C:\Program Files\nodejs\npx.CMD"

print("Starting Vite dev server on port 3001...")
proc = subprocess.Popen(
    [NPX, "vite", "dev", "--host", "127.0.0.1", "--port", "3001"],
    stdout=open(r"C:\Users\User\AppData\Local\Temp\opencode\vite_stdout.log", "w"),
    stderr=open(r"C:\Users\User\AppData\Local\Temp\opencode\vite_stderr.log", "w"),
    env=env,
)
print(f"Vite PID: {proc.pid}")

time.sleep(12)

poll = proc.poll()
print(f"Process poll: {poll}")

try:
    r = httpx.get("http://127.0.0.1:3001/", timeout=10)
    print(f"UI Status: {r.status_code}")
    print(f"Title check: {'AetherDesk' in r.text or 'Call Center' in r.text or 'Agent' in r.text}")
except Exception as e:
    print(f"UI check failed: {e}")

# Read stderr
with open(r"C:\Users\User\AppData\Local\Temp\opencode\vite_stderr.log") as f:
    stderr = f.read()
    if stderr:
        print("=== VITE STDERR ===")
        print(stderr[-2000:])

# Read stdout
with open(r"C:\Users\User\AppData\Local\Temp\opencode\vite_stdout.log") as f:
    stdout = f.read()
    if stdout:
        print("=== VITE STDOUT ===")
        print(stdout[-2000:])