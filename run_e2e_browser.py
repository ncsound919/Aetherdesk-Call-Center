#!/usr/bin/env python3
"""
Run E2E tests in a visible browser (headed mode)
Follows the full user journey through the UI
"""
import os
import sys
import subprocess
import time
import signal
import httpx

os.environ["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
os.environ["JWT_SECRET"] = "dev-secret-key-change-me"
os.environ["USE_POSTGRES"] = "false"
os.environ["DEV_USERS_CONFIGURED"] = "true"

PROJECT_DIR = r"C:\Users\User\Desktop\aetherdesk_scaffold"

# Start API server
print("=" * 60)
print("Starting API server on port 8000...")
print("=" * 60)
api_proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd=PROJECT_DIR,
    env={**os.environ, "DATABASE_URL": "sqlite:///aetherdesk.db"},
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# Wait for API to be ready
for i in range(30):
    try:
        resp = httpx.get("http://127.0.0.1:8000/health", timeout=2)
        if resp.status_code == 200:
            print("API server is UP!")
            break
    except:
        pass
    time.sleep(1)
else:
    print("Failed to start API server")
    api_proc.terminate()
    sys.exit(1)

# Start UI server
print("\n" + "=" * 60)
print("Starting UI server on port 3001...")
print("=" * 60)
ui_env = os.environ.copy()
ui_env["VITE_API_URL"] = "http://127.0.0.1:8000"
ui_env["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="

# Use npm directly on Windows
npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
ui_proc = subprocess.Popen(
    [npm_cmd, "run", "dev", "--", "--host", "127.0.0.1", "--port", "3001", "--strictPort"],
    cwd=os.path.join(PROJECT_DIR, "agent-ui"),
    env=ui_env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# Wait for UI to be ready
for i in range(30):
    try:
        resp = httpx.get("http://127.0.0.1:3001", timeout=2)
        if resp.status_code == 200:
            print("UI server is UP!")
            break
    except:
        pass
    time.sleep(1)
else:
    print("Failed to start UI server")
    api_proc.terminate()
    ui_proc.terminate()
    sys.exit(1)

print("\n" + "=" * 60)
print("Running E2E tests in headed mode (visible browser)...")
print("=" * 60)

# Run Playwright tests with headed mode (visible browser)
result = subprocess.run(
    [sys.executable, "-m", "pytest", 
     "tests/e2e/test_customer_journey.py", 
     "-v", 
     "--headed",      # Run in visible browser
     "-m", "ui",      # Only UI tests
     "--tb=short"],
    cwd=PROJECT_DIR,
    env={**os.environ, "E2E_BASE_URL": "http://127.0.0.1:3001"},
)

# Cleanup
print("\n" + "=" * 60)
print("Shutting down servers...")
print("=" * 60)
api_proc.terminate()
ui_proc.terminate()
api_proc.wait()
ui_proc.wait()

sys.exit(result.returncode)