import httpx

from ..config import settings


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
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
