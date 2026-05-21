from typing import Iterable, List, Optional

from ...engine.models import MemoryNode
from ..serializers import memory_to_row, row_to_memory
from ..sqlite import SQLiteStore, get_store


_COLUMNS = (
    "id, entity_key, entity_type, content, content_tokens, title, title_tokens, "
    "parent_id, mutation_type, mutation_reason, created_at, valid_from, valid_until, "
    "is_current, confidence, review_status, archived_reason, archived_at, conflict, "
    "conflict_with_id, tags, source, origin_client, origin_session_id, source_thread_id, "
    "source_refs, access_count, last_accessed_at, reinforce_count"
)


def _placeholders(n: int) -> str:
    return ",".join(["?"] * n)


class MemoryRepository:
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
    ) -> List[MemoryNode]:
        clauses = ["is_current = 1"]
        params: list = []
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        sql = (
            f"SELECT {_COLUMNS} FROM memories "
            f"WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at DESC LIMIT ?"
        )
        params.append(int(limit))
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, params)
        return [row_to_memory(r) for r in rows]

    async def hard_delete(self, memory_id: str) -> bool:
        """Used by VectorStore.delete and tools.memory_delete(hard=True)."""
        async with self._store.get_db() as db:
            cur = await db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return (cur.rowcount or 0) > 0

    async def fts_search(self, tokens: str, limit: int = 50) -> List[dict]:
        """FTS5 search via the jieba-pre-tokenized memories_fts virtual table.

        Returns ``[{"memory_id", "bm25", "node"}]`` ordered by bm25 ascending
        (FTS5 returns lower bm25 = better match). Used by M2 hybrid_search.
        """
        if not tokens.strip():
            return []
        sql = (
            f"SELECT m.id AS memory_id, bm25(memories_fts) AS bm25, {_COLUMNS} "
            f"FROM memories_fts JOIN memories m ON m.rowid = memories_fts.rowid "
            f"WHERE memories_fts MATCH ? ORDER BY bm25 ASC LIMIT ?"
        )
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, (tokens, int(limit)))
        out: list[dict] = []
        for r in rows:
            node = row_to_memory(r)
            out.append({"memory_id": r["memory_id"], "bm25": r["bm25"], "node": node})
        return out
