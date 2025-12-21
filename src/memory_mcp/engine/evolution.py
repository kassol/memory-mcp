import re
from uuid import uuid4
from datetime import datetime, timezone
from difflib import SequenceMatcher

from ..engine.models import MemoryNode, MutationType
from ..storage.vector import vector_store
from ..storage.graph import graph_store

# In a real expanded version, this would call an LLM to determine the mutation type and reason.
# For MVP, we can use simple heuristics or valid mock placeholders logic, 
# but per PRD 5.3 it lists rules. We'll implement basic heuristic rules here.

_NEGATION_TOKENS = [
    " not ",
    " no ",
    " never ",
    "不是",
    "不再",
    "不",
    "没有",
    "无",
]
_CORRECTION_TOKENS = [
    "纠正",
    "更正",
    "修正",
    "其实",
    "事实上",
    "应该是",
    "actually",
    "correction",
]

def _contains_any(text: str, tokens: list[str]) -> bool:
    return any(token in text for token in tokens)

def _has_negation_flip(old: str, new: str) -> bool:
    old_has = _contains_any(old, _NEGATION_TOKENS)
    new_has = _contains_any(new, _NEGATION_TOKENS)
    return old_has != new_has

def _numeric_tokens(text: str) -> list[str]:
    return re.findall(r"\d+(?:\\.\\d+)?", text)

def infer_mutation_type(old: str, new: str) -> MutationType:
    old_lower = old.lower()
    new_lower = new.lower()
    similarity = SequenceMatcher(None, old_lower, new_lower).ratio()

    # 1. Reversal detection: negation flips with reasonable similarity
    if _has_negation_flip(old_lower, new_lower) and similarity >= 0.4:
        return MutationType.REVERSAL

    # 2. Correction detection: explicit correction cues
    if _contains_any(new_lower, _CORRECTION_TOKENS):
        return MutationType.CORRECTION

    # 3. Refinement detection: more details while preserving context
    if len(new) > len(old) * 1.5 and similarity >= 0.6:
        return MutationType.REFINEMENT

    # 4. Update detection: numeric changes or close length with moderate similarity
    old_nums = _numeric_tokens(old_lower)
    new_nums = _numeric_tokens(new_lower)
    if old_nums and new_nums and old_nums != new_nums:
        return MutationType.UPDATE
    if similarity >= 0.6:
        return MutationType.UPDATE

    return MutationType.EVOLUTION

def generate_mutation_reason(old: str, new: str, mutation_type: MutationType) -> str:
    return f"Auto-detected {mutation_type.value} from content change."

async def evolve_memory(
    new_content: str,
    existing_node: MemoryNode,
    embedding: list[float],
    *,
    mutation_type_override: MutationType | None = None,
    conflict: bool = False,
    conflict_with_id: str | None = None,
) -> MemoryNode:
    
    # 1. Infer mutation type
    mutation_type = mutation_type_override or infer_mutation_type(existing_node.content, new_content)
    
    # 2. Generate reason
    mutation_reason = generate_mutation_reason(existing_node.content, new_content, mutation_type)
    
    # 3. Create new node
    new_node = MemoryNode(
        id=str(uuid4()),
        entity_key=existing_node.entity_key,
        entity_type=existing_node.entity_type,
        content=new_content,
        embedding=embedding,
        parent_id=existing_node.id,
        mutation_type=mutation_type,
        mutation_reason=mutation_reason,
        created_at=datetime.now(timezone.utc),
        valid_from=datetime.now(timezone.utc),
        is_current=True,
        conflict=conflict,
        conflict_with_id=conflict_with_id if conflict else None,
        tags=existing_node.tags # Carry over tags? PRD doesn't specify, but makes sense.
    )
    
    # 4. Update old node
    existing_node.is_current = False
    existing_node.valid_until = datetime.now(timezone.utc)
    
    # 5. Persist
    await vector_store.update(existing_node)
    await vector_store.insert(new_node)
    await graph_store.add_evolution_edge(existing_node.id, new_node.id)
    
    return new_node
