"""Protocol adapters for model calls (issue #12): OpenAI-compatible, Anthropic and Gemini.

Every call records its outcome on the provider row (last call status and time), so a failing
provider is visible in the console. Errors are mapped to one readable message: timeouts, connection
failures, non-2xx responses with a short body excerpt, and responses missing the expected field.

Reasoning is turned off in each protocol's own way (`reasoning.enabled` for OpenAI-compatible,
`thinkingBudget` for Gemini; Anthropic models in use have none). JSON-only output is requested with
`response_format` on OpenAI-compatible, `responseMimeType` on Gemini, and a system instruction for
Anthropic, which has no JSON mode.
"""
from typing import Awaitable, Optional

import httpx

from .. import providers
from ..providers import Provider

_OPENROUTER_HEADERS = {"HTTP-Referer": "https://memory-mcp.app", "X-Title": "Memory MCP"}
_JSON_INSTRUCTION = "只输出 JSON，不要包含解释或代码块标记。"


class ProviderCallError(Exception):
    """A model call failed; the message is safe to show and goes to the provider's last call status."""

    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


def _snippet(response: httpx.Response) -> str:
    return " ".join(response.text.split())[:200]


async def _request(
    method: str,
    url: str,
    *,
    headers: Optional[dict] = None,
    json: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: float,
) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            # post/get rather than request: callers mock them, and they read the same here.
            if method == "POST":
                response = await client.post(url, headers=headers, json=json, params=params, timeout=timeout)
            else:
                response = await client.get(url, headers=headers, params=params, timeout=timeout)
    except httpx.TimeoutException:
        raise ProviderCallError(f"请求超时（{timeout:g} 秒）") from None
    except httpx.HTTPError as exc:
        raise ProviderCallError(f"连接失败：{exc!r}") from None
    if response.status_code >= 400:
        raise ProviderCallError(f"HTTP {response.status_code}：{_snippet(response)}", response.status_code)
    try:
        return response.json()
    except ValueError:
        raise ProviderCallError(f"响应不是 JSON：{_snippet(response)}") from None


async def _record(provider: Provider, what: str, run: Awaitable) -> object:
    try:
        result = await run
    except ProviderCallError as exc:
        await providers.record_call(provider.id, ok=False, error=f"{what}：{exc}")
        raise
    await providers.record_call(provider.id, ok=True)
    return result


# ---- chat -------------------------------------------------------------------
def _openai_headers(provider: Provider) -> dict:
    return {"Authorization": f"Bearer {provider.api_key}", **_OPENROUTER_HEADERS}


async def _openai_chat(provider: Provider, model: str, prompt: str, timeout: float, json_mode: bool) -> str:
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "reasoning": {"enabled": False},
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    data = await _request(
        "POST",
        f"{provider.base_url}/chat/completions",
        headers=_openai_headers(provider),
        json=body,
        timeout=timeout,
    )
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError):
        raise ProviderCallError("响应缺少 choices[0].message.content") from None


async def _anthropic_chat(provider: Provider, model: str, prompt: str, timeout: float, json_mode: bool) -> str:
    body: dict = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        body["system"] = _JSON_INSTRUCTION
    data = await _request(
        "POST",
        f"{provider.base_url}/messages",
        headers={"x-api-key": provider.api_key, "anthropic-version": "2023-06-01"},
        json=body,
        timeout=timeout,
    )
    parts = data.get("content")
    if not isinstance(parts, list):
        raise ProviderCallError("响应缺少 content")
    text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
    if not text:
        raise ProviderCallError("响应没有文本内容")
    return text


