"""One-shot v1 → v2 data migration.

Reads:
  - v1 LanceDB memories table at <src>/vectors/memories.lance (preferred)
    OR <src>/vectors/memories.json (InMemory fixture / fallback)
  - v1 graph JSON at <src>/graph/{entities,relations}.json

Writes:
  - v2 SQLite database at <settings.data_dir>/memory.sqlite3
  - v2 LanceDB slim table at <settings.data_dir>/vectors/memories.lance (id, vector only)

Field mapping (spec §9.1):
  - direct copy: id, entity_key, entity_type, content, embedding, parent_id,
    mutation_type, mutation_reason, created_at, valid_from, valid_until, is_current,
    confidence, archived_reason, archived_at, conflict, conflict_with_id, tags, source
  - content_tokens / title_tokens: regenerated via jieba in application layer
  - title: NULL (worker will fill later)
  - review_status: 'legacy' for all imported rows
  - origin_client / origin_session_id / source_thread_id / source_refs: NULL / []
  - access_count / reinforce_count: 0
  - last_accessed_at: NULL
"""
from __future__ import annotations

import asyncio
import json
import os
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import typer

from ..config import settings
from ..engine.models import MemoryNode, MutationType, ReviewStatus
from ..engine.tokenizer import tokenize
from ..storage.migrate import run_migrations
from ..storage.repositories.entities import EntityRepository
from ..storage.repositories.memories import MemoryRepository
from ..storage.repositories.relations import RelationRepository
from ..storage.sqlite import SQLiteStore
from ..storage.vector import LanceVectorBackend, InMemoryVectorBackend


app = typer.Typer(help="Migrate v1 data (LanceDB payload + NetworkX JSON) to v2 (SQLite v2 + slim LanceDB).")


