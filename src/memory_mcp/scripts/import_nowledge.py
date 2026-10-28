"""One-shot import of Nowledge Mem memories into memory-mcp.

Input: the output of ``nmem --json m list -n 10000`` (``{"memories": [...]}``),
a bare JSON array, or JSONL with one memory object per line.

Every listed memory is imported (``m list`` already hides archived/forgotten ones),
oldest ``created_at`` first. Each one gets an entity_key from ``assign_entity_key``
and is written through ``remember_tool`` with its original ``created_at``, so it
joins existing evolution chains, where a reused key merges old and new content.

Resumable: ``--state`` records imported Nowledge ids (skipped on rerun) and the
latest failure per id (retried on rerun).

Usage:
  python -m memory_mcp.scripts.import_nowledge --input export.json --state state.json [--limit N] [--dry-run]
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import typer

app = typer.Typer(help="Import Nowledge Mem memories into memory-mcp.")

ORIGIN_CLIENT = "nowledge"


def load_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(data, dict):
        data = data["memories"]
    return data


def created_at(record: dict[str, Any]) -> datetime:
    value = datetime.fromisoformat(record["created_at"])
    if value.tzinfo is None:
        raise ValueError(f"created_at has no timezone: {record['id']} {record['created_at']!r}")
    return value


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Oldest first, so later Nowledge memories evolve earlier ones."""
    return sorted(records, key=created_at)


def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"done": [], "failed": []}


def save_state(path: Path, state: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def fetch_labels(memory_id: str) -> list[str]:
    """`m list` omits labels; read them with the read-only `nmem m show`."""
    out = subprocess.run(
        ["nmem", "--json", "m", "show", memory_id], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(out).get("labels") or []


async def import_one(record: dict[str, Any]) -> dict[str, Any]:
    # Imported lazily so --dry-run never opens (or creates) the stores.
    from ..engine import embedding, key_assignment
    from ..tools import remember

    content = record["content"]
    labels = record["labels"] if "labels" in record else fetch_labels(record["id"])
    vector = await embedding.embedding_service.get_embedding(content)
    entity_key, entity_type = await key_assignment.assign_entity_key(content, vector)
    return await remember.remember_tool(
        {
            "content": content,
            "entity_key": entity_key,
            "entity_type": entity_type,
            "tags": labels,
            "title": record.get("title") or None,
            "origin_client": ORIGIN_CLIENT,
            "origin_session_id": record["id"],
            "skip_semantic_merge": True,
        },
        embedding=vector,
        created_at=created_at(record),
    )


async def run_import(records: list[dict[str, Any]], state_path: Path, limit: Optional[int] = None) -> dict[str, Any]:
    state = load_state(state_path)
    done = set(state["done"])
    failed = {f["id"]: f for f in state["failed"]}
    pending = [r for r in records if r["id"] not in done]
    if limit is not None:
        pending = pending[:limit]

    statuses: Counter[str] = Counter()
    conflicts = 0
    run_failed = 0
    for record in pending:
        try:
            result = await import_one(record)
        except Exception as exc:
            run_failed += 1
            failed[record["id"]] = {"id": record["id"], "error": f"{type(exc).__name__}: {exc}"}
            typer.echo(f"FAILED {record['id']}: {type(exc).__name__}: {exc}", err=True)
        else:
            statuses[result["status"]] += 1
            conflicts += bool(result.get("conflict"))
            state["done"].append(record["id"])
            failed.pop(record["id"], None)
        state["failed"] = list(failed.values())
        save_state(state_path, state)

    return {
        "processed": len(pending),
        "created": statuses["created"],
        "evolved": statuses["evolved"],
        "no_change": statuses["no_change"],
        "conflicts": conflicts,
        "failed": run_failed,
        "skipped_already_done": len(records) - len([r for r in records if r["id"] not in done]),
        "failed_total_in_state": len(failed),
    }


async def _run_and_close(records: list[dict[str, Any]], state_path: Path, limit: Optional[int]) -> dict[str, Any]:
    from ..storage.sqlite import get_store

    try:
        return await run_import(records, state_path, limit)
    finally:
        await get_store().close()


@app.command()
def main(
    input_path: Path = typer.Option(..., "--input", help="nmem --json m list output (JSON or JSONL)"),
    state: Path = typer.Option(..., "--state", help="Resume state file (created if missing)"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Process at most N pending memories"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse and sort only; no LLM calls, no writes"),
) -> None:
    """CLI entry point: python -m memory_mcp.scripts.import_nowledge --input ... --state ..."""
    records = sort_records(load_records(input_path))

    if dry_run:
        summary = {
            "total": len(records),
            "earliest_created_at": records[0]["created_at"] if records else None,
            "latest_created_at": records[-1]["created_at"] if records else None,
            "already_done_in_state": len(set(load_state(state)["done"]) & {r["id"] for r in records}),
        }
        typer.echo(json.dumps(summary, indent=2, ensure_ascii=False))
        for r in records[:5]:
            typer.echo(f"{r['created_at']}  {r['id']}  {r.get('title') or r['content'][:60]}")
        return

    from ..config import settings
    from ..storage.migrate import run_migrations

    if settings.auto_migrate:
        run_migrations()
    report = asyncio.run(_run_and_close(records, state, limit))
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
