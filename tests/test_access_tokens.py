"""Named access tokens (issue #11), through the full HTTP app."""
import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

ORIGIN = "https://testserver"
INITIAL = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def app(test_env):
    import memory_mcp.access_tokens as access_tokens
    import memory_mcp.server as server

    importlib.reload(access_tokens)
    importlib.reload(server)
    return server.app


@pytest.fixture()
def console(app) -> TestClient:
    """A signed-in console (admin password set)."""
    c = TestClient(app, base_url=ORIGIN)
    assert c.post("/api/v1/console/login", json={"token": "test-token"}, headers={"Origin": ORIGIN}).status_code == 200
    assert c.put("/api/v1/console/password", json={"new_password": "pw"}, headers={"Origin": ORIGIN}).status_code == 200
    return c


def create(console: TestClient, name: str) -> dict:
    res = console.post("/api/v1/tokens", json={"name": name}, headers={"Origin": ORIGIN})
    assert res.status_code == 201, res.text
    return res.json()["data"]


def bearer(value: str) -> dict:
    return {"Authorization": f"Bearer {value}"}


def remember(c: TestClient, headers: dict, content: str, **extra) -> dict:
    body = {"content": content, "entity_key": f"fact:{content}", "entity_type": "fact", **extra}
    res = c.post("/api/v1/memories", json=body, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


def origin_of(c: TestClient, memory_id: str) -> str | None:
    res = c.get(f"/api/v1/memories/{memory_id}", headers=INITIAL)
    assert res.status_code == 200, res.text
    return res.json()["data"]["origin_token"]


def listed(console: TestClient) -> dict[str, dict]:
    res = console.get("/api/v1/tokens")
    assert res.status_code == 200, res.text
    return {t["name"]: t for t in res.json()["data"]["items"]}


def test_new_token_reads_and_writes_over_rest_and_origin_records_it(app, console):
    created = create(console, "laptop")
    value = created["value"]
    assert created["name"] == "laptop" and value

    c = TestClient(app, base_url=ORIGIN)
    assert c.get("/api/v1/memories", headers=bearer(value)).status_code == 200
    assert c.get("/api/v1/findings", headers=bearer(value)).status_code == 200
    # A client cannot claim another token's name.
    written = remember(c, bearer(value), "uses-zsh", origin_token="someone-else")
    assert origin_of(c, written["memory_id"]) == "laptop"
    by_initial = remember(c, INITIAL, "uses-vim")
    assert origin_of(c, by_initial["memory_id"]) == "initial"


def _mcp(c: TestClient, headers: dict, method: str, params: dict, session: str | None = None, id_: int = 1):
    h = {**headers, "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if session:
        h["mcp-session-id"] = session
    res = c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params})
    assert res.status_code == 200, res.text
    data = [line[5:].strip() for line in res.text.splitlines() if line.startswith("data:") and line[5:].strip()]
    return res.headers.get("mcp-session-id"), json.loads(data[-1])


def test_mcp_remember_records_the_token_name(app, console, monkeypatch):
    import memory_mcp.engine.key_assignment as key_mod

    async def fake_assign(content, embedding=None):
        return "fact:mcp_written", "fact"

    monkeypatch.setattr(key_mod, "assign_entity_key", fake_assign)
    value = create(console, "agent-host")["value"]
    with TestClient(app, base_url=ORIGIN) as c:
        init = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}
        session, reply = _mcp(c, bearer(value), "initialize", init)
        assert "result" in reply, reply
        h = {**bearer(value), "Accept": "application/json, text/event-stream", "mcp-session-id": session}
        c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        _, reply = _mcp(c, bearer(value), "tools/call", {"name": "remember", "arguments": {"content": "via mcp"}},
                        session=session, id_=2)
        result = json.loads(reply["result"]["content"][0]["text"])
        assert result["status"] == "created", result
        assert origin_of(c, result["memory_id"]) == "agent-host"


