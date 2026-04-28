from ..storage.graph import graph_store


async def unrelate_tool(arguments: dict) -> dict:
    relation_id = arguments.get("relation_id")

    if not relation_id:
        raise ValueError("Missing required argument: relation_id")

    deleted = await graph_store.delete_relation(relation_id)
    return {
        "status": "deleted" if deleted else "not_found",
        "relation_id": relation_id,
    }
