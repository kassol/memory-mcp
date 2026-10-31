"""REST routes the web console uses to govern memories (issue #6)."""
import anyio
import pytest
from starlette.testclient import TestClient

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def client(test_env):
    import importlib

    from starlette.applications import Starlette
    from starlette.middleware import Middleware

    import memory_mcp.api.routes as routes_mod
    import memory_mcp.tools.forget as forget_mod
    import memory_mcp.tools.recall as recall_mod
    import memory_mcp.tools.recall_all as recall_all_mod
    import memory_mcp.tools.remember as remember_mod
    import memory_mcp.tools.trace as trace_mod
    import memory_mcp.transport.auth as auth_mod

    for mod in (remember_mod, recall_mod, recall_all_mod, trace_mod, forget_mod, routes_mod, auth_mod):
        importlib.reload(mod)
    app = Starlette(routes=routes_mod.routes, middleware=[Middleware(auth_mod.AuthMiddleware)])
    return TestClient(app)


def _remember(client, key: str, content: str) -> str:
    res = client.post(
        "/api/v1/memories",
        json={"content": content, "entity_key": key, "entity_type": key.split(":", 1)[0]},
        headers=AUTH,
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["memory_id"]


def test_get_memory_by_id(client):
    mid = _remember(client, "fact:city", "Lives in Shanghai")
    res = client.get(f"/api/v1/memories/{mid}", headers=AUTH)
    assert res.status_code == 200
    data = res.json()["data"]
    assert (data["memory_id"], data["entity_key"], data["content"], data["is_current"]) == (
        mid, "fact:city", "Lives in Shanghai", True
    )
    assert [v["memory_id"] for v in data["versions"]] == [mid]
    assert client.get("/api/v1/memories/no-such-id", headers=AUTH).status_code == 404


def test_detail_lists_versions_newest_first_with_archive_reason(client):
    old = _remember(client, "fact:city", "Lives in Shanghai")
    new = client.post(f"/api/v1/memories/{old}/correct", json={"content": "Lives in Hangzhou"},
                      headers=AUTH).json()["data"]["memory_id"]
    client.post(f"/api/v1/memories/{new}/archive", json={"reason": "moved again"}, headers=AUTH)

    data = client.get(f"/api/v1/memories/{old}", headers=AUTH).json()["data"]
    versions = data["versions"]
    assert [(v["memory_id"], v["mutation_type"], v["is_current"], v["archived_reason"]) for v in versions] == [
        (new, "correction", False, "moved again"),
        (old, "initial", False, None),
    ]


def test_correct_creates_correction_version_without_llm(client, monkeypatch):
    import memory_mcp.engine.merge as merge
    import memory_mcp.engine.conflict as conflict
    import memory_mcp.engine.llm as llm

    def no_llm(*_a, **_k):
        raise AssertionError("correction must not call an LLM")

    monkeypatch.setattr(merge, "merge_memories", no_llm)
    monkeypatch.setattr(conflict.conflict_detector, "check_conflict", no_llm)
    monkeypatch.setattr(llm, "chat", no_llm)

    old = _remember(client, "fact:city", "Lives in Shanghai")
    res = client.post(f"/api/v1/memories/{old}/correct", json={"content": " Lives in Hangzhou "}, headers=AUTH)
    assert res.status_code == 200, res.text
    new = res.json()["data"]
    assert (new["entity_key"], new["content"], new["mutation_type"], new["is_current"]) == (
        "fact:city", "Lives in Hangzhou", "correction", True
    )

    assert client.get(f"/api/v1/memories/{old}", headers=AUTH).json()["data"]["is_current"] is False
    hits = client.get("/api/v1/memories/search?query=Hangzhou", headers=AUTH).json()["data"]["results"]
    assert [h["memory_id"] for h in hits] == [new["memory_id"]]

    again = client.post(f"/api/v1/memories/{old}/correct", json={"content": "x"}, headers=AUTH)
    assert again.status_code == 409
    missing = client.post("/api/v1/memories/no-such-id/correct", json={"content": "x"}, headers=AUTH)
    assert missing.status_code == 404
    empty = client.post(f"/api/v1/memories/{new['memory_id']}/correct", json={"content": "  "}, headers=AUTH)
    assert empty.status_code == 400


def test_archive_by_id_hides_memory_from_list_and_search(client):
    mid = _remember(client, "fact:city", "Lives in Shanghai")
    keep = _remember(client, "fact:food", "Likes noodles")

    res = client.post(f"/api/v1/memories/{mid}/archive", json={"reason": "wrong"}, headers=AUTH)
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "archived"

    listed = client.get("/api/v1/memories", headers=AUTH).json()["data"]["results"]
    assert [m["entity_key"] for m in listed] == ["fact:food"]
    hits = client.get("/api/v1/memories/search?query=Shanghai", headers=AUTH).json()["data"]["results"]
    assert mid not in [h["memory_id"] for h in hits]
    detail = client.get(f"/api/v1/memories/{mid}", headers=AUTH).json()["data"]
    assert (detail["is_current"], detail["archived_reason"]) == (False, "wrong")

    assert client.post(f"/api/v1/memories/{mid}/archive", json={"reason": "x"}, headers=AUTH).status_code == 409
    assert client.post("/api/v1/memories/no-such-id/archive", json={"reason": "x"}, headers=AUTH).status_code == 404
    assert client.get(f"/api/v1/memories/{keep}", headers=AUTH).json()["data"]["is_current"] is True


def test_list_pages_and_orders_by_valid_from(client):
    ids = [_remember(client, f"fact:k{i}", f"memory {i}") for i in range(5)]
    # Correcting k0 gives it the newest valid_from while created_at order stays k0..k4 for originals.
    corrected = client.post(f"/api/v1/memories/{ids[0]}/correct", json={"content": "memory 0 fixed"},
                            headers=AUTH).json()["data"]["memory_id"]

    default = client.get("/api/v1/memories", headers=AUTH).json()["data"]
    assert set(default) == {"results", "total", "matched"}
    assert [m["entity_key"] for m in default["results"]] == ["fact:k0", "fact:k4", "fact:k3", "fact:k2", "fact:k1"]
    assert default["results"][0]["memory_id"] == corrected

    stale_first = client.get("/api/v1/memories?order=valid_from&limit=2", headers=AUTH).json()["data"]
    assert [m["entity_key"] for m in stale_first["results"]] == ["fact:k1", "fact:k2"]
    page2 = client.get("/api/v1/memories?order=valid_from&limit=2&offset=2", headers=AUTH).json()["data"]
    assert [m["entity_key"] for m in page2["results"]] == ["fact:k3", "fact:k4"]

    assert client.get("/api/v1/memories?order=bogus", headers=AUTH).status_code == 400
    assert client.get("/api/v1/memories?offset=-1", headers=AUTH).status_code == 400


def test_dismiss_finding(client):
    from datetime import datetime, timezone
    from uuid import uuid4

    from memory_mcp.storage.sqlite import get_db

    a = _remember(client, "fact:a", "one")
    b = _remember(client, "fact:b", "two")
    fid = str(uuid4())

    async def seed():
        async with get_db() as db:
            await db.execute(
                "INSERT INTO memory_findings (id, kind, memory_id, other_memory_id, detail, status, created_at) "
                "VALUES (?, 'duplicate', ?, ?, 'same fact', 'open', ?)",
                (fid, a, b, datetime.now(timezone.utc).isoformat()),
            )

    anyio.run(seed)
    res = client.post(f"/api/v1/findings/{fid}/dismiss", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "dismissed"
    assert client.get("/api/v1/findings?status=open", headers=AUTH).json()["data"]["total"] == 0
    dismissed = client.get("/api/v1/findings?status=dismissed", headers=AUTH).json()["data"]["items"]
    assert [f["id"] for f in dismissed] == [fid]
    assert dismissed[0]["resolved_at"] is not None

    assert client.post(f"/api/v1/findings/{fid}/dismiss", headers=AUTH).status_code == 409
    assert client.post("/api/v1/findings/no-such-id/dismiss", headers=AUTH).status_code == 404


def test_new_routes_need_a_valid_token(client):
    mid = _remember(client, "fact:city", "Lives in Shanghai")
    calls = [
        ("get", f"/api/v1/memories/{mid}", None),
        ("post", f"/api/v1/memories/{mid}/correct", {"content": "x"}),
        ("post", f"/api/v1/memories/{mid}/archive", {"reason": "x"}),
        ("post", "/api/v1/findings/f/dismiss", None),
        ("get", "/api/v1/memories?order=valid_from", None),
    ]
    for method, url, body in calls:
        kwargs = {"json": body} if body is not None else {}
        assert getattr(client, method)(url, **kwargs).status_code == 401, url
        bad = getattr(client, method)(url, headers={"Authorization": "Bearer wrong"}, **kwargs)
        assert bad.status_code == 403, url
    assert client.get(f"/api/v1/memories/{mid}", headers=AUTH).json()["data"]["is_current"] is True


def test_by_key_routes_still_match_next_to_by_id_routes(client):
    """entity_key paths contain ':' and may contain '/'; they must keep reaching trace and forget."""
    _remember(client, "project:x/y", "nested key")
    trace = client.get("/api/v1/memories/project:x/y/trace", headers=AUTH)
    assert trace.status_code == 200
    assert trace.json()["data"]["total_versions"] == 1
    forgot = client.delete("/api/v1/memories/project:x/y", headers=AUTH)
    assert forgot.json()["data"]["status"] == "archived"
    # A by-key path ending in /correct or /archive is not a key the console uses; by-id wins.
    assert client.post("/api/v1/memories/project:x/correct", json={"content": "x"}, headers=AUTH).status_code == 404


def _console_build(tmp_path, monkeypatch, server):
    """The console build is not committed; serve a stand-in from a temporary directory."""
    build = tmp_path / "ui"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html><title>记忆登记簿</title>", encoding="utf-8")
    (build / "assets" / "index.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(server.ui_app, "all_directories", [str(build)])


def test_ui_is_served_without_token_but_data_still_needs_one(test_env, tmp_path, monkeypatch):
    import importlib

    import memory_mcp.server as server

    importlib.reload(server)
    _console_build(tmp_path, monkeypatch, server)
    with TestClient(server.app) as client:
        page = client.get("/ui/")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert "<title>记忆登记簿</title>" in page.text
        assert client.get("/ui/assets/index.js").status_code == 200
        assert client.get("/ui/../health").status_code == 200  # normalised to /health, not a file read
        assert client.get("/api/v1/memories").status_code == 401
        assert client.get("/uix").status_code == 401  # only the /ui/ prefix is open


def test_service_starts_without_a_console_build(test_env, tmp_path, monkeypatch):
    import importlib

    import memory_mcp.server as server

    importlib.reload(server)
    monkeypatch.setattr(server.ui_app, "all_directories", [str(tmp_path / "missing")])
    with TestClient(server.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ui/").status_code == 404


def test_correct_keeps_title_and_provenance(client):
    res = client.post("/api/v1/memories", headers=AUTH, json={
        "content": "Lives in Shanghai", "entity_key": "fact:city", "entity_type": "fact",
        "title": "Home city", "origin_client": "cli",
    })
    old = res.json()["data"]["memory_id"]
    new = client.post(f"/api/v1/memories/{old}/correct", json={"content": "Lives in Hangzhou"},
                      headers=AUTH).json()["data"]["memory_id"]

    from memory_mcp.storage.vector import vector_store

    node = anyio.run(vector_store.get_by_id, new)
    assert (node.title, node.origin_client) == ("Home city", "cli")


def test_correct_with_unchanged_content_creates_no_version(client):
    mid = _remember(client, "fact:city", "Lives in Shanghai")
    res = client.post(f"/api/v1/memories/{mid}/correct", json={"content": "Lives in Shanghai"}, headers=AUTH)
    assert res.status_code == 200
    assert res.json()["data"]["memory_id"] == mid
    assert len(client.get(f"/api/v1/memories/{mid}", headers=AUTH).json()["data"]["versions"]) == 1


def test_archive_requires_a_reason(client):
    mid = _remember(client, "fact:city", "Lives in Shanghai")
    for body in ({}, {"reason": "  "}):
        assert client.post(f"/api/v1/memories/{mid}/archive", json=body, headers=AUTH).status_code == 400
    assert client.get(f"/api/v1/memories/{mid}", headers=AUTH).json()["data"]["is_current"] is True


def test_ui_without_trailing_slash_redirects_to_the_page(test_env, tmp_path, monkeypatch):
    import importlib

    import memory_mcp.server as server

    importlib.reload(server)
    _console_build(tmp_path, monkeypatch, server)
    with TestClient(server.app) as client:
        res = client.get("/ui", follow_redirects=False)
        assert res.status_code in (301, 307, 308)
        assert res.headers["location"].endswith("/ui/")


def test_dismiss_only_changes_an_open_finding(client):
    """The status check and the write are one conditional UPDATE, so a concurrent auto-resolve is not overwritten."""
    from datetime import datetime, timezone
    from uuid import uuid4

    from memory_mcp.storage.sqlite import get_db

    a = _remember(client, "fact:a", "one")
    fid = str(uuid4())

    async def seed():
        async with get_db() as db:
            await db.execute(
                "INSERT INTO memory_findings (id, kind, memory_id, detail, status, created_at) "
                "VALUES (?, 'internal_contradiction', ?, 'x', 'resolved', ?)",
                (fid, a, datetime.now(timezone.utc).isoformat()),
            )

    anyio.run(seed)
    assert client.post(f"/api/v1/findings/{fid}/dismiss", headers=AUTH).status_code == 409
    resolved = client.get("/api/v1/findings?status=resolved", headers=AUTH).json()["data"]["items"]
    assert [f["id"] for f in resolved] == [fid]


def test_list_sorts_by_any_column_filters_by_key_and_counts_matches(client):
    for key, content in [("fact:beta", "b"), ("tool:alpha", "a"), ("fact:gamma", "g")]:
        _remember(client, key, content)

    def keys(query: str) -> list[str]:
        res = client.get(f"/api/v1/memories?{query}", headers=AUTH)
        assert res.status_code == 200, res.text
        return [m["entity_key"] for m in res.json()["data"]["results"]]

    assert keys("sort=entity_key&direction=asc") == ["fact:beta", "fact:gamma", "tool:alpha"]
    assert keys("sort=entity_key&direction=desc") == ["tool:alpha", "fact:gamma", "fact:beta"]
    assert keys("sort=created_at&direction=asc") == ["fact:beta", "tool:alpha", "fact:gamma"]
    assert keys("sort=entity_type&direction=desc&limit=1") == ["tool:alpha"]
    assert keys("key=A&sort=entity_key&direction=asc") == ["fact:beta", "fact:gamma", "tool:alpha"]
    assert keys("key=GAM") == ["fact:gamma"]  # case-insensitive substring of the key
    assert keys("key=%25") == []  # LIKE wildcards in the filter are literal

    data = client.get("/api/v1/memories?entity_type=fact&limit=1", headers=AUTH).json()["data"]
    assert (data["total"], data["matched"]) == (1, 2)
    assert client.get("/api/v1/memories?sort=content", headers=AUTH).status_code == 400
    assert client.get("/api/v1/memories?sort=entity_key&direction=up", headers=AUTH).status_code == 400


def test_entity_types_with_current_counts(client):
    for key in ("fact:a", "fact:b", "tool:c"):
        _remember(client, key, key)
    res = client.get("/api/v1/memories/types", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["data"]["items"] == [{"entity_type": "fact", "count": 2}, {"entity_type": "tool", "count": 1}]
