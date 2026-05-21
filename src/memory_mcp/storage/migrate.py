import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from ..config import settings

logger = logging.getLogger(__name__)


def _make_config() -> Config:
    repo_root = Path(__file__).resolve().parents[3]
    ini_path = repo_root / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(repo_root / "src" / "memory_mcp" / "storage" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.alembic_url)
    return cfg


def run_migrations() -> None:
    """Apply all pending migrations to head. Called at FastAPI lifespan startup
    when MEMORY_MCP_AUTO_MIGRATE is true (the default).
    """
    os.makedirs(os.path.dirname(settings.sqlite_path) or ".", exist_ok=True)
    cfg = _make_config()
    logger.info("Running alembic upgrade head against %s", settings.sqlite_path)
    command.upgrade(cfg, "head")


def downgrade(revision: str = "-1") -> None:
    cfg = _make_config()
    command.downgrade(cfg, revision)


def current() -> str | None:
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    engine = create_engine(settings.alembic_url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        return ctx.get_current_revision()
