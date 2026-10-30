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


def test_vector_index_keeps_current_versions_only(tools, test_env):
    """Stale versions must not crowd the ANN candidates that recall and key assignment filter to current."""
    import anyio

    async def run():
        remember = tools[0]
        _, vector, _ = test_env
        fact = {"entity_key": "fact:home", "entity_type": "fact"}
        await remember.remember_tool({**fact, "content": "Lives in Beijing"})
        await remember.remember_tool({**fact, "content": "Lives in Shanghai"})

        history = await vector.vector_store.get_history("fact:home")
        indexed = set(vector.vector_store._backend._vectors)
        assert indexed == {h.id for h in history if h.is_current} and len(history) == 2

    anyio.run(run)


def test_lance_backend_compacts_fragments(tmp_path, monkeypatch):
    import anyio

    pytest.importorskip("lancedb")  # miniconda's lancedb breaks on numpy 2; the lock venv runs it

    import memory_mcp.storage.vector as vector_mod

    monkeypatch.setattr(vector_mod.settings, "embedding_dim", 3)
    monkeypatch.setattr(vector_mod, "COMPACT_EVERY_WRITES", 10)
    backend = vector_mod.LanceVectorBackend(str(tmp_path))

    async def run():
        for i in range(10):
            await backend.upsert(f"m{i}", [0.1, 0.2, float(i)])

    anyio.run(run)
    assert backend._table.stats()["fragment_stats"]["num_fragments"] == 1
    assert backend._table.count_rows() == 10


def test_lance_backend_sees_writes_from_another_process(tmp_path, monkeypatch):
    """The service must see rows an import or ops script writes through a separate connection."""
    import anyio

    pytest.importorskip("lancedb")  # miniconda's lancedb breaks on numpy 2; the lock venv runs it
    import memory_mcp.storage.vector as vector_mod

    monkeypatch.setattr(vector_mod.settings, "embedding_dim", 3)
    service = vector_mod.LanceVectorBackend(str(tmp_path))
    script = vector_mod.LanceVectorBackend(str(tmp_path))

    async def run():
        assert await service.search([0.1, 0.2, 0.3], limit=1) == []
        await script.upsert("m1", [0.1, 0.2, 0.3])
        assert [mid for mid, _ in await service.search([0.1, 0.2, 0.3], limit=1)] == ["m1"]

    anyio.run(run)


@pytest.mark.parametrize("backend_name", ["lance", "memory"])
def test_cosine_neighbours_use_the_stored_vector(tmp_path, monkeypatch, backend_name):
    """Neighbours are ranked by cosine similarity of stored vectors and exclude the memory itself."""
    import anyio

    import memory_mcp.storage.vector as vector_mod

    if backend_name == "lance":
        pytest.importorskip("lancedb")
        monkeypatch.setattr(vector_mod.settings, "embedding_dim", 3)
        backend = vector_mod.LanceVectorBackend(str(tmp_path))
    else:
        backend = vector_mod.InMemoryVectorBackend(str(tmp_path))

    async def run():
        await backend.upsert("a", [1.0, 0.0, 0.0])
        await backend.upsert("b", [2.0, 2.0, 0.0])  # cosine 0.707, length does not matter
        await backend.upsert("c", [0.0, 0.0, 5.0])  # cosine 0
        await backend.upsert("d", [3.0, 0.3, 0.0])  # cosine 0.995
        hits = await backend.cosine_neighbours("a", limit=2)
        assert [mid for mid, _ in hits] == ["d", "b"]
        assert [round(cos, 3) for _, cos in hits] == [0.995, 0.707]
        assert await backend.cosine_neighbours("missing", limit=2) == []

    anyio.run(run)
