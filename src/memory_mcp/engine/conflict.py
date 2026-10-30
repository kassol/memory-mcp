import re

from ..config import settings
from .llm import NO_REASONING
import httpx

# PRD mentions using "LLM Judgment" for conflict.
# We'll mock the interface or implement a simple call similar to EmbeddingService if credentials provided.
# Since we reuse OpenRouter, we can use that.


class ConflictCheckError(RuntimeError):
    """Raised when the conflict judgment cannot be obtained; never read that as "no conflict"."""


_VERDICT = re.compile(r"^\W*(YES|NO)\b")


class ConflictDetector:
    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url
        self.model = settings.llm_model

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
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://memory-mcp.app",
            "X-Title": "Memory MCP"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        **NO_REASONING,
                    },
                    timeout=10.0
                )
        except Exception as exc:
            raise ConflictCheckError("Conflict check request failed") from exc

        if response.status_code != 200:
            raise ConflictCheckError(f"Conflict check returned HTTP {response.status_code}")
        try:
            result = response.json()["choices"][0]["message"]["content"].strip().upper()
        except Exception as exc:
            raise ConflictCheckError("Conflict check response is malformed") from exc
        match = _VERDICT.match(result)
        if not match:
            raise ConflictCheckError(f"Conflict check answer is not YES/NO: {result[:100]!r}")
        return match.group(1) == "YES"

conflict_detector = ConflictDetector()
