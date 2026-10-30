from datetime import datetime, timezone

from ..storage.graph import graph_store
from ..storage.vector import vector_store


class MemoryNotFound(ValueError):
    pass


class MemoryNotCurrent(ValueError):
    pass


async def forget_tool(arguments: dict) -> dict:
    """Archive the current memory given by `memory_id`, or the current memory of `entity_key`."""
    memory_id = arguments.get("memory_id")
    entity_key = arguments.get("entity_key")
    reason = arguments.get("reason", "User requested archive")

    if memory_id:
        current_node = await vector_store.get_by_id(memory_id)
        if current_node is None:
            raise MemoryNotFound(f"Memory not found: {memory_id}")
        if not current_node.is_current:
            raise MemoryNotCurrent(f"Memory {memory_id} is not current (already archived or superseded)")
        entity_key = current_node.entity_key
    elif entity_key:
        history = await vector_store.get_history(entity_key)
        current_node = next((n for n in history if n.is_current), None)
        if not current_node:
            return {"status": "not_found", "message": f"No active memory found for {entity_key}"}
    else:
        raise ValueError("Missing required argument: memory_id or entity_key")

    current_node.is_current = False
    current_node.valid_until = datetime.now(timezone.utc)
    current_node.archived_reason = reason
    current_node.archived_at = datetime.now(timezone.utc)

    await vector_store.update(current_node)
    await graph_store.clear_current_memory(entity_key)

    return {
        "status": "archived",
        "memory_id": current_node.id,
        "entity_key": entity_key,
        "previous_content": current_node.content,
        "archived_reason": reason,
    }
