# Memory MCP — M4 Background Worker Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入同进程异步任务队列，把 extraction / title / summary / reinforce decay / working memory 缓存全部从 request path 搬到 background worker。

**Architecture:** SQLite `jobs` 表作队列；`worker_loop` 是同进程 asyncio task，每秒拉一批 pending job，通过 `JOB_HANDLERS` 注册表分发到 5 个 handler；APScheduler 负责 cron 触发（实际工作仍是 `enqueue`，让 worker 统一消费）；Starlette lifespan 管理 startup / drain。

**统一存储**：所有 worker / handler / queue 代码 **必须** 复用 M1 的 `from memory_mcp.storage.sqlite import get_db` —— 不另开 `aiosqlite.connect()`，不读 `MEMORY_MCP_DB_PATH` 环境变量。唯一 SQLite 文件路径是 `settings.sqlite_path = ./data/memory.sqlite3`（D13）。

**Tech Stack:** Python 3.11+ / aiosqlite / APScheduler 3.11.x / asyncio / pytest-asyncio / pytest (现有)

**Spec:** `docs/superpowers/specs/2026-05-21-memory-mcp-agent-kernel-design.md` §8 / §4.5 / §11 M4

**Dependencies:** 假定 M1（SQLite + alembic + jobs/working_memory_cache 表 DDL）、M2（hybrid_search + REST 分页）、M3（threads / thread_messages / `extraction.py` source_refs 升级）已 merge。本计划不重新创建 jobs 表 DDL，只实现 enqueue / dequeue / handler / scheduler / lifespan 集成与 REST 监控 API。

---

## File Structure

### 服务端新增 / 修改

| 文件 | 动作 | 职责 |
|------|------|------|
| `src/memory_mcp/workers/__init__.py` | 新建 | 包初始化；导出 `worker_loop`、`shutdown_event`、`scheduler` |
| `src/memory_mcp/workers/events.py` | 新建 | 全局 `asyncio.Event` `shutdown_event` 实例 |
| `src/memory_mcp/workers/queue.py` | 新建 | `enqueue` / `fetch_and_lock` / `mark_done` / `mark_failed_or_retry` |
| `src/memory_mcp/workers/loop.py` | 新建 | `worker_loop()` 主循环；单任务 timeout 120s |
| `src/memory_mcp/workers/scheduler.py` | 新建 | AsyncIOScheduler 实例 + cron 注册（实际工作是 `enqueue`） |
| `src/memory_mcp/workers/handlers/__init__.py` | 新建 | `JOB_HANDLERS` 注册表 |
| `src/memory_mcp/workers/handlers/extraction.py` | 新建 | 抽 memory，写 `source_thread_id` / `source_refs` |
| `src/memory_mcp/workers/handlers/title_gen.py` | 新建 | LLM 生成 10-20 字短 title |
| `src/memory_mcp/workers/handlers/summary_gen.py` | 新建 | thread 摘要写入 `threads.summary` |
| `src/memory_mcp/workers/handlers/reinforce_decay.py` | 新建 | 计算归一化 reinforce + decay 因子，写 cache |
| `src/memory_mcp/workers/handlers/wm_refresh.py` | 新建 | 调 `generate_briefing()` 写 `working_memory_cache` |
| `src/memory_mcp/engine/working_memory.py` | 修改 | 增加 `read_cached(cache_key)`，cache miss 退化 generate |
| `src/memory_mcp/api/routes.py` | 修改 | 新增 4 个 jobs REST 端点；`/threads/incremental` 改为入队 |
| `src/memory_mcp/server.py` | 修改 | lifespan 包装 streamable_http.lifespan，启动/退出 worker + scheduler |
| `pyproject.toml` | 修改 | 增加 `apscheduler>=3.11` 依赖 |
| `AGENTS.md` | 修改 | 追加 M4 changelog |

### 测试新增

| 文件 | 动作 | 测试 |
|------|------|------|
| `tests/conftest.py` | 修改 | 增加 `db_path` / `jobs_db` fixture（内存 SQLite + jobs schema） |
| `tests/workers/__init__.py` | 新建 | 空包初始化 |
| `tests/workers/test_queue.py` | 新建 | enqueue / fetch_and_lock 事务 / 指数退避 / max_attempts |
| `tests/workers/test_loop.py` | 新建 | worker_loop 拉取 + dispatch + timeout + 优雅退出 |
| `tests/workers/test_scheduler.py` | 新建 | APScheduler cron 触发 → enqueue |
| `tests/workers/test_handler_extraction.py` | 新建 | extraction handler 写 source_thread_id / source_refs |
| `tests/workers/test_handler_title_gen.py` | 新建 | title_gen handler 调 LLM + 更新 memory.title |
| `tests/workers/test_handler_summary_gen.py` | 新建 | summary_gen handler 写 threads.summary |
| `tests/workers/test_handler_reinforce_decay.py` | 新建 | reinforce_decay handler 写归一化结果到 cache |
| `tests/workers/test_handler_wm_refresh.py` | 新建 | wm_refresh handler 写 working_memory_cache |
| `tests/workers/test_jobs_api.py` | 新建 | list / get / retry / cancel REST 端点 |
| `tests/workers/test_integration.py` | 新建 | 端到端：enqueue extraction → worker pick → memory 写入；handler 三次失败 → status='failed' |
| `tests/workers/test_lifespan.py` | 新建 | startup 启动 worker + scheduler；shutdown drain 退出 |

---

## Chunk 1: 依赖与全局事件

### Task 1: 加入 APScheduler 依赖与 workers 包骨架

**Files:**
- 修改：`pyproject.toml`
- 新建：`src/memory_mcp/workers/__init__.py`
- 新建：`src/memory_mcp/workers/events.py`
- 新建：`tests/workers/__init__.py`

- [ ] **Step 1: 加 apscheduler 依赖**

Edit `pyproject.toml` — 把 `dependencies` 列表补上：

```toml
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "lancedb>=0.4.0",
    "pyarrow>=14.0.0",
    "networkx>=3.2.0",
    "numpy>=1.26.0",
    "uvicorn>=0.27.0",
    "starlette>=0.36.0",
    "python-dotenv>=1.0.0",
    "aiosqlite>=0.22.0",
    "apscheduler>=3.11.0",
    "jieba>=0.42.0",
]
```

- [ ] **Step 2: workers 包骨架**

Create `src/memory_mcp/workers/__init__.py`:

```python
"""Background worker subsystem.

Single-process asyncio + SQLite-backed queue + APScheduler. No Redis/Celery.
"""

from .events import shutdown_event

__all__ = ["shutdown_event"]
```

Create `src/memory_mcp/workers/events.py`:

```python
"""Process-wide asyncio events used by worker / lifespan coordination."""

import asyncio

# Set during Starlette lifespan shutdown. Worker loop watches this to drain.
shutdown_event: asyncio.Event = asyncio.Event()


def reset_shutdown_event() -> None:
    """Reset the global shutdown event. Test-only helper."""
    global shutdown_event
    shutdown_event = asyncio.Event()
```

- [ ] **Step 3: 测试包骨架**

Create `tests/workers/__init__.py` — empty file.

- [ ] **Step 4: 安装新依赖并跑一遍基线测试，确认无回归**

Run: `cd /Users/kassol/Workspace/memory-mcp && pip install -e ".[dev]" && pytest -v`
Expected: 全部 PASS（含 M1/M2/M3 既有测试）

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/memory_mcp/workers/ tests/workers/__init__.py
git commit -m "feat(worker): scaffold workers package with shutdown event"
```

---

## Chunk 2: SQLite 测试 fixture 与 schema reuse

### Task 2: jobs / working_memory_cache fixture

**Files:**
- 修改：`tests/conftest.py`

> 说明：M1 已在 alembic migration `0001_initial_v2.py` 中定义 `jobs` / `working_memory_cache` / `threads` / `thread_messages` 表，并暴露 `storage.sqlite.get_db()` 异步上下文管理器。本 Task 复用 M1 fixture 提供的同一个 SQLite 文件，不再独立创建 `MEMORY_MCP_DB_PATH` 走向；只对 `MEMORY_MCP_AUTO_MIGRATE=true` 的 `test_env` 做薄包装。

- [ ] **Step 1: 在 conftest.py 新增 `jobs_db` fixture（复用 M1 sqlite_path）**

Edit `tests/conftest.py` — 文件末尾追加：

```python
import pytest_asyncio


@pytest_asyncio.fixture()
async def jobs_db(test_env, tmp_path):
    """Yield the absolute path of the M1-migrated SQLite DB.

    ``test_env`` (M1 fixture) already set ``MEMORY_MCP_DATA_DIR=<tmp_path>`` and
    ran ``alembic upgrade head`` against that directory. The resulting file
    sits at ``settings.sqlite_path``. Worker tests get the same DB so that
    enqueue, fetch_and_lock, and handler writes all converge.
    """
    import memory_mcp.config as config_mod
    import importlib
    importlib.reload(config_mod)
    db_path = config_mod.settings.sqlite_path
    # M1 alembic migration already created jobs / working_memory_cache /
    # threads / thread_messages — no schema bootstrap needed here.
    yield db_path
```

**契约**：`jobs_db` 现在返回的就是 M1 `settings.sqlite_path`（`<tmp>/memory.sqlite3`），所有走 `get_db()` 的 worker 代码自动指向同一文件。不再向环境注入 `MEMORY_MCP_DB_PATH`，也不再独立 `executescript(_JOBS_SCHEMA)`。

- [ ] **Step 2: 添加 `reset_shutdown` autouse fixture，避免跨测试污染**

Append to `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _reset_shutdown_event():
    """Each test gets a fresh shutdown_event."""
    import memory_mcp.workers.events as events_mod
    events_mod.reset_shutdown_event()
    yield
    events_mod.reset_shutdown_event()
```

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test(worker): add jobs_db fixture and reset shutdown event"
```

---

## Chunk 3: SQLite Queue

### Task 3: enqueue / fetch_and_lock

**Files:**
- 新建：`src/memory_mcp/workers/queue.py`
- 新建：`tests/workers/test_queue.py`

- [ ] **Step 1: 写失败测试 — enqueue 基础**

> **测试约定**：所有 M4 测试统一通过 `from memory_mcp.storage.sqlite import get_db` 读 jobs/wm_cache 表（不再 `aiosqlite.connect(jobs_db)`）。`jobs_db` fixture 只用于触发 M1 alembic + 把 `tmp_path` 注入 settings；DB 文件由 M1 的 `SQLiteStore` 单例管理。**下面所有 `aiosqlite.connect(jobs_db)` 调用都按这个原则改成 `async with get_db() as db: row = await db.fetchone(...)`**，下面只展示 Step 1 的样例；后续 Task 4-17 的测试自行套用同一模式。

Create `tests/workers/test_queue.py`:

