"""Alembic environment configuration for AetherDesk.

Supports both PostgreSQL (production) and SQLite (development).
Uses raw SQL migrations via op.execute() since the codebase
does not use SQLAlchemy ORM models.
"""

import os
import re
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Database URL resolution ──────────────────────────────────────

USE_POSTGRES = os.getenv("USE_POSTGRES", "false").lower() == "true"

if USE_POSTGRES:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        user = os.getenv("DB_USER", "aetherdesk_admin")
        password = os.getenv("DB_PASSWORD", "")
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "aetherdesk")
        db_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
else:
    sqlite_path = os.getenv("SQLITE_PATH", "aetherdesk.db")
    db_url = f"sqlite:///{sqlite_path}"

# Alembic's online mode uses a sync driver — override with psycopg2 for Postgres
if USE_POSTGRES:
    user = os.getenv("DB_USER", "aetherdesk_admin")
    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "aetherdesk")
    sync_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
else:
    sqlite_path = os.getenv("SQLITE_PATH", "aetherdesk.db")
    sync_url = f"sqlite:///{sqlite_path}"

config.set_main_option("sqlalchemy.url", sync_url)

# No SQLAlchemy ORM models — raw SQL only
target_metadata = None


def include_object(obj, name, type_, reflected, compare_to):
    """Skip Alembic's autogenerate internal tables."""
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without connecting)."""
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
