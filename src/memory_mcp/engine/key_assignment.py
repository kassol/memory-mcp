import json
import re

from ..storage.vector import vector_store
from .embedding import embedding_service
from .llm import chat


class KeyAssignmentError(RuntimeError):
    """Raised when an entity_key cannot be assigned (LLM failure or unusable output)."""


NEIGHBOR_LIMIT = 5

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_]+$")

_KEY_ASSIGNMENT_PROMPT = """You assign an entity_key to a new memory so that facts about the same subject share one key.
A shared key lets the store track updates and detect contradictions over time.

Existing current memories most similar to the new one:
{neighbors}

New memory:
{content}

Decide:
- If the new memory describes the same entity or topic as one existing memory (it repeats, updates, refines, or contradicts it), reuse that memory's entity_key and entity_type exactly.
- Otherwise, create a new entity_key in the format "<entity_type>:<snake_case_subject>", using lowercase English letters, digits and underscores only (e.g. "preference:main_editor", "fact:home_city"). entity_type is a short lowercase category such as preference, fact, skill, project, decision, procedure.
- Reuse only when the subject is the same; a related but different subject gets a new key.

Output ONLY a JSON object, nothing else:
{{"entity_key": "...", "entity_type": "..."}}
"""


def _format_neighbors(neighbors: list) -> str:
    if not neighbors:
        return "(none)"
    return "\n".join(
        json.dumps(
            {"entity_key": n.entity_key, "entity_type": n.entity_type, "content": n.content},
            ensure_ascii=False,
        )
        for n in neighbors
    )


def _parse_output(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise KeyAssignmentError(f"Key assignment output is not JSON: {text[:200]!r}")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise KeyAssignmentError(f"Key assignment output is not JSON: {text[:200]!r}") from exc
    if not isinstance(data, dict):
        raise KeyAssignmentError(f"Key assignment output is not a JSON object: {text[:200]!r}")
    return data


async def assign_entity_key(content: str, embedding: list[float] | None = None) -> tuple[str, str]:
    """Return (entity_key, entity_type), reusing a neighbor's key when it is the same subject."""
    if embedding is None:
        embedding = await embedding_service.get_embedding(content)
    hits = await vector_store.search(query_vector=embedding, limit=NEIGHBOR_LIMIT, filter_current=True)
    neighbors = [node for node, _ in hits]

    prompt = _KEY_ASSIGNMENT_PROMPT.format(neighbors=_format_neighbors(neighbors), content=content)
    try:
        text = await chat(prompt)
    except Exception as exc:
        raise KeyAssignmentError(f"LLM key assignment failed: {exc!r}") from exc

    data = _parse_output(text)
    entity_key = data.get("entity_key")
    entity_type = data.get("entity_type")
    if not isinstance(entity_key, str) or not isinstance(entity_type, str):
        raise KeyAssignmentError(f"Key assignment output missing entity_key/entity_type: {data!r}")

    # Reuse: neighbor keys may predate the naming format, so trust the stored type, not the LLM's.
    existing = {n.entity_key: n.entity_type for n in neighbors}
    if entity_key in existing:
        return entity_key, existing[entity_key]

    if not _KEY_PATTERN.match(entity_key) or not entity_key.startswith(f"{entity_type}:"):
        raise KeyAssignmentError(f"Invalid new entity_key {entity_key!r} for entity_type {entity_type!r}")
    return entity_key, entity_type
