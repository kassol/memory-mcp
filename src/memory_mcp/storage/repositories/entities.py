from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..sqlite import SQLiteStore, get_store


def _infer_entity_name(entity_key: str) -> str:
    if ":" in entity_key:
        return entity_key.split(":", 1)[1]
    return entity_key


class EntityRepository:
    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        self._store = store or get_store()

    async def upsert(
        self,
        entity_key: str,
        entity_type: str,
        current_memory_id: Optional[str],
        name: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        display_name = name or _infer_entity_name(entity_key)
        async with self._store.get_db() as db:
            existing = await db.fetchone(
                "SELECT entity_key FROM entities WHERE entity_key = ?",
                (entity_key,),
            )
            if existing is None:
                await db.execute(
                    "INSERT INTO entities (entity_key, name, entity_type, current_memory_id, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (entity_key, display_name, entity_type, current_memory_id, now, now),
                )
            else:
                await db.execute(
                    "UPDATE entities SET name = COALESCE(?, name), entity_type = ?, "
                    "current_memory_id = ?, updated_at = ? WHERE entity_key = ?",
                    (display_name, entity_type, current_memory_id, now, entity_key),
                )

    async def clear_current_memory(self, entity_key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self._store.get_db() as db:
            await db.execute(
                "UPDATE entities SET current_memory_id = NULL, updated_at = ? WHERE entity_key = ?",
                (now, entity_key),
            )

    async def get(self, entity_key: str) -> Optional[Dict[str, Any]]:
        async with self._store.get_db() as db:
            row = await db.fetchone(
                "SELECT entity_key, name, entity_type, current_memory_id, created_at, updated_at "
                "FROM entities WHERE entity_key = ?",
                (entity_key,),
            )
        return dict(row) if row else None

    async def list_all(self) -> List[Dict[str, Any]]:
        async with self._store.get_db() as db:
            rows = await db.fetchall(
                "SELECT entity_key, name, entity_type, current_memory_id, created_at, updated_at "
                "FROM entities ORDER BY entity_key"
            )
        return [dict(r) for r in rows]

    async def delete(self, entity_key: str) -> bool:
        async with self._store.get_db() as db:
            cur = await db.execute("DELETE FROM entities WHERE entity_key = ?", (entity_key,))
        return (cur.rowcount or 0) > 0
