import json
import re

import httpx

from ..config import settings
from ..tools.remember import remember_tool


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
    prompt = _EXTRACTION_PROMPT + conversation_text

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://memory-mcp.app",
        "X-Title": "Memory MCP",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers=headers,
            json={
                "model": settings.llm_model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()


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
            result = await remember_tool({
                "entity_key": entity_key,
                "entity_type": entity_type,
                "content": content,
                "skip_semantic_merge": True,
            })
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
