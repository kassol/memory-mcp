"""Recall log and daily statistics (issue #15).

Terms follow GLOSSARY.md (Recall log).

Every recall writes a daily event (day, access token, whether it was a recall, its latency), whatever
the log setting says: the statistics are the long-lived signal for tuning and are kept 90 days. The
log itself — the query text, the access token and the ids of the top three results — is written only
while the `recall_log_enabled` setting is on, is kept 30 days, and one action clears it. A `remember`
call that stores a version also writes a daily event, so a day shows how much went in and how much
was looked up.

Pruning runs at most once an hour per process, on the next record after the interval, so no cron
entry is needed.
"""
import json
import statistics
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import settings_registry
from .storage.sqlite import get_db

LOG_DAYS = 30
STATS_DAYS = 90
TOP_IDS = 3
PRUNE_INTERVAL = 3600.0  # seconds
_last_prune = 0.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


BEIJING = timezone(timedelta(hours=8))


def _day(moment: datetime) -> str:
    """The Beijing calendar day; daily statistics use the same day the console displays."""
    return moment.astimezone(BEIJING).strftime("%Y-%m-%d")


async def record(
    query: str, token: Optional[str], latency_ms: float, results: int, memory_ids: list[str]
) -> None:
    """One recall: always a daily event, and the log entry while logging is on."""
    now = _now()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO daily_events (day, token, kind, latency_ms) VALUES (?, ?, 'recall', ?)",
            (_day(now), token or "", latency_ms),
        )
        if await settings_registry.get("recall_log_enabled"):
            await db.execute(
                "INSERT INTO recall_log (id, at, token, query, latency_ms, results, memory_ids) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), now.isoformat(), token, query, latency_ms, results, json.dumps(memory_ids[:TOP_IDS])),
            )
    await _prune_if_due()


async def record_write(token: Optional[str]) -> None:
    """One stored version (a remember that created or evolved a memory)."""
    async with get_db() as db:
        await db.execute(
            "INSERT INTO daily_events (day, token, kind, latency_ms) VALUES (?, ?, 'write', NULL)",
            (_day(_now()), token or ""),
        )
    await _prune_if_due()


async def recent(limit: int = 50, offset: int = 0) -> dict:
    """Log entries, newest first."""
    async with get_db() as db:
        rows = await db.fetchall(
            "SELECT id, at, token, query, latency_ms, results, memory_ids FROM recall_log "
            "ORDER BY at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        total = (await db.fetchone("SELECT count(*) FROM recall_log"))[0]
    return {
        "items": [
            {
                "id": row["id"],
                "at": row["at"],
                "token": row["token"],
                "query": row["query"],
                "latency_ms": row["latency_ms"],
                "results": row["results"],
                "memory_ids": json.loads(row["memory_ids"]),
            }
            for row in rows
        ],
        "total": total,
    }


async def clear() -> dict:
    """Drop every log entry; the daily statistics are separate and stay."""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM recall_log")
        return {"deleted": cursor.rowcount}


async def daily(days: int = 30) -> list[dict]:
    """Per day and access token: writes, recalls and the median recall latency."""
    since = _day(_now() - timedelta(days=days - 1))
    async with get_db() as db:
        rows = await db.fetchall(
            "SELECT day, token, kind, latency_ms FROM daily_events WHERE day >= ? ORDER BY day", (since,)
        )
    grouped: dict[tuple[str, str], dict] = {}
    latencies: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        key = (row["day"], row["token"])
        entry = grouped.setdefault(
            key,
            {"day": row["day"], "token": row["token"], "writes": 0, "recalls": 0, "median_latency_ms": None},
        )
        if row["kind"] == "write":
            entry["writes"] += 1
        else:
            entry["recalls"] += 1
            latencies.setdefault(key, []).append(row["latency_ms"])
    for key, values in latencies.items():
        grouped[key]["median_latency_ms"] = round(statistics.median(values), 1)
    return list(grouped.values())


async def prune() -> dict:
    """Drop log entries older than 30 days and daily events older than 90."""
    now = _now()
    log_cutoff = (now - timedelta(days=LOG_DAYS)).isoformat()
    day_cutoff = _day(now - timedelta(days=STATS_DAYS))
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM recall_log WHERE at < ?", (log_cutoff,))
        log_deleted = cursor.rowcount
        cursor = await db.execute("DELETE FROM daily_events WHERE day < ?", (day_cutoff,))
        stats_deleted = cursor.rowcount
    return {"log": log_deleted, "daily_events": stats_deleted}


async def _prune_if_due() -> None:
    global _last_prune
    now = time.monotonic()
    if now - _last_prune < PRUNE_INTERVAL:
        return
    _last_prune = now
    await prune()


def reset_prune_for_tests() -> None:
    global _last_prune
    _last_prune = 0.0
