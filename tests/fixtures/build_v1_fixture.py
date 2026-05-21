"""Generate a small v1 fixture (10 memories + 5 entities + 3 relations).

Run once locally:
    PYTHONPATH=src python tests/fixtures/build_v1_fixture.py

The output (vectors/memories.json + vectors/memories.lance + graph/*.json) is
checked into git so that tests/test_migrate_v1_to_v2.py can replay it without
needing live LanceDB writes in CI.
"""
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


FIXTURE_ROOT = Path(__file__).resolve().parent / "v1_data"
VECTORS_DIR = FIXTURE_ROOT / "vectors"
GRAPH_DIR = FIXTURE_ROOT / "graph"


def _dt(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _make_memory(entity_key: str, entity_type: str, content: str, days_ago: int, is_current: bool = True, parent_id: str | None = None) -> dict:
    return {
        "id": str(uuid4()),
        "entity_key": entity_key,
        "entity_type": entity_type,
        "content": content,
        "embedding": [0.1, 0.2, 0.3],
        "parent_id": parent_id,
        "mutation_type": "initial" if parent_id is None else "update",
        "mutation_reason": None,
        "created_at": _dt(days_ago),
        "valid_from": _dt(days_ago),
        "valid_until": None if is_current else _dt(max(days_ago - 1, 0)),
        "is_current": is_current,
        "confidence": 1.0,
        "archived_reason": None,
        "archived_at": None,
        "conflict": False,
        "conflict_with_id": None,
        "tags": [],
        "source": "conversation",
    }


def build() -> None:
    if FIXTURE_ROOT.exists():
        shutil.rmtree(FIXTURE_ROOT)
    VECTORS_DIR.mkdir(parents=True)
    GRAPH_DIR.mkdir(parents=True)

    memories: list[dict] = []
    # 5 entity keys, each with 1-3 memory versions = 10 memories total
    base = [
        ("preference:editor", "preference", ["Vim", "VSCode", "Cursor"]),
        ("fact:location", "fact", ["Beijing", "Shanghai"]),
        ("project:memory-mcp", "project", ["Building memory-mcp"]),
        ("person:alice", "person", ["Alice is a colleague", "Alice is a teammate"]),
        ("preference:theme", "preference", ["Light", "Dark"]),
    ]
    days_ago = 30
    for entity_key, entity_type, versions in base:
        parent_id: str | None = None
        for idx, content in enumerate(versions):
            is_current = idx == len(versions) - 1
            mem = _make_memory(
                entity_key=entity_key,
                entity_type=entity_type,
                content=content,
                days_ago=days_ago,
                is_current=is_current,
                parent_id=parent_id,
            )
            memories.append(mem)
            parent_id = mem["id"]
            days_ago -= 1
    assert len(memories) == 10

    with open(VECTORS_DIR / "memories.json", "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)

    # also write a LanceDB table so the migration script can read both paths
    try:
        import lancedb
        import pyarrow as pa

        db = lancedb.connect(str(VECTORS_DIR))
        schema = pa.schema(
            [
                pa.field("vector", pa.list_(pa.float32(), 3)),
                pa.field("id", pa.string()),
                pa.field("entity_key", pa.string()),
                pa.field("entity_type", pa.string()),
                pa.field("content", pa.string()),
                pa.field("payload", pa.string()),
                pa.field("is_current", pa.bool_()),
                pa.field("mutation_type", pa.string()),
            ]
        )
        table = db.create_table("memories", schema=schema, exist_ok=True)
        rows = [
            {
                "vector": m["embedding"],
                "id": m["id"],
                "entity_key": m["entity_key"],
                "entity_type": m["entity_type"],
                "content": m["content"],
                "payload": json.dumps(m, ensure_ascii=False),
                "is_current": bool(m["is_current"]),
                "mutation_type": m["mutation_type"],
            }
            for m in memories
        ]
        table.add(rows)
        print("Wrote LanceDB table at", VECTORS_DIR)
    except Exception as exc:
        print("Skipped LanceDB fixture (will rely on memories.json):", exc)

    entities = [
        {
            "entity_key": e[0],
            "entity_type": e[1],
            "name": e[0].split(":", 1)[1],
            "current_memory_id": next(m["id"] for m in reversed(memories) if m["entity_key"] == e[0] and m["is_current"]),
            "created_at": _dt(30),
            "updated_at": _dt(0),
        }
        for e in base
    ]
    with open(GRAPH_DIR / "entities.json", "w", encoding="utf-8") as f:
        json.dump(entities, f, ensure_ascii=False, indent=2)

    relations = [
        {
            "id": str(uuid4()),
            "from_entity_key": "person:alice",
            "to_entity_key": "project:memory-mcp",
            "relation_type": "WORKS_ON",
            "properties": {"role": "collaborator"},
            "created_at": _dt(10),
        },
        {
            "id": str(uuid4()),
            "from_entity_key": "project:memory-mcp",
            "to_entity_key": "preference:editor",
            "relation_type": "USES",
            "properties": {},
            "created_at": _dt(8),
        },
        {
            "id": str(uuid4()),
            "from_entity_key": "preference:editor",
            "to_entity_key": "preference:theme",
            "relation_type": "RELATED_TO",
            "properties": {},
            "created_at": _dt(5),
        },
    ]
    with open(GRAPH_DIR / "relations.json", "w", encoding="utf-8") as f:
        json.dump(relations, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    os.makedirs(FIXTURE_ROOT, exist_ok=True)
    build()
    print("Fixture written to", FIXTURE_ROOT)
