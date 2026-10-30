from ..engine import hybrid_search
from ..storage.vector import vector_store


async def recall_tool(arguments: dict) -> dict:
    query = arguments.get("query")
    entity_type = arguments.get("entity_type")
    limit = arguments.get("limit", 10)
    include_evolution = arguments.get("include_evolution", False)
    explain = arguments.get("explain", False)

    if not query:
        raise ValueError("Missing required argument: query")

    hits = await hybrid_search.search(query, limit=limit, entity_type=entity_type)

    formatted_results = []
    for hit in hits:
        node = hit.node
        res = {
            "memory_id": node.id,
            "entity_key": node.entity_key,
            "content": node.content,
            "entity_type": node.entity_type,
            "created_at": node.created_at.isoformat(),
            "last_mutation": node.mutation_type.value,
            "relevance": hit.score,
        }
        if include_evolution:
            history = await vector_store.get_history(node.entity_key)
            res["evolution_count"] = len(history)
        if explain:
            res["vector_rank"] = hit.vector_rank
            res["fts_rank"] = hit.fts_rank
            res["graph_rank"] = hit.graph_rank
            res["rrf_score"] = hit.score
        formatted_results.append(res)

    return {"results": formatted_results, "total": len(formatted_results)}
