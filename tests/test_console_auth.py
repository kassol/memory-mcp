"""Admin password and console sessions (issue #10, docs/adr/0001), through the full HTTP app."""
import importlib
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

TOKEN = {"Authorization": "Bearer test-token"}
ORIGIN = "https://testserver"


@pytest.fixture()
def app(test_env):
    import memory_mcp.console_auth as console_auth
    import memory_mcp.server as server

    importlib.reload(console_auth)
    importlib.reload(server)
    return server.app


def client_for(app) -> TestClient:
    """A browser with its own cookie jar. Secure cookies need https, so it talks https.

    Used without `with`: the app lifespan (MCP session manager) may run only once per test, and
    nothing here needs it. Settings are read lazily from SQLite after migrations in test_env.
    """
    return TestClient(app, base_url=ORIGIN)


def post(c: TestClient, path: str, body=None, origin: str | None = ORIGIN, **kw):
    headers = {"Origin": origin} if origin else {}
    return c.post(path, json=body, headers=headers, **kw)


def bootstrap(c: TestClient, password: str = "first-password") -> None:
    assert post(c, "/api/v1/console/login", {"token": "test-token"}).status_code == 200
    assert c.put("/api/v1/console/password", json={"new_password": password},
                 headers={"Origin": ORIGIN}).status_code == 200


def test_session_status_before_sign_in(app):
    c = client_for(app)
    res = c.get("/api/v1/console/session")
    assert res.status_code == 200
    assert res.json()["data"] == {"signed_in": False, "password_set": False, "bootstrap": False}


def test_bootstrap_session_can_only_set_the_password(app):
    c = client_for(app)
    assert post(c, "/api/v1/console/login", {"token": "wrong"}).status_code == 401
    assert post(c, "/api/v1/console/login", {"password": "anything"}).status_code == 401
    res = post(c, "/api/v1/console/login", {"token": "test-token"})
    assert res.status_code == 200
    assert c.get("/api/v1/console/session").json()["data"] == {
        "signed_in": True, "password_set": False, "bootstrap": True,
    }
    # Restricted to setting the password: no data, no settings.
    assert c.get("/api/v1/findings").status_code == 403
    assert c.get("/api/v1/settings").status_code == 403

    res = c.put("/api/v1/console/password", json={"new_password": "first-password"}, headers={"Origin": ORIGIN})
    assert res.status_code == 200
    status = c.get("/api/v1/console/session").json()["data"]
    assert status == {"signed_in": True, "password_set": True, "bootstrap": False}
    assert c.get("/api/v1/settings").status_code == 200


def test_config_token_cannot_open_the_console_once_a_password_exists(app):
    c = client_for(app)
    bootstrap(c)
    c = client_for(app)
    res = post(c, "/api/v1/console/login", {"token": "test-token"})
    assert res.status_code == 401
    assert post(c, "/api/v1/console/login", {"password": "wrong"}).status_code == 401
    assert post(c, "/api/v1/console/login", {"password": "first-password"}).status_code == 200
    assert c.get("/api/v1/console/session").json()["data"]["signed_in"] is True


def test_session_cookie_flags_and_only_its_hash_is_stored(app):
    c = client_for(app)
    res = post(c, "/api/v1/console/login", {"token": "test-token"})
    cookie = res.headers["set-cookie"]
    assert cookie.startswith("mm_session=")
    lowered = cookie.lower()
    for flag in ("httponly", "secure", "samesite=strict", "path=/"):
        assert flag in lowered
    assert "max-age=604800" in lowered
    value = cookie.split(";", 1)[0].split("=", 1)[1]

    import sqlite3

    import memory_mcp.config as config

    con = sqlite3.connect(config.settings.sqlite_path)
    stored = [r[0] for r in con.execute("SELECT token_hash FROM console_sessions")]
    con.close()
    assert len(stored) == 1 and value not in stored[0] and stored[0] != value


