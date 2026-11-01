"""Recall log and daily statistics (issue #15) over the full HTTP app.

A recall always counts in the daily statistics; the log entry — query, token, latency, top memory
ids — appears only while the setting is on. Pruning and clearing are covered directly.
"""
import importlib
import sqlite3
from datetime import datetime, timedelta, timezone

import anyio
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


@pytest.fixture()
def api(app) -> TestClient:
    """A client with an access token: agents write and recall through this."""
    return TestClient(app, base_url=ORIGIN)


def remember(c: TestClient, content: str) -> dict:
    res = c.post(
        "/api/v1/memories",
        json={"content": content, "entity_key": f"fact:{content}", "entity_type": "fact"},
        headers=BEARER,
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def recall(c: TestClient, query: str, limit: int = 10) -> dict:
    res = c.get("/api/v1/memories/search", params={"query": query, "limit": limit}, headers=BEARER)
    assert res.status_code == 200, res.text
    return res.json()["data"]


def log(console: TestClient, **params) -> dict:
    res = console.get("/api/v1/recall-log", params=params, headers=AUTH)
    assert res.status_code == 200, res.text
    return res.json()["data"]


def daily(console: TestClient, days: int = 30) -> list[dict]:
    res = console.get("/api/v1/recall-log/daily", params={"days": days}, headers=AUTH)
    assert res.status_code == 200, res.text
    return res.json()["data"]["items"]


def insert_event(day: str, token: str, kind: str, latency: float | None = None) -> None:
    from memory_mcp.config import settings

    con = sqlite3.connect(settings.sqlite_path)
    try:
        with con:
            con.execute(
                "INSERT INTO daily_events (day, token, kind, latency_ms) VALUES (?, ?, ?, ?)",
                (day, token, kind, latency),
            )
    finally:
        con.close()


def insert_log_entry(at: str, query: str = "old") -> None:
    from memory_mcp.config import settings

    con = sqlite3.connect(settings.sqlite_path)
    try:
        with con:
            con.execute(
                "INSERT INTO recall_log (id, at, token, query, latency_ms, results, memory_ids) "
                "VALUES (?, ?, 'initial', ?, 1.0, 0, '[]')",
                (f"old-{at}", at, query),
            )
    finally:
        con.close()


# ---- what a recall records --------------------------------------------------
def test_a_recall_writes_a_log_entry_and_a_daily_event(app, console, api):
    remember(api, "Prefers Zed")
    result = recall(api, "editor")
    assert result["total"] >= 1

    entry = log(console)["items"][0]
    assert entry["query"] == "editor"
    assert entry["token"] == "initial"
    assert entry["results"] == result["total"]
    assert entry["latency_ms"] >= 0
    assert [mid for mid in entry["memory_ids"]] == [r["memory_id"] for r in result["results"][:3]]
    assert entry["at"].startswith(datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    today = daily(console)[0]
    assert (today["recalls"], today["writes"], today["token"]) == (1, 1, "initial")
    assert today["median_latency_ms"] is not None


def test_only_the_first_three_memory_ids_are_kept(app, console, api):
    for i in range(5):
        remember(api, f"Fact number {i} about editors")
    result = recall(api, "editors", limit=5)
    assert result["total"] == 5
    entry = log(console)["items"][0]
    assert entry["results"] == 5
    assert entry["memory_ids"] == [r["memory_id"] for r in result["results"][:3]]


def test_the_log_holds_fifty_entries_by_default_and_pages(app, console, api):
    for i in range(3):
        recall(api, f"query {i}")
    page = log(console)
    assert page["total"] == 3 and [e["query"] for e in page["items"]] == ["query 2", "query 1", "query 0"]

    second = log(console, limit=1, offset=1)
    assert second["total"] == 3 and [e["query"] for e in second["items"]] == ["query 1"]


# ---- the setting and clearing -----------------------------------------------
def test_turning_logging_off_stops_entries_but_not_statistics(app, console, api):
    res = console.put("/api/v1/settings/recall_log_enabled", json={"value": False}, headers=AUTH)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["type"] == "bool" and res.json()["data"]["value"] is False

    recall(api, "editor")
    assert log(console)["total"] == 0
    assert daily(console)[0]["recalls"] == 1

    assert console.put("/api/v1/settings/recall_log_enabled", json={"value": True}, headers=AUTH).status_code == 200
    recall(api, "editor again")
    assert log(console)["total"] == 1


def test_clearing_removes_entries_and_keeps_the_statistics(app, console, api):
    remember(api, "Prefers Zed")
    recall(api, "editor")
    before = daily(console)[0]["recalls"]
    assert before == 1

    res = console.delete("/api/v1/recall-log", headers=AUTH)
    assert res.status_code == 200 and res.json()["data"]["deleted"] == 1
    assert log(console)["total"] == 0
    assert daily(console)[0]["recalls"] == before


def test_daily_statistics_group_by_day_and_token_and_report_the_median(app, console, api):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    insert_event(today, "laptop", "write")
    insert_event(today, "laptop", "recall", 10.0)
    insert_event(today, "laptop", "recall", 30.0)
    insert_event(today, "ci", "recall", 100.0)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    insert_event(yesterday, "laptop", "recall", 20.0)

    rows = {(r["day"], r["token"]): r for r in daily(console)}
    assert (rows[(today, "laptop")]["writes"], rows[(today, "laptop")]["recalls"]) == (1, 2)
    assert rows[(today, "laptop")]["median_latency_ms"] == 20.0
    assert rows[(today, "ci")]["median_latency_ms"] == 100.0
    assert rows[(yesterday, "laptop")]["recalls"] == 1

    # One day back keeps yesterday out.
    assert {(r["day"], r["token"]) for r in daily(console, days=1)} == {(today, "laptop"), (today, "ci")}


# ---- retention --------------------------------------------------------------
def test_pruning_drops_old_log_entries_and_old_daily_events(app, console, api):
    from memory_mcp import recall_log

    now = datetime.now(timezone.utc)
    insert_log_entry((now - timedelta(days=40)).isoformat())
    insert_log_entry(now.isoformat(), query="fresh")
    insert_event((now - timedelta(days=100)).strftime("%Y-%m-%d"), "laptop", "recall", 5.0)
    insert_event((now - timedelta(days=10)).strftime("%Y-%m-%d"), "laptop", "recall", 5.0)

    result = anyio.run(recall_log.prune)
    assert result == {"log": 1, "daily_events": 1}
    assert [e["query"] for e in log(console)["items"]] == ["fresh"]
    from memory_mcp.config import settings

    con = sqlite3.connect(settings.sqlite_path)
    try:
        assert con.execute("SELECT count(*) FROM daily_events").fetchone()[0] == 1
    finally:
        con.close()


def test_a_recall_prunes_once_an_hour(app, console, api):
    from memory_mcp import recall_log

    now = datetime.now(timezone.utc)
    insert_log_entry((now - timedelta(days=40)).isoformat())
    recall_log.reset_prune_for_tests()

    recall(api, "anything")
    assert log(console)["total"] == 1  # the old entry is gone, the new one stays


# ---- access and validation --------------------------------------------------
def test_the_log_accepts_only_a_console_session(app, console, api):
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/recall-log", headers=BEARER).status_code == 403
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/recall-log").status_code == 401


def test_bad_parameters_are_rejected(console, api):
    assert console.get("/api/v1/recall-log", params={"limit": "x"}, headers=AUTH).status_code == 400
    assert console.get("/api/v1/recall-log", params={"limit": 0}, headers=AUTH).status_code == 400
    assert console.get("/api/v1/recall-log", params={"offset": -1}, headers=AUTH).status_code == 400
    assert console.get("/api/v1/recall-log/daily", params={"days": 0}, headers=AUTH).status_code == 400
    assert console.get("/api/v1/recall-log/daily", params={"days": 500}, headers=AUTH).status_code == 400
