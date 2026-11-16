"""Alembic environment.

Migrations run as the owner role, never as the application role. The URL comes
from ORDERDESK_MIGRATIONS_DATABASE_URL, or from ``config.attributes`` when a
test passes it in directly.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from orderdesk.db import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    url = config.attributes.get("database_url") or os.environ.get(
        "ORDERDESK_MIGRATIONS_DATABASE_URL"
    )
    if not url:
        raise RuntimeError(
            "Set ORDERDESK_MIGRATIONS_DATABASE_URL to the owner role's database URL "
            "before running migrations."
        )
    return str(url)


def run_migrations_offline() -> None:
    """Write the migration SQL to stdout without connecting (alembic --sql)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
