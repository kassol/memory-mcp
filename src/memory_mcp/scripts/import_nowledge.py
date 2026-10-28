"""One-shot import of Nowledge Mem memories into memory-mcp.

Input: the output of ``nmem --json m list -n 10000`` (``{"memories": [...]}``),
a bare JSON array, or JSONL with one memory object per line.

Only current memories are imported, oldest ``created_at`` first. ``m list`` already
hides archived/forgotten memories; replaced ones are dropped using the ``replaces``
EVOLVES edges (``nmem graph evolves``, cached in ``--evolves``). Each one gets an
entity_key from ``assign_entity_key`` and is written through ``remember_tool`` so
it joins existing evolution chains and conflict detection.

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
from concurrent.futures import ThreadPoolExecutor
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


def fetch_evolves(memory_id: str) -> list[dict[str, Any]]:
    """EVOLVES edges touching one memory, via the read-only `nmem graph evolves`."""
    out = subprocess.run(
        ["nmem", "--json", "graph", "evolves", "-n", "200", memory_id], capture_output=True, text=True, check=True
    ).stdout
    data = json.loads(out)
    if data["total"] > len(data["edges"]):
        raise RuntimeError(f"EVOLVES edges truncated for {memory_id}: {len(data['edges'])}/{data['total']}")
    return data["edges"]


def load_or_collect_evolves(path: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`m list` carries no supersede info, so collect EVOLVES edges once and cache them at `path`."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    typer.echo(f"Collecting EVOLVES edges for {len(records)} memories into {path} ...", err=True)
    with ThreadPoolExecutor(8) as pool:
        edges = [e for es in pool.map(fetch_evolves, [r["id"] for r in records]) for e in es]
    path.write_text(json.dumps(edges, ensure_ascii=False), encoding="utf-8")
    return edges


def select_current(records: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop memories replaced by a newer listed memory; return the rest oldest first.

    `m list` already hides archived/forgotten memories, but still lists replaced ones.
    """
    listed = {r["id"] for r in records}
    replaced = {e["older_id"] for e in edges if e["content_relation"] == "replaces" and e["newer_id"] in listed}
    current = [r for r in records if r["id"] not in replaced and r.get("content")]
    return sorted(current, key=lambda r: datetime.fromisoformat(r["created_at"]))


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
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse, filter and sort only; no LLM calls, no writes"),
    evolves: Optional[Path] = typer.Option(
        None, "--evolves", help="EVOLVES edge cache (default <input>.evolves.json; collected via nmem if missing)"
    ),
) -> None:
    """CLI entry point: python -m memory_mcp.scripts.import_nowledge --input ... --state ..."""
    records = load_records(input_path)
    edges = load_or_collect_evolves(evolves or input_path.with_name(input_path.name + ".evolves.json"), records)
    current = select_current(records, edges)

    if dry_run:
        summary = {
            "total": len(records),
            "excluded": len(records) - len(current),
            "current": len(current),
            "earliest_created_at": current[0]["created_at"] if current else None,
            "latest_created_at": current[-1]["created_at"] if current else None,
            "already_done_in_state": len(set(load_state(state)["done"]) & {r["id"] for r in current}),
        }
        typer.echo(json.dumps(summary, indent=2, ensure_ascii=False))
        for r in current[:5]:
            typer.echo(f"{r['created_at']}  {r['id']}  {r.get('title') or r['content'][:60]}")
        return

    from ..config import settings
    from ..storage.migrate import run_migrations

    if settings.auto_migrate:
        run_migrations()
    report = asyncio.run(_run_and_close(current, state, limit))
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