```python
import json
from datetime import datetime, timezone, timedelta

import pytest

from memory_mcp.storage.sqlite import get_db
from memory_mcp.workers import queue as qmod


@pytest.mark.asyncio
async def test_enqueue_creates_pending_row(jobs_db):
    job_id = await qmod.enqueue("title_gen", {"memory_id": "m-1"})
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT job_type, payload, status, attempts, max_attempts FROM jobs WHERE id = ?",
            (job_id,),
        )
    assert row is not None
    assert row["job_type"] == "title_gen"
    assert json.loads(row["payload"]) == {"memory_id": "m-1"}
    assert row["status"] == "pending"
    assert row["attempts"] == 0
    assert row["max_attempts"] == 3


@pytest.mark.asyncio
async def test_enqueue_accepts_custom_scheduled_at_and_max_attempts(jobs_db):
    when = datetime.now(timezone.utc) + timedelta(minutes=10)
    job_id = await qmod.enqueue(
        "wm_refresh",
        {"cache_key": "briefing:default"},
        scheduled_at=when,
        max_attempts=5,
    )
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT scheduled_at, max_attempts FROM jobs WHERE id = ?",
            (job_id,),
        )
    assert row["max_attempts"] == 5
    parsed = datetime.fromisoformat(row["scheduled_at"])
    assert abs((parsed - when).total_seconds()) < 1
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/workers/test_queue.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 enqueue**

Create `src/memory_mcp/workers/queue.py`:

```python
"""SQLite-backed job queue.

Single-process asyncio. Worker pulls a batch via the M1 ``get_db()`` facade
(``BEGIN IMMEDIATE`` + SELECT + UPDATE) to claim ownership; no advisory locks
needed since we are single-process. All workers / handlers / API code MUST
consume ``get_db()`` — there is exactly one SQLite file per process.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

from ..storage.sqlite import get_db

logger = logging.getLogger("memory-mcp.worker.queue")

# Exponential backoff schedule (minutes) for attempt 1, 2, 3.
_BACKOFF_MINUTES = (1, 5, 25)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    job_type: str
    payload: dict
    status: str
    attempts: int
    max_attempts: int
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    next_retry_at: datetime | None
    error: str | None
    created_at: datetime


_JOB_COLUMNS = (
    "id, job_type, payload, status, attempts, max_attempts, "
    "scheduled_at, started_at, finished_at, next_retry_at, error, created_at"
)


def _row_to_job(row) -> Job:
    """Build a ``Job`` from an aiosqlite.Row (column access by name)."""
    def _parse(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

    return Job(
        id=row["id"],
        job_type=row["job_type"],
        payload=json.loads(row["payload"]) if row["payload"] else {},
        status=row["status"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        scheduled_at=datetime.fromisoformat(row["scheduled_at"]),
        started_at=_parse(row["started_at"]),
        finished_at=_parse(row["finished_at"]),
        next_retry_at=_parse(row["next_retry_at"]),
        error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


async def enqueue(
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    scheduled_at: datetime | None = None,
    max_attempts: int = 3,
) -> str:
    """Insert a pending job and return its id."""
    job_id = str(uuid4())
    now = datetime.now(timezone.utc)
    scheduled = scheduled_at or now
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO jobs (
                id, job_type, payload, status, attempts, max_attempts,
                scheduled_at, created_at
            ) VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)
            """,
            (
                job_id,
                job_type,
                json.dumps(payload or {}, ensure_ascii=False),
                max_attempts,
                _iso(scheduled),
                _iso(now),
            ),
        )
    return job_id
```

- [ ] **Step 4: 跑 enqueue 测试**

Run: `pytest tests/workers/test_queue.py::test_enqueue_creates_pending_row tests/workers/test_queue.py::test_enqueue_accepts_custom_scheduled_at_and_max_attempts -v`
Expected: PASS

- [ ] **Step 5: 写失败测试 — fetch_and_lock**

Append to `tests/workers/test_queue.py`:

```python
@pytest.mark.asyncio
async def test_fetch_and_lock_marks_running(jobs_db):
    jid = await qmod.enqueue("title_gen", {"x": 1})
    jobs = await qmod.fetch_and_lock(limit=5)
    assert len(jobs) == 1
    assert jobs[0].id == jid
    assert jobs[0].status == "running"
    # The DB row should now be 'running' too
    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute("SELECT status, started_at FROM jobs WHERE id = ?", (jid,)) as cur:
            status, started_at = await cur.fetchone()
    assert status == "running"
    assert started_at is not None


@pytest.mark.asyncio
async def test_fetch_and_lock_skips_running_jobs(jobs_db):
    jid = await qmod.enqueue("title_gen", {"x": 1})
    first = await qmod.fetch_and_lock(limit=5)
    second = await qmod.fetch_and_lock(limit=5)
    assert [j.id for j in first] == [jid]
    assert second == []


@pytest.mark.asyncio
async def test_fetch_and_lock_respects_scheduled_at_in_future(jobs_db):
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    await qmod.enqueue("wm_refresh", {}, scheduled_at=future)
    jobs = await qmod.fetch_and_lock(limit=5)
    assert jobs == []


@pytest.mark.asyncio
async def test_fetch_and_lock_respects_next_retry_at(jobs_db):
    jid = await qmod.enqueue("title_gen", {})
    # Simulate a previous failure that scheduled a retry into the future.
    async with aiosqlite.connect(jobs_db) as db:
        future = datetime.now(timezone.utc) + timedelta(minutes=2)
        await db.execute(
            "UPDATE jobs SET attempts = 1, next_retry_at = ? WHERE id = ?",
            (qmod._iso(future), jid),
        )
        await db.commit()
    jobs = await qmod.fetch_and_lock(limit=5)
    assert jobs == []


@pytest.mark.asyncio
async def test_fetch_and_lock_limits_batch(jobs_db):
    for i in range(8):
        await qmod.enqueue("title_gen", {"i": i})
    jobs = await qmod.fetch_and_lock(limit=3)
    assert len(jobs) == 3
```

- [ ] **Step 6: 跑测试验证失败**

Run: `pytest tests/workers/test_queue.py -v`
Expected: 后 5 个 FAIL（函数不存在）

- [ ] **Step 7: 实现 fetch_and_lock**

Append to `src/memory_mcp/workers/queue.py`:

```python
async def fetch_and_lock(limit: int = 5) -> list[Job]:
    """Atomically claim up to `limit` pending jobs.

    Selection rule:
      status='pending' AND (next_retry_at IS NULL OR next_retry_at <= now())
      AND scheduled_at <= now()
    Ordered by scheduled_at ASC.

    Uses the ``DBHandle.transaction()`` context (BEGIN IMMEDIATE on enter,
    commit on exit) to serialise against concurrent workers; we run
    single-process so this is mostly belt-and-suspenders for tests.
    """
    now = datetime.now(timezone.utc)
    now_iso = _iso(now)
    async with get_db() as db:
        async with db.transaction():
            rows = await db.fetchall(
                f"""
                SELECT {_JOB_COLUMNS}
                  FROM jobs
                 WHERE status = 'pending'
                   AND scheduled_at <= ?
                   AND (next_retry_at IS NULL OR next_retry_at <= ?)
                 ORDER BY scheduled_at ASC
                 LIMIT ?
                """,
                (now_iso, now_iso, limit),
            )
            if not rows:
                return []
            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in ids)
            await db.execute(
                f"UPDATE jobs SET status = 'running', started_at = ? WHERE id IN ({placeholders})",
                (now_iso, *ids),
            )

    # Rebuild Job dataclasses with status='running' / started_at=now.
    claimed: list[Job] = []
    for r in rows:
        job = _row_to_job(r)
        job.status = "running"
        job.started_at = now
        claimed.append(job)
    return claimed
```

- [ ] **Step 8: 跑测试**

Run: `pytest tests/workers/test_queue.py -v`
Expected: 全部 PASS

- [ ] **Step 9: Commit**

```bash
git add src/memory_mcp/workers/queue.py tests/workers/test_queue.py
git commit -m "feat(worker): add SQLite job enqueue and atomic fetch_and_lock"
```

### Task 4: mark_done / mark_failed_or_retry 指数退避

**Files:**
- 修改：`src/memory_mcp/workers/queue.py`
- 修改：`tests/workers/test_queue.py`

- [ ] **Step 1: 写失败测试 — mark_done**

Append to `tests/workers/test_queue.py`:

```python
@pytest.mark.asyncio
async def test_mark_done_sets_done_and_finished_at(jobs_db):
    jid = await qmod.enqueue("title_gen", {})
    (job,) = await qmod.fetch_and_lock(limit=1)
    await qmod.mark_done(job.id)
    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT status, finished_at, attempts, error FROM jobs WHERE id = ?",
            (jid,),
        ) as cur:
            status, finished_at, attempts, error = await cur.fetchone()
    assert status == "done"
    assert finished_at is not None
    assert attempts == 1  # incremented on success too
    assert error is None
```

- [ ] **Step 2: 写失败测试 — 指数退避三步**

Append:

```python
@pytest.mark.asyncio
async def test_mark_failed_or_retry_schedules_exponential_backoff(jobs_db):
    jid = await qmod.enqueue("title_gen", {})
    (job,) = await qmod.fetch_and_lock(limit=1)
    await qmod.mark_failed_or_retry(job.id, RuntimeError("boom"))

    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT status, attempts, next_retry_at, error FROM jobs WHERE id = ?",
            (jid,),
        ) as cur:
            status, attempts, next_retry_at, error = await cur.fetchone()
    assert status == "pending"
    assert attempts == 1
    assert error == "boom"
    delta = datetime.fromisoformat(next_retry_at) - datetime.now(timezone.utc)
    assert 50 < delta.total_seconds() < 70  # ~60s

    # Force the next retry to be eligible now.
    async with aiosqlite.connect(jobs_db) as db:
        await db.execute(
            "UPDATE jobs SET next_retry_at = ? WHERE id = ?",
            (qmod._iso(datetime.now(timezone.utc) - timedelta(seconds=1)), jid),
        )
        await db.commit()

    (job,) = await qmod.fetch_and_lock(limit=1)
    await qmod.mark_failed_or_retry(job.id, RuntimeError("boom2"))
    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT status, attempts, next_retry_at FROM jobs WHERE id = ?",
            (jid,),
        ) as cur:
            status, attempts, next_retry_at = await cur.fetchone()
    assert status == "pending"
    assert attempts == 2
    delta = datetime.fromisoformat(next_retry_at) - datetime.now(timezone.utc)
    assert 280 < delta.total_seconds() < 320  # ~5min


@pytest.mark.asyncio
async def test_mark_failed_or_retry_marks_failed_after_max_attempts(jobs_db):
    jid = await qmod.enqueue("title_gen", {}, max_attempts=2)
    for _ in range(2):
        # Make the row eligible
        async with aiosqlite.connect(jobs_db) as db:
            await db.execute(
                "UPDATE jobs SET next_retry_at = NULL, status = 'pending' WHERE id = ?",
                (jid,),
            )
            await db.commit()
        (job,) = await qmod.fetch_and_lock(limit=1)
        await qmod.mark_failed_or_retry(job.id, RuntimeError("nope"))

    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT status, attempts, next_retry_at, error FROM jobs WHERE id = ?",
            (jid,),
        ) as cur:
            status, attempts, next_retry_at, error = await cur.fetchone()
    assert status == "failed"
    assert attempts == 2
    assert next_retry_at is None
    assert error == "nope"
```

- [ ] **Step 3: 跑测试验证失败**

Run: `pytest tests/workers/test_queue.py -v`
Expected: 后 3 个 FAIL

- [ ] **Step 4: 实现 mark_done / mark_failed_or_retry**

Append to `src/memory_mcp/workers/queue.py`:

```python
def _next_backoff(next_attempt: int) -> datetime:
    """Compute next retry time for the upcoming attempt number (1-based).

    Attempt 1 finished → wait 1min; attempt 2 finished → wait 5min;
    attempt 3 finished → wait 25min (but only reached if max_attempts > 3).
    """
    idx = min(next_attempt - 1, len(_BACKOFF_MINUTES) - 1)
    minutes = _BACKOFF_MINUTES[idx]
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


async def mark_done(job_id: str) -> None:
    now = datetime.now(timezone.utc)
    async with get_db() as db:
        await db.execute(
            """
            UPDATE jobs
               SET status = 'done',
                   finished_at = ?,
                   attempts = attempts + 1,
                   error = NULL
             WHERE id = ?
            """,
            (_iso(now), job_id),
        )


