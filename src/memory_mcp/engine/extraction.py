import json
import re

from ..tools.remember import remember_tool
from .embedding import embedding_service
from .key_assignment import assign_entity_key
from .llm import chat


class ExtractionError(RuntimeError):
    """Raised when extraction cannot be completed due to upstream/service failure."""


_EXTRACTION_PROMPT = """You are a memory extraction assistant. Given a conversation, extract structured memories.

For each distinct piece of information worth remembering, output a JSON object with:
- "entity_key": a unique string identifier (e.g., "preference:editor", "fact:location")
- "entity_type": the category (e.g., "preference", "fact", "skill", "project")
- "content": the exact memory content as a concise statement

Output ONLY a JSON array of these objects, nothing else. Example:
[
  {"entity_key": "preference:editor", "entity_type": "preference", "content": "Prefers Cursor as main editor"},
  {"entity_key": "fact:location", "entity_type": "fact", "content": "Lives in Shanghai"}
]

If nothing is worth remembering, output an empty array: []

Conversation to analyze:
"""


async def _call_llm(messages: list[dict]) -> str:
    conversation_text = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
    )
    return await chat(_EXTRACTION_PROMPT + conversation_text)


def _parse_llm_output(text: str) -> list[dict]:
    # Try direct JSON parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # Fall back to extracting from code fences
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    return []


async def extract_memories(messages: list[dict]) -> dict:
    try:
        llm_output = await _call_llm(messages)
    except Exception as exc:
        raise ExtractionError("LLM extraction failed") from exc

    candidates = _parse_llm_output(llm_output)

    results = []
    errors = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        entity_key = candidate.get("entity_key")
        entity_type = candidate.get("entity_type")
        content = candidate.get("content")
        if not entity_key or not entity_type or not content:
            continue
        try:
            # The extraction LLM cannot see stored keys; reassign against current memories.
            embedding = await embedding_service.get_embedding(content)
            entity_key, entity_type = await assign_entity_key(content, embedding)
            result = await remember_tool(
                {
                    "entity_key": entity_key,
                    "entity_type": entity_type,
                    "content": content,
                    "skip_semantic_merge": True,
                },
                embedding=embedding,
            )
            results.append(result)
        except Exception as exc:
            errors.append(
                {
                    "entity_key": entity_key,
                    "entity_type": entity_type,
                    "content": content,
                    "error": str(exc),
                }
            )

    return {"results": results, "errors": errors, "total": len(results), "failed": len(errors)}
