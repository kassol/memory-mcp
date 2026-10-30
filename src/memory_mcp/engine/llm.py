import httpx

from ..config import settings

# Key assignment, merge and conflict checks are short structured tasks. OpenRouter turns
# reasoning on by default for some models; measured 10-28 s per merge with it, 2-3 s without.
NO_REASONING = {"reasoning": {"enabled": False}}


async def chat(prompt: str, timeout: float = 30.0) -> str:
    """Single-turn OpenRouter chat completion; raises on HTTP/transport errors."""
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
                **NO_REASONING,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
