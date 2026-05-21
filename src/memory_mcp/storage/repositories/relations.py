import json
from typing import Any, Dict, List, Optional

from ...engine.models import Relation
from ..sqlite import SQLiteStore, get_store


def _row_to_dict(row) -> Dict[str, Any]:
    data = dict(row)
    raw = data.get("properties")
    data["properties"] = json.loads(raw) if raw else {}
    return data


class RelationRepository:
    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        self._store = store or get_store()

    async def insert(self, relation: Relation) -> None:
        async with self._store.get_db() as db:
            await db.execute(
                "INSERT INTO relations (id, from_entity_key, to_entity_key, relation_type, "
                "properties, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    relation.id,
                    relation.from_entity_key,
                    relation.to_entity_key,
                    relation.relation_type,
                    json.dumps(relation.properties, ensure_ascii=False),
                    relation.created_at.isoformat(),
                ),
            )

    async def delete(self, relation_id: str) -> bool:
        async with self._store.get_db() as db:
            cur = await db.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
        return (cur.rowcount or 0) > 0

    async def list_by_entity(self, entity_key: str) -> List[Dict[str, Any]]:
        sql = (
            "SELECT id, from_entity_key, to_entity_key, relation_type, properties, created_at "
            "FROM relations WHERE from_entity_key = ? OR to_entity_key = ? ORDER BY created_at"
        )
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, (entity_key, entity_key))
        return [_row_to_dict(r) for r in rows]

    async def list_all(self) -> List[Dict[str, Any]]:
        async with self._store.get_db() as db:
            rows = await db.fetchall(
                "SELECT id, from_entity_key, to_entity_key, relation_type, properties, created_at "
                "FROM relations ORDER BY created_at"
            )
        return [_row_to_dict(r) for r in rows]
