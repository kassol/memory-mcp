from ..storage.vector import vector_store

async def trace_tool(arguments: dict) -> dict:
    entity_key = arguments.get("entity_key")
    output_format = arguments.get("format", "timeline")
    
    if not entity_key:
        raise ValueError("Missing required argument: entity_key")
        
    history = await vector_store.get_history(entity_key)
    
    if not history:
        return {"entity_key": entity_key, "chain": [], "total_versions": 0}
        
    # Sort just in case
    history.sort(key=lambda x: x.created_at)
    output_format = str(output_format).lower()

    if output_format == "summary":
        current_node = next((n for n in history if n.is_current), history[-1])
        summary = f"total_versions={len(history)}, current={current_node.content}"
        return {
            "entity_key": entity_key,
            "summary": summary,
            "total_versions": len(history),
            "current": {
                "id": current_node.id,
                "content": current_node.content,
                "mutation_type": current_node.mutation_type.value,
                "created_at": current_node.created_at.isoformat(),
                "is_current": current_node.is_current,
            },
        }
    
    chain = []
    for node in history:
        item = {
            "id": node.id,
            "content": node.content,
            "mutation_type": node.mutation_type.value,
            "created_at": node.created_at.isoformat(),
            "is_current": node.is_current,
            "conflict": node.conflict,
        }
        if node.conflict_with_id:
            item["conflict_with_id"] = node.conflict_with_id
        if node.mutation_reason:
            item["mutation_reason"] = node.mutation_reason
        chain.append(item)
        
    return {
        "entity_key": entity_key,
        "chain": chain,
        "total_versions": len(chain)
    }
