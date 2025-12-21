from datetime import datetime, timezone
from uuid import uuid4
from ..engine.models import Relation
from ..storage.graph import graph_store

async def relate_tool(arguments: dict) -> dict:
    from_key = arguments.get("from_entity_key")
    to_key = arguments.get("to_entity_key")
    relation_type = arguments.get("relation_type")
    properties = arguments.get("properties", {})
    
    if not from_key or not to_key or not relation_type:
        raise ValueError("Missing required arguments: from_entity_key, to_entity_key, relation_type")
        
    relation = Relation(
        id=str(uuid4()),
        from_entity_key=from_key,
        to_entity_key=to_key,
        relation_type=relation_type,
        properties=properties,
        created_at=datetime.now(timezone.utc)
    )
    
    await graph_store.add_relation(relation)
    
    return {
        "status": "created",
        "relation_id": relation.id,
        "from": from_key,
        "to": to_key,
        "type": relation_type
    }
