#!/usr/bin/env python
"""
AetherDesk Call Center — Start both servers with Honcho (no Docker needed).
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

env = os.environ.copy()
env["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
env["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"

cmd = ["honcho", "start"]
print("Starting AetherDesk with Honcho...")
print("  API → http://127.0.0.1:8000/docs")
print("  UI  → http://127.0.0.1:3001")
print("  Press Ctrl+C to stop all services.")
print()

proc = subprocess.Popen(cmd, cwd=BASE, env=env)
try:
    proc.wait()
except KeyboardInterrupt:
    proc.terminate()
    proc.wait()
    print("\nAll services stopped.")
    sys.exit(0)
