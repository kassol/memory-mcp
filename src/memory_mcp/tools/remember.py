from datetime import datetime, timezone
from uuid import uuid4

from ..config import settings
from ..engine import key_assignment, merge
from ..engine.conflict import conflict_detector
from ..engine.embedding import embedding_service
from ..engine.evolution import evolve_memory, infer_mutation_type
from ..engine.models import MemoryNode, MutationType, SourceRef
from ..engine.tokenizer import tokenize
from ..storage.graph import graph_store
from ..storage.vector import vector_store


def _distance_to_relevance(distance: float | None) -> float | None:
    if distance is None:
        return None
    return 1 / (1 + distance)


def _build_labels(conflict: bool, mutation_type: MutationType) -> list[str]:
    labels: list[str] = []
    if conflict:
        labels.append("conflict")
    if mutation_type == MutationType.CORRECTION:
        labels.append("correction")
    elif mutation_type == MutationType.REVERSAL:
        labels.append("reversal")
    return labels


def _parse_source_refs(raw) -> list[SourceRef]:
    if not raw:
        return []
    out: list[SourceRef] = []
    for item in raw:
        if isinstance(item, SourceRef):
            out.append(item)
        elif isinstance(item, dict) and item.get("thread_id"):
            out.append(SourceRef(**item))
    return out


async def _merge_with(old_content: str, content: str, embedding: list[float]) -> tuple[str, bool, list[float]]:
    """Merge into the old version; the stored vector must describe the merged text."""
    merged, conflict = await merge.merge_memories(old_content, content)
    if merged not in (content, old_content):  # old_content means no_change; nothing gets stored
        embedding = await embedding_service.get_embedding(merged)
    return merged, conflict, embedding