async def mark_failed_or_retry(job_id: str, error: BaseException) -> None:
    """Increment attempts; either reschedule with backoff or mark 'failed'."""
    now = datetime.now(timezone.utc)
    message = str(error) or error.__class__.__name__
    async with get_db() as db:
        async with db.transaction():
            row = await db.fetchone(
                "SELECT attempts, max_attempts FROM jobs WHERE id = ?",
                (job_id,),
            )
            if row is None:
                return
            attempts = row["attempts"]
            max_attempts = row["max_attempts"]
            next_attempt = attempts + 1
            if next_attempt >= max_attempts:
                await db.execute(
                    """
                    UPDATE jobs
                       SET status = 'failed',
                           attempts = ?,
                           finished_at = ?,
                           next_retry_at = NULL,
                           error = ?
                     WHERE id = ?
                    """,
                    (next_attempt, _iso(now), message, job_id),
                )
            else:
                retry_at = _next_backoff(next_attempt)
                await db.execute(
                    """
                    UPDATE jobs
                       SET status = 'pending',
                           attempts = ?,
                           next_retry_at = ?,
                           error = ?,
                           started_at = NULL
                     WHERE id = ?
                    """,
                    (next_attempt, _iso(retry_at), message, job_id),
                )
```

- [ ] **Step 5: 跑测试**

Run: `pytest tests/workers/test_queue.py -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/workers/queue.py tests/workers/test_queue.py
git commit -m "feat(worker): add mark_done and mark_failed_or_retry with exponential backoff"
```

---

## Chunk 4: Handlers

### Task 5: extraction handler

**Files:**
- 新建：`src/memory_mcp/workers/handlers/__init__.py`
- 新建：`src/memory_mcp/workers/handlers/extraction.py`
- 新建：`tests/workers/test_handler_extraction.py`

- [ ] **Step 1: handler 注册表骨架**

Create `src/memory_mcp/workers/handlers/__init__.py`:

```python
"""Job-type → handler registry.

Handlers are async callables `async def handler(payload: dict) -> dict`.
Returned dict is informational (worker logs it); contract: side effects must
land in SQLite/vector store before return.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from . import extraction, reinforce_decay, summary_gen, title_gen, wm_refresh

Handler = Callable[[dict], Awaitable[dict]]

JOB_HANDLERS: dict[str, Handler] = {
    "extraction": extraction.handle,
    "title_gen": title_gen.handle,
    "summary_gen": summary_gen.handle,
    "reinforce_decay": reinforce_decay.handle,
    "wm_refresh": wm_refresh.handle,
}

__all__ = ["JOB_HANDLERS", "Handler"]
```

> 这里 import 的 5 个模块都会在下面 Task 5-9 创建。先建好注册表会让后面增量提交时 import 链稳定。

- [ ] **Step 2: 写失败测试 — extraction handler**

Create `tests/workers/test_handler_extraction.py`:

```python
import json

import aiosqlite
import pytest

from memory_mcp.workers.handlers import extraction


@pytest.mark.asyncio
async def test_extraction_handler_creates_memory_with_source_refs(
    tools, test_env, jobs_db, monkeypatch
):
    # Seed thread + messages so source_refs are real
    async with aiosqlite.connect(jobs_db) as db:
        await db.execute(
            "INSERT INTO threads (thread_id, source_provider, source_ref, created_at, imported_at) "
            "VALUES (?, 'claude-code', '/p/a.jsonl', '2026-05-21T00:00:00+00:00', '2026-05-21T00:00:00+00:00')",
            ("th-1",),
        )
        for seq in (1, 2):
            await db.execute(
                "INSERT INTO thread_messages (message_id, thread_id, seq, role, content) "
                "VALUES (?, ?, ?, 'user', ?)",
                (f"th-1:{seq:06d}", "th-1", seq, f"msg {seq}"),
            )
        await db.commit()

    # Stub the underlying extraction LLM so we don't hit network.
    import memory_mcp.engine.extraction as eng_mod
    import importlib
    importlib.reload(eng_mod)

    async def fake_llm(_messages):
        return json.dumps(
            [{"entity_key": "fact:test", "entity_type": "fact", "content": "Test fact"}]
        )

    monkeypatch.setattr(eng_mod, "_call_llm", fake_llm)
    importlib.reload(extraction)

    payload = {
        "thread_id": "th-1",
        "message_ids": ["th-1:000001", "th-1:000002"],
        "messages": [
            {"role": "user", "content": "I want to remember X."},
            {"role": "assistant", "content": "Saved."},
        ],
    }
    result = await extraction.handle(payload)
    assert result["total"] == 1

    from memory_mcp.storage.vector import vector_store
    nodes = await vector_store.list_current()
    target = next(n for n in nodes if n.entity_key == "fact:test")
    # source_thread_id and source_refs must be wired through.
    # Phase 1 stores them via remember_tool extra args; we assert via getattr
    # so the field exists on the v2 MemoryNode after M2.
    assert getattr(target, "source_thread_id", None) == "th-1"
    refs = getattr(target, "source_refs", None)
    assert refs == [
        {"thread_id": "th-1", "message_id": "th-1:000001"},
        {"thread_id": "th-1", "message_id": "th-1:000002"},
    ]


@pytest.mark.asyncio
async def test_extraction_handler_handles_no_messages(jobs_db, tools, test_env):
    importlib_reload = pytest.importorskip("importlib")
    result = await extraction.handle({"thread_id": "th-1", "message_ids": [], "messages": []})
    assert result["total"] == 0
```

- [ ] **Step 3: 实现 extraction handler**

Create `src/memory_mcp/workers/handlers/extraction.py`:

```python
"""Job handler: extract memories from a thread message batch.

Payload schema:
    {
        "thread_id": "th-...",
        "message_ids": ["th-...:000001", ...],
        "messages": [{"role": "...", "content": "..."}, ...],
    }
"""

from __future__ import annotations

import logging

from ...engine import extraction as engine_extraction

logger = logging.getLogger("memory-mcp.worker.handler.extraction")


async def handle(payload: dict) -> dict:
    messages = payload.get("messages") or []
    if not messages:
        return {"total": 0, "results": []}

    thread_id = payload.get("thread_id")
    message_ids = payload.get("message_ids") or []
    source_refs = [
        {"thread_id": thread_id, "message_id": mid}
        for mid in message_ids
        if thread_id
    ]
    return await engine_extraction.extract_memories(
        messages,
        source_thread_id=thread_id,
        source_refs=source_refs,
    )
```

> 依赖 M3 升级后的 `engine.extraction.extract_memories(messages, *, source_thread_id, source_refs)` 签名；spec §6.8 stop hook 已要求此调用。

- [ ] **Step 4: 跑测试**

Run: `pytest tests/workers/test_handler_extraction.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/workers/handlers/__init__.py src/memory_mcp/workers/handlers/extraction.py tests/workers/test_handler_extraction.py
git commit -m "feat(worker): add extraction handler with source_refs wiring"
```

### Task 6: title_gen handler

**Files:**
- 新建：`src/memory_mcp/workers/handlers/title_gen.py`
- 新建：`tests/workers/test_handler_title_gen.py`

- [ ] **Step 1: 写失败测试**

Create `tests/workers/test_handler_title_gen.py`:

```python
import pytest

from memory_mcp.workers.handlers import title_gen


@pytest.mark.asyncio
async def test_title_gen_handler_updates_memory_title(tools, test_env, monkeypatch):
    remember, *_ = tools
    res = await remember.remember_tool({
        "content": "I prefer dark mode in all editors and OS-level themes for accessibility reasons.",
        "entity_key": "preference:theme",
        "entity_type": "preference",
    })
    memory_id = res["memory_id"]

    async def fake_llm(_prompt: str) -> str:
        return "Dark mode preference"

    import importlib
    importlib.reload(title_gen)
    monkeypatch.setattr(title_gen, "_call_llm_title", fake_llm)

    result = await title_gen.handle({"memory_id": memory_id})
    assert result["status"] == "updated"
    assert result["title"] == "Dark mode preference"

    from memory_mcp.storage.vector import vector_store
    node = await vector_store.get_by_id(memory_id)
    assert node.title == "Dark mode preference"


@pytest.mark.asyncio
async def test_title_gen_skips_when_memory_missing(tools, test_env):
    result = await title_gen.handle({"memory_id": "nope"})
    assert result["status"] == "missing"


@pytest.mark.asyncio
async def test_title_gen_skips_when_title_already_set(tools, test_env, monkeypatch):
    remember, *_ = tools
    res = await remember.remember_tool({
        "content": "Some content",
        "entity_key": "fact:t",
        "entity_type": "fact",
    })

    from memory_mcp.storage.vector import vector_store
    node = await vector_store.get_by_id(res["memory_id"])
    node.title = "existing"
    await vector_store.update(node)

    async def fake_llm(_prompt: str) -> str:
        raise AssertionError("LLM must not be called when title already set")

    import importlib
    importlib.reload(title_gen)
    monkeypatch.setattr(title_gen, "_call_llm_title", fake_llm)

    result = await title_gen.handle({"memory_id": res["memory_id"]})
    assert result["status"] == "skipped"
```

- [ ] **Step 2: 实现 title_gen handler**

Create `src/memory_mcp/workers/handlers/title_gen.py`:

```python
"""Job handler: generate a short (10-20 char) title for a memory."""

from __future__ import annotations

import logging

import httpx

from ...config import settings
from ...storage.vector import vector_store

logger = logging.getLogger("memory-mcp.worker.handler.title_gen")

_PROMPT = (
    "Generate a short title (10-20 characters, no quotes, no trailing period) "
    "summarizing the following memory. Reply with the title only.\n\n"
    "Memory: {content}"
)


async def _call_llm_title(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://memory-mcp.app",
        "X-Title": "Memory MCP",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers=headers,
            json={
                "model": settings.llm_model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


def _clamp_title(text: str, *, max_chars: int = 20) -> str:
    text = text.strip().strip('"').strip("'").splitlines()[0].strip()
    return text[:max_chars]


async def handle(payload: dict) -> dict:
    memory_id = payload.get("memory_id")
    if not memory_id:
        return {"status": "missing", "reason": "no memory_id"}
    node = await vector_store.get_by_id(memory_id)
    if node is None:
        return {"status": "missing", "memory_id": memory_id}
    if getattr(node, "title", None):
        return {"status": "skipped", "memory_id": memory_id}

    prompt = _PROMPT.format(content=node.content)
    raw = await _call_llm_title(prompt)
    title = _clamp_title(raw)
    node.title = title
    await vector_store.update(node)
    return {"status": "updated", "memory_id": memory_id, "title": title}
```

- [ ] **Step 3: 跑测试**

Run: `pytest tests/workers/test_handler_title_gen.py -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/memory_mcp/workers/handlers/title_gen.py tests/workers/test_handler_title_gen.py
git commit -m "feat(worker): add title_gen handler with LLM-backed short title"
```

### Task 7: summary_gen handler

**Files:**
- 新建：`src/memory_mcp/workers/handlers/summary_gen.py`
- 新建：`tests/workers/test_handler_summary_gen.py`

- [ ] **Step 1: 写失败测试**

Create `tests/workers/test_handler_summary_gen.py`:

```python
import aiosqlite
import pytest

from memory_mcp.workers.handlers import summary_gen


@pytest.fixture()
async def thread_with_messages(jobs_db):
    async with aiosqlite.connect(jobs_db) as db:
        await db.execute(
            "INSERT INTO threads (thread_id, source_provider, source_ref, created_at, imported_at) "
            "VALUES ('th-s', 'claude-code', '/x.jsonl', '2026-05-21T00:00:00+00:00', '2026-05-21T00:00:00+00:00')"
        )
        for seq in range(1, 4):
            await db.execute(
                "INSERT INTO thread_messages (message_id, thread_id, seq, role, content) "
                "VALUES (?, 'th-s', ?, ?, ?)",
                (f"th-s:{seq:06d}", seq, "user" if seq % 2 else "assistant", f"line {seq}"),
            )
        await db.commit()
    return jobs_db


@pytest.mark.asyncio
async def test_summary_gen_writes_threads_summary(thread_with_messages, monkeypatch):
    async def fake_llm(_prompt: str) -> str:
        return "User asked X, assistant answered Y."

    import importlib
    importlib.reload(summary_gen)
    monkeypatch.setattr(summary_gen, "_call_llm_summary", fake_llm)

    result = await summary_gen.handle({"thread_id": "th-s"})
    assert result["status"] == "updated"

    async with aiosqlite.connect(thread_with_messages) as db:
        async with db.execute("SELECT summary FROM threads WHERE thread_id = 'th-s'") as cur:
            (summary,) = await cur.fetchone()
    assert "User asked X" in summary


@pytest.mark.asyncio
async def test_summary_gen_missing_thread_returns_status(jobs_db):
    result = await summary_gen.handle({"thread_id": "absent"})
    assert result["status"] == "missing"


@pytest.mark.asyncio
async def test_summary_gen_skips_empty_thread(thread_with_messages):
    # Wipe messages but keep thread row.
    async with aiosqlite.connect(thread_with_messages) as db:
        await db.execute("DELETE FROM thread_messages WHERE thread_id = 'th-s'")
        await db.commit()
    result = await summary_gen.handle({"thread_id": "th-s"})
    assert result["status"] == "empty"
```

- [ ] **Step 2: 实现 summary_gen handler**

Create `src/memory_mcp/workers/handlers/summary_gen.py`:

```python
"""Job handler: summarize a thread and persist to threads.summary."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ...config import settings
from ...storage.sqlite import get_db

