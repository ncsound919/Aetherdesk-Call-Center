"""Database migration runner using Alembic.

Integrates Alembic migrations into the app lifespan so that on startup,
any pending migrations are automatically applied for both PostgreSQL
(production) and SQLite (development) databases.
"""

import asyncio
import os
from pathlib import Path

import structlog

logger = structlog.get_logger()

ALEMBIC_CFG_PATH = Path(__file__).resolve().parents[3] / "alembic.ini"


async def run_alembic_migrations() -> bool:
    """Run pending Alembic migrations.

    Returns True if migrations ran successfully (or none were pending),
    False on failure.
    """
    if not ALEMBIC_CFG_PATH.exists():
        logger.warning("alembic.ini not found — skipping migrations")
        return False

    return await _run_migrations_async()


def _run_migrations_async_sync() -> bool:
    """Synchronous helper — Alembic's API is sync-only."""
    from alembic.config import Config

    from alembic import command

    try:
        alembic_cfg = Config(str(ALEMBIC_CFG_PATH))
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations up to date")
        return True
    except Exception as e:
        logger.error("Alembic migration failed", error=str(e))
        return False


async def _run_migrations_async() -> bool:
    """Run Alembic migrations in an executor to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_migrations_async_sync)


async def stamp_db(revision: str = "head") -> bool:
    """Stamp the database at a given revision without running migrations.

    Useful when setting up a fresh database from schema.sql and you
    need Alembic to believe it's already at the latest revision.
    """
    if not ALEMBIC_CFG_PATH.exists():
        return False

    def _stamp():
        from alembic.config import Config

        from alembic import command
        alembic_cfg = Config(str(ALEMBIC_CFG_PATH))
        command.stamp(alembic_cfg, revision)
        logger.info("Database stamped at %s", revision)

    return await asyncio.to_thread(_stamp)


async def check_migration_status() -> dict:
    """Return current migration status for health checks."""
    if not ALEMBIC_CFG_PATH.exists():
        return {"status": "unknown", "detail": "alembic.ini not found"}

    def _check():
        from alembic.config import Config
        from alembic.runtime.environment import EnvironmentContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine


        USE_POSTGRES = os.getenv("USE_POSTGRES", "false").lower() == "true"
        if USE_POSTGRES:
            user = os.getenv("DB_USER", "aetherdesk_admin")
            password = os.getenv("DB_PASSWORD", "")
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "5432")
            name = os.getenv("DB_NAME", "aetherdesk")
            db_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
        else:
            sqlite_path = os.getenv("SQLITE_PATH", "aetherdesk.db")
            db_url = f"sqlite:///{sqlite_path}"

        alembic_cfg = Config(str(ALEMBIC_CFG_PATH))
        script = ScriptDirectory.from_config(alembic_cfg)
        engine = create_engine(db_url)

        with engine.begin() as connection:
            with EnvironmentContext(alembic_cfg, script) as env:
                env.configure(connection=connection)
                head_revision = script.get_current_head()
                current_revision = env.get_head_revision() or "none"
                return {
                    "head": head_revision,
                    "current": current_revision,
                    "up_to_date": head_revision == current_revision,
                }

    return await asyncio.to_thread(_check)


