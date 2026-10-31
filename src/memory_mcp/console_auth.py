"""Console sign-in: admin password and console sessions (docs/adr/0001, GLOSSARY.md).

The console never holds an access token. It signs in with the admin password and gets a random
session token in an HttpOnly, Secure, SameSite=Strict cookie; only the token's hash is stored, with
a 7-day expiry that slides on every use. While no password exists, the configuration-file access
token opens one bootstrap session that may only set the password.
"""
import base64
import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import settings
from .storage.sqlite import get_db

COOKIE = "mm_session"
SESSION_DAYS = 7
SESSION_SECONDS = SESSION_DAYS * 86400

# scrypt cost: 2**14 * 8 * 128 bytes = 16 MiB per hash, about 50 ms.
_N, _R, _P = 2**14, 8, 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    b64 = base64.b64encode
    return f"scrypt${_N}${_R}${_P}${b64(salt).decode()}${b64(digest).decode()}"


def _verify(password: str, stored: str) -> bool:
    _, n, r, p, salt, digest = stored.split("$")
    actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                            dklen=len(base64.b64decode(digest)))
    return hmac.compare_digest(actual, base64.b64decode(digest))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_config_token(token: str) -> bool:
    return hmac.compare_digest(token.encode(), settings.auth_token.encode())


class SignInError(Exception):
    """Wrong password or token; the message is safe to show."""


class PasswordError(ValueError):
    """The password change was refused; the message is safe to show."""


@dataclass(frozen=True)
class Session:
    token_hash: str
    bootstrap: bool


async def _password_hash() -> Optional[str]:
    async with get_db() as db:
        row = await db.fetchone("SELECT password_hash FROM console_admin WHERE id = 1")
    return row["password_hash"] if row else None


async def password_set() -> bool:
    return await _password_hash() is not None


async def _new_session(bootstrap: bool) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO console_sessions (token_hash, bootstrap, created_at, last_used_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (_hash_token(token), int(bootstrap), now.isoformat(), now.isoformat(),
             (now + timedelta(days=SESSION_DAYS)).isoformat()),
        )
    return token


async def sign_in(password: Optional[str], token: Optional[str]) -> str:
    """A new session token, or SignInError. The token path works only while no password exists."""
    stored = await _password_hash()
    if stored is None:
        if token and is_config_token(token):
            return await _new_session(bootstrap=True)
        raise SignInError("尚未设置管理口令，请用配置文件里的访问令牌登录一次" if password else "令牌无效")
    if password and _verify(password, stored):
        return await _new_session(bootstrap=False)
    raise SignInError("口令错误")


async def session_for(token: Optional[str]) -> Optional[Session]:
    """The live session for a cookie value, with its expiry moved 7 days ahead; None if absent or expired."""
    if not token:
        return None
    token_hash = _hash_token(token)
    now = _now()
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT bootstrap, expires_at FROM console_sessions WHERE token_hash = ?", (token_hash,)
        )
        if row is None:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= now:
            await db.execute("DELETE FROM console_sessions WHERE token_hash = ?", (token_hash,))
            return None
        await db.execute(
            "UPDATE console_sessions SET last_used_at = ?, expires_at = ? WHERE token_hash = ?",
            (now.isoformat(), (now + timedelta(days=SESSION_DAYS)).isoformat(), token_hash),
        )
    return Session(token_hash=token_hash, bootstrap=bool(row["bootstrap"]))


async def set_password(session: Session, current: Optional[str], new: str) -> None:
    """Set the first password (bootstrap session) or change it (needs the current one)."""
    if not new:
        raise PasswordError("新口令不能为空")
    stored = await _password_hash()
    if stored is not None and not (current and _verify(current, stored)):
        raise PasswordError("当前口令错误")
    if stored is None and not session.bootstrap:
        raise PasswordError("当前口令错误")
    now = _now().isoformat()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO console_admin (id, password_hash, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET password_hash = excluded.password_hash, updated_at = excluded.updated_at",
            (hash_password(new), now),
        )
        # The bootstrap session becomes a normal one; the configuration-file token stops working here.
        await db.execute("UPDATE console_sessions SET bootstrap = 0 WHERE token_hash = ?", (session.token_hash,))


async def end_session(session: Session) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM console_sessions WHERE token_hash = ?", (session.token_hash,))


async def end_all_sessions() -> int:
    async with get_db() as db:
        cur = await db.execute("DELETE FROM console_sessions")
    return cur.rowcount or 0


def reset_password_offline(db_path: str) -> int:
    """Remove the admin password and every session (host command); returns sessions removed."""
    con = sqlite3.connect(db_path)
    try:
        with con:
            con.execute("DELETE FROM console_admin")
            removed = con.execute("DELETE FROM console_sessions").rowcount
    finally:
        con.close()
    return removed