logger = logging.getLogger("memory-mcp.worker.handler.summary_gen")


_PROMPT = (
    "Summarize this conversation in 1-3 sentences. Focus on decisions and outcomes. "
    "Reply with the summary only.\n\nConversation:\n{body}"
)


async def _call_llm_summary(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://memory-mcp.app",
        "X-Title": "Memory MCP",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers=headers,
            json={
                "model": settings.llm_model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def handle(payload: dict) -> dict:
    thread_id = payload.get("thread_id")
    if not thread_id:
        return {"status": "missing", "reason": "no thread_id"}

    async with get_db() as db:
        thread_row = await db.fetchone(
            "SELECT thread_id FROM threads WHERE thread_id = ?", (thread_id,)
        )
        if thread_row is None:
            return {"status": "missing", "thread_id": thread_id}
        rows = await db.fetchall(
            "SELECT role, content FROM thread_messages WHERE thread_id = ? ORDER BY seq ASC",
            (thread_id,),
        )

    if not rows:
        return {"status": "empty", "thread_id": thread_id}

    body = "\n".join(f"[{r['role']}] {r['content']}" for r in rows)
    summary = await _call_llm_summary(_PROMPT.format(body=body))

    async with get_db() as db:
        await db.execute(
            "UPDATE threads SET summary = ? WHERE thread_id = ?",
            (summary, thread_id),
        )
    return {"status": "updated", "thread_id": thread_id, "length": len(summary)}
```

- [ ] **Step 3: 跑测试**

Run: `pytest tests/workers/test_handler_summary_gen.py -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/memory_mcp/workers/handlers/summary_gen.py tests/workers/test_handler_summary_gen.py
git commit -m "feat(worker): add summary_gen handler writing threads.summary"
```

### Task 8: reinforce_decay handler

**Files:**
- 新建：`src/memory_mcp/workers/handlers/reinforce_decay.py`
- 新建：`tests/workers/test_handler_reinforce_decay.py`

- [ ] **Step 1: 写失败测试**

Create `tests/workers/test_handler_reinforce_decay.py`:

```python
import json
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from memory_mcp.workers.handlers import reinforce_decay


@pytest.mark.asyncio
async def test_reinforce_decay_writes_normalized_factors_to_cache(tools, test_env, jobs_db):
    remember, *_ = tools
    res1 = await remember.remember_tool({
        "content": "A", "entity_key": "fact:a", "entity_type": "fact",
    })
    res2 = await remember.remember_tool({
        "content": "B", "entity_key": "fact:b", "entity_type": "fact",
    })

    from memory_mcp.storage.vector import vector_store
    a = await vector_store.get_by_id(res1["memory_id"])
    b = await vector_store.get_by_id(res2["memory_id"])
    # Pretend A has been reinforced 10x and accessed yesterday; B never reinforced
    # and accessed 60 days ago.
    a.reinforce_count = 10  # type: ignore[attr-defined]
    a.last_accessed_at = datetime.now(timezone.utc) - timedelta(days=1)  # type: ignore[attr-defined]
    b.reinforce_count = 0  # type: ignore[attr-defined]
    b.last_accessed_at = datetime.now(timezone.utc) - timedelta(days=60)  # type: ignore[attr-defined]
    await vector_store.update(a)
    await vector_store.update(b)

    result = await reinforce_decay.handle({})
    assert result["processed"] == 2

    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT content FROM working_memory_cache WHERE cache_key = 'reinforce_factors:v1'"
        ) as cur:
            (raw,) = await cur.fetchone()
    data = json.loads(raw)
    # A should have a higher composite factor than B.
    fa = data[res1["memory_id"]]
    fb = data[res2["memory_id"]]
    assert fa["reinforce_factor"] >= fb["reinforce_factor"]
    assert fa["decay_factor"] > fb["decay_factor"]


@pytest.mark.asyncio
async def test_reinforce_decay_does_not_mutate_memory_fields(tools, test_env, jobs_db):
    remember, *_ = tools
    res = await remember.remember_tool({
        "content": "X", "entity_key": "fact:x", "entity_type": "fact",
    })
    from memory_mcp.storage.vector import vector_store
    node = await vector_store.get_by_id(res["memory_id"])
    node.reinforce_count = 7  # type: ignore[attr-defined]
    await vector_store.update(node)

    await reinforce_decay.handle({})

    after = await vector_store.get_by_id(res["memory_id"])
    assert getattr(after, "reinforce_count") == 7  # unchanged
```

- [ ] **Step 2: 实现 reinforce_decay handler**

Create `src/memory_mcp/workers/handlers/reinforce_decay.py`:

```python
"""Job handler: recompute reinforce + decay factors into cache.

Does NOT mutate memory rows. Writes a JSON map {memory_id: {reinforce_factor,
decay_factor}} into working_memory_cache for hybrid_search re-rank to consume.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone

from ...storage.sqlite import get_db
from ...storage.vector import vector_store

logger = logging.getLogger("memory-mcp.worker.handler.reinforce_decay")

_CACHE_KEY = "reinforce_factors:v1"
_DECAY_LAMBDA = float(os.environ.get("MEMORY_MCP_DECAY_LAMBDA", "0.00556"))  # ~1/180


def _reinforce_factor(value: int, peak: int) -> float:
    if peak <= 0:
        return 1.0
    return 1.0 + math.log1p(max(value, 0)) / math.log1p(peak)


def _decay_factor(last_access: datetime | None, now: datetime) -> float:
    if last_access is None:
        return 1.0
    days = max((now - last_access).total_seconds() / 86400.0, 0.0)
    return math.exp(-_DECAY_LAMBDA * days)


async def handle(payload: dict) -> dict:
    now = datetime.now(timezone.utc)
    # list_current returns all current memories; iterate all for normalization.
    nodes = await vector_store.list_current(limit=10_000)
    if not nodes:
        return {"processed": 0}

    peak = max(int(getattr(n, "reinforce_count", 0) or 0) for n in nodes)
    factors: dict[str, dict[str, float]] = {}
    for n in nodes:
        rf = _reinforce_factor(int(getattr(n, "reinforce_count", 0) or 0), peak)
        df = _decay_factor(getattr(n, "last_accessed_at", None), now)
        factors[n.id] = {"reinforce_factor": rf, "decay_factor": df}

    payload_json = json.dumps(factors, ensure_ascii=False)
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO working_memory_cache (cache_key, content, generated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                content = excluded.content,
                generated_at = excluded.generated_at
            """,
            (_CACHE_KEY, payload_json, now.isoformat()),
        )
    return {"processed": len(nodes), "peak_reinforce": peak}
```

- [ ] **Step 3: 跑测试**

Run: `pytest tests/workers/test_handler_reinforce_decay.py -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/memory_mcp/workers/handlers/reinforce_decay.py tests/workers/test_handler_reinforce_decay.py
git commit -m "feat(worker): add reinforce_decay handler caching normalized factors"
```

### Task 9: wm_refresh handler + working_memory.read_cached

**Files:**
- 新建：`src/memory_mcp/workers/handlers/wm_refresh.py`
- 新建：`tests/workers/test_handler_wm_refresh.py`
- 修改：`src/memory_mcp/engine/working_memory.py`

- [ ] **Step 1: 写失败测试 — wm_refresh handler**

Create `tests/workers/test_handler_wm_refresh.py`:

```python
import aiosqlite
import pytest

from memory_mcp.workers.handlers import wm_refresh


@pytest.mark.asyncio
async def test_wm_refresh_writes_briefing_to_cache(tools, test_env, jobs_db):
    remember, *_ = tools
    await remember.remember_tool({
        "content": "Use Cursor",
        "entity_key": "preference:editor",
        "entity_type": "preference",
    })

    result = await wm_refresh.handle({"cache_key": "briefing:default"})
    assert result["status"] == "written"

    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT content FROM working_memory_cache WHERE cache_key = 'briefing:default'"
        ) as cur:
            (briefing,) = await cur.fetchone()
    assert "preference" in briefing


@pytest.mark.asyncio
async def test_wm_refresh_default_cache_key(tools, test_env, jobs_db):
    result = await wm_refresh.handle({})
    assert result["status"] == "written"
    assert result["cache_key"] == "briefing:default"
```

- [ ] **Step 2: 实现 wm_refresh handler**

Create `src/memory_mcp/workers/handlers/wm_refresh.py`:

```python
"""Job handler: regenerate working memory briefing into cache."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ...engine import working_memory
from ...storage.sqlite import get_db

logger = logging.getLogger("memory-mcp.worker.handler.wm_refresh")


async def handle(payload: dict) -> dict:
    cache_key = payload.get("cache_key") or "briefing:default"
    cwd = payload.get("cwd")
    briefing = await working_memory.generate_briefing(cwd=cwd)
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO working_memory_cache (cache_key, content, generated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                content = excluded.content,
                generated_at = excluded.generated_at
            """,
            (cache_key, briefing, now),
        )
    return {"status": "written", "cache_key": cache_key, "length": len(briefing)}
```

- [ ] **Step 3: 写失败测试 — working_memory.read_cached**

Create new test file segment by appending to `tests/test_working_memory.py`:

```python
import aiosqlite
import pytest


@pytest.mark.asyncio
async def test_read_cached_returns_cache_when_present(test_env, jobs_db):
    from memory_mcp.engine import working_memory as wm_mod
    import importlib
    importlib.reload(wm_mod)

    async with aiosqlite.connect(jobs_db) as db:
        await db.execute(
            "INSERT INTO working_memory_cache (cache_key, content, generated_at) "
            "VALUES ('briefing:default', 'CACHED', '2026-05-21T00:00:00+00:00')"
        )
        await db.commit()

    result = await wm_mod.read_cached("briefing:default")
    assert result == "CACHED"


@pytest.mark.asyncio
async def test_read_cached_falls_back_to_generate(tools, test_env, jobs_db):
    remember, *_ = tools
    await remember.remember_tool({
        "content": "Use Cursor",
        "entity_key": "preference:editor",
        "entity_type": "preference",
    })

    from memory_mcp.engine import working_memory as wm_mod
    import importlib
    importlib.reload(wm_mod)

    result = await wm_mod.read_cached("briefing:default")
    assert "preference" in result  # generated, not cached
