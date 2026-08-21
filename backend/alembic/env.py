"""
Alembic environment configuration.

This module configures the Alembic migration environment for the SmartCarpoolingApp.
It handles both online and offline migration modes.

Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Date: November 8, 2025
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import settings and Base
from app.core.config import settings
from app.db.base import Base

# Import all models for Alembic autogeneration through the central models package
import app.models  # This initializes all models correctly to avoid circular imports

# Alembic Config object
config = context.config

# Interpret the config file for Python logging (if present)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata

# Override sqlalchemy.url from settings
config.set_main_option("sqlalchemy.url", settings.DB_URL)


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations with the given connection.
    
    Args:
        connection: Database connection
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,
        # Important: Don't let SQLAlchemy auto-create enums, we do it in migrations
        include_object=lambda object, name, type_, reflected, compare_to: True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in 'online' mode (async).

    In this scenario we need to create an Engine and associate a
    connection with the context.
    """
    # Create async engine
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode (sync wrapper).
    """
    asyncio.run(run_async_migrations())


# Determine which mode to run
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
