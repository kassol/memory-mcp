from ..storage.graph import graph_store

async def graph_query_tool(arguments: dict) -> dict:
    entity_key = arguments.get("entity_key")
    relation_types = arguments.get("relation_types")
    depth = arguments.get("depth", 1)
    
    if not entity_key:
        raise ValueError("Missing required argument: entity_key")
    if not isinstance(depth, int) or depth < 1:
        depth = 1
        
    relations = await graph_store.get_relations(entity_key, relation_types, depth)
    
    return {
        "entity_key": entity_key,
        "relations": relations,
        "count": len(relations)
    }
