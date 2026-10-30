"""Maintenance run: find memories a person should review. Terms follow GLOSSARY.md.

A run only starts when called (POST /api/v1/maintenance/run, driven by host cron). It is
serial, yields to the event loop after each unit of work, runs LanceDB calls in a thread,
and stops when its LLM budget is spent. Work left over is whatever has no check yet, so
the next run continues there without a cursor.

Checks only create findings; nothing is archived or merged automatically.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from ..config import settings
from ..storage.sqlite import get_db
from ..storage.vector import vector_store
from .llm import chat

logger = logging.getLogger(__name__)

# Cross-key candidates: cosine similarity among the 5 nearest neighbours. Separate from
# settings.similarity_threshold. On production data (3903 current) the old relevance >= 0.85
# rule matched 6 pairs; cosine >= 0.85 matches about 121.
CROSS_KEY_NEIGHBOURS = 5
CROSS_KEY_MIN_COSINE = 0.85

_INTERNAL_PROMPT = """You review one memory for an internal contradiction.

Memory:
{content}

Does the memory state two mutually exclusive states of the same subject as both true now? Examples: "uses tool A" together with "switched from A to B"; "X is configured" together with "X was removed". Facts explicitly marked as past, different aspects of a subject, and added detail are not contradictions.

Output ONLY a JSON object, nothing else:
{{"verdict": "internal_contradiction" or "consistent", "detail": "<one sentence naming the two conflicting statements, in the language of the memory; empty when consistent>"}}
"""

_PAIR_PROMPT = """You compare two memories stored under different subjects.

Memory A:
{a}

Memory B:
{b}

Classify the pair:
- "contradiction": they state facts that cannot both be true now.
- "duplicate": they state the same facts, so one could replace the other.
- "compatible": anything else, such as related, complementary or different aspects.

Output ONLY a JSON object, nothing else:
{{"verdict": "contradiction" or "duplicate" or "compatible", "detail": "<one sentence naming the conflicting or repeated statements, in the language of the memories; empty when compatible>"}}
"""


class AlreadyRunning(RuntimeError):
    """A maintenance run is in progress."""


class JudgmentError(RuntimeError):
    """The LLM verdict could not be obtained; never read that as consistent or compatible."""


class _BudgetSpent(BaseException):
    """Control flow only: the run's LLM budget is used up."""


_running = False
_task: Optional[asyncio.Task] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def start() -> str:
    """Start one run in the background and return its job id; raises AlreadyRunning."""
    global _running, _task
    if _running:
        raise AlreadyRunning("A maintenance run is in progress")
    _running = True
    try:
        job_id = str(uuid4())
        now = _now()
        async with get_db() as db:
            await db.execute(
                "INSERT INTO jobs (id, job_type, payload, status, scheduled_at, started_at, created_at) "
                "VALUES (?, 'maintenance', '{}', 'running', ?, ?, ?)",
                (job_id, now, now, now),
            )
        _task = asyncio.create_task(_run(job_id))
    except BaseException:
        _running = False
        raise
    # Let the task enter _run's try block, so a cancel from now on always closes the job row.
    await asyncio.sleep(0)
    return job_id


async def stop() -> None:
    """Cancel a run in progress (service shutdown); the run records itself as failed."""
    task = _task
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            if not task.done():  # stop() itself was cancelled
                raise


async def run_once() -> str:
    """Run one maintenance round to completion; returns the job id."""
    job_id = await start()
    assert _task is not None
    await _task
    return job_id


async def _run(job_id: str) -> None:
    global _running
    run = _Run(settings.maintenance_max_llm_calls)
    status, error = "done", None
    try:
        await run.execute()
        if run.errors:
            status = "failed"
            error = f"{len(run.errors)} judgment(s) failed; first: {run.errors[0]}"
    except BaseException as exc:  # includes cancellation at service shutdown
        status, error = "failed", f"{type(exc).__name__}: {exc}"
        if not isinstance(exc, Exception):
            raise
    finally:
        if error:
            logger.warning("Maintenance run %s failed: %s", job_id, error)
        _running = False
        async with get_db() as db:
            await db.execute(
                "UPDATE jobs SET status = ?, payload = ?, error = ?, finished_at = ? WHERE id = ?",
                (status, json.dumps(run.stats), error, _now(), job_id),
            )


