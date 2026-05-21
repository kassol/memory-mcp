import importlib
from datetime import datetime, timezone
from uuid import uuid4

import anyio


def _setup(test_env):
    import memory_mcp.storage.migrate as migrate_mod
    importlib.reload(migrate_mod)
    migrate_mod.run_migrations()
    import memory_mcp.storage.sqlite as sqlite_mod
    importlib.reload(sqlite_mod)
    import memory_mcp.storage.graph as graph_mod
    importlib.reload(graph_mod)
    return graph_mod


def test_upsert_entity_then_query(test_env):
    async def run():
        graph_mod = _setup(test_env)
        store = graph_mod.graph_store
        await store.upsert_entity("person:alice", "person", "m1")
        entities = await store.list_entities()
        assert any(e["entity_key"] == "person:alice" for e in entities)

    anyio.run(run)


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

    anyio.run(run)


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

    anyio.run(run)


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

    anyio.run(run)
