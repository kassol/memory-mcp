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

    import memory_mcp.config as config
    importlib.reload(config)

    import memory_mcp.storage.vector as vector
    importlib.reload(vector)

    import memory_mcp.storage.graph as graph
    importlib.reload(graph)

    import memory_mcp.engine.embedding as embedding
    importlib.reload(embedding)

    import memory_mcp.engine.conflict as conflict
    importlib.reload(conflict)

    import memory_mcp.engine.evolution as evolution
    importlib.reload(evolution)

    async def fake_embedding(_text: str):
        return [0.1, 0.1, 0.1]

    async def fake_conflict(_old: str, _new: str):
        return False

    monkeypatch.setattr(embedding.embedding_service, "get_embedding", fake_embedding)
    monkeypatch.setattr(conflict.conflict_detector, "check_conflict", fake_conflict)

    return config, vector, graph


@pytest.fixture()
def tools(test_env):
    import importlib

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
