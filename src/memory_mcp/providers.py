"""Model providers: protocol, address and API key, with keys encrypted at rest (issue #12).

Terms follow GLOSSARY.md (Provider, setting source); the layering decision is docs/adr/0002.

A provider is one model service entry point: an OpenAI-compatible, Anthropic or Gemini endpoint.
A console provider keeps its API key encrypted with AES-GCM under a data key file in the data
directory (`provider-keys.key`, owner-only, created on first use). Only the ciphertext reaches
SQLite and a key never travels back to the browser; the console shows the last four characters.

The configuration-file OpenRouter settings are the provider with id `file`. Its base URL and key
columns stay NULL, which means "use the configuration file"; a console edit writes an override into
those columns, and reverting sets them back to NULL. That row is never deleted, and its protocol
stays OpenAI-compatible because it also serves the embedding role.
"""
import base64
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings
from .storage.sqlite import get_db

FILE_PROVIDER = "file"
PROTOCOLS = ("openai", "anthropic", "gemini")
KEY_FILE = "provider-keys.key"
_COLUMNS = (
    "id, name, protocol, base_url, api_key_cipher, source, created_at, updated_at, "
    "last_call_at, last_call_ok, last_call_error"
)
_UNSET = object()


class ProviderError(ValueError):
    """The request was refused; the message is safe to show."""


class NameTaken(ProviderError):
    pass


class NotDeletable(ProviderError):
    pass


class ProviderInUse(ProviderError):
    pass


@dataclass(frozen=True)
class Provider:
    """A provider with its effective address and key; what a client call needs."""

    id: str
    name: str
    protocol: str
    base_url: str
    api_key: str
    source: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- API keys at rest -------------------------------------------------------
def _key_path() -> Path:
    return Path(settings.data_dir) / KEY_FILE


def data_key() -> bytes:
    """The 32-byte data key, created owner-only on first use."""
    path = _key_path()
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    try:
        # O_EXCL + mode: no window where the file exists with wider permissions.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_bytes()
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    return key


def encrypt(value: str, provider_id: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(data_key()).encrypt(nonce, value.encode(), provider_id.encode())
    return base64.b64encode(nonce + sealed).decode()


def decrypt(ciphertext: str, provider_id: str) -> str:
    raw = base64.b64decode(ciphertext)
    try:
        return AESGCM(data_key()).decrypt(raw[:12], raw[12:], provider_id.encode()).decode()
    except (InvalidTag, ValueError):
        raise ProviderError(
            f"无法解密 API key：数据密钥文件不匹配（{_key_path()}）。恢复该文件或重新填写 key。"
        ) from None


# ---- validation -------------------------------------------------------------
def _clean_name(name: object) -> str:
    value = str(name or "").strip()
    if not value:
        raise ProviderError("名称不能为空")
    return value


def _clean_protocol(protocol: object) -> str:
    value = str(protocol or "").strip()
    if value not in PROTOCOLS:
        raise ProviderError(f"协议必须是 {' / '.join(PROTOCOLS)} 之一")
    return value


def _clean_base_url(base_url: object) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise ProviderError("地址必须以 http:// 或 https:// 开头")
    return value


def _clean_key(api_key: object) -> str:
    value = str(api_key or "").strip()
    if not value:
        raise ProviderError("API key 不能为空")
    return value


# ---- records ----------------------------------------------------------------
def _effective(row) -> Provider:
    if row["api_key_cipher"]:
        api_key = decrypt(row["api_key_cipher"], row["id"])
    elif row["source"] == "file":
        api_key = settings.openrouter_api_key
    else:
        raise ProviderError(f"Provider {row['name']} 没有可用的 API key")
    base_url = row["base_url"] or settings.openrouter_base_url
    return Provider(
        id=row["id"],
        name=row["name"],
        protocol=row["protocol"],
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        source=row["source"],
    )


def _public(row) -> dict:
    """What the console sees: never the key itself, only its last four characters."""
    from_file = row["source"] == "file"
    cipher = row["api_key_cipher"]
    if cipher:
        key_last4: Optional[str] = decrypt(cipher, row["id"])[-4:]
    elif from_file:
        key_last4 = (settings.openrouter_api_key or "")[-4:] or None
    else:
        key_last4 = None
    return {
        "id": row["id"],
        "name": row["name"],
        "protocol": row["protocol"],
        "base_url": row["base_url"] or (settings.openrouter_base_url if from_file else ""),
        "source": row["source"],
        "has_key": key_last4 is not None,
        "api_key_last4": key_last4,
        "overridden": {"base_url": row["base_url"] is not None, "api_key": cipher is not None},
        "file_base_url": settings.openrouter_base_url if from_file else None,
        "file_api_key_last4": ((settings.openrouter_api_key or "")[-4:] or None) if from_file else None,
        "last_call_at": row["last_call_at"],
        "last_call_ok": None if row["last_call_ok"] is None else bool(row["last_call_ok"]),
        "last_call_error": row["last_call_error"],
        "created_at": row["created_at"],
        "deletable": not from_file,
    }


async def _row(provider_id: str):
    async with get_db() as db:
        row = await db.fetchone(f"SELECT {_COLUMNS} FROM providers WHERE id = ?", (provider_id,))
    if row is None:
        raise LookupError(f"Provider not found: {provider_id}")
    return row


async def list_providers() -> list[dict]:
    """Every provider, the configuration-file one first."""
    async with get_db() as db:
        rows = await db.fetchall(f"SELECT {_COLUMNS} FROM providers ORDER BY source != 'file', created_at")
    return [_public(row) for row in rows]


async def resolve(provider_id: str) -> Provider:
    """The provider a call should use, or LookupError."""
    return _effective(await _row(provider_id))


def ad_hoc(protocol: object, base_url: object, api_key: object, provider_id: str = "test") -> Provider:
    """A provider built from form values, so a connection can be tested before it is saved.

    An empty id records no last call status; an existing one updates that provider's row.
    """
    return Provider(
        id=provider_id or "test",
        name="test",
        protocol=_clean_protocol(protocol),
        base_url=_clean_base_url(base_url),
        api_key=_clean_key(api_key),
        source="console",
    )


async def create_provider(name: object, protocol: object, base_url: object, api_key: object) -> dict:
    provider_id = str(uuid4())
    now = _now().isoformat()
    try:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO providers (id, name, protocol, base_url, api_key_cipher, source, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'console', ?, ?)",
                (
                    provider_id,
                    _clean_name(name),
                    _clean_protocol(protocol),
                    _clean_base_url(base_url),
                    encrypt(_clean_key(api_key), provider_id),
                    now,
                    now,
                ),
            )
    except sqlite3.IntegrityError:
        raise NameTaken(f"名称已被使用：{str(name).strip()}") from None
    return _public(await _row(provider_id))


