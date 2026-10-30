import logging
import os
from datetime import timedelta
from typing import List, Optional, Tuple

from ..config import settings
from ..engine.models import MemoryNode
from .repositories.memories import MemoryRepository
from .sqlite import SQLiteStore, get_store

logger = logging.getLogger(__name__)

COMPACT_EVERY_WRITES = 200


def _l2_distance(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("Embedding dimension mismatch")
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


class InMemoryVectorBackend:
    """Pure-Python ANN backend used in tests and as a fallback when LanceDB is unavailable."""

    def __init__(self, vectors_dir: str) -> None:
        self._vectors: dict[str, list[float]] = {}

    async def upsert(self, memory_id: str, vector: list[float]) -> None:
        self._vectors[memory_id] = list(vector)

    async def delete(self, memory_id: str) -> None:
        self._vectors.pop(memory_id, None)

    async def search(self, query_vector: list[float], limit: int = 10) -> list[Tuple[str, float]]:
        scored: list[Tuple[str, float]] = []
        for mid, vec in self._vectors.items():
            try:
                scored.append((mid, _l2_distance(query_vector, vec)))
            except ValueError:
                continue
        scored.sort(key=lambda x: x[1])
        return scored[:limit]


class LanceVectorBackend:
    """LanceDB backend with the slim schema `(id, vector)` only; metadata lives in SQLite."""

    def __init__(self, vectors_dir: str) -> None:
        import lancedb
        import pyarrow as pa

        self._pa = pa
        os.makedirs(vectors_dir, exist_ok=True)
        # Check for newer table versions on every read: without it the service keeps the snapshot it
        # opened at startup and never sees rows written by other processes (import / ops scripts).
        self._db = lancedb.connect(vectors_dir, read_consistency_interval=timedelta(0))
        self._table_name = "memories"
        self._writes = 0
        self._init_table()

    def _init_table(self) -> None:
        pa = self._pa
        if self._table_name not in self._db.table_names():
            schema = pa.schema(
                [
                    pa.field("id", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), settings.embedding_dim)),
                ]
            )
            self._db.create_table(self._table_name, schema=schema)
        self._table = self._db.open_table(self._table_name)

    async def upsert(self, memory_id: str, vector: list[float]) -> None:
        # LanceDB upsert: delete-then-add to keep this simple and version-agnostic
        self._table.delete(f"id = '{memory_id}'")
        self._table.add([{"id": memory_id, "vector": list(vector)}])
        self._after_write()

    async def delete(self, memory_id: str) -> None:
        self._table.delete(f"id = '{memory_id}'")
        self._after_write()

    def _after_write(self) -> None:
        # Every add writes a new fragment and version; without compaction a 9k-row import
        # left ~9.5k fragments and searches slowed from ~5 s to ~22 s per imported memory.
        self._writes += 1
        if self._writes % COMPACT_EVERY_WRITES == 0:
            self.optimize()

    def optimize(self) -> None:
        # Keep an hour of versions so a concurrent reader's snapshot stays readable.
        self._table.optimize(cleanup_older_than=timedelta(hours=1))

    async def search(self, query_vector: list[float], limit: int = 10) -> list[Tuple[str, float]]:
        results = self._table.search(query_vector).limit(limit).to_list()
        out: list[Tuple[str, float]] = []
        for r in results:
            mid = r.get("id")
            distance = r.get("_distance")
            if mid is None or distance is None:
                continue
            out.append((mid, float(distance)))
        return out


class VectorStore:
    """High-level vector store: routes (id, vector) ops to backend, joins via MemoryRepository."""

    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        self.backend_name = ""
        self._repo = MemoryRepository(store or get_store())

        os.makedirs(settings.vectors_dir, exist_ok=True)

        backend = settings.vector_backend.strip().lower()
        if backend == "memory":
            self._backend = InMemoryVectorBackend(settings.vectors_dir)
            self.backend_name = "memory"
            return

        if backend in {"lancedb", "lance"}:
            try:
                self._backend = LanceVectorBackend(settings.vectors_dir)
            except Exception as exc:
                raise RuntimeError("Failed to initialize LanceDB vector backend") from exc
            self.backend_name = "lancedb"
            return

        if backend != "auto":
            raise ValueError(f"Unsupported vector backend: {backend}")

        try:
            self._backend = LanceVectorBackend(settings.vectors_dir)
            self.backend_name = "lancedb"
        except Exception as exc:
            logger.warning("LanceDB unavailable, falling back to in-memory backend: %s", exc)
            self._backend = InMemoryVectorBackend(settings.vectors_dir)
            self.backend_name = "memory"

    # ---- Write path -------------------------------------------------------
    # The vector index holds current memories only: every search filters to current, and
    # stale versions crowding the ANN candidates would hide the current one. A memory's
    # content (and vector) never changes in place; new content is a new node via insert.
    async def insert(self, node: MemoryNode) -> None:
        await self._repo.insert(node)
        if node.embedding and node.is_current:
            await self._backend.upsert(node.id, node.embedding)

    async def update(self, node: MemoryNode) -> None:
        await self._repo.update(node)
        if not node.is_current:
            await self._backend.delete(node.id)

    async def delete(self, memory_id: str) -> bool:
        await self._backend.delete(memory_id)
        # SQLite hard-delete only when caller explicitly wants it; soft delete is via update
        return await self._repo.hard_delete(memory_id)

    # ---- Read path --------------------------------------------------------
    async def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        filter_current: bool = True,
        entity_type: Optional[str] = None,
        overfetch: int = 4,
    ) -> list[tuple[MemoryNode, float | None]]:
        # Over-fetch from ANN so that post-filtering keeps `limit` results when possible
        ann_limit = max(limit * overfetch, 20)
        candidates = await self._backend.search(query_vector, limit=ann_limit)
        if not candidates:
            return []
        ids = [mid for mid, _ in candidates]
        loaded = await self._repo.get_by_ids(ids)
        by_id = {n.id: n for n in loaded}
        out: list[tuple[MemoryNode, float | None]] = []
        for mid, dist in candidates:
            node = by_id.get(mid)
            if node is None:
                continue
            if filter_current and not node.is_current:
                continue
            if entity_type and node.entity_type != entity_type:
                continue
            out.append((node, dist))
            if len(out) >= limit:
                break
        return out

    async def get_by_id(self, memory_id: str) -> Optional[MemoryNode]:
        return await self._repo.get_by_id(memory_id)

    async def get_history(self, entity_key: str) -> List[MemoryNode]:
        return await self._repo.get_history(entity_key)

    async def list_current(
        self,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryNode]:
        return await self._repo.list_current(entity_type=entity_type, limit=limit)


vector_store = VectorStore()
