import importlib
import os

import anyio


REQUIRED_TABLES = {
    "memories",
    "memories_fts",
    "entities",
    "relations",
    "threads",
    "thread_messages",
    "thread_messages_fts",
    "jobs",
    "working_memory_cache",
    "alembic_version",
}

REQUIRED_INDEXES = {
    "idx_memories_entity_key",
    "idx_memories_entity_type",
    "idx_memories_current",
    "idx_memories_review_status",
    "idx_memories_origin_client",
    "idx_memories_source_thread_id",
    "idx_memories_created_at",
    "idx_memories_last_accessed_at",
    "idx_entities_entity_type",
    "idx_relations_from",
    "idx_relations_to",
    "idx_relations_type",
    "idx_threads_provider",
    "idx_threads_started_at",
    "idx_thread_messages_thread_id",
    "idx_jobs_pending",
    "idx_jobs_retry",
}

REQUIRED_TRIGGERS = {
    "memories_fts_ai",
    "memories_fts_ad",
    "memories_fts_au",
    "thread_messages_fts_ai",
    "thread_messages_fts_ad",
    "thread_messages_fts_au",
}


def _names(rows, col=0) -> set[str]:
    return {r[col] for r in rows}


def test_alembic_upgrade_creates_v2_schema(test_env):
    async def run():
        import memory_mcp.storage.migrate as migrate_mod
        importlib.reload(migrate_mod)

        migrate_mod.run_migrations()
        assert os.path.exists(migrate_mod.settings.sqlite_path)

        import memory_mcp.storage.sqlite as sqlite_mod
        importlib.reload(sqlite_mod)
        async with sqlite_mod.get_db() as db:
            tables = await db.fetchall(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            )
            indexes = await db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            )
            triggers = await db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        await sqlite_mod.get_store().close()

        table_names = _names(tables)
        assert REQUIRED_TABLES.issubset(table_names), f"missing tables: {REQUIRED_TABLES - table_names}"
        assert REQUIRED_INDEXES.issubset(_names(indexes))
        assert REQUIRED_TRIGGERS.issubset(_names(triggers))

    anyio.run(run)


def test_entities_current_memory_id_has_fk_to_memories(test_env):
    """Spec §4 requires entities.current_memory_id -> memories(id) ON DELETE SET NULL.
    PRAGMA foreign_key_list is the authoritative way to assert SQLite stored the FK."""
    async def run():
        import memory_mcp.storage.migrate as migrate_mod
        importlib.reload(migrate_mod)
        migrate_mod.run_migrations()
        import memory_mcp.storage.sqlite as sqlite_mod
        importlib.reload(sqlite_mod)
        async with sqlite_mod.get_db() as db:
            fks = await db.fetchall("PRAGMA foreign_key_list(entities)")
        await sqlite_mod.get_store().close()
        matching = [
            f for f in fks
            if f["from"] == "current_memory_id" and f["table"] == "memories" and f["to"] == "id"
        ]
        assert len(matching) == 1, f"expected exactly one FK current_memory_id->memories(id); got {[dict(f) for f in fks]}"
        assert matching[0]["on_delete"] == "SET NULL", f"on_delete must be SET NULL, got {matching[0]['on_delete']}"

    anyio.run(run)


def test_alembic_upgrade_is_idempotent(test_env):
    async def run():
        import memory_mcp.storage.migrate as migrate_mod
        importlib.reload(migrate_mod)
        migrate_mod.run_migrations()
        migrate_mod.run_migrations()  # second call must not raise
        assert migrate_mod.current() is not None

    anyio.run(run)


def test_alembic_upgrade_without_ini(test_env, monkeypatch):
    """Non-editable installs (Dockerfile) have no alembic.ini above site-packages."""
    async def run():
        import memory_mcp.storage.migrate as migrate_mod
        importlib.reload(migrate_mod)
        monkeypatch.setattr(migrate_mod, "_find_ini", lambda: None)
        migrate_mod.run_migrations()
        assert migrate_mod.current() is not None

    anyio.run(run)
