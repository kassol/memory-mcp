from ..storage.vector import vector_store


async def recall_all_tool(arguments: dict) -> dict:
    entity_type = arguments.get("entity_type")
    limit = arguments.get("limit", 100)
    offset = arguments.get("offset", 0)
    order = arguments.get("order", "created_at")
    sort = arguments.get("sort")
    direction = arguments.get("direction", "desc")
    key = arguments.get("key")

    memories = await vector_store.list_current(
        entity_type=entity_type, limit=limit, offset=offset, order=order,
        sort=sort, direction=direction, key=key,
    )
    results = [
        {
            "memory_id": node.id,
            "entity_key": node.entity_key,
            "content": node.content,
            "entity_type": node.entity_type,
            "created_at": node.created_at.isoformat(),
            "valid_from": node.valid_from.isoformat(),
            "last_mutation": node.mutation_type.value,
        }
        for node in memories
    ]
    # total: items in this page (unchanged meaning); matched: all current memories the filters match.
    matched = await vector_store.count_current(entity_type=entity_type, key=key)
    return {"results": results, "total": len(results), "matched": matched}
