import json
from datetime import datetime
from typing import Any, Iterable

from ..engine.models import MemoryNode, MutationType, ReviewStatus, SourceRef


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def memory_to_row(node: MemoryNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "entity_key": node.entity_key,
        "entity_type": node.entity_type,
        "content": node.content,
        "content_tokens": node.content_tokens,
        "title": node.title,
        "title_tokens": node.title_tokens,
        "parent_id": node.parent_id,
        "mutation_type": node.mutation_type.value,
        "mutation_reason": node.mutation_reason,
        "created_at": _to_iso(node.created_at),
        "valid_from": _to_iso(node.valid_from),
        "valid_until": _to_iso(node.valid_until),
        "is_current": 1 if node.is_current else 0,
        "confidence": node.confidence,
        "review_status": node.review_status.value,
        "archived_reason": node.archived_reason,
        "archived_at": _to_iso(node.archived_at),
        "conflict": 1 if node.conflict else 0,
        "conflict_with_id": node.conflict_with_id,
        "tags": json.dumps(node.tags, ensure_ascii=False),
        "source": node.source,
        "origin_client": node.origin_client,
        "origin_session_id": node.origin_session_id,
        "source_thread_id": node.source_thread_id,
        "source_refs": json.dumps([r.model_dump() for r in node.source_refs], ensure_ascii=False),
        "access_count": node.access_count,
        "last_accessed_at": _to_iso(node.last_accessed_at),
        "reinforce_count": node.reinforce_count,
    }


def row_to_memory(row: Iterable[Any], embedding: list[float] | None = None) -> MemoryNode:
    data = dict(row)  # supports both sqlite3.Row and dict
    tags_raw = data.get("tags")
    refs_raw = data.get("source_refs")
    return MemoryNode(
        id=data["id"],
        entity_key=data["entity_key"],
        entity_type=data["entity_type"],
        content=data["content"],
        content_tokens=data.get("content_tokens"),
        title=data.get("title"),
        title_tokens=data.get("title_tokens"),
        embedding=list(embedding or []),
        parent_id=data.get("parent_id"),
        mutation_type=MutationType(data["mutation_type"]),
        mutation_reason=data.get("mutation_reason"),
        created_at=_dt(data["created_at"]),
        valid_from=_dt(data["valid_from"]),
        valid_until=_dt(data.get("valid_until")),
        is_current=bool(data.get("is_current")),
        confidence=float(data["confidence"]) if data.get("confidence") is not None else 1.0,
        review_status=ReviewStatus(data.get("review_status") or "auto"),
        archived_reason=data.get("archived_reason"),
        archived_at=_dt(data.get("archived_at")),
        conflict=bool(data.get("conflict")),
        conflict_with_id=data.get("conflict_with_id"),
        tags=json.loads(tags_raw) if tags_raw else [],
        source=data.get("source") or "conversation",
        origin_client=data.get("origin_client"),
        origin_session_id=data.get("origin_session_id"),
        source_thread_id=data.get("source_thread_id"),
        source_refs=[SourceRef(**r) for r in (json.loads(refs_raw) if refs_raw else [])],
        access_count=int(data.get("access_count") or 0),
        last_accessed_at=_dt(data.get("last_accessed_at")),
        reinforce_count=int(data.get("reinforce_count") or 0),
    )