async def update_provider(
    provider_id: str,
    *,
    name: object = _UNSET,
    protocol: object = _UNSET,
    base_url: object = _UNSET,
    api_key: object = _UNSET,
) -> dict:
    """Change fields; a None base_url or api_key reverts the configuration-file provider only."""
    row = await _row(provider_id)
    from_file = row["source"] == "file"
    sets: list[str] = []
    values: list[object] = []

    if name is not _UNSET:
        sets.append("name = ?")
        values.append(_clean_name(name))
    if protocol is not _UNSET:
        if from_file:
            # It also serves the embedding role, and stored vectors depend on an OpenAI-compatible endpoint.
            raise ProviderError("配置文件 Provider 的协议固定为 OpenAI 兼容，不能修改")
        sets.append("protocol = ?")
        values.append(_clean_protocol(protocol))
    if base_url is not _UNSET:
        if base_url is None and not from_file:
            raise ProviderError("地址不能为空")
        sets.append("base_url = ?")
        values.append(None if base_url is None else _clean_base_url(base_url))
    if api_key is not _UNSET:
        if api_key is None and not from_file:
            raise ProviderError("API key 不能为空")
        sets.append("api_key_cipher = ?")
        values.append(None if api_key is None else encrypt(_clean_key(api_key), provider_id))
    if not sets:
        return _public(row)

    sets.append("updated_at = ?")
    values.append(_now().isoformat())
    try:
        async with get_db() as db:
            await db.execute(f"UPDATE providers SET {', '.join(sets)} WHERE id = ?", (*values, provider_id))
    except sqlite3.IntegrityError:
        raise NameTaken(f"名称已被使用：{str(name).strip()}") from None
    return _public(await _row(provider_id))


async def delete_provider(provider_id: str) -> dict:
    from . import model_roles  # imported here: model_roles imports this module

    row = await _row(provider_id)
    if row["source"] == "file":
        raise NotDeletable("配置文件 Provider 不能删除，可以恢复为配置文件值")
    async with get_db() as db:
        using = await db.fetchone("SELECT role FROM model_roles WHERE provider_id = ?", (provider_id,))
    if using is not None:
        label = model_roles.LABELS.get(using["role"], using["role"])
        raise ProviderInUse(f"Provider 正被模型用途「{label}」使用，先改用途再删除")
    async with get_db() as db:
        await db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
    return {"id": provider_id, "deleted": True}


async def record_call(provider_id: str, ok: bool, error: Optional[str] = None) -> None:
    """Remember the outcome of the last call, so a failing provider is visible in the console."""
    async with get_db() as db:
        await db.execute(
            "UPDATE providers SET last_call_at = ?, last_call_ok = ?, last_call_error = ? WHERE id = ?",
            (_now().isoformat(), 1 if ok else 0, error, provider_id),
        )
