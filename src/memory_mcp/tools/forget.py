from datetime import datetime, timezone

from ..storage.vector import vector_store
from ..storage.graph import graph_store

async def forget_tool(arguments: dict) -> dict:
    entity_key = arguments.get("entity_key")
    reason = arguments.get("reason", "User requested archive")
    
    if not entity_key:
        raise ValueError("Missing required argument: entity_key")
        
    # Find current memory for this key
    history = await vector_store.get_history(entity_key)
    current_node = next((n for n in history if n.is_current), None)
    
    if not current_node:
        return {"status": "not_found", "message": f"No active memory found for {entity_key}"}
        
    # Mark as not current and set archive metadata
    current_node.is_current = False
    current_node.valid_until = datetime.now(timezone.utc)
    current_node.archived_reason = reason
    current_node.archived_at = datetime.now(timezone.utc)
    
    await vector_store.update(current_node)
    await graph_store.clear_current_memory(entity_key)
    
    return {
        "status": "archived",
        "entity_key": entity_key,
        "previous_content": current_node.content,
        "archived_reason": reason,
    }