class _Run:
    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.llm_calls = 0
        # A failed judgment skips its memory or pair for this run (no check, so the next run
        # retries it); one unjudgeable memory must not stop every later check.
        self.errors: list[str] = []
        self._failed: set[str] = set()  # subjects not to try again in this run
        self.stats = {
            "llm_calls": 0,
            "resolved": 0,
            "multiple_current": 0,
            "internal_checked": 0,
            "internal_contradiction": 0,
            "neighbour_scans": 0,
            "pairs_checked": 0,
            "contradiction": 0,
            "duplicate": 0,
        }

    async def execute(self) -> None:
        await self._resolve_stale()
        await self._multiple_current()
        # The two LLM checks share the budget evenly; whatever one leaves goes to the other.
        await self._internal(limit=self.budget // 2)
        await self._cross_key()
        await self._internal(limit=self.budget)

    # ---- LLM -------------------------------------------------------------
    async def _judge(self, prompt: str, verdicts: set[str], limit: int) -> tuple[str, str]:
        if self.llm_calls >= limit:
            raise _BudgetSpent
        self.llm_calls += 1
        self.stats["llm_calls"] = self.llm_calls
        try:
            text = await chat(prompt)
        except Exception as exc:
            raise JudgmentError(f"LLM request failed: {exc!r}") from exc
        match = re.search(r"\{.*\}", text, re.DOTALL)
        try:
            data = json.loads(match.group(0), strict=False) if match else None
        except json.JSONDecodeError:
            data = None
        verdict = data.get("verdict") if isinstance(data, dict) else None
        detail = data.get("detail") if isinstance(data, dict) else None
        if verdict not in verdicts or not isinstance(detail, str):
            raise JudgmentError(f"Unusable verdict: {text[:200]!r}")
        if verdict not in {"consistent", "compatible"} and not detail.strip():
            raise JudgmentError(f"Finding without detail: {text[:200]!r}")
        return verdict, detail.strip()

    # ---- Checks ----------------------------------------------------------
    async def _resolve_stale(self) -> None:
        async with get_db() as db:
            cur = await db.execute(
                "UPDATE memory_findings SET status = 'resolved', resolved_at = ? "
                "WHERE status = 'open' AND ("
                "  memory_id NOT IN (SELECT id FROM memories WHERE is_current = 1)"
                "  OR (other_memory_id IS NOT NULL"
                "      AND other_memory_id NOT IN (SELECT id FROM memories WHERE is_current = 1)))",
                (_now(),),
            )
        self.stats["resolved"] = cur.rowcount or 0

    async def _multiple_current(self) -> None:
        async with get_db() as db:
            groups = await db.fetchall(
                "SELECT entity_key FROM memories GROUP BY entity_key HAVING SUM(is_current) > 1 "
                "EXCEPT SELECT entity_key FROM memory_findings "
                "WHERE kind = 'multiple_current' AND status IN ('open', 'dismissed')"
            )
            for group in groups:
                ids = await db.fetchall(
                    "SELECT id FROM memories WHERE entity_key = ? AND is_current = 1 "
                    "ORDER BY created_at, id LIMIT 2",
                    (group["entity_key"],),
                )
                await _add_finding(db, "multiple_current", ids[0]["id"], ids[1]["id"],
                                   group["entity_key"], None)
        self.stats["multiple_current"] = len(groups)

    async def _internal(self, limit: int) -> None:
        # Only memories from a conflicting merge: that merge keeps old facts the new one did not
        # explicitly retire, which is where internal contradictions come from (314 of 3903 in
        # production). Other memories show no such failure and would cost 12x the LLM calls.
        async with get_db() as db:
            todo = await db.fetchall(
                "SELECT id, entity_key, content FROM memories "
                "WHERE is_current = 1 AND conflict = 1 AND id NOT IN "
                "(SELECT subject FROM memory_checks WHERE check_type = 'internal') "
                "ORDER BY created_at, id"
            )
        for row in todo:
            if row["id"] in self._failed:
                continue
            try:
                verdict, detail = await self._judge(
                    _INTERNAL_PROMPT.format(content=row["content"]),
                    {"internal_contradiction", "consistent"},
                    limit,
                )
            except _BudgetSpent:
                return
            except JudgmentError as exc:
                self.errors.append(f"internal {row['id']}: {exc}")
                self._failed.add(row["id"])
                continue
            async with get_db() as db:
                await _add_check(db, "internal", row["id"], verdict)
                if verdict == "internal_contradiction":
                    await _add_finding(db, verdict, row["id"], None, row["entity_key"], detail)
                    self.stats["internal_contradiction"] += 1
            self.stats["internal_checked"] += 1
            await asyncio.sleep(0)

    async def _cross_key(self) -> None:
        async with get_db() as db:
            todo = await db.fetchall(
                "SELECT id, entity_key, content FROM memories WHERE is_current = 1 AND id NOT IN "
                "(SELECT subject FROM memory_checks WHERE check_type = 'neighbours') "
                "ORDER BY created_at, id"
            )
        for row in todo:
            if await self._scan_neighbours(row):
                return

    async def _scan_neighbours(self, row) -> bool:
        """Judge one memory's cross-key pairs; True when the budget ran out.

        The neighbour-scan check is written only when every pair has a check, so pairs
        skipped by the budget or a failed judgment are found again next run.
        """
        neighbours = await vector_store.cosine_neighbours(row["id"], CROSS_KEY_NEIGHBOURS)
        candidates = [mid for mid, cos in neighbours if cos >= CROSS_KEY_MIN_COSINE]
        async with get_db() as db:
            others = await db.fetchall(
                f"SELECT id, entity_key, content FROM memories WHERE is_current = 1 "
                f"AND entity_key != ? AND id IN ({','.join('?' * len(candidates))})",
                [row["entity_key"], *candidates],
            ) if candidates else []
        complete = True
        for other in others:
            subject = "|".join(sorted((row["id"], other["id"])))
            async with get_db() as db:
                if await _has_check(db, "pair", subject):
                    continue
            try:
                verdict, detail = await self._judge(
                    _PAIR_PROMPT.format(a=row["content"], b=other["content"]),
                    {"contradiction", "duplicate", "compatible"},
                    self.budget,
                )
            except _BudgetSpent:
                return True
            except JudgmentError as exc:
                self.errors.append(f"pair {subject}: {exc}")
                complete = False
                continue
            async with get_db() as db:
                await _add_check(db, "pair", subject, verdict)
                if verdict != "compatible":
                    await _add_finding(db, verdict, row["id"], other["id"], None, detail)
                    self.stats[verdict] += 1
            self.stats["pairs_checked"] += 1
            await asyncio.sleep(0)
        if complete:
            async with get_db() as db:
                await _add_check(db, "neighbours", row["id"], str(len(others)))
            self.stats["neighbour_scans"] += 1
        await asyncio.sleep(0)
        return False


async def _add_check(db, check_type: str, subject: str, outcome: str) -> None:
    await db.execute(
        "INSERT INTO memory_checks (check_type, subject, outcome, checked_at) VALUES (?, ?, ?, ?)",
        (check_type, subject, outcome, _now()),
    )


async def _has_check(db, check_type: str, subject: str) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM memory_checks WHERE check_type = ? AND subject = ?", (check_type, subject)
    )
    return row is not None


async def _add_finding(db, kind: str, memory_id: str, other_memory_id: Optional[str],
                       entity_key: Optional[str], detail: Optional[str]) -> None:
    await db.execute(
        "INSERT INTO memory_findings (id, kind, memory_id, other_memory_id, entity_key, detail, "
        "status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'open', ?)",
        (str(uuid4()), kind, memory_id, other_memory_id, entity_key, detail, _now()),
    )


async def list_findings(status: Optional[str] = None, kind: Optional[str] = None) -> list[dict]:
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    async with get_db() as db:
        rows = await db.fetchall(
            "SELECT id, kind, memory_id, other_memory_id, entity_key, detail, status, created_at, "
            f"resolved_at FROM memory_findings {where} ORDER BY created_at, id",
            params,
        )
    return [dict(r) for r in rows]
