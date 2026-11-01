"""Model roles: which provider, model and timeout each kind of model call uses (issue #13).

Terms follow GLOSSARY.md (Model role). Two roles are configurable:

- write: key assignment, merge and the conflict judgment inside `remember`;
- maintenance: the judgments of the background checks.

Terms and defaults without a row are what the service had before roles existed: the
configuration-file provider, `llm_model` and a 30 second timeout. A role row names a provider, so
deleting a provider that a role uses is refused (providers.delete_provider checks this table).

The embedding role is read-only and always follows the configuration file: stored vectors were
computed with that model, so changing it would make every stored vector incomparable
(docs/adr/0002). It is reported here so the console can show what the vectors depend on.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from . import providers
from .config import settings
from .engine import model_client
from .storage.sqlite import get_db

WRITE = "write"
MAINTENANCE = "maintenance"
EMBEDDING = "embedding"
ROLES = (WRITE, MAINTENANCE, EMBEDDING)
CONFIGURABLE = (WRITE, MAINTENANCE)
LABELS = {WRITE: "写入", MAINTENANCE: "维护", EMBEDDING: "向量"}
DEFAULT_TIMEOUT = 30.0
MIN_TIMEOUT = 5.0
MAX_TIMEOUT = 600.0


class RoleError(ValueError):
    """The request was refused; the message is safe to show."""


@dataclass(frozen=True)
class Role:
    name: str
    provider: providers.Provider
    model: str
    timeout: float


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(role: str) -> str:
    if role not in ROLES:
        raise LookupError(f"Unknown model role: {role}")
    if role not in CONFIGURABLE:
        raise RoleError("向量用途只读：已存的向量是用这个模型算出来的，改了就无法与存量比较")
    return role


async def _row(role: str):
    async with get_db() as db:
        return await db.fetchone(
            "SELECT role, provider_id, model, timeout FROM model_roles WHERE role = ?", (role,)
        )


async def resolve(role: str) -> Role:
    """The provider, model and timeout a call of this role uses, read at call time."""
    if role == EMBEDDING:
        return Role(role, await providers.resolve(providers.FILE_PROVIDER), settings.embedding_model, DEFAULT_TIMEOUT)
    row = await _row(role)
    if row is None:
        return Role(role, await providers.resolve(providers.FILE_PROVIDER), settings.llm_model, DEFAULT_TIMEOUT)
    return Role(role, await providers.resolve(row["provider_id"]), row["model"], float(row["timeout"]))


async def chat(role: str, prompt: str, *, timeout: Optional[float] = None, json_mode: bool = False) -> str:
    """One-turn completion for a role; raises on HTTP/transport errors."""
    chosen = await resolve(role)
    return await model_client.chat(
        chosen.provider, chosen.model, prompt, timeout=timeout or chosen.timeout, json_mode=json_mode
    )


async def embed(text: str) -> list[float]:
    """The embedding role's vector; the dimension must match what stored vectors use."""
    chosen = await resolve(EMBEDDING)
    embedding = await model_client.embed(chosen.provider, chosen.model, text, timeout=chosen.timeout)
    if len(embedding) != settings.embedding_dim:
        raise ValueError("Embedding dimension mismatch")
    return embedding


async def _describe(role: str, row) -> dict:
    if role == EMBEDDING:
        provider = await providers.resolve(providers.FILE_PROVIDER)
        return {
            "role": role,
            "label": LABELS[role],
            "provider_id": provider.id,
            "provider_name": provider.name,
            "model": settings.embedding_model,
            "dimension": settings.embedding_dim,
            "timeout": DEFAULT_TIMEOUT,
            "custom": False,
            "read_only": True,
            "defaults": None,
        }
    provider_id = row["provider_id"] if row else providers.FILE_PROVIDER
    provider = await providers.resolve(provider_id)
    return {
        "role": role,
        "label": LABELS[role],
        "provider_id": provider.id,
        "provider_name": provider.name,
        "model": row["model"] if row else settings.llm_model,
        "dimension": None,
        "timeout": float(row["timeout"]) if row else DEFAULT_TIMEOUT,
        "custom": row is not None,
        "read_only": False,
        "defaults": {
            "provider_id": providers.FILE_PROVIDER,
            "provider_name": (await providers.resolve(providers.FILE_PROVIDER)).name,
            "model": settings.llm_model,
            "timeout": DEFAULT_TIMEOUT,
        },
    }


async def describe_all() -> list[dict]:
    """Every role with its effective choice and, for the configurable ones, whether it is custom."""
    rows = {role: await _row(role) for role in CONFIGURABLE}
    return [await _describe(role, rows.get(role)) for role in (WRITE, MAINTENANCE, EMBEDDING)]


async def set_role(role: str, provider_id: object, model: object, timeout: object) -> dict:
    role = _check(role)
    provider = await providers.resolve(str(provider_id or ""))
    chosen_model = str(model or "").strip()
    if not chosen_model:
        raise RoleError("模型不能为空")
    try:
        seconds = float(timeout)
    except (TypeError, ValueError):
        raise RoleError("超时需要是秒数") from None
    if not MIN_TIMEOUT <= seconds <= MAX_TIMEOUT:
        raise RoleError(f"超时需要在 {MIN_TIMEOUT:g} 到 {MAX_TIMEOUT:g} 秒之间")
    async with get_db() as db:
        await db.execute(
            "INSERT INTO model_roles (role, provider_id, model, timeout, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(role) DO UPDATE SET provider_id = excluded.provider_id, model = excluded.model, "
            "timeout = excluded.timeout, updated_at = excluded.updated_at",
            (role, provider.id, chosen_model, seconds, _now()),
        )
    return await _describe(role, await _row(role))


async def clear_role(role: str) -> dict:
    """Drop the row, so the defaults (configuration-file provider, `llm_model`, 30 s) apply again."""
    role = _check(role)
    async with get_db() as db:
        await db.execute("DELETE FROM model_roles WHERE role = ?", (role,))
    return await _describe(role, None)
