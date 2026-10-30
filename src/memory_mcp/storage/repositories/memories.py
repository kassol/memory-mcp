from typing import Iterable, List, Optional

from ...engine.models import MemoryNode
from ..serializers import memory_to_row, row_to_memory
from ..sqlite import SQLiteStore, get_store


_COLUMNS = (
    "id, entity_key, entity_type, content, content_tokens, title, title_tokens, "
    "parent_id, mutation_type, mutation_reason, created_at, valid_from, valid_until, "
    "is_current, confidence, review_status, archived_reason, archived_at, conflict, "
    "conflict_with_id, tags, source, origin_client, origin_session_id, "
    "access_count, last_accessed_at, reinforce_count"
)


def _placeholders(n: int) -> str:
    return ",".join(["?"] * n)


class MemoryRepository:
    """SQLite-backed CRUD for the memories table.

    Note: MemoryNode.embedding is owned by `storage.vector.VectorStore`.
    Nodes returned by this repository carry `embedding=[]`; callers that
    need the vector must merge it in via `VectorStore.get(memory_id)`
    (M2 hybrid_search does this).
    """

    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        self._store = store or get_store()

    async def insert(self, node: MemoryNode) -> None:
        row = memory_to_row(node)
        columns = list(row.keys())
        values = [row[c] for c in columns]
        sql = (
            f"INSERT INTO memories ({', '.join(columns)}) "
            f"VALUES ({_placeholders(len(columns))})"
        )
        async with self._store.get_db() as db:
            await db.execute(sql, values)

    async def update(self, node: MemoryNode) -> None:
        row = memory_to_row(node)
        columns = [c for c in row.keys() if c != "id"]
        values = [row[c] for c in columns] + [node.id]
        assignments = ", ".join(f"{c} = ?" for c in columns)
        sql = f"UPDATE memories SET {assignments} WHERE id = ?"
        async with self._store.get_db() as db:
            await db.execute(sql, values)

    async def get_by_id(self, memory_id: str) -> Optional[MemoryNode]:
        sql = f"SELECT {_COLUMNS} FROM memories WHERE id = ?"
        async with self._store.get_db() as db:
            row = await db.fetchone(sql, (memory_id,))
        if row is None:
            return None
        return row_to_memory(row)

    async def get_by_ids(self, memory_ids: Iterable[str]) -> List[MemoryNode]:
        ids = list(memory_ids)
        if not ids:
            return []
        sql = f"SELECT {_COLUMNS} FROM memories WHERE id IN ({_placeholders(len(ids))})"
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, ids)
        by_id = {dict(r)["id"]: row_to_memory(r) for r in rows}
        # preserve input order
        return [by_id[i] for i in ids if i in by_id]

    async def get_history(self, entity_key: str) -> List[MemoryNode]:
        sql = (
            f"SELECT {_COLUMNS} FROM memories WHERE entity_key = ? ORDER BY created_at ASC"
        )
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, (entity_key,))
        return [row_to_memory(r) for r in rows]

    async def list_current(
        self,
        entity_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order: str = "created_at",
    ) -> List[MemoryNode]:
        """Current memories: newest created first, or oldest valid_from first (stale ones first)."""
        order_by = {"created_at": "created_at DESC, id", "valid_from": "valid_from ASC, id"}[order]
        clauses = ["is_current = 1"]
        params: list = []
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        sql = (
            f"SELECT {_COLUMNS} FROM memories "
            f"WHERE {' AND '.join(clauses)} "
            f"ORDER BY {order_by} LIMIT ? OFFSET ?"
        )
        params.extend([int(limit), int(offset)])
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, params)
        return [row_to_memory(r) for r in rows]

    async def get_current_by_entity_keys(self, entity_keys: Iterable[str]) -> List[MemoryNode]:
        """Current memory of each key, in input key order; keys without one are skipped."""
        keys = list(entity_keys)
        if not keys:
            return []
        sql = (
            f"SELECT {_COLUMNS} FROM memories "
            f"WHERE is_current = 1 AND entity_key IN ({_placeholders(len(keys))})"
        )
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, keys)
        by_key: dict[str, List[MemoryNode]] = {}
        for r in rows:
            node = row_to_memory(r)
            by_key.setdefault(node.entity_key, []).append(node)
        return [node for k in keys for node in by_key.get(k, [])]

    async def hard_delete(self, memory_id: str) -> bool:
        """Used by VectorStore.delete and tools.memory_delete(hard=True)."""
        async with self._store.get_db() as db:
            cur = await db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return (cur.rowcount or 0) > 0

    async def fts_search(
        self, tokens: str, limit: int = 50, entity_type: Optional[str] = None
    ) -> List[dict]:
        """FTS5 search over current memories via the memories_fts virtual table.

        The FTS index covers every version; without the is_current filter old versions
        would take the top `limit` slots.

        The FTS5 tokenizer is unicode61 (see migration 0001_initial_v2). Callers
        are expected to pass `tokens` already pre-segmented by jieba (the
        `engine.tokenizer.tokenize()` helper), matching how `memories.content_tokens`
        is populated. `tokens` is an FTS5 MATCH expression (see
        `engine.hybrid_search.build_fts_query`).

        Returns ``[{"memory_id", "bm25", "node"}]`` ordered by bm25 ascending
        (FTS5 returns lower bm25 = better match).
        """
        if not tokens.strip():
            return []
        clauses = ["memories_fts MATCH ?", "m.is_current = 1"]
        params: list = [tokens]
        if entity_type:
            clauses.append("m.entity_type = ?")
            params.append(entity_type)
        # CROSS JOIN pins memories_fts as the outer loop. With a plain JOIN the planner starts
        # from idx_memories_current and runs the MATCH once per current row: 1.7-7.6 s at
        # ~3.9k current rows, against ~10 ms this way.
        sql = (
            f"SELECT bm25(memories_fts) AS bm25, "
            f"{', '.join('m.' + c.strip() for c in _COLUMNS.split(','))} "
            f"FROM memories_fts CROSS JOIN memories m ON m.rowid = memories_fts.rowid "
            f"WHERE {' AND '.join(clauses)} ORDER BY bm25 ASC LIMIT ?"
        )
        params.append(int(limit))
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, params)
        out: list[dict] = []
        for r in rows:
            node = row_to_memory(r)
            out.append({"memory_id": r["id"], "bm25": r["bm25"], "node": node})
        return out
