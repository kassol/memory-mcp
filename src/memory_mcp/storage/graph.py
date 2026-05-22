import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import networkx as nx

from ..engine.models import Relation
from .repositories.entities import EntityRepository
from .repositories.relations import RelationRepository
from .sqlite import SQLiteStore, get_store


def _infer_entity_type(entity_key: str) -> str:
    if ":" in entity_key:
        return entity_key.split(":", 1)[0]
    return "unknown"


class GraphStore:
    """Runtime graph view backed by SQLite.

    On first read we hydrate a `nx.MultiDiGraph` from SQLite; writes go to SQLite
    + the in-memory graph (double-write). Calling `reload()` re-hydrates the
    graph from SQLite, which is how the M1 design avoids JSON persistence.
    """

    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        sqlite_store = store or get_store()
        self._entities = EntityRepository(sqlite_store)
        self._relations = RelationRepository(sqlite_store)
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._loaded: bool = False
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._lock:
            if self._loaded:
                return
            await self._hydrate()
            self._loaded = True

    async def _hydrate(self) -> None:
        self._graph = nx.MultiDiGraph()
        for entity in await self._entities.list_all():
            self._graph.add_node(entity["entity_key"], **entity)
        for rel in await self._relations.list_all():
            self._graph.add_edge(
                rel["from_entity_key"],
                rel["to_entity_key"],
                key=rel["id"],
                **rel,
            )

    async def reload(self) -> None:
        async with self._lock:
            await self._hydrate()
            self._loaded = True

    # ---- Entity API -------------------------------------------------------
    async def upsert_entity(
        self,
        entity_key: str,
        entity_type: Optional[str],
        current_memory_id: Optional[str],
    ) -> None:
        await self._ensure_loaded()
        ent_type = entity_type or _infer_entity_type(entity_key)
        await self._entities.upsert(entity_key, ent_type, current_memory_id)
        entity = await self._entities.get(entity_key)
        if entity is None:
            return
        try:
            if entity_key in self._graph.nodes:
                self._graph.nodes[entity_key].update(entity)
            else:
                self._graph.add_node(entity_key, **entity)
        except Exception:
            self._loaded = False
            raise

    async def clear_current_memory(self, entity_key: str) -> None:
        await self._ensure_loaded()
        await self._entities.clear_current_memory(entity_key)
        try:
            if entity_key in self._graph.nodes:
                self._graph.nodes[entity_key]["current_memory_id"] = None
        except Exception:
            self._loaded = False
            raise

    async def list_entities(self) -> List[Dict[str, Any]]:
        await self._ensure_loaded()
        # Source of truth is SQLite — return repo data, not nx attributes
        return await self._entities.list_all()

    # ---- Relation API -----------------------------------------------------
    async def add_relation(self, relation: Relation) -> None:
        await self._ensure_loaded()
        await self._entities.upsert(
            relation.from_entity_key,
            _infer_entity_type(relation.from_entity_key),
            current_memory_id=None,
        )
        await self._entities.upsert(
            relation.to_entity_key,
            _infer_entity_type(relation.to_entity_key),
            current_memory_id=None,
        )
        await self._relations.insert(relation)
        try:
            for k in (relation.from_entity_key, relation.to_entity_key):
                ent = await self._entities.get(k)
                if ent is None:
                    continue
                if k in self._graph.nodes:
                    self._graph.nodes[k].update(ent)
                else:
                    self._graph.add_node(k, **ent)
            self._graph.add_edge(
                relation.from_entity_key,
                relation.to_entity_key,
                key=relation.id,
                id=relation.id,
                from_entity_key=relation.from_entity_key,
                to_entity_key=relation.to_entity_key,
                relation_type=relation.relation_type,
                properties=dict(relation.properties),
                created_at=relation.created_at.isoformat(),
            )
        except Exception:
            self._loaded = False
            raise

    async def delete_relation(self, relation_id: str) -> bool:
        await self._ensure_loaded()
        deleted = await self._relations.delete(relation_id)
        if not deleted:
            return False
        try:
            for u, v, k in list(self._graph.edges(keys=True)):
                if k == relation_id:
                    self._graph.remove_edge(u, v, key=k)
                    break
        except Exception:
            self._loaded = False
            raise
        return True

    async def get_relations(
        self,
        entity_key: str,
        relation_types: Optional[List[str]] = None,
        depth: int = 1,
    ) -> List[Dict[str, Any]]:
        await self._ensure_loaded()
        if entity_key not in self._graph or depth < 1:
            return []

        def _serialize(value: Any) -> Any:
            if isinstance(value, datetime):
                return value.isoformat()
            return value

        results: List[Dict[str, Any]] = []
        seen_edges: set[str] = set()
        visited = {entity_key}
        queue: list[tuple[str, int]] = [(entity_key, 0)]

        while queue:
            current, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue
            for u, v, k, data in self._graph.out_edges(current, data=True, keys=True):
                if relation_types and data.get("relation_type") not in relation_types:
                    continue
                edge_id = data.get("id", k)
                if edge_id in seen_edges:
                    continue
                seen_edges.add(edge_id)
                item = {key: _serialize(val) for key, val in data.items()}
                results.append(item)
                if v not in visited:
                    visited.add(v)
                    queue.append((v, current_depth + 1))
            for u, v, k, data in self._graph.in_edges(current, data=True, keys=True):
                if relation_types and data.get("relation_type") not in relation_types:
                    continue
                edge_id = data.get("id", k)
                if edge_id in seen_edges:
                    continue
                seen_edges.add(edge_id)
                item = {key: _serialize(val) for key, val in data.items()}
                results.append(item)
                if u not in visited:
                    visited.add(u)
                    queue.append((u, current_depth + 1))
        return results


graph_store = GraphStore()
