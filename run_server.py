#!/usr/bin/env python
"""Start the AetherDesk dev server and keep it running."""
import os
import sys

os.environ["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"

if __name__ == "__main__":
    import uvicorn
    print("Starting AetherDesk dev server...")
    print("Access at: http://127.0.0.1:8000")
    print("API Docs at: http://127.0.0.1:8000/docs")
    print("Health: http://127.0.0.1:8000/health")
    print("-" * 40)
    
    uvicorn.run(
        "apps.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )