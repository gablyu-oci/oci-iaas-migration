"""Alembic environment configuration for async SQLAlchemy."""

from logging.config import fileConfig

import sys
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy import engine_from_config
from alembic import context

# Make sure the backend app package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import models so Alembic can detect them for autogenerate
from app.db.models import Base
from app.config import settings

# Alembic Config object
config = context.config

# Convert async URL to sync URL for Alembic's online mode
db_url = settings.DATABASE_URL
if "+asyncpg" in db_url:
    db_url = db_url.replace("+asyncpg", "+psycopg2")
config.set_main_option("sqlalchemy.url", db_url)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
