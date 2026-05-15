#!/usr/bin/env python
"""Simplest possible server start + test."""
import subprocess, os, sys, time

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
os.environ["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
os.environ["JWT_SECRET"] = "test-websocket-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"
os.environ["DEEPGRAM_API_KEY"] = "6d7905409a8d2384ab88de756a671b7fe5be7fa3"
os.environ["GROQ_API_KEY"] = "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"

proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000"],
    stdout=sys.stdout, stderr=sys.stderr
)
print("PID:", proc.pid)
time.sleep(15)
print("Done waiting - server should be running")