async def _gemini_chat(provider: Provider, model: str, prompt: str, timeout: float, json_mode: bool) -> str:
    generation: dict = {"temperature": 0}
    if json_mode:
        generation["responseMimeType"] = "application/json"
    body: dict = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": generation}
    url = f"{provider.base_url}/models/{model}:generateContent"
    params = {"key": provider.api_key}
    if model.startswith(("gemini-2.5", "gemini-3")):
        # Thinking models accept a zero budget; older ones reject the field, so ask only for those.
        body["generationConfig"] = {**generation, "thinkingConfig": {"thinkingBudget": 0}}
    data = await _request("POST", url, json=body, params=params, timeout=timeout)
    candidates = data.get("candidates")
    try:
        parts = candidates[0]["content"]["parts"]
        text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
    except (IndexError, KeyError, TypeError):
        raise ProviderCallError("响应缺少 candidates[0].content.parts") from None
    if not text:
        raise ProviderCallError("响应没有文本内容")
    return text


async def chat(
    provider: Provider, model: str, prompt: str, *, timeout: float = 30.0, json_mode: bool = False
) -> str:
    """One-turn completion; raises ProviderCallError with a readable reason."""
    adapter = {"openai": _openai_chat, "anthropic": _anthropic_chat, "gemini": _gemini_chat}.get(provider.protocol)
    if adapter is None:
        raise ProviderCallError(f"未知协议：{provider.protocol}")
    return await _record(provider, "对话", adapter(provider, model, prompt, timeout, json_mode))


# ---- embeddings -------------------------------------------------------------
async def _openai_embed(provider: Provider, model: str, text: str, timeout: float) -> list[float]:
    data = await _request(
        "POST",
        f"{provider.base_url}/embeddings",
        headers=_openai_headers(provider),
        json={"model": model, "input": text},
        timeout=timeout,
    )
    try:
        return [float(v) for v in data["data"][0]["embedding"]]
    except (KeyError, IndexError, TypeError, ValueError):
        raise ProviderCallError("响应缺少 data[0].embedding") from None


async def _gemini_embed(provider: Provider, model: str, text: str, timeout: float) -> list[float]:
    data = await _request(
        "POST",
        f"{provider.base_url}/models/{model}:embedContent",
        params={"key": provider.api_key},
        json={"content": {"parts": [{"text": text}]}},
        timeout=timeout,
    )
    try:
        return [float(v) for v in data["embedding"]["values"]]
    except (KeyError, TypeError, ValueError):
        raise ProviderCallError("响应缺少 embedding.values") from None


async def embed(provider: Provider, model: str, text: str, *, timeout: float = 30.0) -> list[float]:
    if provider.protocol == "anthropic":
        raise ProviderCallError("Anthropic 协议不提供 embedding 接口")
    adapter = _openai_embed if provider.protocol == "openai" else _gemini_embed
    return await _record(provider, "向量", adapter(provider, model, text, timeout))


# ---- model list -------------------------------------------------------------
async def _openai_models(provider: Provider, timeout: float) -> list[str]:
    data = await _request(
        "GET", f"{provider.base_url}/models", headers=_openai_headers(provider), timeout=timeout
    )
    return [str(m["id"]) for m in data.get("data") or [] if isinstance(m, dict) and "id" in m]


async def _anthropic_models(provider: Provider, timeout: float) -> list[str]:
    data = await _request(
        "GET",
        f"{provider.base_url}/models",
        headers={"x-api-key": provider.api_key, "anthropic-version": "2023-06-01"},
        params={"limit": 100},
        timeout=timeout,
    )
    return [str(m["id"]) for m in data.get("data") or [] if isinstance(m, dict) and "id" in m]


async def _gemini_models(provider: Provider, timeout: float) -> list[str]:
    data = await _request(
        "GET",
        f"{provider.base_url}/models",
        params={"key": provider.api_key, "pageSize": 100},
        timeout=timeout,
    )
    return [
        str(m["name"]).removeprefix("models/")
        for m in data.get("models") or []
        if isinstance(m, dict) and "name" in m
    ]


async def list_models(provider: Provider, *, timeout: float = 15.0) -> list[str]:
    """The provider's models; also how the console tests a connection (it costs no tokens)."""
    adapter = {
        "openai": _openai_models,
        "anthropic": _anthropic_models,
        "gemini": _gemini_models,
    }.get(provider.protocol)
    if adapter is None:
        raise ProviderCallError(f"未知协议：{provider.protocol}")
    return await _record(provider, "模型列表", adapter(provider, timeout))
