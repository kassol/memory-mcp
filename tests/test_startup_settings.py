"""Startup settings (issue #14, docs/adr/0002): draft, check, apply, restart and fallback.

The API tests run in process. The restart tests spawn the real service in a subprocess, because the
whole point is that the process exits with a dedicated code and the next start behaves differently.
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

ORIGIN = "https://testserver"
AUTH = {"Origin": ORIGIN}
BEARER = {"Authorization": "Bearer test-token"}
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def app(test_env):
    import importlib

    import memory_mcp.server as server

    importlib.reload(server)
    return server.app


@pytest.fixture()
def console(app) -> TestClient:
    c = TestClient(app, base_url=ORIGIN)
    assert c.post("/api/v1/console/login", json={"token": "test-token"}, headers=AUTH).status_code == 200
    assert c.put("/api/v1/console/password", json={"new_password": "pw"}, headers=AUTH).status_code == 200
    return c


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def startup_files(directory: str | Path) -> tuple[Path, Path, Path]:
    root = Path(directory)
    return root / "startup-settings.json", root / "startup-settings.pending.json", root / "startup-apply.json"


# ---- the console API, in process -------------------------------------------
def test_describe_lists_effective_values_the_draft_and_what_is_editable(console, monkeypatch, test_env):
    import memory_mcp.startup as startup

    config, _, _ = test_env
    monkeypatch.setattr(startup, "inside_container", lambda: False)
    data = console.get("/api/v1/startup-settings", headers=AUTH).json()["data"]
    assert data["container"] is False and data["read_only"] == {}
    assert data["editable"] == ["port", "data_dir", "vector_backend", "debug"]
    assert data["effective"]["vector_backend"] == "memory"
    assert data["effective"]["port"] == config.settings.port
    assert data["draft"] == {} and data["last_apply"] is None
    assert data["defaults"]["port"] == 8765


def test_inside_a_container_port_and_data_directory_are_read_only(console, monkeypatch):
    import memory_mcp.startup as startup

    monkeypatch.setattr(startup, "inside_container", lambda: True)
    data = console.get("/api/v1/startup-settings", headers=AUTH).json()["data"]
    assert data["container"] is True
    assert set(data["read_only"]) == {"port", "data_dir"}
    assert data["editable"] == ["vector_backend", "debug"]

    res = console.put("/api/v1/startup-settings", json={"port": 9000}, headers=AUTH)
    assert res.status_code == 400 and "容器编排" in res.json()["error"]


def test_draft_validation(console):
    for body, expected in (
        ({"port": 0}, "端口"),
        ({"port": "abc"}, "整数"),
        ({"vector_backend": "faiss"}, "向量后端"),
        ({"debug": "yes"}, "调试日志"),
        ({"embedding_dim": 7}, "只在配置文件里改"),
        ({"nonsense": 1}, "不是启动设置"),
        ({}, "没有要保存的启动设置"),
    ):
        res = console.put("/api/v1/startup-settings", json=body, headers=AUTH)
        assert res.status_code == 400, body
        assert expected in res.json()["error"], res.text


def test_a_bad_draft_is_reported_by_check_and_refused_by_apply(console, test_env):
    import memory_mcp.startup as startup

    config, _, _ = test_env
    override, _, apply_state = startup_files(config.settings.data_dir)
    console.put("/api/v1/startup-settings", json={"data_dir": "/nonexistent/memory"}, headers=AUTH)

    problems = console.post("/api/v1/startup-settings/check", headers=AUTH).json()["data"]
    assert problems["ok"] is False
    assert any("数据目录不存在" in p for p in problems["problems"])

    res = console.post("/api/v1/startup-settings/apply", headers=AUTH)
    assert res.status_code == 400 and "数据目录不存在" in res.json()["error"]
    assert not override.exists() and not apply_state.exists()


def test_apply_writes_the_override_and_the_marker_then_marks_it_applied(console, test_env):
    import memory_mcp.startup as startup

    config, _, _ = test_env
    override, pending, apply_state = startup_files(config.settings.data_dir)

    console.put("/api/v1/startup-settings", json={"debug": True}, headers=AUTH)
    assert pending.exists()
    res = console.post("/api/v1/startup-settings/check", headers=AUTH).json()["data"]
    assert res == {"ok": True, "problems": []}

    res = console.post("/api/v1/startup-settings/apply", headers=AUTH)
    assert res.status_code == 202, res.text
    assert res.json()["data"]["applying"] is True
    assert json.loads(override.read_text()) == {"debug": True}
    assert not pending.exists()
    marker = json.loads(apply_state.read_text())
    assert marker["status"] == "pending" and marker["previous"] == {}

    # The next start reaching a healthy service marks it applied.
    startup.mark_healthy()
    listed = console.get("/api/v1/startup-settings", headers=AUTH).json()["data"]
    assert listed["last_apply"]["status"] == "applied" and listed["last_apply"]["requested"] == {"debug": True}
    assert listed["draft"] == {}


def test_clearing_the_draft_changes_nothing(console, test_env):
    import memory_mcp.startup as startup

    config, _, _ = test_env
    override, pending, _ = startup_files(config.settings.data_dir)
    console.put("/api/v1/startup-settings", json={"debug": True}, headers=AUTH)
    res = console.delete("/api/v1/startup-settings", headers=AUTH)
    assert res.status_code == 200 and res.json()["data"]["draft"] == {}
    assert not pending.exists() and not override.exists()


def test_startup_settings_accept_only_a_console_session(app):
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/startup-settings", headers=BEARER).status_code == 403
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/startup-settings").status_code == 401


# ---- the real process: restart and fallback --------------------------------
def _env(data_dir: Path, port: int) -> dict:
    return {
        **os.environ,
        "MEMORY_MCP_AUTH_TOKEN": "test-token",
        "MEMORY_MCP_OPENROUTER_API_KEY": "test-key",
        "MEMORY_MCP_DATA_DIR": str(data_dir),
        "MEMORY_MCP_EMBEDDING_DIM": "3",
        "MEMORY_MCP_EMBEDDING_MODEL": "test-embedding",
        "MEMORY_MCP_VECTOR_BACKEND": "memory",
        "MEMORY_MCP_AUTO_MIGRATE": "true",
        "MEMORY_MCP_PORT": str(port),
        "PYTHONPATH": str(ROOT / "src"),
    }


def _spawn(data_dir: Path, port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "memory_mcp"],
        cwd=ROOT,
        env=_env(data_dir, port),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _await_healthy(port: int, timeout: float = 40.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise AssertionError(f"service on port {port} did not become healthy")


def _signed_in(port: int) -> httpx.Client:
    """Sign in over plain http: the session cookie is Secure, so httpx needs it sent by hand.

    The first start bootstraps the admin password from the access token; later starts use it.
    """
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", headers={"Origin": f"http://127.0.0.1:{port}"}, timeout=10.0)
    login = client.post("/api/v1/console/login", json={"password": "pw"})
    if login.status_code != 200:
        login = client.post("/api/v1/console/login", json={"token": "test-token"})
        assert login.status_code == 200, login.text
        client.headers["Cookie"] = login.headers["set-cookie"].split(";")[0]
        assert client.put("/api/v1/console/password", json={"new_password": "pw"}).status_code == 200
        return client
    client.headers["Cookie"] = login.headers["set-cookie"].split(";")[0]
    return client


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover - only on a stuck process
            proc.kill()


def test_apply_exits_with_the_dedicated_code_and_the_next_start_uses_the_values(test_env, tmp_path):
    import memory_mcp.lifecycle as lifecycle

    config, _, _ = test_env
    data_dir = Path(config.settings.data_dir)
    port = free_port()

    proc = _spawn(data_dir, port)
    try:
        _await_healthy(port)
        client = _signed_in(port)
        try:
            res = client.put("/api/v1/startup-settings", json={"debug": True})
            assert res.status_code == 200, res.text
            assert client.post("/api/v1/startup-settings/check").json()["data"]["ok"] is True
            assert client.post("/api/v1/startup-settings/apply").status_code == 202
        finally:
            client.close()

        # The process stops serving and exits with the code the restart policy reacts to.
        assert proc.wait(timeout=60) == lifecycle.EXIT_CODE, proc.stdout.read() if proc.stdout else ""
    finally:
        _stop(proc)

    proc = _spawn(data_dir, port)
    try:
        _await_healthy(port)
        client = _signed_in(port)
        try:
            data = client.get("/api/v1/startup-settings").json()["data"]
            assert data["effective"]["debug"] is True
            assert data["overrides"] == {"debug": True}
            assert data["last_apply"]["status"] == "applied"
            assert data["draft"] == {}
        finally:
            client.close()
    finally:
        _stop(proc)


def test_a_start_that_never_becomes_healthy_restores_the_previous_settings(test_env):
    config, _, _ = test_env
    data_dir = Path(config.settings.data_dir)
    port = free_port()

    # An apply whose restart cannot come up: the data directory became unusable after the check.
    blocker = data_dir / "blocker"
    blocker.write_text("not a directory")
    bad_dir = str(blocker / "data")
    override, _, apply_state = startup_files(data_dir)
    override.write_text(json.dumps({"data_dir": bad_dir}))
    apply_state.write_text(
        json.dumps(
            {
                "status": "pending",
                "attempts": 0,
                "requested": {"data_dir": bad_dir},
                "previous": {},
                "at": "2026-11-01T00:00:00+00:00",
            }
        )
    )
    failed = _spawn(data_dir, port)
    assert failed.wait(timeout=60) != 0

    proc = _spawn(data_dir, port)
    try:
        _await_healthy(port)
        client = _signed_in(port)
        try:
            data = client.get("/api/v1/startup-settings").json()["data"]
            # Back on the configured port, the override is gone, and the reason is recorded.
            assert data["effective"]["port"] == port
            assert data["overrides"] == {}
            assert data["last_apply"]["status"] == "failed"
            assert "未能启动" in data["last_apply"]["reason"]
        finally:
            client.close()
    finally:
        _stop(proc)
