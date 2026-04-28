import json
import logging
import os
from typing import List, Optional

from ..config import settings
from ..engine.models import MemoryNode

logger = logging.getLogger(__name__)


def _l2_distance(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("Embedding dimension mismatch")
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


class InMemoryVectorStore:
    def __init__(self, file_path: str) -> None:
        self._file_path = file_path
        self._nodes_by_id: dict[str, MemoryNode] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                node = MemoryNode.model_validate(item)
                self._nodes_by_id[node.id] = node
        except Exception as e:
            logger.warning("Failed to load in-memory vector store: %s", e)

    def _save(self) -> None:
        tmp_path = f"{self._file_path}.tmp"
        data = [node.model_dump(mode="json") for node in self._nodes_by_id.values()]
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._file_path)

    async def insert(self, node: MemoryNode):
        self._nodes_by_id[node.id] = node
        self._save()

    async def update(self, node: MemoryNode):
        self._nodes_by_id[node.id] = node
        self._save()

    async def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        filter_current: bool = True,
        entity_type: Optional[str] = None,
    ) -> list[tuple[MemoryNode, float | None]]:
        candidates = list(self._nodes_by_id.values())
        if filter_current:
            candidates = [n for n in candidates if n.is_current]
        if entity_type:
            candidates = [n for n in candidates if n.entity_type == entity_type]

        scored: list[tuple[MemoryNode, float]] = [(n, _l2_distance(query_vector, n.embedding)) for n in candidates]
        scored.sort(key=lambda x: x[1])
        return [(n, d) for n, d in scored[:limit]]

    async def get_by_id(self, node_id: str) -> Optional[MemoryNode]:
        return self._nodes_by_id.get(node_id)

    async def get_history(self, entity_key: str) -> List[MemoryNode]:
        nodes = [n for n in self._nodes_by_id.values() if n.entity_key == entity_key]
        return sorted(nodes, key=lambda x: x.created_at)

    async def list_current(self, entity_type: Optional[str] = None, limit: int = 100) -> List[MemoryNode]:
        nodes = [n for n in self._nodes_by_id.values() if n.is_current]
        if entity_type:
            nodes = [n for n in nodes if n.entity_type == entity_type]
        nodes.sort(key=lambda x: x.created_at, reverse=True)
        return nodes[:limit]


class LanceVectorStore:
    def __init__(self, vectors_dir: str) -> None:
        import lancedb
        import pyarrow as pa

        self._pa = pa
        self.db = lancedb.connect(vectors_dir)
        self.table_name = "memories"
        self._init_table()

    def _init_table(self) -> None:
        pa = self._pa
        if self.table_name not in self.db.table_names():
            schema = pa.schema(
                [
                    pa.field("vector", pa.list_(pa.float32(), settings.embedding_dim)),
                    pa.field("id", pa.string()),
                    pa.field("entity_key", pa.string()),
                    pa.field("entity_type", pa.string()),
                    pa.field("content", pa.string()),
                    pa.field("payload", pa.string()),
                    pa.field("is_current", pa.bool_()),
                    pa.field("mutation_type", pa.string()),
                ]
            )
            self.db.create_table(self.table_name, schema=schema)
        self.table = self.db.open_table(self.table_name)

    async def insert(self, node: MemoryNode):
        data = [
            {
                "vector": node.embedding,
                "id": node.id,
                "entity_key": node.entity_key,
                "entity_type": node.entity_type,
                "content": node.content,
                "payload": node.model_dump_json(),
                "is_current": node.is_current,
                "mutation_type": node.mutation_type.value,
            }
        ]
        self.table.add(data)

    async def update(self, node: MemoryNode):
        self.table.update(
            where=f"id = '{node.id}'",
            values={
                "is_current": node.is_current,
                "payload": node.model_dump_json(),
            },
        )

    async def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        filter_current: bool = True,
        entity_type: Optional[str] = None,
    ) -> list[tuple[MemoryNode, float | None]]:
        query = self.table.search(query_vector).limit(limit)

        filters = []
        if filter_current:
            filters.append("is_current = true")
        if entity_type:
            filters.append(f"entity_type = '{entity_type}'")

        if filters:
            query = query.where(" AND ".join(filters), prefilter=True)

        results = query.to_list()
        return [(MemoryNode.model_validate_json(r["payload"]), r.get("_distance")) for r in results]

    async def get_by_id(self, node_id: str) -> Optional[MemoryNode]:
        results = self.table.search(None).where(f"id = '{node_id}'").limit(1).to_list()
        if results:
            return MemoryNode.model_validate_json(results[0]["payload"])
        return None

    async def get_history(self, entity_key: str) -> List[MemoryNode]:
        results = self.table.search(None).where(f"entity_key = '{entity_key}'").to_list()
        nodes = [MemoryNode.model_validate_json(r["payload"]) for r in results]
        return sorted(nodes, key=lambda x: x.created_at)

    async def list_current(self, entity_type: Optional[str] = None, limit: int = 100) -> List[MemoryNode]:
        query = self.table.search(None)
        filters = ["is_current = true"]
        if entity_type:
            filters.append(f"entity_type = '{entity_type}'")
        query = query.where(" AND ".join(filters))
        if limit:
            query = query.limit(limit)
        results = query.to_list()
        return [MemoryNode.model_validate_json(r["payload"]) for r in results]


class VectorStore:
    def __init__(self):
        vectors_dir = os.path.join(settings.data_dir, "vectors")
        os.makedirs(vectors_dir, exist_ok=True)
        self.backend_name = ""

        backend = settings.vector_backend.strip().lower()
        if backend == "memory":
            self._impl = InMemoryVectorStore(os.path.join(vectors_dir, "memories.json"))
            self.backend_name = "memory"
            return

        if backend in {"lancedb", "lance"}:
            try:
                self._impl = LanceVectorStore(vectors_dir)
            except Exception as e:
                raise RuntimeError("Failed to initialize LanceDB vector backend") from e
            self.backend_name = "lancedb"
            return

        if backend != "auto":
            raise ValueError(f"Unsupported vector backend: {backend}")

        try:
            self._impl = LanceVectorStore(vectors_dir)
            self.backend_name = "lancedb"
        except Exception as e:
            logger.warning("LanceDB unavailable, falling back to in-memory store: %s", e)
            self._impl = InMemoryVectorStore(os.path.join(vectors_dir, "memories.json"))
            self.backend_name = "memory"

    async def insert(self, node: MemoryNode):
        await self._impl.insert(node)

    async def update(self, node: MemoryNode):
        await self._impl.update(node)

    async def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        filter_current: bool = True,
        entity_type: Optional[str] = None,
    ) -> list[tuple[MemoryNode, float | None]]:
        return await self._impl.search(
            query_vector=query_vector,
            limit=limit,
            filter_current=filter_current,
            entity_type=entity_type,
        )

    async def get_by_id(self, node_id: str) -> Optional[MemoryNode]:
        return await self._impl.get_by_id(node_id)

    async def get_history(self, entity_key: str) -> List[MemoryNode]:
        return await self._impl.get_history(entity_key)

    async def list_current(self, entity_type: Optional[str] = None, limit: int = 100) -> List[MemoryNode]:
        return await self._impl.list_current(entity_type=entity_type, limit=limit)


vector_store = VectorStore()
