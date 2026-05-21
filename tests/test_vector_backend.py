import importlib

import anyio
import pytest


def test_lancedb_backend_init_failure_raises(test_env, monkeypatch):
    _, vector_mod, _ = test_env

    class FailingLanceVectorStore:
        def __init__(self, _vectors_dir: str) -> None:
            raise RuntimeError("lancedb down")

    monkeypatch.setattr(vector_mod.settings, "vector_backend", "lancedb")
    monkeypatch.setattr(vector_mod, "LanceVectorBackend", FailingLanceVectorStore)

    with pytest.raises(RuntimeError, match="Failed to initialize LanceDB vector backend"):
        vector_mod.VectorStore()


def test_auto_backend_falls_back_to_memory(test_env, monkeypatch):
    _, vector_mod, _ = test_env

    class FailingLanceVectorStore:
        def __init__(self, _vectors_dir: str) -> None:
            raise RuntimeError("lancedb down")

    monkeypatch.setattr(vector_mod.settings, "vector_backend", "auto")
    monkeypatch.setattr(vector_mod, "LanceVectorBackend", FailingLanceVectorStore)

    store = vector_mod.VectorStore()
    assert store.backend_name == "memory"


def test_vector_backend_only_stores_id_and_vector(test_env):
    async def run():
        import memory_mcp.storage.migrate as migrate_mod
        importlib.reload(migrate_mod)
        migrate_mod.run_migrations()

        _, vector_mod, _ = test_env
        importlib.reload(vector_mod)

        store = vector_mod.VectorStore()
        backend = store._backend
        # InMemoryVectorBackend exposes _vectors dict {id: vector}
        if hasattr(backend, "_vectors"):
            assert backend._vectors == {}
        # Public surface check
        await backend.upsert("mem-1", [0.1, 0.1, 0.1])
        ids = await backend.search([0.1, 0.1, 0.1], limit=5)
        assert ids[0][0] == "mem-1"

    anyio.run(run)
