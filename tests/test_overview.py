"""Overview and maintenance history (issue #16): one snapshot, and past rounds."""
import importlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

ORIGIN = "https://testserver"
AUTH = {"Origin": ORIGIN}
BEARER = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def app(test_env):
    import memory_mcp.server as server

    importlib.reload(server)
    return server.app


@pytest.fixture()
def console(app) -> TestClient:
    c = TestClient(app, base_url=ORIGIN)
    assert c.post("/api/v1/console/login", json={"token": "test-token"}, headers=AUTH).status_code == 200
    assert c.put("/api/v1/console/password", json={"new_password": "pw"}, headers=AUTH).status_code == 200
    return c


def _now(days: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def seed(test_env) -> None:
    config, _, _ = test_env
    con = sqlite3.connect(config.settings.sqlite_path)
    try:
        with con:
            for mid, key, mutation, created, current in (
                ("m-old", "fact:old", "initial", _now(40), 0),
                ("m-new", "fact:new", "initial", _now(3), 1),
                ("m-merge", "fact:merged", "update", _now(10), 1),
                ("m-stale", "fact:stale", "initial", _now(400), 1),
            ):
                con.execute(
                    "INSERT INTO memories (id, entity_key, entity_type, content, mutation_type, created_at, valid_from, "
                    "is_current) VALUES (?, ?, 'fact', ?, ?, ?, ?, ?)",
                    (mid, key, f"content of {mid}", mutation, created, created, current),
                )
            for i, (kind, status) in enumerate((
                ("duplicate", "open"),
                ("duplicate", "open"),
                ("internal_contradiction", "open"),
                ("multiple_current", "dismissed"),
            )):
                con.execute(
                    "INSERT INTO memory_findings (id, kind, memory_id, detail, status, created_at) "
                    "VALUES (?, ?, 'm-new', 'detail', ?, ?)",
                    (f"f-{i}", kind, status, _now(1)),
                )
            con.execute(
                "INSERT INTO jobs (id, job_type, payload, status, scheduled_at, started_at, finished_at, created_at) "
                "VALUES ('job-1', 'maintenance', ?, 'done', ?, ?, ?, ?)",
                (json.dumps({"llm_calls": 12, "duplicate": 3}), _now(1), _now(1), _now(1), _now(1)),
            )
            con.execute(
                "INSERT INTO jobs (id, job_type, payload, status, scheduled_at, started_at, finished_at, created_at) "
                "VALUES ('job-2', 'maintenance', '{}', 'failed', ?, ?, ?, ?)",
                (_now(2), _now(2), _now(2), _now(2)),
            )
            # Daily statistics and a provider call, as a recall and a failed call would leave them.
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for token, kind, latency in (("initial", "recall", 12.0), ("", "recall", 30.0), ("initial", "write", None)):
                con.execute(
                    "INSERT INTO daily_events (day, token, kind, latency_ms) VALUES (?, ?, ?, ?)",
                    (today, token, kind, latency),
                )
            con.execute(
                "UPDATE providers SET last_call_at = ?, last_call_ok = 0, last_call_error = ? WHERE id = 'file'",
                (_now(0), "对话：HTTP 401"),
            )
    finally:
        con.close()


def test_overview_snapshot_counts_everything_once(console, test_env):
    seed(test_env)

    res = console.get("/api/v1/overview", headers=AUTH)
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    assert data["findings"] == [{"kind": "duplicate", "count": 2}, {"kind": "internal_contradiction", "count": 1}]
    assert data["memories"] == {"total": 3, "new_7d": 1, "evolved_7d": 0, "new_30d": 1, "evolved_30d": 1}
    assert data["schedule"].startswith("每天 04:17")

    # The newest round first, with its statistics and duration.
    assert data["last_round"]["id"] == "job-1"
    assert data["last_round"]["stats"] == {"llm_calls": 12, "duplicate": 3}
    assert data["last_round"]["duration_ms"] == 0

    file_provider = next(p for p in data["providers"] if p["id"] == "file")
    assert file_provider["last_call_ok"] is False and "HTTP 401" in file_provider["last_call_error"]

    # Stalest first, current memories only.
    assert [m["memory_id"] for m in data["stalest"]] == ["m-stale", "m-merge", "m-new"]

    assert data["tokens"][0]["name"] == "initial" and data["tokens"][0]["revoked_at"] is None

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = {(r["day"], r["token"]): r for r in data["daily"]}
    assert rows[(today, "initial")]["recalls"] == 1 and rows[(today, "initial")]["writes"] == 1
    assert rows[(today, "")]["recalls"] == 1 and rows[(today, "")]["median_latency_ms"] == 30.0


def test_rounds_are_listed_newest_first_with_a_limit(console, test_env):
    seed(test_env)
    res = console.get("/api/v1/overview/rounds", headers=AUTH)
    assert res.status_code == 200, res.text
    items = res.json()["data"]["items"]
    assert [r["id"] for r in items] == ["job-1", "job-2"]
    assert items[1]["status"] == "failed"

    assert len(console.get("/api/v1/overview/rounds", params={"limit": 1}, headers=AUTH).json()["data"]["items"]) == 1
    assert console.get("/api/v1/overview/rounds", params={"limit": 0}, headers=AUTH).status_code == 400
    assert console.get("/api/v1/overview/rounds", params={"limit": "x"}, headers=AUTH).status_code == 400


def test_overview_accepts_only_a_console_session(app):
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/overview", headers=BEARER).status_code == 403
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/overview").status_code == 401
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/overview/rounds").status_code == 401