def test_revoked_token_is_rejected_and_others_keep_working(app, console):
    a = create(console, "a")
    b = create(console, "b")
    res = console.delete(f"/api/v1/tokens/{a['id']}", headers={"Origin": ORIGIN})
    assert res.status_code == 200, res.text
    c = TestClient(app, base_url=ORIGIN)
    assert c.get("/api/v1/memories", headers=bearer(a["value"])).status_code == 403
    assert c.post("/mcp", json={}, headers=bearer(a["value"])).status_code == 403
    assert c.get("/api/v1/memories", headers=bearer(b["value"])).status_code == 200
    assert listed(console)["a"]["revoked_at"] is not None
    assert listed(console)["b"]["revoked_at"] is None


def test_initial_token_is_revoked_like_any_other(app, console):
    c = TestClient(app, base_url=ORIGIN)
    initial = listed(console)["initial"]
    assert initial["source"] == "file" and initial["revoked_at"] is None
    res = console.delete(f"/api/v1/tokens/{initial['id']}", headers={"Origin": ORIGIN})
    assert res.status_code == 200, res.text
    assert c.get("/api/v1/memories", headers=INITIAL).status_code == 403
    assert c.post("/mcp", json={}, headers=INITIAL).status_code == 403
    assert listed(console)["initial"]["revoked_at"] is not None


def _set_config_token(monkeypatch, value: str) -> None:
    import memory_mcp.config as config

    monkeypatch.setattr(config.settings, "auth_token", value)


def test_the_configuration_value_counts_only_on_first_use(app, console, monkeypatch):
    c = TestClient(app, base_url=ORIGIN)
    # The stored hash is the token now; editing the configuration file does not change it.
    _set_config_token(monkeypatch, "edited-in-env")
    assert c.get("/api/v1/memories", headers=INITIAL).status_code == 200
    assert c.get("/api/v1/memories", headers=bearer("edited-in-env")).status_code == 403


def test_reset_restores_the_initial_token_from_the_configuration_value(app, console, monkeypatch):
    initial = listed(console)["initial"]
    console.delete(f"/api/v1/tokens/{initial['id']}", headers={"Origin": ORIGIN})
    _set_config_token(monkeypatch, "rotated-in-env")
    from memory_mcp import reset_password

    reset_password.main()
    c = TestClient(app, base_url=ORIGIN)
    assert c.get("/api/v1/memories", headers=INITIAL).status_code == 403
    assert c.get("/api/v1/memories", headers=bearer("rotated-in-env")).status_code == 200
    # The restored initial token opens the bootstrap session to set a new password.
    res = c.post("/api/v1/console/login", json={"token": "rotated-in-env"}, headers={"Origin": ORIGIN})
    assert res.status_code == 200


def test_revoked_initial_token_cannot_open_a_bootstrap_session(app, console):
    initial = listed(console)["initial"]
    console.delete(f"/api/v1/tokens/{initial['id']}", headers={"Origin": ORIGIN})
    import sqlite3

    import memory_mcp.config as config

    con = sqlite3.connect(config.settings.sqlite_path)
    with con:
        con.execute("DELETE FROM console_admin")  # no password, without the reset command
    con.close()
    c = TestClient(app, base_url=ORIGIN)
    res = c.post("/api/v1/console/login", json={"token": "test-token"}, headers={"Origin": ORIGIN})
    assert res.status_code == 401


def test_a_named_token_cannot_open_a_bootstrap_session(app, console):
    value = create(console, "agent")["value"]
    import sqlite3

    import memory_mcp.config as config

    con = sqlite3.connect(config.settings.sqlite_path)
    with con:
        con.execute("DELETE FROM console_admin")
    con.close()
    c = TestClient(app, base_url=ORIGIN)
    assert c.post("/api/v1/console/login", json={"token": value}, headers={"Origin": ORIGIN}).status_code == 401


