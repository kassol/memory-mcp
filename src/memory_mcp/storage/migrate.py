import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from ..config import settings

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    """Walk up from this module until pyproject.toml is found.

    Resilient to file relocation; replaces fragile ``parents[N]`` math.
    """
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("repo root with pyproject.toml not found")


def _make_config() -> Config:
    repo_root = _repo_root()
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