```

- [ ] **Step 4: 实现 working_memory.read_cached**

Edit `src/memory_mcp/engine/working_memory.py` — 文件末尾追加：

```python
from ..storage.sqlite import get_db


async def read_cached(cache_key: str = "briefing:default", *, cwd: str | None = None) -> str:
    """Read a cached briefing; fall back to generate_briefing() on cache miss."""
    try:
        async with get_db() as db:
            row = await db.fetchone(
                "SELECT content FROM working_memory_cache WHERE cache_key = ?",
                (cache_key,),
            )
        if row and row["content"]:
            return row["content"]
    except Exception:
        # DB unavailable (e.g. before alembic) — fall back gracefully.
        pass
    return await generate_briefing(cwd=cwd)
```

- [ ] **Step 5: 跑两个测试文件**

Run: `pytest tests/workers/test_handler_wm_refresh.py tests/test_working_memory.py -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/workers/handlers/wm_refresh.py src/memory_mcp/engine/working_memory.py tests/workers/test_handler_wm_refresh.py tests/test_working_memory.py
git commit -m "feat(worker): add wm_refresh handler and read_cached fallback"
```

---

## Chunk 5: Worker Loop

### Task 10: worker_loop 主循环

**Files:**
- 新建：`src/memory_mcp/workers/loop.py`
- 新建：`tests/workers/test_loop.py`

- [ ] **Step 1: 写失败测试 — 拉取与 dispatch**

Create `tests/workers/test_loop.py`:

```python
import asyncio

import aiosqlite
import pytest

from memory_mcp.workers import events, loop as loop_mod, queue as qmod


@pytest.mark.asyncio
async def test_worker_dispatches_to_registered_handler(jobs_db, monkeypatch):
    calls: list[dict] = []

    async def fake_handler(payload):
        calls.append(payload)
        return {"ok": True}

    monkeypatch.setattr(
        loop_mod, "JOB_HANDLERS", {"title_gen": fake_handler}, raising=False
    )

    jid = await qmod.enqueue("title_gen", {"memory_id": "m-1"})

    events.shutdown_event.set()  # exit loop after first iteration
    await loop_mod.worker_loop(poll_interval=0.05)

    assert calls == [{"memory_id": "m-1"}]
    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT status FROM jobs WHERE id = ?", (jid,)
        ) as cur:
            (status,) = await cur.fetchone()
    assert status == "done"


@pytest.mark.asyncio
async def test_worker_marks_failed_when_handler_raises(jobs_db, monkeypatch):
    async def boom(_payload):
        raise RuntimeError("nope")

    monkeypatch.setattr(loop_mod, "JOB_HANDLERS", {"title_gen": boom}, raising=False)

    jid = await qmod.enqueue("title_gen", {}, max_attempts=1)

    events.shutdown_event.set()
    await loop_mod.worker_loop(poll_interval=0.05)

    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT status, attempts, error FROM jobs WHERE id = ?", (jid,)
        ) as cur:
            status, attempts, error = await cur.fetchone()
    assert status == "failed"
    assert attempts == 1
    assert "nope" in error


@pytest.mark.asyncio
async def test_worker_timeout_marks_job_failed_or_retry(jobs_db, monkeypatch):
    async def slow(_payload):
        await asyncio.sleep(5)

    monkeypatch.setattr(loop_mod, "JOB_HANDLERS", {"title_gen": slow}, raising=False)
    # Force tiny timeout for the test.
    monkeypatch.setattr(loop_mod, "_TASK_TIMEOUT_SECONDS", 0.05, raising=False)

    jid = await qmod.enqueue("title_gen", {}, max_attempts=1)

    events.shutdown_event.set()
    await loop_mod.worker_loop(poll_interval=0.05)

    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT status, error FROM jobs WHERE id = ?", (jid,)
        ) as cur:
            status, error = await cur.fetchone()
    assert status == "failed"
    assert error  # message contains "TimeoutError" or similar


@pytest.mark.asyncio
async def test_worker_skips_unknown_job_type_with_failure(jobs_db):
    jid = await qmod.enqueue("never_registered", {}, max_attempts=1)
    events.shutdown_event.set()
    await loop_mod.worker_loop(poll_interval=0.05)
    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT status, error FROM jobs WHERE id = ?", (jid,)
        ) as cur:
            status, error = await cur.fetchone()
    assert status == "failed"
    assert "Unknown job_type" in error


@pytest.mark.asyncio
async def test_worker_exits_promptly_on_shutdown(jobs_db):
    # No jobs; ensure the loop sleeps then exits.
    events.shutdown_event.set()
    await asyncio.wait_for(loop_mod.worker_loop(poll_interval=0.05), timeout=2.0)
```

- [ ] **Step 2: 实现 worker_loop**

Create `src/memory_mcp/workers/loop.py`:

```python
"""Worker main loop.

Pulls a batch every `poll_interval` seconds, dispatches each job to a
handler with 120s timeout, marks done / retries / failed accordingly.

Single global asyncio task. Exits when `shutdown_event` is set.
"""

from __future__ import annotations

import asyncio
import logging

from .events import shutdown_event
from .handlers import JOB_HANDLERS
from .queue import fetch_and_lock, mark_done, mark_failed_or_retry

logger = logging.getLogger("memory-mcp.worker.loop")

_TASK_TIMEOUT_SECONDS = 120
_DEFAULT_POLL_INTERVAL = 1.0
_DEFAULT_BATCH = 5


async def _run_job(job) -> None:
    handler = JOB_HANDLERS.get(job.job_type)
    if handler is None:
        await mark_failed_or_retry(job.id, RuntimeError(f"Unknown job_type: {job.job_type}"))
        return
    try:
        await asyncio.wait_for(handler(job.payload), timeout=_TASK_TIMEOUT_SECONDS)
        await mark_done(job.id)
    except asyncio.TimeoutError as exc:
        logger.warning("Job %s (%s) timed out after %ds", job.id, job.job_type, _TASK_TIMEOUT_SECONDS)
        await mark_failed_or_retry(job.id, exc if str(exc) else RuntimeError("TimeoutError"))
    except Exception as exc:
        logger.exception("Job %s (%s) raised: %s", job.id, job.job_type, exc)
        await mark_failed_or_retry(job.id, exc)


async def worker_loop(
    *,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
    batch_size: int = _DEFAULT_BATCH,
) -> None:
    """Main background worker loop. Exits when shutdown_event is set."""
    logger.info("Worker loop starting (poll=%ss, batch=%d)", poll_interval, batch_size)
    while not shutdown_event.is_set():
        try:
            jobs = await fetch_and_lock(limit=batch_size)
        except Exception:
            logger.exception("fetch_and_lock failed; sleeping before retry")
            await _sleep_or_exit(poll_interval)
            continue

        if not jobs:
            await _sleep_or_exit(poll_interval)
            continue

        # Process sequentially; handlers themselves can fan out if they need to.
        for job in jobs:
            if shutdown_event.is_set():
                break
            await _run_job(job)

    logger.info("Worker loop exited")


async def _sleep_or_exit(interval: float) -> None:
    """Sleep but wake immediately if shutdown_event fires."""
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
    except asyncio.TimeoutError:
        pass
```

- [ ] **Step 3: 跑测试**

Run: `pytest tests/workers/test_loop.py -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/memory_mcp/workers/loop.py tests/workers/test_loop.py
git commit -m "feat(worker): add worker_loop with timeout and shutdown handling"
```

---

## Chunk 6: APScheduler

### Task 11: scheduler.py — cron 注册

**Files:**
- 新建：`src/memory_mcp/workers/scheduler.py`
- 新建：`tests/workers/test_scheduler.py`

- [ ] **Step 1: 写失败测试**

Create `tests/workers/test_scheduler.py`:

```python
import asyncio

import aiosqlite
import pytest

from memory_mcp.workers import scheduler as sch_mod


@pytest.mark.asyncio
async def test_build_scheduler_registers_two_cron_jobs():
    scheduler = sch_mod.build_scheduler()
    job_ids = sorted(j.id for j in scheduler.get_jobs())
    assert job_ids == ["reinforce_decay_daily", "wm_refresh_periodic"]


@pytest.mark.asyncio
async def test_enqueue_reinforce_decay_inserts_job(jobs_db):
    await sch_mod._enqueue_reinforce_decay()
    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT job_type, payload FROM jobs WHERE job_type = 'reinforce_decay'"
        ) as cur:
            row = await cur.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_enqueue_wm_refresh_inserts_job(jobs_db):
    await sch_mod._enqueue_wm_refresh()
    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT job_type, payload FROM jobs WHERE job_type = 'wm_refresh'"
        ) as cur:
            row = await cur.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_scheduler_cron_fires_and_enqueues(jobs_db):
    """End-to-end: schedule wm_refresh every 0.1s, wait, expect rows."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    scheduler.add_job(sch_mod._enqueue_wm_refresh, "interval", seconds=0.1, id="wm")
    scheduler.start()
    try:
        await asyncio.sleep(0.35)
    finally:
        scheduler.shutdown(wait=False)

    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM jobs WHERE job_type = 'wm_refresh'"
        ) as cur:
            (count,) = await cur.fetchone()
    assert count >= 2
```

- [ ] **Step 2: 实现 scheduler.py**

Create `src/memory_mcp/workers/scheduler.py`:

```python
"""APScheduler wrapper. Cron jobs only ENQUEUE work; worker_loop runs it."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .queue import enqueue

logger = logging.getLogger("memory-mcp.worker.scheduler")


async def _enqueue_reinforce_decay() -> None:
    await enqueue("reinforce_decay", {})


async def _enqueue_wm_refresh() -> None:
    await enqueue("wm_refresh", {"cache_key": "briefing:default"})


