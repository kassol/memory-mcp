import os
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import networkx as nx

from ..config import settings
from ..engine.models import Relation

class GraphStore:
    def __init__(self):
        self.graph_dir = os.path.join(settings.data_dir, "graph")
        os.makedirs(self.graph_dir, exist_ok=True)
        self.entities_path = os.path.join(self.graph_dir, "entities.json")
        self.relations_path = os.path.join(self.graph_dir, "relations.json")
        self.evolution_path = os.path.join(self.graph_dir, "evolution_chains.json")
        
        self.g = nx.MultiDiGraph()
        self._load()

    def _load(self):
        # Load Entities (Nodes)
        if os.path.exists(self.entities_path):
            with open(self.entities_path, 'r') as f:
                try:
                    entities = json.load(f)
                    for e in entities:
                        entity_key = e.get("entity_key") or e.get("id") or e.get("key")
                        if not entity_key:
                            continue
                        node_data = dict(e)
                        node_data["entity_key"] = entity_key
                        self.g.add_node(entity_key, **node_data)
                except json.JSONDecodeError:
                    pass

        # Load Relations (Edges)
        if os.path.exists(self.relations_path):
            with open(self.relations_path, 'r') as f:
                try:
                    relations = json.load(f)
                    for r in relations:
                        self.g.add_edge(
                            r['from_entity_key'],
                            r['to_entity_key'],
                            key=r['id'],
                            **r
                        )
                except json.JSONDecodeError:
                    pass
    
    def _save(self):
        # Save Entities
        nodes_data: list[dict[str, Any]] = []
        for n, data in self.g.nodes(data=True):
            # We only save Serializable data
            # datetimes need conversion
            dump_data = data.copy()
            dump_data["entity_key"] = dump_data.get("entity_key", n)
            nodes_data.append(dump_data)
            
        with open(self.entities_path, 'w') as f:
            json.dump(nodes_data, f, default=str, indent=2)

        # Save Relations
        edges_data = []
        for u, v, k, data in self.g.edges(data=True, keys=True):
            dump_data = data.copy()
            edges_data.append(dump_data)
            
        with open(self.relations_path, 'w') as f:
            json.dump(edges_data, f, default=str, indent=2)

    def _infer_entity_type(self, entity_key: str) -> str:
        if ":" in entity_key:
            return entity_key.split(":", 1)[0]
        return "unknown"

    def _infer_entity_name(self, entity_key: str) -> str:
        if ":" in entity_key:
            return entity_key.split(":", 1)[1]
        return entity_key

    async def upsert_entity(
        self,
        entity_key: str,
        entity_type: Optional[str],
        current_memory_id: Optional[str],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if entity_key in self.g.nodes:
            data = self.g.nodes[entity_key]
            data["entity_key"] = entity_key
            data["entity_type"] = entity_type or data.get("entity_type") or self._infer_entity_type(entity_key)
            if current_memory_id is not None:
                data["current_memory_id"] = current_memory_id
            data["updated_at"] = now
        else:
            self.g.add_node(
                entity_key,
                entity_key=entity_key,
                entity_type=entity_type or self._infer_entity_type(entity_key),
                name=self._infer_entity_name(entity_key),
                current_memory_id=current_memory_id,
                created_at=now,
                updated_at=now,
            )
        self._save()

    async def clear_current_memory(self, entity_key: str) -> None:
        if entity_key not in self.g.nodes:
            return
        data = self.g.nodes[entity_key]
        data["current_memory_id"] = None
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    async def list_entities(self) -> List[Dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        for n, data in self.g.nodes(data=True):
            item = dict(data)
            item["entity_key"] = item.get("entity_key", n)
            entities.append(item)
        return entities

    async def add_relation(self, relation: Relation):
        data = relation.model_dump()
        # Convert datetime objects to string for JSON serialization within NetworkX attributes if needed
        # Or just keep as object in memory and convert on save.
        # NetworkX handles objects fine in memory.
        
        self.g.add_edge(
            relation.from_entity_key,
            relation.to_entity_key,
            key=relation.id,
            **data
        )
        await self.upsert_entity(
            relation.from_entity_key,
            self._infer_entity_type(relation.from_entity_key),
            current_memory_id=None,
        )
        await self.upsert_entity(
            relation.to_entity_key,
            self._infer_entity_type(relation.to_entity_key),
            current_memory_id=None,
        )

    async def delete_relation(self, relation_id: str) -> bool:
        for from_key, to_key, edge_key in list(self.g.edges(keys=True)):
            if edge_key == relation_id:
                self.g.remove_edge(from_key, to_key, key=edge_key)
                self._save()
                return True
        return False

    async def get_relations(self, entity_key: str, relation_types: Optional[List[str]] = None, depth: int = 1) -> List[Dict]:
        if entity_key not in self.g or depth < 1:
            return []

        def _serialize(value: Any) -> Any:
            if isinstance(value, datetime):
                return value.isoformat()
            return value

        results: list[dict[str, Any]] = []
        seen_edges: set[str] = set()
        visited = {entity_key}
        queue: list[tuple[str, int]] = [(entity_key, 0)]

        while queue:
            current, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue

            # Outgoing edges
            for u, v, k, data in self.g.out_edges(current, data=True, keys=True):
                if relation_types and data.get("relation_type") not in relation_types:
                    continue
                edge_id = data.get("id", k)
                if edge_id in seen_edges:
                    continue
                seen_edges.add(edge_id)
                item = dict(data)
                item["from_entity_key"] = data.get("from_entity_key", u)
                item["to_entity_key"] = data.get("to_entity_key", v)
                results.append({k: _serialize(v) for k, v in item.items()})
                if v not in visited:
                    visited.add(v)
                    queue.append((v, current_depth + 1))

            # Incoming edges
            for u, v, k, data in self.g.in_edges(current, data=True, keys=True):
                if relation_types and data.get("relation_type") not in relation_types:
                    continue
                edge_id = data.get("id", k)
                if edge_id in seen_edges:
                    continue
                seen_edges.add(edge_id)
                item = dict(data)
                item["from_entity_key"] = data.get("from_entity_key", u)
                item["to_entity_key"] = data.get("to_entity_key", v)
                results.append({k: _serialize(v) for k, v in item.items()})
                if u not in visited:
                    visited.add(u)
                    queue.append((u, current_depth + 1))

        return results

    async def add_evolution_edge(self, from_id: str, to_id: str):
        # Evolution is stored separately or as a specific edge type in the graph?
        # PRD mentions "evolution_chains.json" in structure but also "Graph Store (NetworkX)".
        # And "add_evolution_edge" in "evolve_memory".
        # Let's simply track evolution parent/child in the graph but maybe with a special prefix or type?
        # OR just use the MemoryNode parent_id logic which is already in VectorStore.
        # If we need graph visualization of evolution, we can add it to the graph.
        # But MemoryNodes are not Entities. The Entity is "preference:editor".
        # So evolution happens *inside* the Entity's history.
        # The GraphStore in PRD primarily links Entities.
        
        # However, 5.2 code says: `await graph_store.add_evolution_edge(from_id, to_id)`
        # This implies we might want to track memory node relationships in a graph too?
        # Or perhaps this is for a separate "Evolution Graph".
        # Let's implement it by appending to a list or simple adjacency in memory if needed.
        # Or Just use the `evolution_chains.json`.
        
        chain_entry = {"from": from_id, "to": to_id, "timestamp": datetime.now(timezone.utc).isoformat()}
        
        chains = []
        if os.path.exists(self.evolution_path):
            with open(self.evolution_path, 'r') as f:
                try:
                    chains = json.load(f)
                except json.JSONDecodeError:
                    pass
        chains.append(chain_entry)
        
        with open(self.evolution_path, 'w') as f:
            json.dump(chains, f, indent=2)

graph_store = GraphStore()
