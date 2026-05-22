import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable, Optional, Sequence

import aiosqlite

from ..config import settings

logger = logging.getLogger(__name__)


_PRAGMAS = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA temp_store = MEMORY",
)


class DBHandle:
    """Authoritative async DB API consumed by M1/M2/M3/M4.

    All downstream layers (repositories, hybrid_search, threads, workers) MUST
    use this interface — never reach for the underlying aiosqlite connection
    directly. Contract: ``fetchone`` / ``fetchall`` return ``aiosqlite.Row``
    (dict-like + index-able). Cursors returned by ``execute`` / ``executemany``
    are intended for ``rowcount`` / ``lastrowid`` inspection only — do not
    iterate them; use ``fetchone`` / ``fetchall`` instead.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # -- Mutating ops --------------------------------------------------------
    async def execute(self, sql: str, params: Sequence[Any] | None = None) -> aiosqlite.Cursor:
        return await self._conn.execute(sql, tuple(params) if params is not None else ())

    async def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> aiosqlite.Cursor:
        return await self._conn.executemany(sql, [tuple(p) for p in seq_of_params])

    async def executescript(self, script: str) -> None:
        """Run a multi-statement SQL script (e.g., schema bootstrap).

        SQLite forbids transaction control inside ``executescript``: do NOT call
        this while an outer ``transaction()`` block is open, and do not embed
        ``BEGIN`` / ``COMMIT`` inside ``script`` if the caller already started a
        transaction.
        """
        await self._conn.executescript(script)

    # -- Read ops ------------------------------------------------------------
    async def fetchone(self, sql: str, params: Sequence[Any] | None = None) -> Optional[aiosqlite.Row]:
        async with self._conn.execute(sql, tuple(params) if params is not None else ()) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] | None = None) -> list[aiosqlite.Row]:
        async with self._conn.execute(sql, tuple(params) if params is not None else ()) as cur:
            rows = await cur.fetchall()
        return list(rows)

    # -- Transactions --------------------------------------------------------
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["DBHandle"]:
        await self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self
        except Exception:
            await self._conn.rollback()
            raise
        else:
            await self._conn.commit()

    async def commit(self) -> None:
        await self._conn.commit()

    # -- Escape hatch (avoid in product code; tests only) --------------------
    @property
    def raw(self) -> aiosqlite.Connection:
        return self._conn


class SQLiteStore:
    """Async SQLite primary store wrapper.

    - WAL + NORMAL synchronous + busy_timeout for safer concurrent access
    - Foreign keys ON enforced on every connection
    - Single shared aiosqlite connection (aiosqlite serialises writes anyway);
      callers acquire a `DBHandle` via `get_db()` / `store.get_db()`.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or settings.sqlite_path
        self._conn: Optional[aiosqlite.Connection] = None
        # Serializes every get_db() block — including lazy init — so two
        # coroutines can't share the underlying aiosqlite connection's
        # implicit transaction state and prematurely commit each other's
        # partial writes.
        self._lock = asyncio.Lock()

    async def _do_initialize(self) -> None:
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        if self._conn is not None:
            return
        self._conn = await aiosqlite.connect(self._db_path)
        for pragma in _PRAGMAS:
            await self._conn.execute(pragma)
        await self._conn.commit()
        # aiosqlite returns rows as tuples by default; opt-in to Row factory
        self._conn.row_factory = aiosqlite.Row

    async def initialize(self) -> None:
        async with self._lock:
            await self._do_initialize()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def get_db(self) -> AsyncIterator[DBHandle]:
        """Authoritative entry point — returns the unified DBHandle facade.

        Holds ``self._lock`` for the entire block so the shared aiosqlite
        connection's transaction state can't be observed mid-flight by a
        concurrent coroutine. Auto-commits at exit when no exception was
        raised AND the caller has leftover work outside ``transaction()``.
        On exception, any leftover transaction state is rolled back to
        avoid silent partial writes.
        """
        async with self._lock:
            if self._conn is None:
                await self._do_initialize()
            assert self._conn is not None
            handle = DBHandle(self._conn)
            try:
                yield handle
            except Exception:
                if self._conn.in_transaction:
                    await self._conn.rollback()
                raise
            else:
                if self._conn.in_transaction:
                    await self._conn.commit()


    @property
    def db_path(self) -> str:
        return self._db_path


_default_store: Optional[SQLiteStore] = None


def get_store() -> SQLiteStore:
    global _default_store
    if _default_store is None:
        _default_store = SQLiteStore()
    return _default_store


@asynccontextmanager
async def get_db() -> AsyncIterator[DBHandle]:
    """Module-level convenience for the default store.

    M2/M3/M4 import this directly: ``from ..storage.sqlite import get_db``.
    """
    store = get_store()
    async with store.get_db() as handle:
        yield handle


async def reset_store_for_tests() -> None:
    """Tests may force a clean store after monkeypatching settings/path."""
    global _default_store
    if _default_store is not None:
        await _default_store.close()
    _default_store = SQLiteStore()
