from datetime import datetime, timezone
from uuid import uuid4

from ..engine.models import MemoryNode, MutationType
from ..engine.embedding import embedding_service
from ..engine.evolution import evolve_memory, infer_mutation_type
from ..engine.conflict import conflict_detector
from ..storage.vector import vector_store
from ..storage.graph import graph_store
from ..config import settings

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

async def remember_tool(arguments: dict) -> dict:
    content = arguments.get("content")
    entity_key = arguments.get("entity_key")
    entity_type = arguments.get("entity_type")
    tags = arguments.get("tags", [])
    skip_semantic_merge = arguments.get("skip_semantic_merge", False)

    if not content or not entity_key or not entity_type:
        raise ValueError("Missing required arguments: content, entity_key, entity_type")

    # 1. Generate embedding
    embedding = await embedding_service.get_embedding(content)
    
    # 2. Check for existing current memory for this entity_key
    history = await vector_store.get_history(entity_key)
    current_node = next((n for n in history if n.is_current), None)
    
    if current_node:
        # Check if identical content (dup)
        if current_node.content == content:
            return {"status": "no_change", "memory_id": current_node.id}

        llm_conflict = await conflict_detector.check_conflict(current_node.content, content)
        suggested_type = infer_mutation_type(current_node.content, content)

        if llm_conflict:
            mutation_type_override = (
                MutationType.REVERSAL if suggested_type == MutationType.REVERSAL else MutationType.CORRECTION
            )
        else:
            mutation_type_override = suggested_type

        conflict = llm_conflict or mutation_type_override in {MutationType.CORRECTION, MutationType.REVERSAL}

        new_node = await evolve_memory(
            content,
            current_node,
            embedding,
            mutation_type_override=mutation_type_override,
            conflict=conflict,
            conflict_with_id=current_node.id,
        )
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

    # 3. Semantic similarity check for conflict detection when entity_key not found
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
                    suggested_type = infer_mutation_type(candidate.content, content)
                    mutation_type_override = (
                        MutationType.REVERSAL if suggested_type == MutationType.REVERSAL else MutationType.CORRECTION
                    )
                    new_node = await evolve_memory(
                        content,
                        candidate,
                        embedding,
                        mutation_type_override=mutation_type_override,
                        conflict=True,
                        conflict_with_id=candidate.id,
                    )
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

    # 4. Initial memory
    new_node = MemoryNode(
        id=str(uuid4()),
        entity_key=entity_key,
        entity_type=entity_type,
        content=content,
        embedding=embedding,
        mutation_type=MutationType.INITIAL,
        created_at=datetime.now(timezone.utc),
        valid_from=datetime.now(timezone.utc),
        is_current=True,
        tags=tags,
    )
    await vector_store.insert(new_node)
    await graph_store.upsert_entity(entity_key, entity_type, new_node.id)
    return {
        "status": "created",
        "memory_id": new_node.id,
        "entity_key": entity_key,
        "mutation_type": "initial"
    }
