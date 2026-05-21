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
    import memory_mcp.storage.repositories.entities as ent_mod
    import memory_mcp.storage.repositories.relations as rel_mod
    importlib.reload(ent_mod)
    importlib.reload(rel_mod)
    store = sqlite_mod.SQLiteStore()
    return ent_mod.EntityRepository(store), rel_mod.RelationRepository(store)


def test_upsert_entity_insert_and_update(test_env):
    async def run():
        ent_repo, _ = _setup(test_env)
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

    anyio.run(run)


def test_clear_current_memory(test_env):
    async def run():
        ent_repo, _ = _setup(test_env)
        await ent_repo.upsert("person:alice", "person", "m1")
        await ent_repo.clear_current_memory("person:alice")
        loaded = await ent_repo.get("person:alice")
        assert loaded["current_memory_id"] is None

    anyio.run(run)


def test_relation_insert_and_delete(test_env):
    async def run():
        ent_repo, rel_repo = _setup(test_env)
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

    anyio.run(run)


def test_relation_fk_cascade_on_entity_delete(test_env):
    async def run():
        ent_repo, rel_repo = _setup(test_env)
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

    anyio.run(run)