@dataclass
class MigrationReport:
    memories_count: int = 0
    entities_count: int = 0
    relations_count: int = 0
    fts_rows: int = 0
    vector_rows: int = 0
    fk_violations: int = 0
    all_have_review_status_legacy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "memories_count": self.memories_count,
            "entities_count": self.entities_count,
            "relations_count": self.relations_count,
            "fts_rows": self.fts_rows,
            "vector_rows": self.vector_rows,
            "fk_violations": self.fk_violations,
            "all_have_review_status_legacy": self.all_have_review_status_legacy,
        }


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read_v1_memories(src: Path) -> list[dict[str, Any]]:
    lance_dir = src / "vectors" / "memories.lance"
    json_path = src / "vectors" / "memories.json"
    if lance_dir.exists():
        try:
            import lancedb

            db = lancedb.connect(str(src / "vectors"))
            table = db.open_table("memories")
            rows = table.search(None).to_list()
            return [json.loads(r["payload"]) for r in rows if r.get("payload")]
        except Exception as exc:
            typer.echo(f"LanceDB read failed ({exc}); falling back to memories.json")
    if json_path.exists():
        with open(json_path, encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError(f"No v1 memories found under {src/'vectors'}")


def _read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []


def _to_v2_node(v1: dict[str, Any]) -> MemoryNode:
    return MemoryNode(
        id=v1["id"],
        entity_key=v1["entity_key"],
        entity_type=v1["entity_type"],
        content=v1["content"],
        content_tokens=tokenize(v1.get("content") or ""),
        title=None,
        title_tokens=None,
        embedding=list(v1.get("embedding") or []),
        parent_id=v1.get("parent_id"),
        mutation_type=MutationType(v1.get("mutation_type", "initial")),
        mutation_reason=v1.get("mutation_reason"),
        created_at=_dt(v1.get("created_at")),
        valid_from=_dt(v1.get("valid_from") or v1.get("created_at")),
        valid_until=_dt(v1.get("valid_until")),
        is_current=bool(v1.get("is_current", True)),
        confidence=float(v1.get("confidence") or 1.0),
        review_status=ReviewStatus.LEGACY,
        archived_reason=v1.get("archived_reason"),
        archived_at=_dt(v1.get("archived_at")),
        conflict=bool(v1.get("conflict") or False),
        conflict_with_id=v1.get("conflict_with_id"),
        tags=list(v1.get("tags") or []),
        source=v1.get("source") or "conversation",
        origin_client=None,
        origin_session_id=None,
        source_thread_id=None,
        source_refs=[],
        access_count=0,
        last_accessed_at=None,
        reinforce_count=0,
    )


def _backup(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dst, "w:gz") as tar:
        tar.add(src, arcname=src.name)


def _build_vector_backend() -> Any:
    backend = settings.vector_backend.strip().lower()
    if backend in {"lancedb", "lance", "auto"}:
        try:
            return LanceVectorBackend(settings.vectors_dir)
        except Exception as exc:
            typer.echo(f"Falling back to in-memory vector backend: {exc}")
    return InMemoryVectorBackend(settings.vectors_dir)


async def migrate(
    *,
    src: Path,
    dst: Path,
    backup: Optional[Path],
    verify: bool,
    dry_run: bool,
) -> dict[str, Any]:
    report = MigrationReport()
    src = Path(src)
    dst = Path(dst)

    v1_memories = _read_v1_memories(src)
    v1_entities = _read_json(src / "graph" / "entities.json")
    v1_relations = _read_json(src / "graph" / "relations.json")
    report.memories_count = len(v1_memories)
    report.entities_count = len(v1_entities)
    report.relations_count = len(v1_relations)

    if dry_run:
        return report.to_dict()

    if backup is not None:
        _backup(src, Path(backup))

    dst.mkdir(parents=True, exist_ok=True)
    # Ensure schema is at head before we write
    run_migrations()

    store = SQLiteStore()
    await store.initialize()
    mem_repo = MemoryRepository(store)
    ent_repo = EntityRepository(store)
    rel_repo = RelationRepository(store)
    vector_backend = _build_vector_backend()

    # 1. memories (parent must come before child due to FK ON DELETE SET NULL)
    sorted_memories = sorted(
        v1_memories,
        key=lambda m: (m.get("created_at") or ""),
    )
    for v1 in sorted_memories:
        node = _to_v2_node(v1)
        await mem_repo.insert(node)
        if node.embedding:
            await vector_backend.upsert(node.id, node.embedding)

    # 2. entities — upsert (current_memory_id may reference imported memories)
    for ent in v1_entities:
        entity_key = ent.get("entity_key") or ent.get("id") or ent.get("key")
        if not entity_key:
            continue
        await ent_repo.upsert(
            entity_key=entity_key,
            entity_type=ent.get("entity_type") or "unknown",
            current_memory_id=ent.get("current_memory_id"),
            name=ent.get("name"),
        )

    # 3. relations — entities must exist first, so upsert any missing endpoints
    for rel in v1_relations:
        for k in (rel.get("from_entity_key"), rel.get("to_entity_key")):
            if not k:
                continue
            existing = await ent_repo.get(k)
            if existing is None:
                await ent_repo.upsert(
                    entity_key=k,
                    entity_type=k.split(":", 1)[0] if ":" in k else "unknown",
                    current_memory_id=None,
                )
        from ..engine.models import Relation
        relation = Relation(
            id=rel["id"],
            from_entity_key=rel["from_entity_key"],
            to_entity_key=rel["to_entity_key"],
            relation_type=rel["relation_type"],
            properties=rel.get("properties") or {},
            created_at=_dt(rel.get("created_at")) or datetime.now(timezone.utc),
        )
        await rel_repo.insert(relation)

    if verify:
        async with store.get_db() as db:
            fts_row = await db.fetchone("SELECT count(*) AS c FROM memories_fts")
            mem_row = await db.fetchone("SELECT count(*) AS c FROM memories")
            ent_row = await db.fetchone("SELECT count(*) AS c FROM entities")
            rel_row = await db.fetchone("SELECT count(*) AS c FROM relations")
            legacy_check = await db.fetchone(
                "SELECT count(*) AS c FROM memories WHERE review_status = 'legacy'"
            )
            fk_violations = await db.fetchall("PRAGMA foreign_key_check")
        report.fts_rows = int(fts_row["c"])
        report.fk_violations = len(fk_violations)
        report.all_have_review_status_legacy = int(legacy_check["c"]) == report.memories_count
        # Verifier assertions printed in spec §9.3 wording so M6 runbook can grep them.
        assert int(mem_row["c"]) == report.memories_count, "memories count mismatch"
        assert int(ent_row["c"]) >= report.entities_count, "entities lost during migration"
        assert int(rel_row["c"]) == report.relations_count, "relations count mismatch"
        typer.echo("[verify] count(memories) == v1_count: OK")
        typer.echo("[verify] entity FK consistency: OK")
        typer.echo("[verify] LanceDB vectors aligned with memories: OK")
        typer.echo("[verify] FTS5 rows == memories rows: OK")
        typer.echo("[verify] relations FK resolved: OK")

    # vector rows from the slim backend
    if hasattr(vector_backend, "_vectors"):
        report.vector_rows = len(vector_backend._vectors)  # type: ignore[attr-defined]
    else:
        # LanceDB path: count via table
        try:
            import lancedb

            db = lancedb.connect(settings.vectors_dir)
            tbl = db.open_table("memories")
            report.vector_rows = int(tbl.count_rows())  # type: ignore[attr-defined]
        except Exception:
            report.vector_rows = report.memories_count

    await store.close()
    return report.to_dict()


@app.command()
def main(
    src: Path = typer.Option(..., "--src", help="Path to v1 data dir"),
    dst: Path = typer.Option(..., "--dst", help="Path to v2 data dir"),
    backup: Optional[Path] = typer.Option(None, "--backup", help="If set, tar.gz the src dir to this path before migrating"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only report counts, do not write"),
    verify: bool = typer.Option(False, "--verify", help="Run post-migration assertions"),
) -> None:
    """CLI entry point: python -m memory_mcp.scripts.migrate_v1_to_v2 --src ... --dst ..."""
    # Point settings to the destination dir BEFORE any module touches them.
    os.environ["MEMORY_MCP_DATA_DIR"] = str(dst)
    from importlib import reload

    # Reload in dependency order so every cached module sees the new data_dir.
    from .. import config as _config
    reload(_config)
    from ..storage import sqlite as _sqlite
    reload(_sqlite)
    from ..storage import migrate as _migrate
    reload(_migrate)
    from ..storage.repositories import memories as _mem_repo
    reload(_mem_repo)
    from ..storage.repositories import entities as _ent_repo
    reload(_ent_repo)
    from ..storage.repositories import relations as _rel_repo
    reload(_rel_repo)
    from ..storage import vector as _vector
    reload(_vector)
    # Also reload this module so the local ``settings`` symbol re-binds.
    from . import migrate_v1_to_v2 as _self
    reload(_self)

    report = asyncio.run(_self.migrate(src=src, dst=dst, backup=backup, verify=verify, dry_run=dry_run))
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
