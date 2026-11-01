"""The write path's model call: the configuration-file provider and the configured model.

Issue #13 gives each model role its own provider and model; until then key assignment, merge and
the conflict judgment all use this one.
"""
from .. import providers
from ..config import settings
from . import model_client


async def chat(prompt: str, timeout: float = 30.0) -> str:
    """Single-turn completion; raises on HTTP/transport errors."""
    provider = await providers.resolve(providers.FILE_PROVIDER)
    return await model_client.chat(provider, settings.llm_model, prompt, timeout=timeout)
