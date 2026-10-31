"""Settings registry over REST (issue #9): precedence, source, revert, validation, call-time effect."""
from datetime import datetime, timezone
from uuid import uuid4

import anyio
import pytest
from starlette.testclient import TestClient

# Settings accept only a console session (docs/adr/0001); the client signs in once and sends the
# matching Origin on every request, as the console page does.
ORIGIN = "https://testserver"
AUTH = {"Origin": ORIGIN}


@pytest.fixture()
def client(test_env):
    import importlib

    from starlette.applications import Starlette
    from starlette.middleware import Middleware

    import memory_mcp.api.console as console_mod
    import memory_mcp.api.routes as routes_mod
    import memory_mcp.tools.recall as recall_mod
    import memory_mcp.transport.auth as auth_mod

    for mod in (recall_mod, routes_mod, console_mod, auth_mod):
        importlib.reload(mod)
    app = Starlette(routes=[*console_mod.routes, *routes_mod.routes], middleware=[Middleware(auth_mod.AuthMiddleware)])
    c = TestClient(app, base_url=ORIGIN)
    assert c.post("/api/v1/console/login", json={"token": "test-token"}, headers=AUTH).status_code == 200
    assert c.put("/api/v1/console/password", json={"new_password": "pw"}, headers=AUTH).status_code == 200
    return c


def _item(client, key: str) -> dict:
    res = client.get("/api/v1/settings", headers=AUTH)
    assert res.status_code == 200, res.text
    return next(i for i in res.json()["data"]["items"] if i["key"] == key)


def test_settings_need_the_console_sign_in(client):
    client.cookies.clear()
    assert client.get("/api/v1/settings").status_code == 401
    assert client.put("/api/v1/settings/fts_weight", json={"value": 1}, headers=AUTH).status_code == 401


def test_list_reports_value_source_and_metadata(client):
    fts = _item(client, "fts_weight")
    assert (fts["value"], fts["source"], fts["default"], fts["recommended"]) == (2.0, "default", 2.0, 2.0)
    assert (fts["group"], fts["type"]) == ("advanced", "float")
    assert fts["min"] < 2.0 < fts["max"] and fts["note"] and fts["label"]
    assert fts["file_value"] is None

    budget = _item(client, "maintenance_max_llm_calls")
    assert (budget["value"], budget["group"], budget["type"], budget["recommended"]) == (100, "behaviour", "int", None)

    keys = {i["key"] for i in client.get("/api/v1/settings", headers=AUTH).json()["data"]["items"]}
    assert keys == {
        "similarity_threshold", "maintenance_max_llm_calls",
        "fts_weight", "rrf_k", "candidates_per_source", "graph_seeds", "decay_lambda",
        "cross_key_min_cosine", "cross_key_neighbours",
    }


def test_console_value_beats_file_value_beats_default_and_revert_returns_to_file(client, monkeypatch):
    import memory_mcp.settings_registry as registry

    assert _item(client, "similarity_threshold")["source"] == "default"

    monkeypatch.setattr(registry.settings, "similarity_threshold", 0.9)
    item = _item(client, "similarity_threshold")
    assert (item["value"], item["source"], item["file_value"]) == (0.9, "file", 0.9)

    res = client.put("/api/v1/settings/similarity_threshold", json={"value": 0.95}, headers=AUTH)
    assert res.status_code == 200, res.text
    assert (res.json()["data"]["value"], res.json()["data"]["source"]) == (0.95, "console")
    assert (_item(client, "similarity_threshold")["value"], _item(client, "similarity_threshold")["source"]) == (
        0.95, "console"
    )

    res = client.delete("/api/v1/settings/similarity_threshold", headers=AUTH)
    assert res.status_code == 200
    assert (res.json()["data"]["value"], res.json()["data"]["source"]) == (0.9, "file")

    monkeypatch.setattr(registry.settings, "similarity_threshold", None)
    assert (_item(client, "similarity_threshold")["value"], _item(client, "similarity_threshold")["source"]) == (
        0.85, "default"
    )


