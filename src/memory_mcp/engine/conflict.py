import re

from .llm import chat

# PRD mentions using "LLM Judgment" for conflict.
# We'll mock the interface or implement a simple call similar to EmbeddingService if credentials provided.
# Since we reuse OpenRouter, we can use that.


class ConflictCheckError(RuntimeError):
    """Raised when the conflict judgment cannot be obtained; never read that as "no conflict"."""


_VERDICT = re.compile(r"^\W*(YES|NO)\b")


class ConflictDetector:
    async def check_conflict(self, old_content: str, new_content: str) -> bool:
        """
        Returns True if the new content conflicts with the old content.
        Raises ConflictCheckError when the LLM call fails or its answer is not YES/NO.
        """
        prompt = f"""
        Determine if the following two statements are factually conflicting or contradictory.
        Statement 1: "{old_content}"
        Statement 2: "{new_content}"
        
        If they contradict, output "YES". If they are just different aspects or updates, output "NO".
        """
        # The write role's provider and model (issue #13), read per call.
        try:
            answer = await chat(prompt)
        except Exception as exc:
            raise ConflictCheckError(f"Conflict check request failed: {exc}") from exc
        result = answer.strip().upper()
        match = _VERDICT.match(result)
        if not match:
            raise ConflictCheckError(f"Conflict check answer is not YES/NO: {result[:100]!r}")
        return match.group(1) == "YES"


conflict_detector = ConflictDetector()
