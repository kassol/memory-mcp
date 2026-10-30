"""Human governance of memories from the web console: read one, list, correct. REST only, not MCP."""
from typing import Optional

from ..engine.embedding import embedding_service
from ..engine.evolution import evolve_memory
from ..engine.models import MemoryNode, MutationType
from ..storage.vector import vector_store


class NotCurrent(ValueError):
    """The memory exists but is no longer the current version."""


def memory_view(node: MemoryNode) -> dict:
    return {
        "memory_id": node.id,
        "entity_key": node.entity_key,
        "entity_type": node.entity_type,
        "content": node.content,
        "mutation_type": node.mutation_type.value,
        "created_at": node.created_at.isoformat(),
        "valid_from": node.valid_from.isoformat(),
        "is_current": node.is_current,
        "conflict": node.conflict,
        "archived_reason": node.archived_reason,
    }


async def get_memory(memory_id: str) -> Optional[dict]:
    """One memory plus every version of its entity_key, newest first."""
    node = await vector_store.get_by_id(memory_id)
    if node is None:
        return None
    history = await vector_store.get_history(node.entity_key)
    return {
        **memory_view(node),
        "versions": [memory_view(v) for v in sorted(history, key=lambda v: v.created_at, reverse=True)],
    }


async def correct_memory(memory_id: str, content: str) -> dict:
    """Replace a current memory with person-written content as a new correction version.

    The person's text is authoritative, so there is no LLM merge; only the embedding is recomputed.
    """
    if not content or not content.strip():
        raise ValueError("Missing required field: content")
    node = await vector_store.get_by_id(memory_id)
    if node is None:
        raise LookupError(f"Memory not found: {memory_id}")
    if not node.is_current:
        raise NotCurrent(f"Memory {memory_id} is not current")
    content = content.strip()
    embedding = await embedding_service.get_embedding(content)
    new_node = await evolve_memory(
        content, node, embedding, mutation_type_override=MutationType.CORRECTION
    )
    return memory_view(new_node)
