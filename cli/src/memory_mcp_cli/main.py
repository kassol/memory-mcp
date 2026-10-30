import json
from typing import Optional

import typer

from .client import MemoryClient
from .config import load_config

app = typer.Typer(help="mem — CLI client for memory-mcp", add_completion=False)

db_app = typer.Typer(help="Alembic schema management.")
app.add_typer(db_app, name="db")


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Apply all pending migrations to head."""
    from memory_mcp.storage import migrate as migrate_mod
    migrate_mod.run_migrations()
    typer.echo("Upgraded to head.")


@db_app.command("downgrade")
def db_downgrade(
    revision: str = typer.Option("-1", "--revision", "-r", help="Target revision (default: -1 step back)"),
) -> None:
    """Roll back to a specific revision (use -1 for one step)."""
    from memory_mcp.storage import migrate as migrate_mod
    migrate_mod.downgrade(revision)
    typer.echo(f"Downgraded to {revision}.")


@db_app.command("current")
def db_current() -> None:
    """Print the currently applied revision (matches /health.schema_version)."""
    from memory_mcp.storage import migrate as migrate_mod
    rev = migrate_mod.current()
    typer.echo(rev if rev is not None else "<none>")


@db_app.command("history")
def db_history() -> None:
    """Print all known revisions newest-first."""
    from memory_mcp.storage import migrate as migrate_mod
    for entry in migrate_mod.history():
        marker = " (head)" if entry["is_head"] else ""
        down = entry["down_revision"] or "<base>"
        typer.echo(f"{entry['revision']} <- {down}{marker}")


_format_opt = typer.Option("json", "--format", "-f", help="Output format: json or text")


def _client() -> MemoryClient:
    cfg = load_config()
    return MemoryClient(cfg["api_url"], cfg["api_key"])


def _out(data: dict, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    # text format: unwrap data["data"]
    inner = data.get("data", data)
    if isinstance(inner, dict):
        # single-value string dicts: print the value directly
        values = list(inner.values())
        if len(values) == 1 and isinstance(values[0], str):
            print(values[0])
            return
    print(json.dumps(inner, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# remember
# ---------------------------------------------------------------------------
@app.command()
def remember(
    content: str = typer.Argument(..., help="Memory content to store"),
    entity_type: Optional[str] = typer.Option(None, "--type", "-t", help="Entity type"),
    entity_key: Optional[str] = typer.Option(None, "--key", "-k", help="Entity key"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
    fmt: str = _format_opt,
) -> None:
    """Store a new memory."""
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else None
    result = _client().remember(content, entity_type, entity_key, tag_list)
    _out(result, fmt)


# ---------------------------------------------------------------------------
# recall
# ---------------------------------------------------------------------------
@app.command()
def recall(
    query: Optional[str] = typer.Argument(None, help="Search query (omit with --all)"),
    all_memories: bool = typer.Option(False, "--all", "-a", help="List all memories"),
    entity_type: Optional[str] = typer.Option(None, "--type", "-t"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n"),
    include_evolution: bool = typer.Option(False, "--evolution", help="Include evolution history"),
    fmt: str = _format_opt,
) -> None:
    """Search or list memories."""
    client = _client()
    if all_memories:
        result = client.recall_all(entity_type, limit)
    else:
        if not query:
            typer.echo("Error: provide a query or use --all", err=True)
            raise SystemExit(1)
        result = client.recall(query, entity_type, limit, include_evolution)
    _out(result, fmt)


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------
@app.command()
def trace(
    entity_key: str = typer.Argument(..., help="Entity key to trace"),
    trace_format: Optional[str] = typer.Option(None, "--trace-format", help="Trace format: timeline or summary"),
    fmt: str = _format_opt,
) -> None:
    """Show evolution history of a memory entity."""
    result = _client().trace(entity_key, trace_format)
    _out(result, fmt)


# ---------------------------------------------------------------------------
# forget
# ---------------------------------------------------------------------------
@app.command()
def forget(
    entity_key: str = typer.Argument(..., help="Entity key to delete"),
    reason: Optional[str] = typer.Option(None, "--reason", "-r", help="Reason for deletion"),
    fmt: str = _format_opt,
) -> None:
    """Delete a memory."""
    result = _client().forget(entity_key, reason)
    _out(result, fmt)


# ---------------------------------------------------------------------------
# relate
# ---------------------------------------------------------------------------
@app.command()
def relate(
    from_key: str = typer.Argument(..., help="Source entity key"),
    to_key: str = typer.Argument(..., help="Target entity key"),
    relation_type: str = typer.Argument(..., help="Relation type"),
    weight: Optional[float] = typer.Option(None, "--weight", "-w"),
    fmt: str = _format_opt,
) -> None:
    """Create a relation between two entities."""
    result = _client().relate(from_key, to_key, relation_type, weight)
    _out(result, fmt)


@app.command()
def unrelate(
    relation_id: str = typer.Argument(..., help="Relation id to delete"),
    fmt: str = _format_opt,
) -> None:
    """Delete a relation by id."""
    result = _client().unrelate(relation_id)
    _out(result, fmt)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
@app.command()
def status() -> None:
    """Check server health."""
    result = _client().health()
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------
@app.command(name="config")
def show_config() -> None:
    """Show current configuration (api_key masked)."""
    cfg = load_config()
    key = cfg.get("api_key", "")
    cfg["api_key"] = key[:4] + "****" if len(key) > 4 else "****" if key else ""
    print(json.dumps(cfg, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
