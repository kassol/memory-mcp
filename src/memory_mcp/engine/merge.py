import json
import re

from .llm import chat


class MergeError(RuntimeError):
    """Raised when two versions cannot be merged; never fall back to replacing the old version."""


_MERGE_PROMPT = """You merge two versions of one memory about the same subject into a single memory.

Old version:
{old}

New version:
{new}

Rules:
- Keep every durable fact from both versions that does not conflict: decisions, conclusions, root causes, preferences, settings, procedures.
- Where the versions conflict, the new version wins.
- Drop old facts the new version makes obsolete, such as earlier progress snapshots or intermediate status; keep only the latest state.
- Remove duplicates. Keep the result at most 1500 characters.
- Keep existing date annotations such as [2026-05] as they are.

Also decide whether the new version contradicts any fact in the old version.

Output ONLY a JSON object, nothing else:
{{"content": "<merged memory>", "conflict": true or false}}
"""


async def merge_memories(old_content: str, new_content: str) -> tuple[str, bool]:
    """Return (merged content, whether new contradicts old). Raises MergeError on any failure."""
    try:
        text = await chat(_MERGE_PROMPT.format(old=old_content, new=new_content))
    except Exception as exc:
        raise MergeError(f"LLM merge failed: {exc!r}") from exc

    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        raise MergeError(f"Merge output is not a JSON object: {text[:200]!r}")
    content = data.get("content")
    conflict = data.get("conflict")
    if not isinstance(content, str) or not content.strip() or not isinstance(conflict, bool):
        raise MergeError(f"Merge output missing content/conflict: {data!r}")
    return content.strip(), conflict
