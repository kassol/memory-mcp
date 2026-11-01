"""Model providers (issue #12): three protocols over HTTP, keys encrypted at rest, console CRUD.

The protocol tests talk to a local HTTP server, so the adapters are exercised over the wire as a
provider is: request shape, headers, reason-off and JSON mode, error mapping, last call status.
"""
import json
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anyio
import pytest
from starlette.testclient import TestClient

ORIGIN = "https://testserver"
AUTH = {"Origin": ORIGIN}
BEARER = {"Authorization": "Bearer test-token"}


class FakeProvider:
    """A local HTTP server with one path prefix per protocol, plus /fail for error mapping."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.delay = 0.0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # keep pytest output clean
                pass

            def do_GET(self) -> None:
                outer._handle(self)

            def do_POST(self) -> None:
                outer._handle(self)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeProvider":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def paths(self) -> list[str]:
        return [call["path"] for call in self.calls]

    def _handle(self, request) -> None:
        length = int(request.headers.get("content-length") or 0)
        raw = request.rfile.read(length) if length else b""
        body = json.loads(raw) if raw else None
        self.calls.append(
            {
                "method": request.command,
                "path": request.path,
                "headers": {k.lower(): v for k, v in request.headers.items()},
                "body": body,
            }
        )
        if self.delay:
            time.sleep(self.delay)
        status, payload = self._respond(request.path.split("?", 1)[0])
        data = json.dumps(payload).encode()
        request.send_response(status)
        request.send_header("content-type", "application/json")
        request.send_header("content-length", str(len(data)))
        request.end_headers()
        request.wfile.write(data)

    @staticmethod
    def _respond(path: str) -> tuple[int, dict]:
        # Called without the query string; assertions still see it in calls[].path.
        if "/fail/" in path:
            return 401, {"error": {"message": "invalid api key"}}
        if "/badjson/" in path:
            return 200, {"unexpected": True}
        protocol = path.split("/")[1]
        if protocol == "openai":
            if path.endswith("/chat/completions"):
                return 200, {"choices": [{"message": {"content": " pong "}}]}
            if path.endswith("/embeddings"):
                return 200, {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
            if path.endswith("/models"):
                return 200, {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4.1"}]}
        if protocol == "anthropic":
            if path.endswith("/messages"):
                return 200, {"content": [{"type": "text", "text": "pong"}]}
            if path.endswith("/models"):
                return 200, {"data": [{"id": "claude-3-5-haiku"}]}
        if protocol == "gemini":
            if ":generateContent" in path:
                return 200, {"candidates": [{"content": {"parts": [{"text": "pong"}]}}]}
            if ":embedContent" in path:
                return 200, {"embedding": {"values": [0.1, 0.2, 0.3]}}
            if path.endswith("/models"):
                return 200, {"models": [{"name": "models/gemini-2.5-flash"}]}
        return 404, {"error": {"message": f"no fake route for {path}"}}


@pytest.fixture()
def fake():
    with FakeProvider() as server:
        yield server


@pytest.fixture()
def app(test_env):
    import importlib

    import memory_mcp.server as server

    importlib.reload(server)
    return server.app


@pytest.fixture()
def console(app) -> TestClient:
    """A signed-in console (admin password set)."""
    c = TestClient(app, base_url=ORIGIN)
    assert c.post("/api/v1/console/login", json={"token": "test-token"}, headers=AUTH).status_code == 200
    assert c.put("/api/v1/console/password", json={"new_password": "pw"}, headers=AUTH).status_code == 200
    return c


def _create(console: TestClient, name: str, protocol: str, base_url: str, api_key: str = "sk-secret-1234") -> dict:
    res = console.post(
        "/api/v1/providers",
        json={"name": name, "protocol": protocol, "base_url": base_url, "api_key": api_key},
        headers=AUTH,
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


# ---- the three protocols ----------------------------------------------------
def test_openai_chat_turns_reasoning_off_and_returns_text(test_env, fake):
    from memory_mcp import providers
    from memory_mcp.engine import model_client

    async def run() -> tuple[dict, str, str]:
        saved = await providers.create_provider("local", "openai", f"{fake.url}/openai/v1", "sk-test")
        provider = await providers.resolve(saved["id"])
        plain = await model_client.chat(provider, "gpt-4o-mini", "ping")
        as_json = await model_client.chat(provider, "gpt-4o-mini", "ping", json_mode=True)
        rows = {p["id"]: p for p in await providers.list_providers()}
        return saved, plain, as_json, rows[saved["id"]]

    saved, plain, as_json, row = anyio.run(run)
    assert (plain, as_json) == ("pong", "pong")

    plain_call, json_call = fake.calls[-2], fake.calls[-1]
    assert plain_call["path"] == "/openai/v1/chat/completions"
    assert plain_call["headers"]["authorization"] == "Bearer sk-test"
    assert plain_call["body"] == {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "ping"}],
        "reasoning": {"enabled": False},
    }
    assert json_call["body"]["response_format"] == {"type": "json_object"}
    assert row["last_call_ok"] is True


def test_anthropic_chat_uses_its_headers_and_a_json_instruction(test_env, fake):
    from memory_mcp import providers
    from memory_mcp.engine import model_client

    async def run() -> str:
        saved = await providers.create_provider("claude", "anthropic", f"{fake.url}/anthropic/v1", "sk-ant")
        provider = await providers.resolve(saved["id"])
        return await model_client.chat(provider, "claude-3-5-haiku", "ping", json_mode=True)

    assert anyio.run(run) == "pong"
    call = fake.calls[-1]
    assert call["path"] == "/anthropic/v1/messages"
    assert call["headers"]["x-api-key"] == "sk-ant"
    assert call["headers"]["anthropic-version"] == "2023-06-01"
    assert call["body"]["messages"] == [{"role": "user", "content": "ping"}]
    assert "JSON" in call["body"]["system"]
    assert "reasoning" not in call["body"]


def test_gemini_chat_sends_thinking_budget_and_json_mime_type(test_env, fake):
    from memory_mcp import providers
    from memory_mcp.engine import model_client

    async def run() -> str:
        saved = await providers.create_provider("gem", "gemini", f"{fake.url}/gemini/v1beta", "g-key")
        provider = await providers.resolve(saved["id"])
        return await model_client.chat(provider, "gemini-2.5-flash", "ping", json_mode=True)

    assert anyio.run(run) == "pong"
    call = fake.calls[-1]
    assert call["path"].startswith("/gemini/v1beta/models/gemini-2.5-flash:generateContent")
    assert "key=g-key" in call["path"]
    assert call["body"]["generationConfig"] == {
        "temperature": 0,
        "responseMimeType": "application/json",
        "thinkingConfig": {"thinkingBudget": 0},
    }


def test_older_gemini_models_do_not_get_a_thinking_budget(test_env, fake):
    from memory_mcp import providers
    from memory_mcp.engine import model_client

    async def run() -> str:
        saved = await providers.create_provider("gem", "gemini", f"{fake.url}/gemini/v1beta", "g-key")
        provider = await providers.resolve(saved["id"])
        return await model_client.chat(provider, "gemini-1.5-flash", "ping")

    assert anyio.run(run) == "pong"
    assert "thinkingConfig" not in fake.calls[-1]["body"]["generationConfig"]


def test_embeddings_on_openai_and_gemini_but_not_anthropic(test_env, fake):
    from memory_mcp import providers
    from memory_mcp.engine import model_client

    async def run() -> tuple[list[float], list[float], dict]:
        openai = await providers.create_provider("o", "openai", f"{fake.url}/openai/v1", "sk-o")
        gemini = await providers.create_provider("g", "gemini", f"{fake.url}/gemini/v1beta", "g-key")
        first = await model_client.embed(await providers.resolve(openai["id"]), "text-embedding-3-small", "hello")
        second = await model_client.embed(await providers.resolve(gemini["id"]), "text-embedding-004", "hello")
        anthropic = await providers.create_provider("a", "anthropic", f"{fake.url}/anthropic/v1", "sk-a")
        with pytest.raises(model_client.ProviderCallError, match="embedding"):
            await model_client.embed(await providers.resolve(anthropic["id"]), "claude-3-5-haiku", "hello")
        rows = {p["id"]: p for p in await providers.list_providers()}
        return first, second, rows[anthropic["id"]]

    first, second, anthropic_row = anyio.run(run)
    assert first == second == [0.1, 0.2, 0.3]
    assert fake.calls[0]["body"] == {"model": "text-embedding-3-small", "input": "hello"}
    assert ":embedContent" in fake.calls[1]["path"]
    # Nothing was attempted, so the provider's last call status stays empty.
    assert anthropic_row["last_call_at"] is None and anthropic_row["last_call_ok"] is None


def test_model_lists_are_normalised_per_protocol(test_env, fake):
    from memory_mcp import providers
    from memory_mcp.engine import model_client

    async def run() -> dict[str, list[str]]:
        lists = {}
        for name, protocol, path in (
            ("o", "openai", "openai/v1"),
            ("a", "anthropic", "anthropic/v1"),
            ("g", "gemini", "gemini/v1beta"),
        ):
            saved = await providers.create_provider(name, protocol, f"{fake.url}/{path}", "k")
            lists[protocol] = await model_client.list_models(await providers.resolve(saved["id"]))
        return lists

    lists = anyio.run(run)
    assert lists == {
        "openai": ["gpt-4o-mini", "gpt-4.1"],
        "anthropic": ["claude-3-5-haiku"],
        # Gemini answers with resource names; the client strips the "models/" prefix.
        "gemini": ["gemini-2.5-flash"],
    }


# ---- error mapping and last call status -------------------------------------
def test_http_timeout_and_connection_errors_are_readable_and_recorded(test_env, fake):
    from memory_mcp import providers
    from memory_mcp.engine import model_client

    with socket.socket() as sock:  # a port nothing listens on
        sock.bind(("127.0.0.1", 0))
        closed_port = sock.getsockname()[1]

    async def run() -> tuple[str, str, str, dict]:
        failing = await providers.create_provider("bad", "openai", f"{fake.url}/fail/v1", "sk-bad")
        with pytest.raises(model_client.ProviderCallError) as http:
            await model_client.chat(await providers.resolve(failing["id"]), "m", "ping")
        slow = await providers.create_provider("slow", "openai", f"{fake.url}/openai/v1", "sk-slow")
        fake.delay = 0.5
        with pytest.raises(model_client.ProviderCallError) as timeout:
            await model_client.chat(await providers.resolve(slow["id"]), "m", "ping", timeout=0.1)
        fake.delay = 0
        gone = await providers.create_provider("gone", "openai", f"http://127.0.0.1:{closed_port}/v1", "sk-gone")
        with pytest.raises(model_client.ProviderCallError) as refused:
            await model_client.chat(await providers.resolve(gone["id"]), "m", "ping")
        rows = {p["id"]: p for p in await providers.list_providers()}
        return str(http.value), str(timeout.value), str(refused.value), rows[failing["id"]]

    http_error, timeout_error, refused_error, row = anyio.run(run)
    assert http_error.startswith("HTTP 401") and "invalid api key" in http_error
    assert "超时" in timeout_error
    assert "连接失败" in refused_error
    assert row["last_call_ok"] is False
    assert row["last_call_error"].startswith("对话：HTTP 401")
    assert row["last_call_at"] is not None


def test_a_malformed_response_names_the_missing_field(test_env, fake):
    from memory_mcp import providers
    from memory_mcp.engine import model_client

    async def run() -> str:
        # A 200 whose body lacks the expected field must say which field, not fail as a KeyError.
        saved = await providers.create_provider("o", "openai", f"{fake.url}/badjson/v1", "k")
        with pytest.raises(model_client.ProviderCallError) as exc:
            await model_client.chat(await providers.resolve(saved["id"]), "m", "ping")
        return str(exc.value)

    assert "choices[0].message.content" in anyio.run(run)


# ---- keys at rest -----------------------------------------------------------
def test_keys_are_encrypted_at_rest_and_never_returned(app, console, test_env):
    from memory_mcp import providers
    from memory_mcp.config import settings

    created = _create(console, "prod", "openai", "https://api.example.com/v1", "sk-plain-secret-1234")
    assert created["api_key_last4"] == "1234"
    assert "api_key" not in created and "sk-plain-secret-1234" not in json.dumps(created)

    for path in Path(settings.data_dir).glob("memory.sqlite3*"):
        assert b"sk-plain-secret-1234" not in path.read_bytes(), path

    con = sqlite3.connect(settings.sqlite_path)
    try:
        cipher = con.execute("SELECT api_key_cipher FROM providers WHERE id = ?", (created["id"],)).fetchone()[0]
    finally:
        con.close()
    assert cipher and cipher != "sk-plain-secret-1234"
    assert providers.decrypt(cipher, created["id"]) == "sk-plain-secret-1234"

    # The data key is owner-only, and losing it is the documented restore risk.
    key_file = Path(settings.data_dir) / providers.KEY_FILE
    assert key_file.exists() and (key_file.stat().st_mode & 0o077) == 0


def test_the_console_lists_the_key_only_by_its_last_four(app, console):
    _create(console, "prod", "openai", "https://api.example.com/v1", "sk-plain-secret-1234")
    res = console.get("/api/v1/providers", headers=AUTH)
    assert res.status_code == 200, res.text
    items = res.json()["data"]["items"]
    assert "sk-plain-secret-1234" not in res.text
    prod = next(item for item in items if item["name"] == "prod")
    assert prod["api_key_last4"] == "1234" and prod["has_key"] is True


# ---- console management -----------------------------------------------------
def test_create_validation_and_unique_names(app, console):
    res = console.post(
        "/api/v1/providers",
        json={"name": "x", "protocol": "bedrock", "base_url": "https://a/v1", "api_key": "k"},
        headers=AUTH,
    )
    assert res.status_code == 400 and "协议" in res.json()["error"]

    for body in (
        {"name": "", "protocol": "openai", "base_url": "https://a/v1", "api_key": "k"},
        {"name": "n", "protocol": "openai", "base_url": "ftp://a", "api_key": "k"},
        {"name": "n", "protocol": "openai", "base_url": "https://a/v1", "api_key": ""},
    ):
        assert console.post("/api/v1/providers", json=body, headers=AUTH).status_code == 400

    _create(console, "taken", "openai", "https://a/v1")
    res = console.post(
        "/api/v1/providers",
        json={"name": "taken", "protocol": "openai", "base_url": "https://b/v1", "api_key": "k"},
        headers=AUTH,
    )
    assert res.status_code == 409 and "已被使用" in res.json()["error"]


def test_update_replaces_the_key_without_reading_the_old_one(app, console):
    created = _create(console, "prod", "openai", "https://a/v1", "sk-old-1111")
    res = console.put(f"/api/v1/providers/{created['id']}", json={"api_key": "sk-new-2222"}, headers=AUTH)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["api_key_last4"] == "2222" and data["base_url"] == "https://a/v1"

    # A console provider always has an address and a key; only the file provider can revert.
    assert console.put(f"/api/v1/providers/{created['id']}", json={"api_key": None}, headers=AUTH).status_code == 400
    assert console.put(f"/api/v1/providers/{created['id']}", json={"base_url": None}, headers=AUTH).status_code == 400
    assert console.put("/api/v1/providers/nope", json={"name": "z"}, headers=AUTH).status_code == 404


def test_the_file_provider_is_overridable_and_revertible_but_not_deletable(app, console, monkeypatch):
    from memory_mcp import providers

    monkeypatch.setattr(providers.settings, "openrouter_base_url", "https://openrouter.ai/api/v1")

    listing = {item["id"]: item for item in console.get("/api/v1/providers", headers=AUTH).json()["data"]["items"]}
    file_provider = listing["file"]
    assert (file_provider["source"], file_provider["deletable"]) == ("file", False)
    assert file_provider["base_url"] == "https://openrouter.ai/api/v1"
    assert file_provider["overridden"] == {"base_url": False, "api_key": False}

    res = console.put("/api/v1/providers/file", json={"base_url": "https://proxy.local/v1"}, headers=AUTH)
    assert res.status_code == 200 and res.json()["data"]["base_url"] == "https://proxy.local/v1"
    assert res.json()["data"]["overridden"]["base_url"] is True

    res = console.put("/api/v1/providers/file", json={"base_url": None, "api_key": None}, headers=AUTH)
    assert res.status_code == 200
    assert res.json()["data"]["base_url"] == "https://openrouter.ai/api/v1"
    assert res.json()["data"]["overridden"] == {"base_url": False, "api_key": False}

    # Its protocol stays OpenAI-compatible: the embedding role depends on it.
    assert console.put("/api/v1/providers/file", json={"protocol": "anthropic"}, headers=AUTH).status_code == 400
    assert console.delete("/api/v1/providers/file", headers=AUTH).status_code == 409


def test_console_providers_can_be_deleted(app, console):
    created = _create(console, "temp", "openai", "https://a/v1")
    assert console.delete(f"/api/v1/providers/{created['id']}", headers=AUTH).status_code == 200
    assert all(item["id"] != created["id"] for item in console.get("/api/v1/providers", headers=AUTH).json()["data"]["items"])
    assert console.delete(f"/api/v1/providers/{created['id']}", headers=AUTH).status_code == 404


def test_test_endpoint_returns_a_result_instead_of_failing_the_request(app, console, fake):
    res = console.post(
        "/api/v1/providers/test",
        json={"protocol": "openai", "base_url": f"{fake.url}/openai/v1", "api_key": "sk-x"},
        headers=AUTH,
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"] == {"ok": True, "models": 2, "sample": ["gpt-4o-mini", "gpt-4.1"]}

    res = console.post(
        "/api/v1/providers/test",
        json={"protocol": "openai", "base_url": f"{fake.url}/fail/v1", "api_key": "sk-x"},
        headers=AUTH,
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["ok"] is False and "HTTP 401" in body["error"] and body["models"] == 0

    # Without an api_key the saved provider supplies it, so editing does not need the old key.
    created = _create(console, "saved", "openai", f"{fake.url}/openai/v1", "sk-saved")
    res = console.post("/api/v1/providers/test", json={"id": created["id"]}, headers=AUTH)
    assert res.json()["data"]["ok"] is True
    assert fake.calls[-1]["headers"]["authorization"] == "Bearer sk-saved"


def test_model_list_endpoint(app, console, fake):
    created = _create(console, "saved", "openai", f"{fake.url}/openai/v1")
    res = console.get(f"/api/v1/providers/{created['id']}/models", headers=AUTH)
    assert res.status_code == 200 and res.json()["data"]["items"] == ["gpt-4o-mini", "gpt-4.1"]

    broken = _create(console, "broken", "openai", f"{fake.url}/fail/v1")
    res = console.get(f"/api/v1/providers/{broken['id']}/models", headers=AUTH)
    assert res.status_code == 502 and "HTTP 401" in res.json()["error"]
    assert console.get("/api/v1/providers/nope/models", headers=AUTH).status_code == 404


def test_provider_management_accepts_only_a_console_session(app, console):
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/providers", headers=BEARER).status_code == 403
    client = TestClient(app, base_url=ORIGIN)
    assert client.get("/api/v1/providers").status_code == 401


# ---- the write path and embeddings go through the file provider -------------
def test_remembers_chat_and_embeddings_use_the_configuration_provider(test_env, fake, monkeypatch):
    from memory_mcp import providers
    from memory_mcp.config import settings
    from memory_mcp.engine import llm, model_client

    monkeypatch.setattr(settings, "openrouter_base_url", f"{fake.url}/openai/v1")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-from-file")

    async def run() -> tuple[str, list[float], dict]:
        # test_env replaces embedding_service.get_embedding, so reach the client through the same
        # provider and model the service resolves (settings.embedding_model).
        text = await llm.chat("ping")
        vector = await model_client.embed(await providers.resolve(providers.FILE_PROVIDER), settings.embedding_model, "hello")
        file_row = next(p for p in await providers.list_providers() if p["id"] == "file")
        return text, vector, file_row

    text, vector, file_row = anyio.run(run)
    assert text == "pong" and vector == [0.1, 0.2, 0.3]
    assert fake.calls[0]["headers"]["authorization"] == "Bearer sk-from-file"
    assert fake.calls[1]["body"]["model"] == "test-embedding"
    assert file_row["last_call_ok"] is True
