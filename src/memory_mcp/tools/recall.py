from ..engine.embedding import embedding_service
from ..storage.vector import vector_store

def _distance_to_relevance(distance: float | None) -> float | None:
    if distance is None:
        return None
    return 1 / (1 + distance)

async def recall_tool(arguments: dict) -> dict:
    query = arguments.get("query")
    entity_type = arguments.get("entity_type")
    limit = arguments.get("limit", 10)
    include_evolution = arguments.get("include_evolution", False)
    
    if not query:
        raise ValueError("Missing required argument: query")

    # 1. Embedding
    query_vector = await embedding_service.get_embedding(query)
    
    # 2. Search
    results = await vector_store.search(
        query_vector=query_vector,
        limit=limit,
        filter_current=True, # Default to active memories
        entity_type=entity_type
    )
    
    # 3. Format
    formatted_results = []
    for node, distance in results:
        res = {
            "entity_key": node.entity_key,
            "content": node.content,
            "entity_type": node.entity_type,
            "created_at": node.created_at.isoformat(),
            "last_mutation": node.mutation_type.value,
            "relevance": _distance_to_relevance(distance),
        }
        if include_evolution:
            # Fetch simple history count for evolution summary.
            history = await vector_store.get_history(node.entity_key)
            res["evolution_count"] = len(history)
             
        formatted_results.append(res)
        
    return {
        "results": formatted_results,
        "total": len(formatted_results)
    }