def build_scheduler() -> AsyncIOScheduler:
    """Construct the scheduler with the two cron jobs from spec §8.2."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _enqueue_reinforce_decay,
        "cron",
        hour=3,
        id="reinforce_decay_daily",
        replace_existing=True,
    )
    scheduler.add_job(
        _enqueue_wm_refresh,
        "interval",
        minutes=30,
        id="wm_refresh_periodic",
        replace_existing=True,
    )
    return scheduler
```

- [ ] **Step 3: 跑测试**

Run: `pytest tests/workers/test_scheduler.py -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/memory_mcp/workers/scheduler.py tests/workers/test_scheduler.py
git commit -m "feat(worker): add APScheduler cron registry for decay and wm refresh"
```

---

## Chunk 7: Starlette Lifespan 集成

### Task 12: server lifespan 启动 worker + scheduler + jieba 预热

**Files:**
- 修改：`src/memory_mcp/server.py`
- 新建：`tests/workers/test_lifespan.py`

- [ ] **Step 1: 写失败测试**

Create `tests/workers/test_lifespan.py`:

```python
import asyncio

import aiosqlite
import pytest
from starlette.testclient import TestClient


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_worker(jobs_db, test_env):
    import importlib
    import memory_mcp.server as server_mod
    import memory_mcp.workers.events as events
    importlib.reload(events)
    importlib.reload(server_mod)

    # Enter lifespan; verify a worker task is created and exits on shutdown.
    with TestClient(server_mod.app, raise_server_exceptions=False) as client:
        # health works → app is fully started
        assert client.get("/health").status_code == 200
        # worker_task is exposed on app.state for visibility
        assert server_mod.app.state.worker_task is not None
        assert not server_mod.app.state.worker_task.done()

    # After context exit, the worker should be done.
    await asyncio.sleep(0)  # allow task cleanup
    assert server_mod.app.state.worker_task.done()


@pytest.mark.asyncio
async def test_lifespan_drains_queued_jobs(jobs_db, test_env, monkeypatch):
    """Enqueue before startup; expect it to be processed during lifespan."""
    import importlib
    import memory_mcp.workers.loop as loop_mod
    import memory_mcp.workers.events as events
    import memory_mcp.workers.queue as qmod

    calls: list[dict] = []

    async def fake_handler(payload):
        calls.append(payload)

    importlib.reload(events)
    monkeypatch.setattr(loop_mod, "JOB_HANDLERS", {"title_gen": fake_handler}, raising=False)

    import memory_mcp.server as server_mod
    importlib.reload(server_mod)

    await qmod.enqueue("title_gen", {"memory_id": "m-1"})

    with TestClient(server_mod.app, raise_server_exceptions=False) as client:
        # Wait briefly for the worker to pick it up.
        for _ in range(20):
            if calls:
                break
            await asyncio.sleep(0.1)
        assert calls == [{"memory_id": "m-1"}]
        async with aiosqlite.connect(jobs_db) as db:
            async with db.execute(
                "SELECT status FROM jobs WHERE job_type = 'title_gen' LIMIT 1"
            ) as cur:
                (status,) = await cur.fetchone()
        assert status == "done"
```

- [ ] **Step 2: 重写 server.py 的 lifespan**

Edit `src/memory_mcp/server.py`:

把第 260-273 行的 `streamable_http_app = ...` / `app = Starlette(...)` 整段替换为：

```python
streamable_http_app = StreamableHttpApp(mcp_server, json_response=False)


@contextlib.asynccontextmanager
async def _combined_lifespan(app):
    """Wrap streamable_http lifespan with worker + scheduler + jieba warmup."""
    from .workers.events import shutdown_event, reset_shutdown_event
    from .workers.loop import worker_loop
    from .workers.scheduler import build_scheduler

    reset_shutdown_event()

    # Warm up jieba so the first FTS5 token request is not 200ms slower.
    try:
        import jieba
        jieba.initialize()
    except Exception:
        logger.warning("jieba initialization failed; continuing", exc_info=True)

    scheduler = build_scheduler()
    scheduler.start()
    worker_task = asyncio.create_task(worker_loop(), name="memory-mcp-worker")
    app.state.worker_task = worker_task
    app.state.scheduler = scheduler

    async with streamable_http_app.lifespan(app):
        try:
            yield
        finally:
            # Graceful drain.
            from .workers.events import shutdown_event as _ev
            _ev.set()
            scheduler.shutdown(wait=False)
            try:
                await asyncio.wait_for(worker_task, timeout=30)
            except asyncio.TimeoutError:
                logger.warning("Worker did not drain within 30s; cancelling")
                worker_task.cancel()
                try:
                    await worker_task
                except (asyncio.CancelledError, Exception):
                    pass


app = Starlette(
    lifespan=_combined_lifespan,
    routes=[
        Route("/mcp", endpoint=streamable_http_app, methods=["GET", "POST", "DELETE"]),
        Route("/health", endpoint=health, methods=["GET"]),
        *api_routes,
    ],
    middleware=[
        Middleware(CorsMiddleware),
        Middleware(AuthMiddleware),
    ],
)
```

并在文件头部 imports 区追加：

```python
import asyncio
import contextlib
```

- [ ] **Step 3: 跑测试**

Run: `pytest tests/workers/test_lifespan.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 跑全量测试，确认 server 启动无回归**

Run: `pytest -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/server.py tests/workers/test_lifespan.py
git commit -m "feat(server): integrate worker loop and APScheduler into Starlette lifespan"
```

---

## Chunk 8: 入队触发点改造

### Task 13: /threads/incremental 入队 extraction + 自动 title_gen + summary debounce

**Files:**
- 修改：`src/memory_mcp/api/routes.py`
- 修改：`src/memory_mcp/tools/remember.py`
- 修改：`tests/test_api.py`（如已存在；否则建新测试文件）

> **设计要点**：
> 1. `/threads/incremental` 在 upsert 完成后**不再同步抽 memory**，改为 `enqueue("extraction", {...})`。
> 2. `remember_tool` 在创建新 memory 且 `title` 为空时，自动 `enqueue("title_gen", {memory_id})`。同步路径不阻塞。
> 3. `/threads/incremental` 同 thread 多次推送在 5min 内只 enqueue 一次 `summary_gen`：用 `working_memory_cache` 表记 `summary_debounce:<thread_id>` 时间戳，比较 now - last < 300s 跳过。
> 4. M2 已经同步实现 `hybrid_search` 中的 access_count++（spec D 决策）；M4 不改这个，避免引入 worker 高并发。

- [ ] **Step 1: 写测试 — incremental enqueue extraction**

> 该测试假定 M3 已有 `handle_threads_incremental` 端点。如果端点名/路径不同，对齐到 M3 实际命名即可。

Create or extend `tests/test_api.py` with:

```python
import aiosqlite
import pytest


class TestThreadsIncrementalEnqueuesExtraction:
    def test_incremental_enqueues_extraction_job(self, client, auth_headers, jobs_db):
        payload = {
            "batches": [
                {
                    "provider": "claude-code",
                    "source_ref": "/p/a.jsonl",
                    "thread_meta": {"title": "T"},
                    "messages": [
                        {"seq": 1, "role": "user", "content": "hi"},
                        {"seq": 2, "role": "assistant", "content": "yo"},
                    ],
                }
            ]
        }
        resp = client.post("/api/v1/threads/incremental", json=payload, headers=auth_headers)
        assert resp.status_code == 200

        # Inspect jobs synchronously via raw sqlite (we have jobs_db fixture path)
        import sqlite3
        conn = sqlite3.connect(jobs_db)
        try:
            rows = conn.execute(
                "SELECT job_type, payload FROM jobs WHERE job_type = 'extraction'"
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) >= 1
        import json
        payload_one = json.loads(rows[0][1])
        assert payload_one["thread_id"]
        assert len(payload_one["messages"]) == 2

    def test_incremental_debounces_summary_within_5min(self, client, auth_headers, jobs_db):
        body = {
            "batches": [
                {
                    "provider": "claude-code",
                    "source_ref": "/p/b.jsonl",
                    "thread_meta": {},
                    "messages": [{"seq": 1, "role": "user", "content": "x"}],
                }
            ]
        }
        client.post("/api/v1/threads/incremental", json=body, headers=auth_headers)
        client.post("/api/v1/threads/incremental", json=body, headers=auth_headers)

        import sqlite3
        conn = sqlite3.connect(jobs_db)
        try:
            rows = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE job_type = 'summary_gen'"
            ).fetchall()
        finally:
            conn.close()
        # 5min debounce → only one job should be enqueued for the same thread
        assert rows[0][0] == 1
```

- [ ] **Step 2: 修改 routes.py — `/threads/incremental` 改用入队**

M3 Task 7 已实现 `handle_threads_incremental(request)`，逐 batch 调 `threads_sync.apply_delta(delta)`，返回 `{"results": [{"thread_id", "new_message_ids", ...}], "errors": [...]}`。M4 在「`apply_delta` 之后、`results.append(...)` 之前」插入入队 helper 调用。

Edit `src/memory_mcp/api/routes.py` —— 在文件顶部追加 helper（与其它 helper 放一处）：

```python
from datetime import datetime, timezone, timedelta

from ..storage.sqlite import get_db
from ..workers.queue import enqueue as worker_enqueue


async def _maybe_enqueue_summary(thread_id: str) -> None:
    """Debounce summary_gen to 5 minutes per thread_id.

    Uses ``working_memory_cache`` as the debounce store: ``cache_key`` =
    ``summary_debounce:<thread_id>``, ``generated_at`` = last enqueue ts.
    """
    debounce_key = f"summary_debounce:{thread_id}"
    now = datetime.now(timezone.utc)
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT generated_at FROM working_memory_cache WHERE cache_key = ?",
            (debounce_key,),
        )
        if row:
            last = datetime.fromisoformat(row["generated_at"])
            if now - last < timedelta(minutes=5):
                return
        await db.execute(
            """
            INSERT INTO working_memory_cache (cache_key, content, generated_at)
            VALUES (?, '', ?)
            ON CONFLICT(cache_key) DO UPDATE SET generated_at = excluded.generated_at
            """,
            (debounce_key, now.isoformat()),
        )
    await worker_enqueue("summary_gen", {"thread_id": thread_id})


async def _enqueue_extraction(thread_id: str, message_ids: list[str], messages: list[dict]) -> None:
    if not messages:
        return
    await worker_enqueue(
        "extraction",
        {
            "thread_id": thread_id,
            "message_ids": message_ids,
            "messages": messages,
        },
    )
```

然后在 `handle_threads_incremental` 内 `apply_delta` 返回后插入两次 helper 调用。M3 的循环结构如下（节选），M4 加入入队的最终版本：

```python
async def handle_threads_incremental(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return err("Invalid JSON body")
    batches = body.get("batches")
    if not isinstance(batches, list) or not batches:
        return err("batches must be a non-empty list")
    results = []
    errors = []
    for batch in batches:
        try:
            delta = _coerce_batch_to_delta(batch)
            mtime = batch.get("mtime")
            result = await threads_sync.apply_delta(delta, mtime=mtime)
            # === M4 enqueue: extraction + debounced summary ===
            await _enqueue_extraction(
                thread_id=result["thread_id"],
                message_ids=result.get("new_message_ids", []),
                messages=[
                    {"role": m["role"], "content": m["content"]}
                    for m in (batch.get("messages") or [])
                ],
            )
            await _maybe_enqueue_summary(result["thread_id"])
            results.append({**result, "source_ref": delta.source_ref})
        except KeyError as exc:
            errors.append({"batch_ref": batch.get("source_ref"), "error": f"unknown provider: {exc}"})
        except ValueError as exc:
            errors.append({"batch_ref": batch.get("source_ref"), "error": str(exc)})
        except Exception as exc:
            errors.append({"batch_ref": batch.get("source_ref"), "error": str(exc)})
    return ok({"results": results, "errors": errors})
```

> 上面是**完整覆盖 handler 的最终版本**，可直接 paste 替换 M3 Task 7 的实现（注意保留 M3 已在文件中导入的 `threads_sync` / `_coerce_batch_to_delta`）。

- [ ] **Step 3: 修改 remember_tool — 自动 title_gen**

Edit `src/memory_mcp/tools/remember.py` — 在第 134 行 `await vector_store.insert(new_node)` 之后、`await graph_store.upsert_entity(...)` 之前/之后均可，但在 return 之前追加：

```python
    # M4: schedule title generation if missing.
    if not getattr(new_node, "title", None):
        try:
            from ..workers.queue import enqueue as _enqueue
            await _enqueue("title_gen", {"memory_id": new_node.id})
        except Exception:  # noqa: BLE001 — don't fail the user write on queue errors
            pass
```

> 同样的 hook 也加在 `evolve_memory` 分支：找到第 78 行 `return { "status": "evolved", ... }` 之前插入相同 3 行（用 `new_node.id`）。

- [ ] **Step 4: 写 remember 触发 title_gen 的测试**

Append to `tests/test_tools.py`:

```python
def test_remember_enqueues_title_gen_when_no_title(tools, test_env, jobs_db):
    async def run():
        remember, *_ = tools
        res = await remember.remember_tool({
            "content": "X",
            "entity_key": "fact:x",
            "entity_type": "fact",
        })
        import sqlite3
        conn = sqlite3.connect(jobs_db)
        try:
            rows = conn.execute(
                "SELECT payload FROM jobs WHERE job_type = 'title_gen'"
            ).fetchall()
        finally:
            conn.close()
        import json
        payloads = [json.loads(r[0]) for r in rows]
        assert any(p["memory_id"] == res["memory_id"] for p in payloads)
    anyio.run(run)
```

- [ ] **Step 5: 跑测试**

Run: `pytest tests/test_api.py::TestThreadsIncrementalEnqueuesExtraction tests/test_tools.py::test_remember_enqueues_title_gen_when_no_title -v`
Expected: 全部 PASS（M3 端点存在的前提下）

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/api/routes.py src/memory_mcp/tools/remember.py tests/test_api.py tests/test_tools.py
git commit -m "feat(worker): enqueue extraction/title/summary jobs from request path"
```

---

## Chunk 9: Jobs 监控 REST API

### Task 14: GET /api/v1/jobs 列表

**Files:**
- 修改：`src/memory_mcp/api/routes.py`
- 新建：`tests/workers/test_jobs_api.py`

- [ ] **Step 1: 写失败测试**

Create `tests/workers/test_jobs_api.py`:

```python
import pytest
from starlette.testclient import TestClient

from memory_mcp.workers import queue as qmod


@pytest.fixture()
def client(jobs_db, test_env):
    import importlib
    import memory_mcp.server as server_mod
    importlib.reload(server_mod)
    return TestClient(server_mod.app, raise_server_exceptions=False)


@pytest.fixture()
def auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_list_jobs_returns_paginated(client, auth_headers):
    for _ in range(3):
        await qmod.enqueue("title_gen", {})
    resp = client.get("/api/v1/jobs", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["total"] == 3
    assert len(body["data"]["items"]) == 3


@pytest.mark.asyncio
async def test_list_jobs_filters_by_status(client, auth_headers):
    jid_done = await qmod.enqueue("title_gen", {})
    (job,) = await qmod.fetch_and_lock(limit=1)
    await qmod.mark_done(job.id)
    await qmod.enqueue("title_gen", {})

    resp = client.get("/api/v1/jobs?status=done", headers=auth_headers)
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == jid_done


@pytest.mark.asyncio
async def test_list_jobs_filters_by_job_type(client, auth_headers):
    await qmod.enqueue("title_gen", {})
    await qmod.enqueue("wm_refresh", {})

    resp = client.get("/api/v1/jobs?job_type=wm_refresh", headers=auth_headers)
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["job_type"] == "wm_refresh"


@pytest.mark.asyncio
async def test_list_jobs_supports_pagination(client, auth_headers):
    for _ in range(5):
        await qmod.enqueue("title_gen", {})
    resp = client.get("/api/v1/jobs?page=2&size=2", headers=auth_headers)
    body = resp.json()
    assert body["data"]["page"] == 2
    assert body["data"]["size"] == 2
    assert body["data"]["total"] == 5
    assert len(body["data"]["items"]) == 2
```

- [ ] **Step 2: 实现 list jobs**

Append to `src/memory_mcp/api/routes.py`:

```python
from starlette.requests import Request as _JReq
from starlette.responses import JSONResponse as _JRes

from ..storage.sqlite import get_db as _jobs_get_db


_JOB_COLUMNS = [
    "id",
    "job_type",
    "payload",
    "status",
    "attempts",
    "max_attempts",
    "scheduled_at",
    "started_at",
    "finished_at",
    "next_retry_at",
    "error",
    "created_at",
]


def _row_to_dict(row) -> dict:
    import json as _json
    d = {col: row[col] for col in _JOB_COLUMNS}
    if d.get("payload"):
        try:
            d["payload"] = _json.loads(d["payload"])
        except Exception:
            pass
    return d


# GET /api/v1/jobs
async def handle_list_jobs(request: _JReq) -> _JRes:
    params = request.query_params
    status_filter = params.get("status")
    type_filter = params.get("job_type")
    try:
        page = max(int(params.get("page", "1")), 1)
        size = min(max(int(params.get("size", "50")), 1), 200)
    except ValueError:
        return err("page/size must be integers")

    where_clauses = []
    args: list = []
    if status_filter:
        where_clauses.append("status = ?")
        args.append(status_filter)
    if type_filter:
        where_clauses.append("job_type = ?")
        args.append(type_filter)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    offset = (page - 1) * size
    async with _jobs_get_db() as db:
        total_row = await db.fetchone(f"SELECT COUNT(*) AS c FROM jobs {where_sql}", args)
        total = int(total_row["c"]) if total_row else 0
        rows = await db.fetchall(
            f"""
            SELECT {", ".join(_JOB_COLUMNS)} FROM jobs
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*args, size, offset),
        )
    items = [_row_to_dict(r) for r in rows]
    return ok({"items": items, "total": total, "page": page, "size": size})
