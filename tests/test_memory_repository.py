import importlib
from datetime import datetime, timezone
from uuid import uuid4

import anyio

_stores = []


def _make_node(entity_key: str = "preference:editor", content: str = "Prefer Cursor"):
    from memory_mcp.engine.models import MemoryNode, MutationType
    now = datetime.now(timezone.utc)
    return MemoryNode(
        id=str(uuid4()),
        entity_key=entity_key,
        entity_type=entity_key.split(":", 1)[0],
        content=content,
        content_tokens=content,
        embedding=[0.1, 0.1, 0.1],
        mutation_type=MutationType.INITIAL,
        created_at=now,
        valid_from=now,
        is_current=True,
    )


def _setup(test_env):
    import memory_mcp.storage.migrate as migrate_mod
    importlib.reload(migrate_mod)
    migrate_mod.run_migrations()

    import memory_mcp.storage.sqlite as sqlite_mod
    importlib.reload(sqlite_mod)
    import memory_mcp.storage.repositories.memories as repo_mod
    importlib.reload(repo_mod)
    store = sqlite_mod.SQLiteStore()
    _stores.append(store)
    return repo_mod.MemoryRepository(store)


def _run(body):
    """Run body and close the stores it opened inside the same event loop.

    A store closed after anyio.run() returns makes the aiosqlite worker thread
    post to a closed loop ("Event loop is closed").
    """
    async def main():
        try:
            await body()
        finally:
            while _stores:
                await _stores.pop().close()

    anyio.run(main)


def test_insert_and_get(test_env):
    async def run():
        repo = _setup(test_env)
        node = _make_node()
        await repo.insert(node)
        loaded = await repo.get_by_id(node.id)
        assert loaded is not None
        assert loaded.content == node.content
        assert loaded.entity_key == node.entity_key
        assert loaded.is_current is True

    _run(run)


def test_update_sets_is_current(test_env):
    async def run():
        repo = _setup(test_env)
        node = _make_node()
        await repo.insert(node)
        node.is_current = False
        node.archived_reason = "test"
        await repo.update(node)
        loaded = await repo.get_by_id(node.id)
        assert loaded.is_current is False
        assert loaded.archived_reason == "test"

    _run(run)


def test_get_history_ordered(test_env):
    async def run():
        repo = _setup(test_env)
        a = _make_node(content="A")
        b = _make_node(content="B")
        b.parent_id = a.id
        await repo.insert(a)
        await repo.insert(b)
        history = await repo.get_history("preference:editor")
        assert [n.content for n in history] == ["A", "B"]

    _run(run)


def test_list_current_filters(test_env):
    async def run():
        repo = _setup(test_env)
        a = _make_node(entity_key="preference:editor", content="A")
        b = _make_node(entity_key="fact:city", content="B")
        await repo.insert(a)
        await repo.insert(b)
        all_current = await repo.list_current()
        assert {n.entity_key for n in all_current} == {"preference:editor", "fact:city"}
        only_pref = await repo.list_current(entity_type="preference")
        assert {n.entity_key for n in only_pref} == {"preference:editor"}

    _run(run)


def test_fts_index_populated_on_insert(test_env):
    async def run():
        repo = _setup(test_env)
        node = _make_node(content="Prefers Cursor editor and dark mode")
        node.content_tokens = "Prefers Cursor editor and dark mode"
        await repo.insert(node)
        async with repo._store.get_db() as db:
            row = await db.fetchone(
                "SELECT count(*) AS c FROM memories_fts WHERE memories_fts MATCH ?",
                ("Cursor",),
            )
        assert row["c"] == 1

    _run(run)


def test_get_by_ids_batch(test_env):
    async def run():
        repo = _setup(test_env)
        nodes = [_make_node(entity_key=f"preference:p{i}", content=f"C{i}") for i in range(3)]
        for n in nodes:
            await repo.insert(n)
        loaded = await repo.get_by_ids([n.id for n in nodes])
        assert {node.content for node in loaded} == {"C0", "C1", "C2"}

    _run(run)
