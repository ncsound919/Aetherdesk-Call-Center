"""
Run the API server inline (foreground) so it doesn't get killed.
Use Ctrl+C to stop.
"""
import os, sys

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
os.environ["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
os.environ["JWT_SECRET"] = "test-websocket-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"
os.environ["DEEPGRAM_API_KEY"] = os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY")

print("=" * 60)
print("  AetherDesk API Server - Running Inline")
print("=" * 60)
print("  URL: http://127.0.0.1:8000")
print("  Docs: http://127.0.0.1:8000/docs")
print("  UI:  http://127.0.0.1:3001")
print("=" * 60)

import uvicorn
uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000, log_level="info")