async def remember_tool(
    arguments: dict, *, embedding: list[float] | None = None, created_at: datetime | None = None
) -> dict:
    """Without entity_key/entity_type the server assigns them via `assign_entity_key`.

    `embedding` (precomputed vector of `content`) and `created_at` (original creation time)
    are for in-process callers only; never exposed via MCP/REST."""
    content = arguments.get("content")
    entity_key = arguments.get("entity_key")
    entity_type = arguments.get("entity_type")
    tags = arguments.get("tags", [])
    skip_semantic_merge = arguments.get("skip_semantic_merge", False)
    origin_client = arguments.get("origin_client")
    origin_session_id = arguments.get("origin_session_id")
    source_thread_id = arguments.get("source_thread_id")
    source_refs = _parse_source_refs(arguments.get("source_refs"))
    title = arguments.get("title")

    if not content:
        raise ValueError("Missing required argument: content")
    if bool(entity_key) != bool(entity_type):
        raise ValueError("entity_key and entity_type must be given together")

    if embedding is None:
        embedding = await embedding_service.get_embedding(content)

    if not entity_key:
        entity_key, entity_type = await key_assignment.assign_entity_key(content, embedding)
        # Key assignment already matched the nearest current memories; a second semantic match would duplicate it.
        skip_semantic_merge = True

    history = await vector_store.get_history(entity_key)
    current_node = next((n for n in history if n.is_current), None)

    if current_node:
        if current_node.content == content:
            return {"status": "no_change", "memory_id": current_node.id}

        merged, llm_conflict, merged_embedding = await _merge_with(current_node.content, content, embedding)
        if merged == current_node.content:
            return {"status": "no_change", "memory_id": current_node.id}
        suggested_type = infer_mutation_type(current_node.content, content)

        if llm_conflict:
            mutation_type_override = (
                MutationType.REVERSAL if suggested_type == MutationType.REVERSAL else MutationType.CORRECTION
            )
        else:
            mutation_type_override = suggested_type

        conflict = llm_conflict or mutation_type_override in {MutationType.CORRECTION, MutationType.REVERSAL}

        new_node = await evolve_memory(
            merged,
            current_node,
            merged_embedding,
            mutation_type_override=mutation_type_override,
            conflict=conflict,
            conflict_with_id=current_node.id,
            created_at=created_at,
            tags=tags,
        )
        if origin_client:
            new_node.origin_client = origin_client
        if origin_session_id:
            new_node.origin_session_id = origin_session_id
        if source_thread_id:
            new_node.source_thread_id = source_thread_id
        if source_refs:
            new_node.source_refs = source_refs
        if title:
            new_node.title = title
            new_node.title_tokens = tokenize(title)
        await vector_store.update(new_node)
        await graph_store.upsert_entity(entity_key, entity_type, new_node.id)
        return {
            "status": "evolved",
            "memory_id": new_node.id,
            "entity_key": new_node.entity_key,
            "mutation_type": new_node.mutation_type.value,
            "mutation_reason": new_node.mutation_reason,
            "parent_id": new_node.parent_id,
            "conflict": new_node.conflict,
            "labels": _build_labels(new_node.conflict, new_node.mutation_type),
        }

    if not skip_semantic_merge:
        similar = await vector_store.search(
            query_vector=embedding,
            limit=1,
            filter_current=True,
            entity_type=entity_type,
        )
        if similar:
            candidate, distance = similar[0]
            relevance = _distance_to_relevance(distance)
            if relevance is not None and relevance >= settings.similarity_threshold:
                is_conflict = await conflict_detector.check_conflict(candidate.content, content)
                if is_conflict:
                    merged, _, merged_embedding = await _merge_with(candidate.content, content, embedding)
                    if merged == candidate.content:
                        return {"status": "no_change", "memory_id": candidate.id}
                    suggested_type = infer_mutation_type(candidate.content, content)
                    mutation_type_override = (
                        MutationType.REVERSAL if suggested_type == MutationType.REVERSAL else MutationType.CORRECTION
                    )
                    new_node = await evolve_memory(
                        merged,
                        candidate,
                        merged_embedding,
                        mutation_type_override=mutation_type_override,
                        conflict=True,
                        conflict_with_id=candidate.id,
                        created_at=created_at,
                        tags=tags,
                    )
                    if origin_client:
                        new_node.origin_client = origin_client
                    if origin_session_id:
                        new_node.origin_session_id = origin_session_id
                    if source_thread_id:
                        new_node.source_thread_id = source_thread_id
                    if source_refs:
                        new_node.source_refs = source_refs
                    if title:
                        new_node.title = title
                        new_node.title_tokens = tokenize(title)
                    await vector_store.update(new_node)
                    await graph_store.upsert_entity(candidate.entity_key, candidate.entity_type, new_node.id)
                    return {
                        "status": "evolved",
                        "memory_id": new_node.id,
                        "entity_key": new_node.entity_key,
                        "mutation_type": new_node.mutation_type.value,
                        "mutation_reason": new_node.mutation_reason,
                        "parent_id": new_node.parent_id,
                        "conflict": new_node.conflict,
                        "labels": _build_labels(new_node.conflict, new_node.mutation_type),
                        "matched_entity_key": candidate.entity_key,
                        "input_entity_key": entity_key,
                    }

    now = created_at or datetime.now(timezone.utc)
    new_node = MemoryNode(
        id=str(uuid4()),
        entity_key=entity_key,
        entity_type=entity_type,
        content=content,
        content_tokens=tokenize(content),
        title=title,
        title_tokens=tokenize(title) if title else None,
        embedding=embedding,
        mutation_type=MutationType.INITIAL,
        created_at=now,
        valid_from=now,
        is_current=True,
        tags=tags,
        origin_client=origin_client,
        origin_session_id=origin_session_id,
        source_thread_id=source_thread_id,
        source_refs=source_refs,
    )
    await vector_store.insert(new_node)
    await graph_store.upsert_entity(entity_key, entity_type, new_node.id)
    return {
        "status": "created",
        "memory_id": new_node.id,
        "entity_key": entity_key,
        "mutation_type": "initial",
    }
