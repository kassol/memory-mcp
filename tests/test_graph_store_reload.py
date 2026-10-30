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
    import memory_mcp.storage.graph as graph_mod
    importlib.reload(graph_mod)
    _stores.append(sqlite_mod.get_store())
    return graph_mod


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


def test_upsert_entity_then_query(test_env):
    async def run():
        graph_mod = _setup(test_env)
        store = graph_mod.graph_store
        # Pass None so we don't need a memories row just to test entity upsert.
        await store.upsert_entity("person:alice", "person", None)
        entities = await store.list_entities()
        assert any(e["entity_key"] == "person:alice" for e in entities)

    _run(run)


def test_add_and_get_relation(test_env):
    async def run():
        graph_mod = _setup(test_env)
        store = graph_mod.graph_store
        from memory_mcp.engine.models import Relation
        rel = Relation(
            id=str(uuid4()),
            from_entity_key="person:alice",
            to_entity_key="project:x",
            relation_type="WORKS_ON",
            created_at=datetime.now(timezone.utc),
        )
        await store.add_relation(rel)
        rels = await store.get_relations("person:alice", depth=1)
        assert len(rels) == 1
        assert rels[0]["relation_type"] == "WORKS_ON"

    _run(run)


def test_depth_traversal_loads_from_sqlite(test_env):
    async def run():
        graph_mod = _setup(test_env)
        store = graph_mod.graph_store
        from memory_mcp.engine.models import Relation
        await store.add_relation(Relation(
            id=str(uuid4()),
            from_entity_key="person:alice",
            to_entity_key="project:x",
            relation_type="WORKS_ON",
            created_at=datetime.now(timezone.utc),
        ))
        await store.add_relation(Relation(
            id=str(uuid4()),
            from_entity_key="project:x",
            to_entity_key="tech:python",
            relation_type="USES",
            created_at=datetime.now(timezone.utc),
        ))
        # Force a reload — simulates fresh process
        await store.reload()
        rels = await store.get_relations("person:alice", depth=2)
        assert len(rels) >= 2

    _run(run)


def test_add_relation_does_not_clobber_existing_current_memory_id(test_env):
    """Regression for the bug fixed in 9f8940f: GraphStore.add_relation upserts
    both endpoints with current_memory_id=None to ensure they exist, but that
    must not reset a current_memory_id already set by a remember/evolve call."""
    async def run():
        graph_mod = _setup(test_env)
        store = graph_mod.graph_store
        from memory_mcp.engine.models import (
            MemoryNode, MutationType, Relation, ReviewStatus,
        )
        # Insert a real memory + entity pinning to it.
        mem_id = str(uuid4())
        await store._entities._store.initialize()
        from memory_mcp.storage.repositories.memories import MemoryRepository
        mem_repo = MemoryRepository(store._entities._store)
        await mem_repo.insert(MemoryNode(
            id=mem_id,
            entity_key="person:alice",
            entity_type="person",
            content="alice is a teammate",
            embedding=[],
            mutation_type=MutationType.INITIAL,
            created_at=datetime.now(timezone.utc),
            valid_from=datetime.now(timezone.utc),
            is_current=True,
            confidence=1.0,
            review_status=ReviewStatus.AUTO,
        ))
        await store.upsert_entity("person:alice", "person", mem_id)
        # Now add a relation — internally upserts both endpoints with None.
        await store.add_relation(Relation(
            id=str(uuid4()),
            from_entity_key="person:alice",
            to_entity_key="project:x",
            relation_type="WORKS_ON",
            created_at=datetime.now(timezone.utc),
        ))
        entities = await store.list_entities()
        alice = next(e for e in entities if e["entity_key"] == "person:alice")
        assert alice["current_memory_id"] == mem_id, \
            f"add_relation clobbered current_memory_id: got {alice['current_memory_id']}"

    _run(run)


def test_delete_relation(test_env):
    async def run():
        graph_mod = _setup(test_env)
        store = graph_mod.graph_store
        from memory_mcp.engine.models import Relation
        rel = Relation(
            id=str(uuid4()),
            from_entity_key="person:alice",
            to_entity_key="project:x",
            relation_type="WORKS_ON",
            created_at=datetime.now(timezone.utc),
        )
        await store.add_relation(rel)
        deleted = await store.delete_relation(rel.id)
        assert deleted is True
        rels = await store.get_relations("person:alice", depth=1)
        assert rels == []

    _run(run)
