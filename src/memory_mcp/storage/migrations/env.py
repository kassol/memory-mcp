from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, event, pool

config = context.config


def _alembic_url() -> str:
    """Compute alembic URL from env without importing global Settings.

    Importing memory_mcp.config.settings would eager-instantiate Settings(),
    which requires MEMORY_MCP_AUTH_TOKEN / OPENROUTER_API_KEY. Alembic must
    run from a clean shell with only MEMORY_MCP_DATA_DIR set (e.g., CI,
    fresh dev checkout, ``mem db upgrade``).
    """
    data_dir = os.environ.get("MEMORY_MCP_DATA_DIR", "./data")
    sqlite_path = Path(data_dir) / "memory.sqlite3"
    return f"sqlite:///{sqlite_path.resolve()}"


# Override sqlalchemy.url from env without instantiating Settings()
config.set_main_option("sqlalchemy.url", _alembic_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Raw SQL migrations only; no SQLAlchemy ORM models, so autogenerate is disabled.
# Task 6 writes op.execute("...") blocks directly.
target_metadata = None


def run_migrations_offline() -> None:
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Enable FK enforcement on every connection alembic opens. Using the engine
    # "connect" event runs the PRAGMA on the raw DBAPI connection so it does
    # not autobegin SQLAlchemy's connection-level transaction — autobegin would
    # cause MigrationContext to treat us as already in an external transaction
    # and silently downgrade begin_transaction() to a no-op, losing the
    # alembic_version INSERT on the first upgrade.
    @event.listens_for(connectable, "connect")
    def _enable_fk(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        try:
            cur.execute("PRAGMA foreign_keys = ON")
        finally:
            cur.close()

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