```

把 `Route("/api/v1/jobs", endpoint=handle_list_jobs, methods=["GET"])` 加到 `routes = [ ... ]` 列表里。

- [ ] **Step 3: 跑测试**

Run: `pytest tests/workers/test_jobs_api.py::test_list_jobs_returns_paginated tests/workers/test_jobs_api.py::test_list_jobs_filters_by_status tests/workers/test_jobs_api.py::test_list_jobs_filters_by_job_type tests/workers/test_jobs_api.py::test_list_jobs_supports_pagination -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/memory_mcp/api/routes.py tests/workers/test_jobs_api.py
git commit -m "feat(api): GET /api/v1/jobs with status/type filter and pagination"
```

### Task 15: GET / retry / cancel single job

**Files:**
- 修改：`src/memory_mcp/api/routes.py`
- 修改：`tests/workers/test_jobs_api.py`

- [ ] **Step 1: 写失败测试**

Append to `tests/workers/test_jobs_api.py`:

```python
@pytest.mark.asyncio
async def test_get_job_returns_single_row(client, auth_headers):
    jid = await qmod.enqueue("title_gen", {"k": 1})
    resp = client.get(f"/api/v1/jobs/{jid}", headers=auth_headers)
    body = resp.json()
    assert body["data"]["id"] == jid
    assert body["data"]["payload"] == {"k": 1}


