from ..storage.vector import vector_store


async def recall_all_tool(arguments: dict) -> dict:
    entity_type = arguments.get("entity_type")
    limit = arguments.get("limit", 100)

    memories = await vector_store.list_current(entity_type=entity_type, limit=limit)
    results = [
        {
            "entity_key": node.entity_key,
            "content": node.content,
            "entity_type": node.entity_type,
            "created_at": node.created_at.isoformat(),
            "last_mutation": node.mutation_type.value,
        }
        for node in memories
    ]
    return {"results": results, "total": len(results)}
