import importlib

import pytest
from starlette.testclient import TestClient


@pytest.fixture()
def app(test_env):
    # Reload tool modules so they pick up the freshly reloaded storage singletons
    # from test_env (vector_store, graph_store, embedding_service, conflict_detector).
    import memory_mcp.tools.remember as _rem
    import memory_mcp.tools.recall as _rec
    import memory_mcp.tools.recall_all as _reca
    import memory_mcp.tools.trace as _tr
    import memory_mcp.tools.forget as _fo
    import memory_mcp.tools.relate as _rel
    import memory_mcp.tools.unrelate as _unrel
    import memory_mcp.tools.graph_query as _gq
    importlib.reload(_rem)
    importlib.reload(_rec)
    importlib.reload(_reca)
    importlib.reload(_tr)
    importlib.reload(_fo)
    importlib.reload(_rel)
    importlib.reload(_unrel)
    importlib.reload(_gq)

    import memory_mcp.api.routes as routes_mod
    importlib.reload(routes_mod)

    # Build a minimal Starlette app with only the REST routes + auth middleware.
    # This avoids triggering the MCP StreamableHTTP lifespan which can close
    # the asyncio event loop and break subsequent anyio.run() calls in other tests.
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    from starlette.requests import Request

    import memory_mcp.transport.auth as auth_mod
    importlib.reload(auth_mod)

    import memory_mcp.transport.cors as cors_mod
    importlib.reload(cors_mod)

    async def health(request: Request):
        return JSONResponse({"status": "healthy"})

    return Starlette(
        routes=[
            Route("/health", endpoint=health, methods=["GET"]),
            *routes_mod.routes,
        ],
        middleware=[
            Middleware(cors_mod.CorsMiddleware),
            Middleware(auth_mod.AuthMiddleware),
        ],
    )


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=True)


