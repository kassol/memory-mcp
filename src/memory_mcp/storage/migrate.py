import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from ..config import settings

logger = logging.getLogger(__name__)


def _find_ini() -> Path | None:
    """alembic.ini only carries logging config, so it is optional.

    A non-editable install (Dockerfile) puts this module in site-packages,
    away from the repo root, so also look in the working directory.
    """
    for parent in (*Path(__file__).resolve().parents, Path.cwd()):
        if (parent / "alembic.ini").is_file():
            return parent / "alembic.ini"
    return None


def _make_config(db_path: str | None = None) -> Config:
    ini_path = _find_ini()
    cfg = Config(str(ini_path)) if ini_path else Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent / "migrations"))
    url = f"sqlite:///{db_path}" if db_path else settings.alembic_url
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def run_migrations(db_path: str | None = None) -> None:
    """Apply all pending migrations to head. Called at FastAPI lifespan startup
    when MEMORY_MCP_AUTO_MIGRATE is true (the default).

    ``db_path`` lets one-shot scripts (e.g. migrate_v1_to_v2) target an
    explicit SQLite file without mutating global settings.
    """
    target = db_path or settings.sqlite_path
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    cfg = _make_config(db_path)
    logger.info("Running alembic upgrade head against %s", target)
    command.upgrade(cfg, "head")


def downgrade(revision: str = "-1") -> None:
    cfg = _make_config()
    command.downgrade(cfg, revision)


def current() -> str | None:
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    engine = create_engine(settings.alembic_url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            return ctx.get_current_revision()
    finally:
        engine.dispose()


def history() -> list[dict[str, object]]:
    """List all alembic revisions in newest-first order."""
    from alembic.script import ScriptDirectory

    cfg = _make_config()
    script_dir = ScriptDirectory.from_config(cfg)
    head = script_dir.get_current_head()
    out: list[dict[str, object]] = []
    for rev in script_dir.walk_revisions():
        out.append({
            "revision": rev.revision,
            "down_revision": rev.down_revision,
            "is_head": rev.revision == head,
        })
    return out
