import subprocess
import os
import sys
import time

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

# Set required env vars
os.environ["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
os.environ["JWT_SECRET"] = "test-jwt-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"
os.environ["DEEPGRAM_API_KEY"] = os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY")

print("Starting uvicorn...")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "debug"],
    stdout=open(r"C:\Users\User\AppData\Local\Temp\opencode\uvicorn_stdout.log", "w"),
    stderr=open(r"C:\Users\User\AppData\Local\Temp\opencode\uvicorn_stderr.log", "w"),
)
print(f"Process started with PID: {proc.pid}")

time.sleep(8)

# Check if still running
poll = proc.poll()
print(f"Process poll result: {poll}")

import httpx
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    print(f"Health check: {r.status_code}")
    print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Health check failed: {e}")

# Read stderr
with open(r"C:\Users\User\AppData\Local\Temp\opencode\uvicorn_stderr.log") as f:
    stderr_content = f.read()
    if stderr_content:
        print("=== STDERR ===")
        print(stderr_content[-2000:])

# Read stdout
with open(r"C:\Users\User\AppData\Local\Temp\opencode\uvicorn_stdout.log") as f:
    stdout_content = f.read()
    if stdout_content:
        print("=== STDOUT ===")
        print(stdout_content[-2000:])