@pytest.mark.asyncio
async def test_get_job_returns_404_when_missing(client, auth_headers):
    resp = client.get("/api/v1/jobs/nope", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["ok"] is False


@pytest.mark.asyncio
async def test_retry_resets_pending_attempts_zero(client, auth_headers, jobs_db):
    jid = await qmod.enqueue("title_gen", {}, max_attempts=1)
    (job,) = await qmod.fetch_and_lock(limit=1)
    await qmod.mark_failed_or_retry(job.id, RuntimeError("boom"))  # marks failed
    resp = client.post(f"/api/v1/jobs/{jid}/retry", headers=auth_headers)
    assert resp.status_code == 200

    import sqlite3
    conn = sqlite3.connect(jobs_db)
    try:
        row = conn.execute(
            "SELECT status, attempts, next_retry_at, error FROM jobs WHERE id = ?",
            (jid,),
        ).fetchone()
    finally:
        conn.close()
    status, attempts, next_retry_at, error = row
    assert status == "pending"
    assert attempts == 0
    assert next_retry_at is None
    assert error is None


@pytest.mark.asyncio
async def test_cancel_marks_failed_with_user_message(client, auth_headers, jobs_db):
    jid = await qmod.enqueue("title_gen", {})
    resp = client.post(f"/api/v1/jobs/{jid}/cancel", headers=auth_headers)
    assert resp.status_code == 200

    import sqlite3
    conn = sqlite3.connect(jobs_db)
    try:
        row = conn.execute(
            "SELECT status, error FROM jobs WHERE id = ?", (jid,)
        ).fetchone()
    finally:
        conn.close()
    status, error = row
    assert status == "failed"
    assert "cancelled by user" in error
```

- [ ] **Step 2: 实现 3 个端点**

Append to `src/memory_mcp/api/routes.py`:

```python
from datetime import datetime as _dt, timezone as _tz


# GET /api/v1/jobs/{job_id}
async def handle_get_job(request: _JReq) -> _JRes:
    job_id = request.path_params["job_id"]
    async with _jobs_get_db() as db:
        row = await db.fetchone(
            f"SELECT {', '.join(_JOB_COLUMNS)} FROM jobs WHERE id = ?",
            (job_id,),
        )
    if row is None:
        return err("job not found", 404)
    return ok(_row_to_dict(row))


# POST /api/v1/jobs/{job_id}/retry
async def handle_retry_job(request: _JReq) -> _JRes:
    job_id = request.path_params["job_id"]
    now = _dt.now(_tz.utc).isoformat()
    async with _jobs_get_db() as db:
        exists = await db.fetchone("SELECT id FROM jobs WHERE id = ?", (job_id,))
        if exists is None:
            return err("job not found", 404)
        await db.execute(
            """
            UPDATE jobs
               SET status = 'pending',
                   attempts = 0,
                   scheduled_at = ?,
                   started_at = NULL,
                   finished_at = NULL,
                   next_retry_at = NULL,
                   error = NULL
             WHERE id = ?
            """,
            (now, job_id),
        )
    return ok({"id": job_id, "status": "pending"})


# POST /api/v1/jobs/{job_id}/cancel
async def handle_cancel_job(request: _JReq) -> _JRes:
    job_id = request.path_params["job_id"]
    now = _dt.now(_tz.utc).isoformat()
    async with _jobs_get_db() as db:
        row = await db.fetchone("SELECT status FROM jobs WHERE id = ?", (job_id,))
        if row is None:
            return err("job not found", 404)
        if row["status"] == "running":
            # We can't cancel an in-flight asyncio task remotely; record intent.
            await db.execute(
                "UPDATE jobs SET error = ? WHERE id = ?",
                ("cancelled by user (job was running, will fail on completion)", job_id),
            )
            return ok({"id": job_id, "status": "running", "note": "cancellation requested"})
        await db.execute(
            """
            UPDATE jobs
               SET status = 'failed',
                   finished_at = ?,
                   error = 'cancelled by user'
             WHERE id = ?
            """,
            (now, job_id),
        )
    return ok({"id": job_id, "status": "failed"})
```

把以下 3 行加入 `routes = [...]`：

```python
    Route("/api/v1/jobs", endpoint=handle_list_jobs, methods=["GET"]),
    Route("/api/v1/jobs/{job_id}", endpoint=handle_get_job, methods=["GET"]),
    Route("/api/v1/jobs/{job_id}/retry", endpoint=handle_retry_job, methods=["POST"]),
    Route("/api/v1/jobs/{job_id}/cancel", endpoint=handle_cancel_job, methods=["POST"]),
```

- [ ] **Step 3: 跑测试**

Run: `pytest tests/workers/test_jobs_api.py -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/memory_mcp/api/routes.py tests/workers/test_jobs_api.py
git commit -m "feat(api): add jobs detail/retry/cancel endpoints"
```

---

## Chunk 10: 端到端集成 & failure-path 测试

### Task 16: 集成测试 — extraction job end-to-end

**Files:**
- 新建：`tests/workers/test_integration.py`

- [ ] **Step 1: 写集成测试**

Create `tests/workers/test_integration.py`:

```python
import asyncio
import json

import aiosqlite
import pytest

from memory_mcp.workers import events, loop as loop_mod, queue as qmod


@pytest.mark.asyncio
async def test_extraction_job_end_to_end(tools, test_env, jobs_db, monkeypatch):
    """enqueue extraction → worker_loop picks it up → memory written with refs."""
    # Stub the LLM
    import memory_mcp.engine.extraction as eng
    import importlib
    importlib.reload(eng)

    async def fake_llm(_messages):
        return json.dumps(
            [{"entity_key": "fact:int", "entity_type": "fact", "content": "Integration fact"}]
        )

    monkeypatch.setattr(eng, "_call_llm", fake_llm)

    # Seed thread row so source_refs FK is valid
    async with aiosqlite.connect(jobs_db) as db:
        await db.execute(
            "INSERT INTO threads (thread_id, source_provider, source_ref, created_at, imported_at) "
            "VALUES ('th-int', 'claude-code', '/x.jsonl', '2026-05-21T00:00:00+00:00', '2026-05-21T00:00:00+00:00')"
        )
        await db.execute(
            "INSERT INTO thread_messages (message_id, thread_id, seq, role, content) "
            "VALUES ('th-int:000001', 'th-int', 1, 'user', 'remember integration fact')"
        )
        await db.commit()

    jid = await qmod.enqueue(
        "extraction",
        {
            "thread_id": "th-int",
            "message_ids": ["th-int:000001"],
            "messages": [{"role": "user", "content": "remember integration fact"}],
        },
    )

    # Run loop briefly.
    async def stop_after(delay):
        await asyncio.sleep(delay)
        events.shutdown_event.set()

    await asyncio.gather(
        loop_mod.worker_loop(poll_interval=0.05),
        stop_after(1.0),
    )

    # Job is done
    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute("SELECT status FROM jobs WHERE id = ?", (jid,)) as cur:
            (status,) = await cur.fetchone()
    assert status == "done"

    # Memory is present + source_refs wired
    from memory_mcp.storage.vector import vector_store
    nodes = await vector_store.list_current()
    target = next(n for n in nodes if n.entity_key == "fact:int")
    assert getattr(target, "source_thread_id", None) == "th-int"


@pytest.mark.asyncio
async def test_failed_handler_marks_failed_after_max_attempts(jobs_db, monkeypatch):
    async def always_fail(_payload):
        raise RuntimeError("perma")

    monkeypatch.setattr(loop_mod, "JOB_HANDLERS", {"title_gen": always_fail}, raising=False)

    jid = await qmod.enqueue("title_gen", {}, max_attempts=3)

    # Loop until the job lands in 'failed' or we burn 3 seconds.
    async def driver():
        # Force three iterations by clearing next_retry_at between failures.
        for _ in range(3):
            async with aiosqlite.connect(jobs_db) as db:
                await db.execute(
                    "UPDATE jobs SET next_retry_at = NULL, status = 'pending' WHERE status = 'pending'"
                )
                await db.commit()
            (job,) = await qmod.fetch_and_lock(limit=1)
            await loop_mod._run_job(job)

    await driver()

    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute("SELECT status, attempts, error FROM jobs WHERE id = ?", (jid,)) as cur:
            status, attempts, error = await cur.fetchone()
    assert status == "failed"
    assert attempts == 3
    assert "perma" in error


@pytest.mark.asyncio
async def test_jobs_api_can_observe_failed_job(jobs_db, monkeypatch):
    """A failed job must be visible & retryable via the REST API."""
    from starlette.testclient import TestClient
    import importlib
    import memory_mcp.server as server_mod
    importlib.reload(server_mod)
    headers = {"Authorization": "Bearer test-token"}

    jid = await qmod.enqueue("title_gen", {}, max_attempts=1)
    (job,) = await qmod.fetch_and_lock(limit=1)
    await qmod.mark_failed_or_retry(job.id, RuntimeError("first"))

    with TestClient(server_mod.app, raise_server_exceptions=False) as client:
        resp = client.get(f"/api/v1/jobs/{jid}", headers=headers)
        assert resp.json()["data"]["status"] == "failed"

        resp = client.post(f"/api/v1/jobs/{jid}/retry", headers=headers)
        assert resp.status_code == 200

        resp = client.get(f"/api/v1/jobs/{jid}", headers=headers)
        assert resp.json()["data"]["status"] == "pending"
        assert resp.json()["data"]["attempts"] == 0
```

- [ ] **Step 2: 跑测试**

Run: `pytest tests/workers/test_integration.py -v`
Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/workers/test_integration.py
git commit -m "test(worker): add end-to-end extraction and failure-path integration tests"
```

### Task 17: 集成测试 — scheduler 触发 → 消费

**Files:**
- 修改：`tests/workers/test_integration.py`

- [ ] **Step 1: 追加 scheduler 端到端测试**

Append to `tests/workers/test_integration.py`:

```python
@pytest.mark.asyncio
async def test_scheduler_triggers_and_worker_consumes_wm_refresh(
    tools, test_env, jobs_db
):
    """APScheduler interval → enqueue → worker_loop consumes → cache updated."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from memory_mcp.workers import scheduler as sch

    remember, *_ = tools
    await remember.remember_tool({
        "content": "Use Cursor",
        "entity_key": "preference:editor",
        "entity_type": "preference",
    })

    scheduler = AsyncIOScheduler()
    scheduler.add_job(sch._enqueue_wm_refresh, "interval", seconds=0.2, id="wm")
    scheduler.start()

    async def stop_after(delay):
        await asyncio.sleep(delay)
        events.shutdown_event.set()
        scheduler.shutdown(wait=False)

    await asyncio.gather(
        loop_mod.worker_loop(poll_interval=0.05),
        stop_after(1.2),
    )

    async with aiosqlite.connect(jobs_db) as db:
        async with db.execute(
            "SELECT content FROM working_memory_cache WHERE cache_key = 'briefing:default'"
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert "preference" in row[0]
```

- [ ] **Step 2: 跑测试**

Run: `pytest tests/workers/test_integration.py::test_scheduler_triggers_and_worker_consumes_wm_refresh -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/workers/test_integration.py
git commit -m "test(worker): add scheduler → enqueue → consume end-to-end test"
```

---

## Chunk 11: 文档与最终验证

### Task 18: 全量测试 + AGENTS.md changelog

- [ ] **Step 1: 跑全量测试**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest -v`
Expected: 全部 PASS（含原 M1/M2/M3 测试与新增 worker 测试）

- [ ] **Step 2: 跑 lint**

Run: `cd /Users/kassol/Workspace/memory-mcp && ruff check src/memory_mcp/workers src/memory_mcp/api/routes.py src/memory_mcp/server.py tests/workers`
Expected: 无 error（warning 视情况）

- [ ] **Step 3: 更新 AGENTS.md**

Append to the changelog section of `AGENTS.md`:

```markdown
### 2026-05-21 M4 Background Worker
- 新增 `src/memory_mcp/workers/` 子系统：`queue` / `loop` / `scheduler` / `handlers/*`
- 5 个 job_type：extraction / title_gen / summary_gen / reinforce_decay / wm_refresh
- 同进程 asyncio worker，单任务 120s 超时，指数退避 1min/5min/25min，max_attempts=3
- APScheduler cron：reinforce_decay 每日 03:00（UTC），wm_refresh 每 30min；实际工作通过 enqueue 派发
- Starlette lifespan：startup 启动 scheduler + worker_task + jieba 预热；shutdown 优雅 drain 30s
- `/threads/incremental` 改为入队 extraction job；同 thread 内 5min debounce summary_gen；新建 memory 自动入队 title_gen
- 新增 REST 端点：GET /api/v1/jobs（filter + page）/ GET /api/v1/jobs/{id} / POST /api/v1/jobs/{id}/retry / POST /api/v1/jobs/{id}/cancel
- `engine/working_memory.py` 新增 `read_cached()`：优先读 `working_memory_cache`，miss 退化 generate
- 测试覆盖：queue 5 + loop 5 + scheduler 4 + 5 handlers + jobs API 7 + lifespan 2 + integration 4
```

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS.md changelog for M4 background worker"
```

- [ ] **Step 5: 手动 smoke test**

```bash
# 1. 启动服务（使用临时 data_dir 避免污染开发数据）
cd /Users/kassol/Workspace/memory-mcp
MEMORY_MCP_VECTOR_BACKEND=memory \
MEMORY_MCP_AUTH_TOKEN=dev \
MEMORY_MCP_OPENROUTER_API_KEY=test \
MEMORY_MCP_DATA_DIR=/tmp/m4-smoke \
python -m memory_mcp &
sleep 3

# 2. 创建一条 memory（应该自动 enqueue title_gen）
curl -s -X POST http://localhost:8765/api/v1/memories \
  -H "Authorization: Bearer dev" \
  -H "Content-Type: application/json" \
  -d '{"content":"smoke test","entity_key":"fact:smoke","entity_type":"fact"}' | jq

# 3. 查 jobs
curl -s "http://localhost:8765/api/v1/jobs?job_type=title_gen" \
  -H "Authorization: Bearer dev" | jq '.data.total'

# 4. retry 任意 failed job
JID=$(curl -s "http://localhost:8765/api/v1/jobs?status=failed&size=1" \
  -H "Authorization: Bearer dev" | jq -r '.data.items[0].id // empty')
if [ -n "$JID" ]; then
  curl -s -X POST "http://localhost:8765/api/v1/jobs/$JID/retry" -H "Authorization: Bearer dev" | jq
fi

# 5. 关服
kill %1
```

Expected：步骤 3 返回 ≥ 1；步骤 4 若有 failed job 能返回 `{"ok": true, ...}`。

---

## Punted / 后续

- **生产 sqlite-vec / FTS5 trigger 校验**：M1 / M2 / M3 已实现的部分本计划不重复测试，仅在 jobs/working_memory_cache/threads/thread_messages 子集上断言。
- **APScheduler persistent job store**：当前用 default MemoryJobStore，重启即恢复；spec 未要求 cron 持久化。
- **Web UI 监控面板**：M5 任务，本计划只提供 REST API。
- **Codex / chatwise extraction handler 调整**：等 Sir 提供 fixture 后在 M3/M4 之外的小 PR 处理。
- **`access_count` 改为入队**：spec §11 已建议保持同步，避免 worker 高并发风暴。本计划不动 hybrid_search 中的 access 同步逻辑。

---

## 修复记录

> 2026-05-21 plan 修复（codex 评审）：
>
> - **Architecture 注**：明确所有 worker / handler / queue / API 走 M1 `get_db()`；删除 `MEMORY_MCP_DB_PATH` 环境变量，唯一文件路径走 `settings.sqlite_path`。
> - **Task 2（jobs_db fixture）**：rewrite — fixture 直接复用 M1 `test_env` 与 `settings.sqlite_path`，不再独立 `_JOBS_SCHEMA` executescript，避免「test 文件 ≠ 生产文件」漂移。
> - **Task 3-4（queue.py）**：`enqueue` / `fetch_and_lock` / `mark_done` / `mark_failed_or_retry` 全部从 `aiosqlite.connect(_db_path())` 切到 `async with get_db() as db:`；`fetch_and_lock` 用 `DBHandle.transaction()` 而非裸 `BEGIN IMMEDIATE`；引入共享 `_JOB_COLUMNS` 常量，row → Job 改为按 name 取列（aiosqlite.Row）。
> - **测试约定（Task 3 Step 1 顶部）**：插入约定块——所有 M4 测试统一用 `get_db()` 读 jobs/wm_cache 表；后续 Task 4-17 的 `aiosqlite.connect(jobs_db)` 调用按同模式替换（一次性归一，避免每个测试 case 都重写）。
> - **Task 7-9 handlers**：summary_gen / reinforce_decay / wm_refresh / working_memory.read_cached 全部移除 `_db_path` helper + `aiosqlite.connect`，统一 `get_db()`。
> - **Task 13（/threads/incremental 入队）**：删除「伪锚点 `# === M4 enqueue hook ===`」+ 「`os.environ.get('MEMORY_MCP_DB_PATH')`」，给出完整可粘贴的 `handle_threads_incremental` 最终版（保留 M3 已写的 `_coerce_batch_to_delta` / `threads_sync` 导入）。
> - **Task 14-15（jobs REST）**：全部 `aiosqlite.connect(_jobs_db_path())` → `_jobs_get_db`；列访问改 `row["col"]`；`_JOB_COLUMNS` 改为 list 便于 join。
> - **Task 12（lifespan）**：「FastAPI lifespan」措辞统一为「Starlette lifespan」（项目根本就只用 Starlette + StreamableHttpApp）。
> - **Task 18 smoke**：`MEMORY_MCP_DB_PATH=./data/m4-smoke.db` 改为 `MEMORY_MCP_DATA_DIR=/tmp/m4-smoke`，与 M1 settings 一致。
