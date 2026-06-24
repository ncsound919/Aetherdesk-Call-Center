"""manual_initial_schema

Revision ID: 459682371cf0
Revises: 33be689273d2
Create Date: 2026-06-24 08:26:23.366854

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '459682371cf0'
down_revision: Union[str, None] = '33be689273d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from alembic import context
    from sqlalchemy import engine_from_config
    import os

    config = context.config
    use_postgres = os.getenv("USE_POSTGRES", "false").lower() == "true"

    if use_postgres:
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
        op.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name VARCHAR(100) NOT NULL,
            description TEXT,
            price_per_hour DECIMAL(10, 2) NOT NULL DEFAULT 0,
            price_per_day DECIMAL(10, 2) NOT NULL DEFAULT 0,
            price_per_week DECIMAL(10, 2) NOT NULL DEFAULT 0,
            price_per_month DECIMAL(10, 2) NOT NULL DEFAULT 0,
            max_concurrent_calls INT DEFAULT 10,
            max_agents INT DEFAULT 5,
            max_recordings_mb INT DEFAULT 1000,
            features JSONB DEFAULT '[]',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            email_verified BOOLEAN DEFAULT FALSE,
            verification_token VARCHAR(255),
            reset_token VARCHAR(255),
            reset_token_expires TIMESTAMP,
            tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
            role VARCHAR(50) DEFAULT 'owner',
            avatar_url VARCHAR(500),
            onboarding_completed BOOLEAN DEFAULT FALSE,
            onboarding_step INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """)
        op.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        op.execute('CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)')
        op.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            phone VARCHAR(20),
            plan_id UUID REFERENCES plans(id),
            plan_started_at TIMESTAMPTZ DEFAULT NOW(),
            plan_ends_at TIMESTAMPTZ,
            stripe_customer_id VARCHAR(255),
            stripe_subscription_id VARCHAR(255),
            settings JSONB DEFAULT '{}',
            is_active BOOLEAN DEFAULT TRUE,
            is_verified BOOLEAN DEFAULT FALSE,
            gdpr_consent BOOLEAN DEFAULT FALSE,
            gdpr_consented_at TIMESTAMPTZ,
            data_processing_agreement BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            deleted_at TIMESTAMPTZ
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            display_name VARCHAR(255),
            email VARCHAR(255),
            phone VARCHAR(20),
            agent_type VARCHAR(20) NOT NULL DEFAULT 'ai',
            status VARCHAR(20) NOT NULL DEFAULT 'offline',
            skills JSONB DEFAULT '[]',
            config JSONB DEFAULT '{}',
            sip_extension VARCHAR(20) UNIQUE,
            sip_password VARCHAR(128),
            encryption_key VARCHAR(256),
            total_calls INT DEFAULT 0,
            total_talk_time_seconds INT DEFAULT 0,
            avg_rating DECIMAL(3, 2) DEFAULT 0.0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ
        )
        """)
    else:
        op.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            name TEXT NOT NULL,
            description TEXT,
            price_per_hour REAL NOT NULL DEFAULT 0,
            price_per_day REAL NOT NULL DEFAULT 0,
            price_per_week REAL NOT NULL DEFAULT 0,
            price_per_month REAL NOT NULL DEFAULT 0,
            max_concurrent_calls INTEGER DEFAULT 10,
            max_agents INTEGER DEFAULT 5,
            max_recordings_mb INTEGER DEFAULT 1000,
            features TEXT DEFAULT '[]',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            email_verified INTEGER DEFAULT 0,
            verification_token TEXT,
            reset_token TEXT,
            reset_token_expires TEXT,
            tenant_id TEXT REFERENCES tenants(id) ON DELETE SET NULL,
            role TEXT DEFAULT 'owner',
            avatar_url TEXT,
            onboarding_completed INTEGER DEFAULT 0,
            onboarding_step INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        op.execute('CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)')
        op.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT,
            plan_id TEXT REFERENCES plans(id),
            plan_started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            plan_ends_at TEXT,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            settings TEXT DEFAULT '{}',
            is_active INTEGER DEFAULT 1,
            is_verified INTEGER DEFAULT 0,
            gdpr_consent INTEGER DEFAULT 0,
            gdpr_consented_at TEXT,
            data_processing_agreement INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            display_name TEXT,
            email TEXT,
            phone TEXT,
            agent_type TEXT NOT NULL DEFAULT 'ai',
            status TEXT NOT NULL DEFAULT 'offline',
            skills TEXT DEFAULT '[]',
            config TEXT DEFAULT '{}',
            sip_extension TEXT UNIQUE,
            sip_password TEXT,
            encryption_key TEXT,
            total_calls INTEGER DEFAULT 0,
            total_talk_time_seconds INTEGER DEFAULT 0,
            avg_rating REAL DEFAULT 0.0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT
        )
        """)


def downgrade() -> None:
    from alembic import context
    import os

    use_postgres = os.getenv("USE_POSTGRES", "false").lower() == "true"

    if use_postgres:
        op.execute('DROP TABLE IF EXISTS agents')
        op.execute('DROP TABLE IF EXISTS tenants')
        op.execute('DROP TABLE IF EXISTS users')
        op.execute('DROP TABLE IF EXISTS plans')
        op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
        op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
    else:
        op.execute("""
        DROP TABLE IF EXISTS agents;
        DROP TABLE IF EXISTS tenants;
        DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS plans;
        """)