def test_revert_without_console_value_is_harmless(client):
    res = client.delete("/api/v1/settings/rrf_k", headers=AUTH)
    assert res.status_code == 200
    assert (res.json()["data"]["value"], res.json()["data"]["source"]) == (60, "default")


@pytest.mark.parametrize("key, body, reason", [
    ("fts_weight", {"value": 11}, "between"),
    ("fts_weight", {"value": -1}, "between"),
    ("fts_weight", {"value": "2"}, "number"),
    ("fts_weight", {}, "value"),
    ("rrf_k", {"value": 1.5}, "integer"),
    ("rrf_k", {"value": True}, "number"),
    ("cross_key_min_cosine", {"value": 1.01}, "between"),
])
def test_invalid_values_are_rejected_with_a_reason(client, key, body, reason):
    res = client.put(f"/api/v1/settings/{key}", json=body, headers=AUTH)
    assert res.status_code == 400
    assert reason in res.json()["error"]
    assert _item(client, key)["source"] == "default"


def test_unknown_setting_is_404(client):
    assert client.put("/api/v1/settings/no_such", json={"value": 1}, headers=AUTH).status_code == 404
    assert client.delete("/api/v1/settings/no_such", headers=AUTH).status_code == 404


def test_integer_given_as_whole_float_is_stored_as_integer(client):
    res = client.put("/api/v1/settings/rrf_k", json={"value": 30.0}, headers=AUTH)
    assert res.status_code == 200
    assert res.json()["data"]["value"] == 30 and isinstance(res.json()["data"]["value"], int)


async def _add(key: str, content: str, embedding: list[float]) -> str:
    from memory_mcp.engine.models import MemoryNode, MutationType
    from memory_mcp.engine.tokenizer import tokenize
    from memory_mcp.storage.vector import vector_store

    now = datetime.now(timezone.utc)
    node = MemoryNode(
        id=str(uuid4()), entity_key=key, entity_type=key.split(":", 1)[0], content=content,
        content_tokens=tokenize(content), embedding=embedding, mutation_type=MutationType.INITIAL,
        created_at=now, valid_from=now, is_current=True,
    )
    await vector_store.insert(node)
    return node.id


def test_saved_tuning_value_changes_the_next_recall(client, monkeypatch):
    import memory_mcp.engine.embedding as embedding

    async def seed():
        await _add("fact:vec", "close in meaning", [1.0, 0.0, 0.0])
        await _add("fact:literal", "W8A8SC weights", [0.0, 0.0, 1.0])

    anyio.run(seed)

    async def query_vector(_text: str):
        return [1.0, 0.0, 0.0]

    monkeypatch.setattr(embedding.embedding_service, "get_embedding", query_vector)

    def top() -> str:
        res = client.get("/api/v1/memories/search", params={"query": "W8A8SC", "limit": 2}, headers=AUTH)
        return res.json()["data"]["results"][0]["entity_key"]

    # vector: vec 1st, literal 2nd; FTS: literal only. With FTS weight 0 the vector order decides.
    assert top() == "fact:literal"
    assert client.put("/api/v1/settings/fts_weight", json={"value": 0}, headers=AUTH).status_code == 200
    assert top() == "fact:vec"
    client.delete("/api/v1/settings/fts_weight", headers=AUTH)
    assert top() == "fact:literal"


def test_out_of_range_file_value_stops_startup_with_the_reason(test_env, monkeypatch):
    import importlib

    import pytest

    import memory_mcp.server as server
    import memory_mcp.settings_registry as registry

    importlib.reload(server)
    monkeypatch.setattr(registry.settings, "rrf_k", 0)
    monkeypatch.setattr(registry.settings, "fts_weight", 2.5)
    with pytest.raises(ValueError, match="rrf_k must be between 1 and 1000"):
        with TestClient(server.app):
            pass

    monkeypatch.setattr(registry.settings, "rrf_k", 30)
    with TestClient(server.app) as c:
        assert c.get("/health").status_code == 200
