import json
import re

from ..tools.remember import remember_tool
from .embedding import embedding_service
from .key_assignment import assign_entity_key
from .llm import chat


class ExtractionError(RuntimeError):
    """Raised when extraction cannot be completed due to upstream/service failure."""


_EXTRACTION_PROMPT = """You are a memory extraction assistant. Given a conversation, extract memories.

For each distinct piece of information worth remembering, output a JSON object with:
- "content": the exact memory content as a concise statement

Output ONLY a JSON array of these objects, nothing else. Example:
[
  {"content": "Prefers Cursor as main editor"},
  {"content": "Lives in Shanghai"}
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
        content = candidate.get("content")
        if not isinstance(content, str) or not content:
            continue
        entity_key = entity_type = None
        try:
            # Keys are assigned against current memories, which the extraction LLM cannot see.
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
