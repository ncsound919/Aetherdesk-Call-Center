#!/usr/bin/env python
"""Start API server and capture all output."""
import subprocess, os, sys, time, httpx

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
os.environ["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
os.environ["JWT_SECRET"] = "test-websocket-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"
os.environ["DEEPGRAM_API_KEY"] = "6d7905409a8d2384ab88de756a671b7fe5be7fa3"
os.environ["GROQ_API_KEY"] = "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"

out = open(r"C:\Users\User\AppData\Local\Temp\opencode\server.log", "w")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "debug"],
    stdout=out, stderr=subprocess.STDOUT
)
print("Server PID:", proc.pid)

# Wait and check
for i in range(30):  # up to 30 seconds
    time.sleep(1)
    poll = proc.poll()
    if poll is not None:
        print("Process died at", i, "seconds!")
        out.close()
        with open(r"C:\Users\User\AppData\Local\Temp\opencode\server.log") as f:
            print("LOG:", f.read()[-2000:])
        sys.exit(1)
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=2)
        if r.status_code == 200:
            print("Server UP at", i, "seconds!")
            print("Health:", r.json()["status"])
            break
    except:
        pass
else:
    print("Server never became ready in 30 seconds")

out.close()
with open(r"C:\Users\User\AppData\Local\Temp\opencode\server.log") as f:
    print("=== SERVER LOG ===")
    print(f.read()[-3000:])