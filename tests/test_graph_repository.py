import importlib
from datetime import datetime, timezone
from uuid import uuid4

import anyio

_stores = []


def _setup(test_env):
    import memory_mcp.storage.migrate as migrate_mod
    importlib.reload(migrate_mod)
    migrate_mod.run_migrations()
    import memory_mcp.storage.sqlite as sqlite_mod
    importlib.reload(sqlite_mod)
    import memory_mcp.storage.repositories.entities as ent_mod
    import memory_mcp.storage.repositories.relations as rel_mod
    import memory_mcp.storage.repositories.memories as mem_mod
    importlib.reload(ent_mod)
    importlib.reload(rel_mod)
    importlib.reload(mem_mod)
    store = sqlite_mod.SQLiteStore()
    _stores.append(store)
    return (
        ent_mod.EntityRepository(store),
        rel_mod.RelationRepository(store),
        mem_mod.MemoryRepository(store),
    )


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


async def _insert_memory(mem_repo, mem_id: str, entity_key: str) -> str:
    from memory_mcp.engine.models import MemoryNode, MutationType, ReviewStatus
    await mem_repo.insert(MemoryNode(
        id=mem_id,
        entity_key=entity_key,
        entity_type=entity_key.split(":", 1)[0],
        content="x",
        embedding=[],
        mutation_type=MutationType.INITIAL,
        created_at=datetime.now(timezone.utc),
        valid_from=datetime.now(timezone.utc),
        is_current=True,
        confidence=1.0,
        review_status=ReviewStatus.AUTO,
    ))
    return mem_id


def test_upsert_entity_insert_and_update(test_env):
    async def run():
        ent_repo, _, mem_repo = _setup(test_env)
        await _insert_memory(mem_repo, "m1", "person:alice")
        await _insert_memory(mem_repo, "m2", "person:alice")
        await ent_repo.upsert(
            entity_key="person:alice",
            entity_type="person",
            current_memory_id="m1",
        )
        loaded = await ent_repo.get("person:alice")
        assert loaded["entity_type"] == "person"
        assert loaded["current_memory_id"] == "m1"

        await ent_repo.upsert(
            entity_key="person:alice",
            entity_type="person",
            current_memory_id="m2",
        )
        loaded = await ent_repo.get("person:alice")
        assert loaded["current_memory_id"] == "m2"

    _run(run)


def test_clear_current_memory(test_env):
    async def run():
        ent_repo, _, mem_repo = _setup(test_env)
        await _insert_memory(mem_repo, "m1", "person:alice")
        await ent_repo.upsert("person:alice", "person", "m1")
        await ent_repo.clear_current_memory("person:alice")
        loaded = await ent_repo.get("person:alice")
        assert loaded["current_memory_id"] is None

    _run(run)


def test_upsert_with_none_preserves_existing_current_memory_id(test_env):
    """Regression: graph_store.add_relation upserts endpoints with
    current_memory_id=None to ensure existence — that must not clobber the
    real current_memory_id set by an earlier remember/evolve call."""
    async def run():
        ent_repo, _, mem_repo = _setup(test_env)
        await _insert_memory(mem_repo, "mem-1", "person:alice")
        await ent_repo.upsert("person:alice", "person", "mem-1")
        await ent_repo.upsert("person:alice", "person", None)
        loaded = await ent_repo.get("person:alice")
        assert loaded["current_memory_id"] == "mem-1"

    _run(run)


def test_relation_insert_and_delete(test_env):
    async def run():
        ent_repo, rel_repo, _ = _setup(test_env)
        from memory_mcp.engine.models import Relation
        await ent_repo.upsert("person:alice", "person", None)
        await ent_repo.upsert("project:x", "project", None)
        relation = Relation(
            id=str(uuid4()),
            from_entity_key="person:alice",
            to_entity_key="project:x",
            relation_type="WORKS_ON",
            properties={"role": "lead"},
            created_at=datetime.now(timezone.utc),
        )
        await rel_repo.insert(relation)
        loaded = await rel_repo.list_by_entity("person:alice")
        assert len(loaded) == 1
        assert loaded[0]["relation_type"] == "WORKS_ON"
        assert loaded[0]["properties"] == {"role": "lead"}

        deleted = await rel_repo.delete(relation.id)
        assert deleted is True
        assert await rel_repo.list_by_entity("person:alice") == []
        again = await rel_repo.delete(relation.id)
        assert again is False

    _run(run)


def test_relation_fk_cascade_on_entity_delete(test_env):
    async def run():
        ent_repo, rel_repo, _ = _setup(test_env)
        from memory_mcp.engine.models import Relation
        await ent_repo.upsert("person:bob", "person", None)
        await ent_repo.upsert("project:y", "project", None)
        relation = Relation(
            id=str(uuid4()),
            from_entity_key="person:bob",
            to_entity_key="project:y",
            relation_type="OWNS",
            created_at=datetime.now(timezone.utc),
        )
        await rel_repo.insert(relation)
        await ent_repo.delete("person:bob")
        assert await rel_repo.list_by_entity("project:y") == []

    _run(run)
