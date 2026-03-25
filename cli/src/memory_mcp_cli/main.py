import json
import sys
from pathlib import Path
from typing import Optional

import typer

from .client import MemoryClient
from .config import load_config

app = typer.Typer(help="mem — CLI client for memory-mcp", add_completion=False)

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
    fmt: str = _format_opt,
) -> None:
    """Store a new memory."""
    result = _client().remember(content, entity_type, entity_key)
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


# ---------------------------------------------------------------------------
# wm  (working memory)
# ---------------------------------------------------------------------------
@app.command()
def wm(
    cwd: Optional[str] = typer.Option(None, "--cwd", help="Current working directory for project-aware briefing"),
    fmt: str = _format_opt,
) -> None:
    """Get working memory briefing."""
    result = _client().wm(cwd=cwd)
    _out(result, fmt)


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------
def _parse_transcript(path: Optional[Path]) -> list[dict]:
    if path is not None:
        raw = path.read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    # Try JSON array first
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fall back to JSONL
    items = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return items


def _filter_messages(items: list[dict]) -> list[dict]:
    return [
        item for item in items
        if item.get("role") in ("user", "assistant")
        and item.get("content", "")
    ]


@app.command()
def extract(
    transcript: Optional[Path] = typer.Option(None, "--transcript", help="Path to transcript file (JSON array or JSONL); reads stdin if omitted"),
    fmt: str = _format_opt,
) -> None:
    """Extract memories from a conversation transcript."""
    items = _parse_transcript(transcript)
    messages = _filter_messages(items)
    if not messages:
        typer.echo("Error: no valid user/assistant messages found in transcript", err=True)
        raise SystemExit(1)
    result = _client().extract(messages)
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