AUTH = {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

def test_auth_missing_token_returns_ok_false(client):
    resp = client.get("/api/v1/memories")
    assert resp.status_code == 401
    body = resp.json()
    assert body["ok"] is False
    assert "error" in body


def test_auth_wrong_token_returns_ok_false(client):
    resp = client.get("/api/v1/memories", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 403
    body = resp.json()
    assert body["ok"] is False
    assert "error" in body


def test_auth_valid_token_passes(client):
    resp = client.get("/api/v1/memories", headers=AUTH)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/v1/memories  (remember)
# ---------------------------------------------------------------------------

def test_remember_creates_memory(client):
    payload = {
        "content": "Prefer Vim as editor",
        "entity_key": "preference:editor",
        "entity_type": "preference",
    }
    resp = client.post("/api/v1/memories", json=payload, headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "created"


def test_remember_missing_field_returns_error(client):
    resp = client.post("/api/v1/memories", json={"content": "x"}, headers=AUTH)
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert "error" in body


# ---------------------------------------------------------------------------
# GET /api/v1/memories  (recall_all)
# ---------------------------------------------------------------------------

def test_recall_all_empty(client):
    resp = client.get("/api/v1/memories", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["total"] == 0


def test_recall_all_after_remember(client):
    client.post(
        "/api/v1/memories",
        json={"content": "I use Python", "entity_key": "fact:lang", "entity_type": "fact"},
        headers=AUTH,
    )
    resp = client.get("/api/v1/memories", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] == 1


def test_recall_all_entity_type_filter(client):
    client.post(
        "/api/v1/memories",
        json={"content": "I use Python", "entity_key": "fact:lang", "entity_type": "fact"},
        headers=AUTH,
    )
    resp = client.get("/api/v1/memories?entity_type=preference", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/memories/search  (recall)
# ---------------------------------------------------------------------------

def test_recall_search(client):
    client.post(
        "/api/v1/memories",
        json={"content": "Prefer dark mode", "entity_key": "preference:theme", "entity_type": "preference"},
        headers=AUTH,
    )
    resp = client.get("/api/v1/memories/search?query=dark+mode", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["total"] >= 1


def test_recall_search_missing_query_returns_error(client):
    resp = client.get("/api/v1/memories/search", headers=AUTH)
    assert resp.status_code == 400
    assert resp.json()["ok"] is False


# ---------------------------------------------------------------------------
# GET /api/v1/memories/{entity_key}/trace  (trace)
# ---------------------------------------------------------------------------

def test_trace_entity(client):
    client.post(
        "/api/v1/memories",
        json={"content": "I live in Beijing", "entity_key": "fact:city", "entity_type": "fact"},
        headers=AUTH,
    )
    resp = client.get("/api/v1/memories/fact:city/trace", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["total_versions"] == 1


def test_trace_unknown_entity(client):
    resp = client.get("/api/v1/memories/fact:unknown/trace", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["total_versions"] == 0


# ---------------------------------------------------------------------------
# DELETE /api/v1/memories/{entity_key}  (forget)
# ---------------------------------------------------------------------------

def test_forget_existing(client):
    client.post(
        "/api/v1/memories",
        json={"content": "Old preference", "entity_key": "preference:old", "entity_type": "preference"},
        headers=AUTH,
    )
    resp = client.delete("/api/v1/memories/preference:old", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "archived"


def test_forget_nonexistent(client):
    resp = client.delete("/api/v1/memories/preference:ghost", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "not_found"


# ---------------------------------------------------------------------------
# POST /api/v1/relations  (relate)
# ---------------------------------------------------------------------------

def test_relate(client):
    payload = {
        "from_entity_key": "person:alice",
        "to_entity_key": "project:x",
        "relation_type": "WORKS_ON",
    }
    resp = client.post("/api/v1/relations", json=payload, headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "created"


def test_relate_missing_field_returns_error(client):
    resp = client.post("/api/v1/relations", json={"from_entity_key": "a"}, headers=AUTH)
    assert resp.status_code == 400
    assert resp.json()["ok"] is False


# ---------------------------------------------------------------------------
# DELETE /api/v1/relations/{relation_id}  (unrelate)
# ---------------------------------------------------------------------------

def test_unrelate_existing(client):
    create_resp = client.post(
        "/api/v1/relations",
        json={
            "from_entity_key": "person:alice",
            "to_entity_key": "project:x",
            "relation_type": "WORKS_ON",
        },
        headers=AUTH,
    )
    relation_id = create_resp.json()["data"]["relation_id"]

    delete_resp = client.delete(f"/api/v1/relations/{relation_id}", headers=AUTH)
    assert delete_resp.status_code == 200
    body = delete_resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "deleted"
    assert body["data"]["relation_id"] == relation_id

    graph_resp = client.get("/api/v1/graph/person:alice", headers=AUTH)
    assert graph_resp.status_code == 200
    assert graph_resp.json()["data"]["count"] == 0


def test_unrelate_nonexistent(client):
    resp = client.delete("/api/v1/relations/missing-relation-id", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "not_found"
    assert body["data"]["relation_id"] == "missing-relation-id"


# ---------------------------------------------------------------------------
# GET /api/v1/graph/{entity_key}  (graph_query)
# ---------------------------------------------------------------------------

def test_graph_query(client):
    client.post(
        "/api/v1/relations",
        json={"from_entity_key": "person:bob", "to_entity_key": "project:y", "relation_type": "OWNS"},
        headers=AUTH,
    )
    resp = client.get("/api/v1/graph/person:bob", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["count"] >= 1


def test_graph_query_with_depth(client):
    resp = client.get("/api/v1/graph/person:nobody?depth=2", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["count"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/wm  (working memory briefing)
# ---------------------------------------------------------------------------

def test_wm_empty(app, client):
    import importlib
    import memory_mcp.engine.working_memory as wm_mod
    importlib.reload(wm_mod)

    resp = client.get("/api/v1/wm", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "No memories yet" in body["data"]["briefing"]


def test_wm_with_memories(client):
    import importlib
    import memory_mcp.engine.working_memory as wm_mod
    importlib.reload(wm_mod)

    client.post(
        "/api/v1/memories",
        json={"content": "I use Cursor", "entity_key": "preference:editor", "entity_type": "preference"},
        headers=AUTH,
    )
    resp = client.get("/api/v1/wm", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "preference" in body["data"]["briefing"]
