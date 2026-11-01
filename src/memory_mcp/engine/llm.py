"""Model calls by role (issues #12, #13): the provider, model and timeout come from `model_roles`.

The write role serves key assignment, merge and the conflict judgment inside `remember`; the
maintenance role serves the background checks. Both are read at call time, so a console save
applies to the next call.
"""
from typing import Optional

from .. import model_roles


async def chat(prompt: str, timeout: Optional[float] = None) -> str:
    """Write role: one-turn completion; raises on HTTP/transport errors."""
    return await model_roles.chat(model_roles.WRITE, prompt, timeout=timeout)


async def maintenance_chat(prompt: str, timeout: Optional[float] = None) -> str:
    """Maintenance role: one-turn completion; raises on HTTP/transport errors."""
    return await model_roles.chat(model_roles.MAINTENANCE, prompt, timeout=timeout)
