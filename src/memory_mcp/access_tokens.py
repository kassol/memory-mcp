"""Named access tokens (issue #11, GLOSSARY.md).

Clients (agents, the CLI, the maintenance cron) authenticate with a Bearer access token. Each token
has a name, which `remember` records on the versions it writes. Only the SHA-256 of a token is
stored; the value is shown once on creation, and a token can be revoked but not restored.

The initial token (row id `initial`) is an ordinary token whose value comes from the configuration
file: startup stores its hash once, after which editing the configuration file does not change it.
It is the only token that may open the console bootstrap session while no admin password exists.
The password reset command stores the current configuration value again and restores the token.
Last use is written at most once a minute per token, so a busy client does not write on every request.
"""
import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from .storage.sqlite import get_db

INITIAL = "initial"
_LAST_USE_INTERVAL = timedelta(minutes=1)
_COLUMNS = "id, name, source, created_at, last_used_at, revoked_at"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class TokenError(ValueError):
    """The request was refused; the message is safe to show."""


class NameTaken(TokenError):
    pass


@dataclass(frozen=True)
class Identity:
    name: str


def store_initial_hash(db_path: str, value: str) -> None:
    """At startup: give the initial token the configuration value's hash, once."""
    con = sqlite3.connect(db_path)
    try:
        with con:
            con.execute(
                "UPDATE access_tokens SET token_hash = ? WHERE id = ? AND token_hash IS NULL", (_hash(value), INITIAL)
            )
    finally:
        con.close()


def restore_initial_offline(con: sqlite3.Connection, value: str) -> None:
    """Password reset: the initial token takes the current configuration value and is live again."""
    con.execute("UPDATE access_tokens SET token_hash = ?, revoked_at = NULL WHERE id = ?", (_hash(value), INITIAL))


async def authenticate(value: str) -> Optional[Identity]:
    """The live token for a Bearer value, or None if unknown or revoked."""
    now = _now()
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT id, name, last_used_at, revoked_at FROM access_tokens WHERE token_hash = ?", (_hash(value),)
        )
        if row is None or row["revoked_at"] is not None:
            return None
        last = row["last_used_at"]
        if last is None or now - datetime.fromisoformat(last) >= _LAST_USE_INTERVAL:
            await db.execute("UPDATE access_tokens SET last_used_at = ? WHERE id = ?", (now.isoformat(), row["id"]))
    return Identity(name=row["name"])


async def opens_bootstrap(value: str) -> bool:
    """Whether `value` is the live initial token (console bootstrap while no password exists)."""
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT 1 FROM access_tokens WHERE id = ? AND token_hash = ? AND revoked_at IS NULL", (INITIAL, _hash(value))
        )
    return row is not None


async def list_tokens() -> list[dict]:
    """Every token, the initial one first, then oldest first. Never includes a value or a hash."""
    async with get_db() as db:
        rows = await db.fetchall(
            f"SELECT {_COLUMNS} FROM access_tokens ORDER BY id != ?, created_at", (INITIAL,)
        )
    return [dict(r) for r in rows]


async def _get(token_id: str) -> dict:
    async with get_db() as db:
        row = await db.fetchone(f"SELECT {_COLUMNS} FROM access_tokens WHERE id = ?", (token_id,))
    if row is None:
        raise LookupError(f"Token not found: {token_id}")
    return dict(row)


async def create_token(name: str) -> dict:
    """A new token; the returned `value` is the only time it is available."""
    name = (name or "").strip()
    if not name:
        raise TokenError("名称不能为空")
    value = secrets.token_urlsafe(32)
    token_id = str(uuid4())
    try:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO access_tokens (id, name, token_hash, source, created_at) VALUES (?, ?, ?, 'console', ?)",
                (token_id, name, _hash(value), _now().isoformat()),
            )
    except sqlite3.IntegrityError:
        # Names stay taken after revocation, so a name in a memory origin points at one token.
        raise NameTaken(f"名称已被使用：{name}") from None
    return {**await _get(token_id), "value": value}


async def revoke_token(token_id: str) -> dict:
    token = await _get(token_id)
    if token["revoked_at"] is None:
        async with get_db() as db:
            await db.execute("UPDATE access_tokens SET revoked_at = ? WHERE id = ?", (_now().isoformat(), token_id))
    return await _get(token_id)
