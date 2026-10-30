import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from uuid import uuid4

from ..engine.models import MemoryNode, MutationType
from ..engine.tokenizer import tokenize
from ..storage.graph import graph_store
from ..storage.vector import vector_store


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
    return re.findall(r"\d+(?:\.\d+)?", text)


def infer_mutation_type(old: str, new: str) -> MutationType:
    old_lower = old.lower()
    new_lower = new.lower()
    similarity = SequenceMatcher(None, old_lower, new_lower).ratio()

    if _has_negation_flip(old_lower, new_lower) and similarity >= 0.4:
        return MutationType.REVERSAL
    if _contains_any(new_lower, _CORRECTION_TOKENS):
        return MutationType.CORRECTION
    if len(new) > len(old) * 1.5 and similarity >= 0.6:
        return MutationType.REFINEMENT
    old_nums = _numeric_tokens(old_lower)
    new_nums = _numeric_tokens(new_lower)
    if old_nums and new_nums and old_nums != new_nums:
        return MutationType.UPDATE
    if similarity >= 0.6:
        return MutationType.UPDATE
    return MutationType.EVOLUTION


def generate_mutation_reason(_old: str, _new: str, mutation_type: MutationType) -> str:
    return f"Auto-detected {mutation_type.value} from content change."


async def evolve_memory(
    new_content: str,
    existing_node: MemoryNode,
    embedding: list[float],
    *,
    mutation_type_override: MutationType | None = None,
    conflict: bool = False,
    conflict_with_id: str | None = None,
    created_at: datetime | None = None,
    tags: list[str] | None = None,
    fields: dict | None = None,
) -> MemoryNode:
    mutation_type = mutation_type_override or infer_mutation_type(existing_node.content, new_content)
    mutation_reason = generate_mutation_reason(existing_node.content, new_content, mutation_type)

    now = created_at or datetime.now(timezone.utc)
    new_node = MemoryNode(
        id=str(uuid4()),
        entity_key=existing_node.entity_key,
        entity_type=existing_node.entity_type,
        content=new_content,
        content_tokens=tokenize(new_content),
        embedding=embedding,
        parent_id=existing_node.id,
        mutation_type=mutation_type,
        mutation_reason=mutation_reason,
        created_at=now,
        valid_from=now,
        is_current=True,
        conflict=conflict,
        conflict_with_id=conflict_with_id if conflict else None,
        # Content is merged, so tags are merged too.
        tags=existing_node.tags + [t for t in tags or [] if t not in existing_node.tags],
        **(fields or {}),
    )

    # Insert first: a stop in between leaves two current versions (visible), never zero.
    await vector_store.insert(new_node)
    existing_node.is_current = False
    existing_node.valid_until = now
    await vector_store.update(existing_node)
    await graph_store.upsert_entity(new_node.entity_key, new_node.entity_type, new_node.id)
    return new_node
