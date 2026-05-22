import os
import sys
from pathlib import Path

# Server package needs auth_token / openrouter key at import time (pydantic settings).
os.environ.setdefault("MEMORY_MCP_AUTH_TOKEN", "test-token")
os.environ.setdefault("MEMORY_MCP_OPENROUTER_API_KEY", "test-key")

from typer.testing import CliRunner

CLI_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
SERVER_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
for _p in (CLI_SRC_DIR, SERVER_SRC_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def test_db_current_invokes_alembic(monkeypatch):
    captured = {}

    def fake_current():
        captured["called"] = True
        return "0001_initial_v2"

    monkeypatch.setattr("memory_mcp.storage.migrate.current", fake_current)

    from memory_mcp_cli.main import app

    result = CliRunner().invoke(app, ["db", "current"])
    assert result.exit_code == 0, result.output
    assert "0001_initial_v2" in result.output
    assert captured.get("called") is True


def test_db_upgrade_runs_head(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "memory_mcp.storage.migrate.run_migrations",
        lambda: seen.append("upgrade"),
    )
    from memory_mcp_cli.main import app

    result = CliRunner().invoke(app, ["db", "upgrade"])
    assert result.exit_code == 0
    assert seen == ["upgrade"]


def test_db_downgrade_passes_revision(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "memory_mcp.storage.migrate.downgrade",
        lambda revision="-1": captured.setdefault("rev", revision),
    )
    from memory_mcp_cli.main import app

    result = CliRunner().invoke(app, ["db", "downgrade", "--revision", "-1"])
    assert result.exit_code == 0
    assert captured["rev"] == "-1"


def test_db_history_prints_revisions(monkeypatch):
    monkeypatch.setattr(
        "memory_mcp.storage.migrate.history",
        lambda: [
            {"revision": "0001_initial_v2", "down_revision": None, "is_head": True},
        ],
    )
    from memory_mcp_cli.main import app

    result = CliRunner().invoke(app, ["db", "history"])
    assert result.exit_code == 0
    assert "0001_initial_v2" in result.output
