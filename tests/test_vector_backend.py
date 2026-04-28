import pytest


def test_lancedb_backend_init_failure_raises(test_env, monkeypatch):
    _, vector_mod, _ = test_env

    class FailingLanceVectorStore:
        def __init__(self, _vectors_dir: str) -> None:
            raise RuntimeError("lancedb down")

    monkeypatch.setattr(vector_mod.settings, "vector_backend", "lancedb")
    monkeypatch.setattr(vector_mod, "LanceVectorStore", FailingLanceVectorStore)

    with pytest.raises(RuntimeError, match="Failed to initialize LanceDB vector backend"):
        vector_mod.VectorStore()


def test_auto_backend_falls_back_to_memory(test_env, monkeypatch):
    _, vector_mod, _ = test_env

    class FailingLanceVectorStore:
        def __init__(self, _vectors_dir: str) -> None:
            raise RuntimeError("lancedb down")

    monkeypatch.setattr(vector_mod.settings, "vector_backend", "auto")
    monkeypatch.setattr(vector_mod, "LanceVectorStore", FailingLanceVectorStore)

    store = vector_mod.VectorStore()
    assert store.backend_name == "memory"
