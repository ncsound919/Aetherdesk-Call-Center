"""admin_tables

Revision ID: 68714fbf072b
Revises: 459682371cf0
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68714fbf072b'
down_revision: Union[str, None] = '459682371cf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from alembic import context
    from sqlalchemy import engine_from_config
    import os

    config = context.config
    use_postgres = os.getenv("USE_POSTGRES", "false").lower() == "true"

    if use_postgres:
        op.execute("""
        CREATE TABLE IF NOT EXISTS seo_content (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            meta_title TEXT, meta_description TEXT, og_title TEXT, og_description TEXT,
            og_image TEXT, keywords TEXT, body TEXT,
            status TEXT DEFAULT 'draft',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS donors (
            id TEXT PRIMARY KEY, name TEXT, email TEXT, phone TEXT,
            amount REAL DEFAULT 0.0, currency TEXT DEFAULT 'USD', tier TEXT, notes TEXT,
            donation_date TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS coupons (
            id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE,
            type TEXT DEFAULT 'percent', value REAL DEFAULT 0.0, min_amount REAL, max_uses INTEGER,
            starts_at TIMESTAMP, ends_at TIMESTAMP, stripe_coupon_id TEXT,
            status TEXT DEFAULT 'local_only', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS contact_notes (
            id TEXT PRIMARY KEY, source TEXT, contact_id TEXT, note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS flyer_saves (
            id TEXT PRIMARY KEY, template_id TEXT, title TEXT, subtitle TEXT, cta_text TEXT,
            cta_url TEXT, theme TEXT, logo_url TEXT, config_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS flyer_templates (
            id TEXT PRIMARY KEY, category TEXT, name TEXT, preset_json TEXT DEFAULT '{}'
        )
        """)
    else:
        op.execute("""
        CREATE TABLE IF NOT EXISTS seo_content (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            meta_title TEXT, meta_description TEXT, og_title TEXT, og_description TEXT,
            og_image TEXT, keywords TEXT, body TEXT,
            status TEXT DEFAULT 'draft',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS donors (
            id TEXT PRIMARY KEY, name TEXT, email TEXT, phone TEXT,
            amount REAL DEFAULT 0.0, currency TEXT DEFAULT 'USD', tier TEXT, notes TEXT,
            donation_date TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS coupons (
            id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE,
            type TEXT DEFAULT 'percent', value REAL DEFAULT 0.0, min_amount REAL, max_uses INTEGER,
            starts_at TIMESTAMP, ends_at TIMESTAMP, stripe_coupon_id TEXT,
            status TEXT DEFAULT 'local_only', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS contact_notes (
            id TEXT PRIMARY KEY, source TEXT, contact_id TEXT, note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS flyer_saves (
            id TEXT PRIMARY KEY, template_id TEXT, title TEXT, subtitle TEXT, cta_text TEXT,
            cta_url TEXT, theme TEXT, logo_url TEXT, config_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        op.execute("""
        CREATE TABLE IF NOT EXISTS flyer_templates (
            id TEXT PRIMARY KEY, category TEXT, name TEXT, preset_json TEXT DEFAULT '{}'
        )
        """)


def downgrade() -> None:
    from alembic import context
    import os

    use_postgres = os.getenv("USE_POSTGRES", "false").lower() == "true"

    if use_postgres:
        op.execute('DROP TABLE IF EXISTS flyer_templates')
        op.execute('DROP TABLE IF EXISTS flyer_saves')
        op.execute('DROP TABLE IF EXISTS contact_notes')
        op.execute('DROP TABLE IF EXISTS coupons')
        op.execute('DROP TABLE IF EXISTS donors')
        op.execute('DROP TABLE IF EXISTS seo_content')
    else:
        op.execute("""
        DROP TABLE IF EXISTS flyer_templates;
        DROP TABLE IF EXISTS flyer_saves;
        DROP TABLE IF EXISTS contact_notes;
        DROP TABLE IF EXISTS coupons;
        DROP TABLE IF EXISTS donors;
        DROP TABLE IF EXISTS seo_content;
        """)
