"""Overview and maintenance history for the console (issue #16).

Everything the overview shows comes from one read-only snapshot: open findings by kind, how many
memories are current and how many were added or evolved in the last 7 and 30 days, the last
maintenance round, each provider's last call, the stalest memories, token last use, and the 30-day
daily statistics. `rounds` lists past maintenance rounds from `jobs`.

The schedule is not known to the service: a host cron calls POST /api/v1/maintenance/run, and the
console only shows that schedule as text.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import recall_log
from .storage.sqlite import get_db

SCHEDULE = "每天 04:17（宿主机 cron，Asia/Shanghai）"
STALE_LIMIT = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _round(row) -> dict:
    started = row["started_at"]
    finished = row["finished_at"]
    duration_ms: Optional[float] = None
    if started and finished:
        duration_ms = round((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds() * 1000, 1)
    try:
        stats = json.loads(row["payload"] or "{}")
    except ValueError:
        stats = {}
    return {
        "id": row["id"],
        "status": row["status"],
        "started_at": started,
        "finished_at": finished,
        "duration_ms": duration_ms,
        "stats": stats,
        "error": row["error"],
    }


async def snapshot() -> dict:
    now = _now()
    seven = (now - timedelta(days=7)).isoformat()
    thirty = (now - timedelta(days=30)).isoformat()

    async with get_db() as db:
        findings = await db.fetchall(
            "SELECT kind, count(*) AS count FROM memory_findings WHERE status = 'open' GROUP BY kind ORDER BY count DESC"
        )
        total = (await db.fetchone("SELECT count(*) AS n FROM memories WHERE is_current = 1"))["n"]
        created = await db.fetchone(
            "SELECT "
            "  sum(created_at >= ? AND mutation_type = 'initial') AS new_7, "
            "  sum(created_at >= ? AND mutation_type != 'initial') AS evolved_7, "
            "  sum(created_at >= ? AND mutation_type = 'initial') AS new_30, "
            "  sum(created_at >= ? AND mutation_type != 'initial') AS evolved_30 "
            "FROM memories",
            (seven, seven, thirty, thirty),
        )
        last_round = await db.fetchone(
            "SELECT id, status, started_at, finished_at, payload, error FROM jobs "
            "WHERE job_type = 'maintenance' ORDER BY created_at DESC LIMIT 1"
        )
        providers = await db.fetchall(
            "SELECT id, name, source, last_call_at, last_call_ok, last_call_error FROM providers "
            "ORDER BY source != 'file', created_at"
        )
        stalest = await db.fetchall(
            "SELECT id, entity_key, content, valid_from FROM memories WHERE is_current = 1 "
            "ORDER BY valid_from LIMIT ?",
            (STALE_LIMIT,),
        )
        tokens = await db.fetchall(
            "SELECT name, last_used_at, revoked_at FROM access_tokens ORDER BY id != 'initial', created_at"
        )

    return {
        "findings": [{"kind": row["kind"], "count": row["count"]} for row in findings],
        "memories": {
            "total": total or 0,
            "new_7d": created["new_7"] or 0,
            "evolved_7d": created["evolved_7"] or 0,
            "new_30d": created["new_30"] or 0,
            "evolved_30d": created["evolved_30"] or 0,
        },
        "last_round": _round(last_round) if last_round else None,
        "schedule": SCHEDULE,
        "providers": [
            {
                "id": row["id"],
                "name": row["name"],
                "source": row["source"],
                "last_call_at": row["last_call_at"],
                "last_call_ok": None if row["last_call_ok"] is None else bool(row["last_call_ok"]),
                "last_call_error": row["last_call_error"],
            }
            for row in providers
        ],
        "stalest": [
            {
                "memory_id": row["id"],
                "entity_key": row["entity_key"],
                "content": row["content"],
                "valid_from": row["valid_from"],
            }
            for row in stalest
        ],
        "tokens": [
            {"name": row["name"], "last_used_at": row["last_used_at"], "revoked_at": row["revoked_at"]} for row in tokens
        ],
        "daily": await recall_log.daily(days=30),
    }


async def rounds(limit: int = 20) -> list[dict]:
    async with get_db() as db:
        rows = await db.fetchall(
            "SELECT id, status, started_at, finished_at, payload, error FROM jobs "
            "WHERE job_type = 'maintenance' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    return [_round(row) for row in rows]
