import importlib
import os
import sqlite3

import anyio


REQUIRED_TABLES = {
    "memories",
    "memories_fts",
    "entities",
    "relations",
    "jobs",
    "memory_findings",
    "memory_checks",
    "alembic_version",
}

REQUIRED_INDEXES = {
    "idx_memories_entity_key",
    "idx_memories_entity_type",
    "idx_memories_current",
    "idx_memories_review_status",
    "idx_memories_origin_client",
    "idx_memories_created_at",
    "idx_memories_last_accessed_at",
    "idx_entities_entity_type",
    "idx_relations_from",
    "idx_relations_to",
    "idx_relations_type",
    "idx_jobs_pending",
    "idx_jobs_retry",
    "idx_memory_findings_status",
}

THREAD_OBJECTS = {
    "threads",
    "thread_messages",
    "thread_messages_fts",
    "idx_threads_provider",
    "idx_threads_started_at",
    "idx_thread_messages_thread_id",
    "idx_memories_source_thread_id",
    "thread_messages_fts_ai",
    "thread_messages_fts_ad",
    "thread_messages_fts_au",
}

REQUIRED_TRIGGERS = {
    "memories_fts_ai",
    "memories_fts_ad",
    "memories_fts_au",
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


def test_head_drops_working_memory_cache_and_downgrade_restores_it(test_env):
    async def run():
        import memory_mcp.storage.migrate as migrate_mod
        importlib.reload(migrate_mod)
        import memory_mcp.storage.sqlite as sqlite_mod

        async def tables():
            importlib.reload(sqlite_mod)
            async with sqlite_mod.get_db() as db:
                rows = await db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
            await sqlite_mod.get_store().close()
            return _names(rows)

        migrate_mod.run_migrations()
        assert migrate_mod.current() == "0004_maintenance_findings"
        assert "working_memory_cache" not in await tables()

        migrate_mod.downgrade("0001_initial_v2")
        assert "working_memory_cache" in await tables()

    anyio.run(run)


def _seed_0002(conn: sqlite3.Connection) -> None:
    """Rows in the 0002 schema: an evolution chain, an entity pointer, Chinese FTS tokens."""
    def mem(mid, key, tokens, parent=None, current=1):
        conn.execute(
            "INSERT INTO memories (id, entity_key, entity_type, content, content_tokens, "
            "parent_id, mutation_type, created_at, valid_from, is_current, tags) "
            "VALUES (?, ?, 'topic', ?, ?, ?, 'initial', '2026-10-01', '2026-10-01', ?, '[]')",
            (mid, key, tokens.replace(" ", ""), tokens, parent, current),
        )

    mem("m-old", "topic:deploy", "部署 流程 旧版", current=0)
    mem("m-new", "topic:deploy", "部署 流程 新版", parent="m-old")
    mem("m-other", "topic:food", "午饭 吃 面条")
    conn.execute("DELETE FROM memories WHERE id = 'm-other'")  # leaves a rowid gap
    mem("m-last", "topic:food", "晚饭 吃 米饭")
    conn.execute(
        "INSERT INTO entities (entity_key, entity_type, current_memory_id, created_at, updated_at) "
        "VALUES ('topic:deploy', 'topic', 'm-new', '2026-10-01', '2026-10-01')"
    )
    conn.commit()


def _snapshot(conn: sqlite3.Connection) -> dict:
    return {
        "rows": conn.execute(
            "SELECT rowid, id, entity_key, content, content_tokens, parent_id, is_current "
            "FROM memories ORDER BY rowid"
        ).fetchall(),
        "fts": {
            q: {r[0] for r in conn.execute(
                "SELECT rowid FROM memories_fts WHERE memories_fts MATCH ?", (q,)
            )}
            for q in ("部署", "吃", "新版", "面条")
        },
        "entities": conn.execute("SELECT entity_key, current_memory_id FROM entities").fetchall(),
    }


def _schema(conn: sqlite3.Connection) -> tuple[set[str], set[str]]:
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    columns = {r[1] for r in conn.execute("PRAGMA table_info(memories)")}
    return names, columns


def test_0003_drops_threads_and_keeps_memories_intact(test_env):
    from alembic import command

    import memory_mcp.storage.migrate as migrate_mod
    importlib.reload(migrate_mod)
    cfg = migrate_mod._make_config()
    db_path = migrate_mod.settings.sqlite_path

    command.downgrade(cfg, "0002_drop_working_memory_cache")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _seed_0002(conn)
        before = _snapshot(conn)
        assert before["fts"]["部署"] and before["fts"]["面条"] == set()
    finally:
        conn.close()

    def check(expect_threads: bool) -> None:
        conn = sqlite3.connect(db_path)
        try:
            assert _snapshot(conn) == before
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
            assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            names, columns = _schema(conn)
            maintenance = {"memory_findings", "memory_checks", "idx_memory_findings_status"}
            assert REQUIRED_TABLES - maintenance <= names and REQUIRED_TRIGGERS <= names
            assert REQUIRED_INDEXES - maintenance <= names
            assert THREAD_OBJECTS <= names if expect_threads else not (THREAD_OBJECTS & names)
            thread_columns = {"source_thread_id", "source_refs"}
            assert thread_columns <= columns if expect_threads else not (thread_columns & columns)
            fks = {(r[2], r[3]) for r in conn.execute("PRAGMA foreign_key_list(memories)")}
            expected_fks = {("memories", "parent_id"), ("memories", "conflict_with_id")}
            assert fks == (expected_fks | {("threads", "source_thread_id")} if expect_threads else expected_fks)
            # Triggers still keep FTS in sync after the rebuild.
            conn.execute("UPDATE memories SET content_tokens = '部署 回滚' WHERE id = 'm-old'")
            assert {r[0] for r in conn.execute(
                "SELECT id FROM memories JOIN memories_fts ON memories.rowid = memories_fts.rowid "
                "WHERE memories_fts MATCH '回滚'"
            )} == {"m-old"}
            conn.rollback()
        finally:
            conn.close()

    command.upgrade(cfg, "0003_drop_threads")
    assert migrate_mod.current() == "0003_drop_threads"
    check(expect_threads=False)

    command.downgrade(cfg, "0002_drop_working_memory_cache")
    assert migrate_mod.current() == "0002_drop_working_memory_cache"
    check(expect_threads=True)


def test_0003_refuses_to_rebuild_when_memories_has_unknown_columns(test_env):
    """An extra column would be dropped silently by the explicit-column copy; stop instead."""
    async def run():
        import pytest
        import sqlite3

        import memory_mcp.storage.migrate as migrate_mod
        importlib.reload(migrate_mod)

        migrate_mod.run_migrations()
        migrate_mod.downgrade("0002_drop_working_memory_cache")
        con = sqlite3.connect(migrate_mod.settings.sqlite_path)
        con.execute("ALTER TABLE memories ADD COLUMN extra_note TEXT")
        con.commit()
        con.close()

        with pytest.raises(RuntimeError, match="extra_note"):
            migrate_mod.run_migrations()
        assert migrate_mod.current() == "0002_drop_working_memory_cache"
        con = sqlite3.connect(migrate_mod.settings.sqlite_path)
        assert "extra_note" in {r[1] for r in con.execute("PRAGMA table_info(memories)")}
        assert con.execute("SELECT count(*) FROM sqlite_master WHERE name = 'threads'").fetchone()[0] == 1
        con.close()

    anyio.run(run)


def test_0004_adds_findings_and_checks_and_downgrade_removes_them(test_env):
    from alembic import command

    import memory_mcp.storage.migrate as migrate_mod
    importlib.reload(migrate_mod)
    cfg = migrate_mod._make_config()
    db_path = migrate_mod.settings.sqlite_path
    objects = {"memory_findings", "memory_checks", "idx_memory_findings_status"}

    def names() -> set[str]:
        conn = sqlite3.connect(db_path)
        try:
            return {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        finally:
            conn.close()

    command.upgrade(cfg, "head")
    assert migrate_mod.current() == "0004_maintenance_findings"
    assert objects <= names()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO memory_checks VALUES ('pair', 'a|b', 'compatible', '2026-10-30')")
        try:
            conn.execute("INSERT INTO memory_checks VALUES ('pair', 'a|b', 'duplicate', '2026-10-30')")
            raise AssertionError("a subject must be judged once per check type")
        except sqlite3.IntegrityError:
            pass
        conn.commit()
    finally:
        conn.close()

    command.downgrade(cfg, "0003_drop_threads")
    assert migrate_mod.current() == "0003_drop_threads"
    assert not (objects & names())
    command.upgrade(cfg, "head")
    assert objects <= names()