def test_state_changes_by_cookie_need_a_matching_origin(app):
    c = client_for(app)
    bootstrap(c)
    body = {"value": 1.5}
    assert c.put("/api/v1/settings/fts_weight", json=body).status_code == 403
    assert c.put("/api/v1/settings/fts_weight", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.put("/api/v1/settings/fts_weight", json=body, headers={"Origin": ORIGIN}).status_code == 200
    # Reads need no Origin.
    assert c.get("/api/v1/settings").status_code == 200


def test_origin_behind_a_proxy_uses_the_forwarded_proto(app):
    c = TestClient(app, base_url="http://mem.example")
    headers = {"Origin": "https://mem.example", "X-Forwarded-Proto": "https"}
    # The cookie is Secure; send it by hand the way the browser would over https.
    res = c.post("/api/v1/console/login", json={"token": "test-token"}, headers=headers)
    assert res.status_code == 200
    session = res.cookies.get("mm_session") or res.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    res = c.put("/api/v1/console/password", json={"new_password": "p"},
                headers={**headers, "Cookie": f"mm_session={session}"})
    assert res.status_code == 200


def test_admin_endpoints_reject_access_tokens(app):
    c = client_for(app)
    assert c.get("/api/v1/settings", headers=TOKEN).status_code == 403
    assert c.put("/api/v1/settings/fts_weight", json={"value": 1}, headers=TOKEN).status_code == 403
    assert c.delete("/api/v1/settings/fts_weight", headers=TOKEN).status_code == 403
    assert c.put("/api/v1/console/password", json={"new_password": "x"}, headers=TOKEN).status_code == 403
    assert c.delete("/api/v1/console/sessions", headers=TOKEN).status_code == 403


def test_memory_and_finding_endpoints_accept_both(app):
    c = client_for(app)
    assert c.get("/api/v1/memories", headers=TOKEN).status_code == 200
    assert c.get("/api/v1/findings", headers=TOKEN).status_code == 200
    assert c.get("/api/v1/memories").status_code == 401
    bootstrap(c)
    assert c.get("/api/v1/memories").status_code == 200
    assert c.get("/api/v1/findings").status_code == 200
    res = c.post("/api/v1/memories", json={"content": "x", "entity_key": "fact:x", "entity_type": "fact"})
    assert res.status_code == 403  # cookie write without Origin
    res = post(c, "/api/v1/memories", {"content": "x", "entity_key": "fact:x", "entity_type": "fact"})
    assert res.status_code == 200


def test_mcp_accepts_only_access_tokens(app):
    c = client_for(app)
    bootstrap(c)
    res = c.post("/mcp", json={}, headers={"Origin": ORIGIN})
    assert res.status_code == 401


def test_change_password_needs_the_current_one(app):
    c = client_for(app)
    bootstrap(c)
    h = {"Origin": ORIGIN}
    assert c.put("/api/v1/console/password", json={"new_password": "second"}, headers=h).status_code == 400
    assert c.put("/api/v1/console/password", json={"current_password": "nope", "new_password": "second"},
                 headers=h).status_code == 400
    assert c.put("/api/v1/console/password", json={"current_password": "first-password", "new_password": ""},
                 headers=h).status_code == 400
    assert c.put("/api/v1/console/password", json={"current_password": "first-password", "new_password": "second"},
                 headers=h).status_code == 200
    c = client_for(app)
    assert post(c, "/api/v1/console/login", {"password": "first-password"}).status_code == 401
    assert post(c, "/api/v1/console/login", {"password": "second"}).status_code == 200


def test_logout_and_sign_out_everywhere(app):
    a, b = client_for(app), client_for(app)
    bootstrap(a)
    assert post(b, "/api/v1/console/login", {"password": "first-password"}).status_code == 200
    assert post(a, "/api/v1/console/logout").status_code == 200
    assert a.get("/api/v1/settings").status_code == 401
    assert b.get("/api/v1/settings").status_code == 200

    assert post(a, "/api/v1/console/login", {"password": "first-password"}).status_code == 200
    assert a.delete("/api/v1/console/sessions", headers={"Origin": ORIGIN}).status_code == 200
    assert a.get("/api/v1/settings").status_code == 401
    assert b.get("/api/v1/settings").status_code == 401


def test_sessions_expire_after_7_days_and_slide_with_use(app, monkeypatch):
    import memory_mcp.console_auth as console_auth

    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(console_auth, "_now", lambda: now)
    c = client_for(app)
    bootstrap(c)
    now += timedelta(days=6)
    assert c.get("/api/v1/settings").status_code == 200  # slides the expiry
    now += timedelta(days=6)
    assert c.get("/api/v1/settings").status_code == 200
    now += timedelta(days=7, seconds=1)
    assert c.get("/api/v1/settings").status_code == 401


def test_reset_command_clears_the_password_and_all_sessions(app, capsys):
    c = client_for(app)
    bootstrap(c)
    assert c.get("/api/v1/settings").status_code == 200

    from memory_mcp import reset_password

    reset_password.main()
    printed = capsys.readouterr().out
    assert "first-password" not in printed and "test-token" not in printed

    assert c.get("/api/v1/settings").status_code == 401
    assert c.get("/api/v1/console/session").json()["data"]["password_set"] is False
    # Back to bootstrap with the configuration-file token.
    assert post(c, "/api/v1/console/login", {"token": "test-token"}).status_code == 200
