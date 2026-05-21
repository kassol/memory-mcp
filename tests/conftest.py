import asyncio
import importlib
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture()
def test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_MCP_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("MEMORY_MCP_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("MEMORY_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORY_MCP_EMBEDDING_DIM", "3")
    monkeypatch.setenv("MEMORY_MCP_EMBEDDING_MODEL", "test-embedding")
    monkeypatch.setenv("MEMORY_MCP_VECTOR_BACKEND", "memory")
    monkeypatch.setenv("MEMORY_MCP_AUTO_MIGRATE", "true")

    import memory_mcp.config as config
    importlib.reload(config)

    # Run migrations into the temp data dir BEFORE storage modules load
    import memory_mcp.storage.migrate as migrate_mod
    importlib.reload(migrate_mod)
    migrate_mod.run_migrations()

    import memory_mcp.storage.sqlite as sqlite_mod
    importlib.reload(sqlite_mod)
    import memory_mcp.storage.repositories.memories as repo_mem
    import memory_mcp.storage.repositories.entities as repo_ent
    import memory_mcp.storage.repositories.relations as repo_rel
    importlib.reload(repo_mem)
    importlib.reload(repo_ent)
    importlib.reload(repo_rel)

    import memory_mcp.storage.vector as vector
    importlib.reload(vector)

    import memory_mcp.storage.graph as graph
    importlib.reload(graph)

    import memory_mcp.engine.tokenizer as tokenizer
    importlib.reload(tokenizer)
    tokenizer.reset_for_tests()

    import memory_mcp.engine.embedding as embedding
    importlib.reload(embedding)

    import memory_mcp.engine.conflict as conflict
    importlib.reload(conflict)

    import memory_mcp.engine.evolution as evolution
    importlib.reload(evolution)

    # Reload every tool module so their captured graph_store / vector_store
    # references rebind to the freshly-created stores. Without this, a tool
    # imported in a previous test keeps its old SQLiteStore alive and its
    # aiosqlite worker thread never gets stopped by cleanup, causing pytest
    # to hang on shutdown.
    import memory_mcp.tools.remember as _t_remember
    import memory_mcp.tools.recall as _t_recall
    import memory_mcp.tools.recall_all as _t_recall_all
    import memory_mcp.tools.trace as _t_trace
    import memory_mcp.tools.forget as _t_forget
    import memory_mcp.tools.relate as _t_relate
    import memory_mcp.tools.unrelate as _t_unrelate
    import memory_mcp.tools.graph_query as _t_graph_query
    for _m in (_t_remember, _t_recall, _t_recall_all, _t_trace, _t_forget, _t_relate, _t_unrelate, _t_graph_query):
        importlib.reload(_m)

    async def fake_embedding(_text: str):
        return [0.1, 0.1, 0.1]

    async def fake_conflict(_old: str, _new: str):
        return False

    monkeypatch.setattr(embedding.embedding_service, "get_embedding", fake_embedding)
    monkeypatch.setattr(conflict.conflict_detector, "check_conflict", fake_conflict)

    yield config, vector, graph

    # Stop every SQLiteStore that has an open aiosqlite worker thread.
    # Walking SQLiteStore instances via gc covers stores referenced from
    # repositories / graph_store / vector_store / tools — any one of which
    # could be holding an old store from a previous fixture cycle.
    import gc
    import memory_mcp.storage.sqlite as sqlite_mod
    for obj in gc.get_objects():
        if isinstance(obj, sqlite_mod.SQLiteStore) and obj._conn is not None:
            obj._conn.stop()
            obj._conn = None
    sqlite_mod._default_store = None


@pytest.fixture()
def tools(test_env):
    import memory_mcp.tools.remember as remember
    import memory_mcp.tools.recall as recall
    import memory_mcp.tools.recall_all as recall_all
    import memory_mcp.tools.trace as trace
    import memory_mcp.tools.forget as forget
    import memory_mcp.tools.relate as relate
    import memory_mcp.tools.unrelate as unrelate
    import memory_mcp.tools.graph_query as graph_query

    importlib.reload(unrelate)
    return (
        importlib.reload(remember),
        importlib.reload(recall),
        importlib.reload(recall_all),
        importlib.reload(trace),
        importlib.reload(forget),
        importlib.reload(relate),
        importlib.reload(graph_query),
    )