def test_startup_stores_the_initial_token_hash_once(test_env):
    import sqlite3

    import anyio

    import memory_mcp.config as config
    import memory_mcp.server as server

    importlib.reload(server)
    con = sqlite3.connect(config.settings.sqlite_path)
    with con:
        con.execute("UPDATE access_tokens SET token_hash = NULL WHERE id = 'initial'")  # as right after 0007
    con.close()

    async def start():
        async with server.app.router.lifespan_context(server.app):
            pass

    anyio.run(start)
    c = TestClient(server.app, base_url=ORIGIN)
    assert c.get("/api/v1/memories", headers=INITIAL).status_code == 200


def test_rest_body_cannot_set_the_origin_through_a_console_session(app, console):
    res = console.post("/api/v1/memories", json={"content": "x", "entity_key": "fact:x", "entity_type": "fact",
                                                 "origin_token": "forged"}, headers={"Origin": ORIGIN})
    assert res.status_code == 200, res.text
    assert origin_of(console, res.json()["data"]["memory_id"]) is None


def test_token_value_is_shown_once_and_only_its_hash_is_stored(app, console):
    created = create(console, "cli")
    items = listed(console)
    assert set(items) == {"initial", "cli"}
    assert all("value" not in t and "token_hash" not in t for t in items.values())
    assert items["cli"]["source"] == "console"

    import sqlite3

    import memory_mcp.config as config

    con = sqlite3.connect(config.settings.sqlite_path)
    stored = [r[0] for r in con.execute("SELECT token_hash FROM access_tokens")]
    con.close()
    assert len(stored) == 2 and all(h and created["value"] not in h and "test-token" not in h for h in stored)


def test_names_are_required_and_unique_even_after_revocation(app, console):
    h = {"Origin": ORIGIN}
    assert console.post("/api/v1/tokens", json={"name": "  "}, headers=h).status_code == 400
    a = create(console, "dup")
    assert console.post("/api/v1/tokens", json={"name": "dup"}, headers=h).status_code == 409
    console.delete(f"/api/v1/tokens/{a['id']}", headers=h)
    # The name stays taken: memories written under it must keep pointing at one token.
    assert console.post("/api/v1/tokens", json={"name": "dup"}, headers=h).status_code == 409
    assert console.post("/api/v1/tokens", json={"name": "initial"}, headers=h).status_code == 409


def test_last_use_is_written_at_most_once_a_minute(app, console, monkeypatch):
    import memory_mcp.access_tokens as access_tokens

    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(access_tokens, "_now", lambda: now)
    value = create(console, "busy")["value"]
    c = TestClient(app, base_url=ORIGIN)
    assert listed(console)["busy"]["last_used_at"] is None

    c.get("/api/v1/memories", headers=bearer(value))
    first = listed(console)["busy"]["last_used_at"]
    assert first == now.isoformat()
    now += timedelta(seconds=59)
    c.get("/api/v1/memories", headers=bearer(value))
    assert listed(console)["busy"]["last_used_at"] == first
    now += timedelta(seconds=2)
    c.get("/api/v1/memories", headers=bearer(value))
    assert listed(console)["busy"]["last_used_at"] == now.isoformat()


def test_token_management_accepts_only_a_console_session(app, console):
    value = create(console, "agent")["value"]
    c = TestClient(app, base_url=ORIGIN)
    for headers in (bearer(value), INITIAL):
        assert c.get("/api/v1/tokens", headers=headers).status_code == 403
        assert c.post("/api/v1/tokens", json={"name": "x"}, headers=headers).status_code == 403
    assert c.get("/api/v1/tokens").status_code == 401
    assert console.post("/api/v1/tokens", json={"name": "x"}).status_code == 403  # cookie write without Origin


def test_unknown_token_is_rejected(app):
    c = TestClient(app, base_url=ORIGIN)
    assert c.get("/api/v1/memories", headers=bearer("nope")).status_code == 403
    assert c.post("/mcp", json={}, headers=bearer("nope")).status_code == 403
