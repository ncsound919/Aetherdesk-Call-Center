import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    None
)
if not DATABASE_URL:
    if os.getenv("USE_POSTGRES", "false").lower() == "true":
        raise RuntimeError("DATABASE_URL environment variable must be set for production.")
    else:
        print("DATABASE_URL not set. Running with SQLite fallback.")
USE_POSTGRES = os.getenv("USE_POSTGRES", "false").lower() == "true"

SQLITE_PATH = os.getenv("SQLITE_PATH", "aetherdesk.db")

SQLITE_POOL_SIZE = int(os.getenv("SQLITE_POOL_SIZE", "5"))
SQLITE_TIMEOUT = int(os.getenv("SQLITE_TIMEOUT", "30"))
