import os

import anyio


def test_sqlite_store_applies_pragmas(test_env):
    async def run():
        import memory_mcp.storage.sqlite as sqlite_mod
        import importlib
        importlib.reload(sqlite_mod)

        async with sqlite_mod.get_db() as db:
            fk_row = await db.fetchone("PRAGMA foreign_keys")
            journal_row = await db.fetchone("PRAGMA journal_mode")
            synchronous_row = await db.fetchone("PRAGMA synchronous")
            busy_row = await db.fetchone("PRAGMA busy_timeout")
        assert fk_row[0] == 1
        assert journal_row[0].lower() == "wal"
        assert synchronous_row[0] == 1   # synchronous NORMAL = 1
        assert busy_row[0] == 5000
        await sqlite_mod.get_store().close()

    anyio.run(run)


def test_get_db_handle_provides_unified_api(test_env):
    async def run():
        import memory_mcp.storage.sqlite as sqlite_mod
        import importlib
        importlib.reload(sqlite_mod)

        # DBHandle must support execute/executemany/fetchone/fetchall/transaction
        async with sqlite_mod.get_db() as db:
            await db.execute("CREATE TABLE smoke (id INTEGER PRIMARY KEY, v TEXT)")
            async with db.transaction():
                await db.executemany(
                    "INSERT INTO smoke (v) VALUES (?)",
                    [("a",), ("b",), ("c",)],
                )
            rows = await db.fetchall("SELECT v FROM smoke ORDER BY id")
            single = await db.fetchone("SELECT v FROM smoke WHERE id = 1")
        assert [r["v"] for r in rows] == ["a", "b", "c"]
        assert single["v"] == "a"

    anyio.run(run)


def test_sqlite_store_persists_across_connections(test_env):
    async def run():
        import memory_mcp.storage.sqlite as sqlite_mod
        import importlib
        importlib.reload(sqlite_mod)

        async with sqlite_mod.get_db() as db:
            await db.execute("CREATE TABLE smoke (id INTEGER PRIMARY KEY, v TEXT)")
            await db.execute("INSERT INTO smoke (v) VALUES (?)", ("hello",))
        # second context manager must see the data because get_db() shares the
        # single store connection per process.
        async with sqlite_mod.get_db() as db:
            row = await db.fetchone("SELECT v FROM smoke WHERE id = 1")
        assert row["v"] == "hello"
        await sqlite_mod.get_store().close()
        assert os.path.exists(sqlite_mod.settings.sqlite_path)

    anyio.run(run)
