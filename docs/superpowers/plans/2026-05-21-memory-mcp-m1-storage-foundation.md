# Memory MCP — M1 存储底座实施计划

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans (or superpowers:subagent-driven-development if subagents are available) to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. Every code-writing step ships a complete, copy-pasteable block — no pseudocode, no TODO/TBD/placeholder.

**Goal:** 把存储栈从「LanceDB payload + NetworkX JSON」搬到「SQLite v2 schema + LanceDB 精简 (id, vector) + 运行时按需构建 NetworkX graph」，并通过破坏性 v1→v2 迁移脚本把现有生产数据搬过去；老的 7 个 MCP tools 对外契约保持不变。

**Architecture:**
- SQLite 升级为主存储（memories / entities / relations / threads / thread_messages / jobs / working_memory_cache + FTS5 + 触发器），通过 aiosqlite 异步访问。
- LanceDB 退到「只存 `(id, vector)`」的辅助索引；运行时检索流程是「LanceDB ANN 拿候选 ID → SQLite WHERE id IN (...) 拿元数据」。
- `GraphStore` 改为运行时从 SQLite 加载 `entities`/`relations` 到 `nx.MultiDiGraph`，写时双写（SQLite + 内存图），不再持久化 JSON。
- `MemoryNode` 扩展 v2 字段（title / title_tokens / content_tokens / review_status / origin_client / origin_session_id / source_thread_id / source_refs / access_count / last_accessed_at / reinforce_count）。
- alembic 管理 schema 版本；FastAPI lifespan 启动时自动 `upgrade head`。
- jieba 应用层分词，在写 memories 时填充 `content_tokens`/`title_tokens`，FTS5 用 `unicode61` 命中。
- M1 不动 tools 对外契约，新字段全部走默认值；hybrid search / memory_crud / threads / worker 留给 M2-M4。

**Tech Stack:**
- Python 3.11+
- aiosqlite 0.22.x（异步 SQLite）
- alembic 1.18.x（schema 版本化）
- jieba（应用层中文分词，无 C 编译）
- LanceDB 0.30.x + pyarrow 24.x（保留）
- NetworkX 3.6.x（保留，运行时使用）
- pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-05-21-memory-mcp-agent-kernel-design.md`（§3 架构 / §4 schema / §9 迁移 / §11 M1 范围 / §13 风险 / §15 依赖版本）

---

## File Structure

### Source code

| File | Action | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | Modify | 新增 `aiosqlite>=0.22`、`alembic>=1.18`、`jieba` 依赖 |
| `requirements.lock` | Modify | 锁定新依赖版本 |
| `src/memory_mcp/config.py` | Modify | 新增 `sqlite_path` 派生属性、`alembic_url` 派生属性、`auto_migrate` 开关 |
| `src/memory_mcp/storage/schema.sql` | Create | DDL 参考（注释，权威在 alembic） |
| `src/memory_mcp/storage/sqlite.py` | Create | `SQLiteStore`：连接管理 / pragmas / `get_db()` 返回 `DBHandle`（统一 `execute/executemany/fetchone/fetchall/transaction()`），并提供模块级 `get_db()` async context 给 M2/M3/M4 复用 |
| `src/memory_mcp/storage/migrations/__init__.py` | Create | 空 |
| `src/memory_mcp/storage/migrations/env.py` | Create | alembic env 入口（aiosqlite-compatible） |
| `src/memory_mcp/storage/migrations/script.py.mako` | Create | alembic 模板 |
| `src/memory_mcp/storage/migrations/versions/__init__.py` | Create | 空 |
| `src/memory_mcp/storage/migrations/versions/0001_initial_v2.py` | Create | v2 全表 DDL + FTS5 + 触发器 + 索引 |
| `src/memory_mcp/storage/migrate.py` | Create | `run_migrations()` 程序化调用 alembic upgrade head |
| `alembic.ini` | Create | alembic 配置文件（仓库根） |
| `src/memory_mcp/storage/repositories/__init__.py` | Create | 空 |
| `src/memory_mcp/storage/repositories/memories.py` | Create | `MemoryRepository`：基于 SQLite 的 CRUD + history + list_current |
| `src/memory_mcp/storage/repositories/entities.py` | Create | `EntityRepository`：upsert / list / clear_current |
| `src/memory_mcp/storage/repositories/relations.py` | Create | `RelationRepository`：insert / delete / fetch_by_entity |
| `src/memory_mcp/storage/vector.py` | Modify | LanceDB 精简到 `(id, vector)`；保留 InMemoryVectorStore 作为 fallback；search 只返回 `(id, distance)` 元组；高层 `VectorStore` 调用 `MemoryRepository` 拼装 `MemoryNode` |
| `src/memory_mcp/storage/graph.py` | Modify | `GraphStore` 改为运行时按需从 SQLite 加载到 `nx.MultiDiGraph`；不再持久化 JSON；新增 `reload()` |
| `src/memory_mcp/engine/tokenizer.py` | Create | `tokenize(text) -> str`（jieba.cut 空格连接）+ 自定义词典 hook + lazy 初始化 |
| `src/memory_mcp/engine/models.py` | Modify | `MemoryNode` 增加 v2 字段（α/β/γ/δ/ε 五组）；`Entity` / `Relation` 字段补齐 |
| `src/memory_mcp/storage/serializers.py` | Create | `MemoryNode <-> sqlite row` 双向转换（JSON 列处理） |
| `src/memory_mcp/scripts/__init__.py` | Create | 空 |
| `src/memory_mcp/scripts/migrate_v1_to_v2.py` | Create | v1 (LanceDB payload + NetworkX JSON) → v2 (SQLite v2 + LanceDB 精简) 一次性迁移脚本（typer CLI） |
| `cli/src/memory_mcp_cli/main.py` | Modify | 新增 `mem db upgrade/downgrade/current/history` 子命令组（M6 runbook 依赖） |
| `src/memory_mcp/server.py` | Modify | lifespan 中调用 `run_migrations()`；`/health` 返回 `{status, vector_backend, sqlite_path, schema_version}` |
| `src/memory_mcp/__main__.py` | Modify | 启动前确保数据目录存在 |
| `Dockerfile` | Modify | 复制 `alembic.ini`；保留 jieba 词典默认（lazy 初始化即可） |
| `AGENTS.md` | Modify | 变更日志记录 M1 |

### Tools（保持对外契约不变，全部跑通现有测试）

| File | Action | Responsibility |
|------|--------|----------------|
| `src/memory_mcp/tools/remember.py` | Modify | 走 `MemoryRepository`；`evolve_memory` 接入；新增字段默认值 |
| `src/memory_mcp/tools/recall.py` | Modify | 走新 `VectorStore`；返回结构不变（hybrid 升级延到 M2） |
| `src/memory_mcp/tools/recall_all.py` | Modify | 走 `MemoryRepository.list_current` |
| `src/memory_mcp/tools/trace.py` | Modify | 走 `MemoryRepository.get_history` |
| `src/memory_mcp/tools/forget.py` | Modify | 走 `MemoryRepository.update`；同时 `EntityRepository.clear_current` |
| `src/memory_mcp/tools/relate.py` | Modify | 走 `RelationRepository.insert` + `GraphStore.add_relation` |
| `src/memory_mcp/tools/unrelate.py` | Modify | 走 `RelationRepository.delete` + `GraphStore.remove_relation` |
| `src/memory_mcp/tools/graph_query.py` | Modify | 走 `GraphStore.get_relations`（运行时加载） |
| `src/memory_mcp/engine/evolution.py` | Modify | 调用新 `vector_store` / `graph_store`；移除旧 `add_evolution_edge` JSON 写入（`parent_id` 已能追溯，见 spec §4.1 废弃说明） |

### Tests

| File | Action | Tests |
|------|--------|-------|
| `tests/conftest.py` | Modify | 启用 `MEMORY_MCP_AUTO_MIGRATE=1`；测试启动跑 migration；reload storage 模块 |
| `tests/test_sqlite_store.py` | Create | pragmas / FK / WAL / busy_timeout / context manager |
| `tests/test_migrations.py` | Create | 跑 `alembic upgrade head` → 断言所有表 / 索引 / FTS5 / 触发器存在 |
| `tests/test_tokenizer.py` | Create | jieba 中英混合 / 空字符串 / 自定义词典 hook |
| `tests/test_memory_repository.py` | Create | insert / update / get_by_id / get_history / list_current / FTS 自动写入 |
| `tests/test_graph_repository.py` | Create | entity upsert / relation CRUD / FK cascade |
| `tests/test_graph_store_reload.py` | Create | 写 entity/relation → reload → MultiDiGraph 一致 |
| `tests/test_vector_backend.py` | Modify | LanceDB schema 仅含 `id` + `vector`；search 返回 `(id, distance)` |
| `tests/test_tools.py` | Modify | 保持原 7 个 tool 行为断言不变；切换到新 storage |
| `tests/test_api.py` | Modify | 保持原 REST 行为断言不变 |
| `tests/test_extraction.py` | Modify（必要时） | 保持 extraction → remember 流不变 |
| `tests/test_working_memory.py` | Modify（必要时） | 保持 briefing 流不变 |
| `tests/fixtures/v1_data/vectors/memories.lance/` | Create | 缩小版 v1 LanceDB（10 memory，3 维向量）— 由 `tests/fixtures/build_v1_fixture.py` 生成 |
| `tests/fixtures/v1_data/graph/entities.json` | Create | 5 entity |
| `tests/fixtures/v1_data/graph/relations.json` | Create | 3 relation |
| `tests/fixtures/build_v1_fixture.py` | Create | 一次性脚本：用旧 LanceVectorStore + JSON 写出 fixture（运行后入 git） |
| `tests/test_migrate_v1_to_v2.py` | Create | 跑 `migrate_v1_to_v2` against fixture → 断言 count / FK / FTS 行数 / LanceDB vector 一致 |

---

## Chunk 1: 依赖与配置准备

### Task 1: 加入 aiosqlite / alembic / jieba 依赖

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.lock`

- [ ] **Step 1: 在 pyproject.toml 增加依赖**

Edit `pyproject.toml`:

```toml
[project]
name = "memory-mcp"
version = "1.0.0"
description = "Personal memory service with semantic search and knowledge graph"
readme = "README.md"
requires-python = ">=3.11"
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
    "alembic>=1.18.0",
    "jieba>=0.42.1",
    "typer>=0.12.0"
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.2.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/memory_mcp"]
```

- [ ] **Step 2: 同步 requirements.lock**

Run from repo root:

```bash
pip install --upgrade pip
pip install --upgrade aiosqlite alembic jieba typer
pip freeze | grep -iE '^(aiosqlite|alembic|jieba|typer|mako|markupsafe)==' >> /tmp/_lock_add.txt
sort -u /tmp/_lock_add.txt | while read -r line; do
  pkg=$(echo "$line" | cut -d= -f1)
  grep -v "^${pkg}==" requirements.lock > requirements.lock.new || true
  mv requirements.lock.new requirements.lock
  echo "$line" >> requirements.lock
done
sort -o requirements.lock requirements.lock
```

Verify the lock includes (lower bound, real version may differ slightly):
- `aiosqlite==0.22.x`
- `alembic==1.18.x`
- `jieba==0.42.x`
- `typer==0.12.x` 或更高
- `Mako==1.x.x`（alembic 依赖）
- `MarkupSafe==3.x.x`（mako 依赖）

- [ ] **Step 3: Commit 依赖变更**

```bash
git add pyproject.toml requirements.lock
git commit -m "build: add aiosqlite, alembic, jieba, typer for v2 storage foundation"
```

### Task 2: 扩展 Settings

**Files:**
- Modify: `src/memory_mcp/config.py`

- [ ] **Step 1: 加入 sqlite_path / auto_migrate / alembic 派生属性**

Edit `src/memory_mcp/config.py`:

```python
import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8765
    debug: bool = False

    # Auth
    auth_token: str

    # Storage
    data_dir: str = "./data"
    vector_backend: str = "lancedb"
    auto_migrate: bool = True  # FastAPI lifespan startup runs alembic upgrade head when True

    # Embedding
    openrouter_api_key: str = Field(
        validation_alias=AliasChoices("MEMORY_MCP_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("MEMORY_MCP_OPENROUTER_BASE_URL", "OPENROUTER_BASE_URL"),
    )
    embedding_model: str = Field(
        default="openai/text-embedding-3-small",
        validation_alias=AliasChoices("MEMORY_MCP_EMBEDDING_MODEL", "EMBEDDING_MODEL"),
    )
    embedding_dim: int = Field(
        default=1536,
        validation_alias=AliasChoices("MEMORY_MCP_EMBEDDING_DIM", "EMBEDDING_DIM"),
    )

    # Conflict Detection
    similarity_threshold: float = 0.85
    llm_model: str = Field(
        default="anthropic/claude-3-haiku",
        validation_alias=AliasChoices("MEMORY_MCP_LLM_MODEL", "LLM_MODEL"),
    )

    # Tokenizer
    jieba_user_dict_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MEMORY_MCP_JIEBA_USER_DICT", "JIEBA_USER_DICT"),
    )

    class Config:
        env_prefix = "MEMORY_MCP_"
        env_file = ".env"
        extra = "ignore"

    @property
    def sqlite_path(self) -> str:
        return os.path.join(self.data_dir, "memory.sqlite3")

    @property
    def vectors_dir(self) -> str:
        return os.path.join(self.data_dir, "vectors")

    @property
    def alembic_url(self) -> str:
        # alembic uses sync driver for migrations
        abs_path = Path(self.sqlite_path).resolve()
        return f"sqlite:///{abs_path}"


settings = Settings()
```

- [ ] **Step 2: Commit config 改动**

```bash
git add src/memory_mcp/config.py
git commit -m "feat(config): add sqlite_path, vectors_dir, alembic_url, auto_migrate, jieba dict"
```

---

## Chunk 2: SQLite 底座

### Task 3: SQLiteStore 抽象

**Files:**
- Create: `src/memory_mcp/storage/sqlite.py`
- Create: `tests/test_sqlite_store.py`

- [ ] **Step 1: 先写 failing test**

Create `tests/test_sqlite_store.py`:

```python
import os

import anyio


def test_sqlite_store_applies_pragmas(test_env):
    async def run():
        import memory_mcp.storage.sqlite as sqlite_mod
        import importlib
        importlib.reload(sqlite_mod)

        async with sqlite_mod.get_db() as db:
            fk_row = await db.fetchone("PRAGMA foreign_keys")
            journal_row = await db.fetchone("PRAGMA journal_mode")
            synchronous_row = await db.fetchone("PRAGMA synchronous")
            busy_row = await db.fetchone("PRAGMA busy_timeout")
        assert fk_row[0] == 1
        assert journal_row[0].lower() == "wal"
        assert synchronous_row[0] == 1   # synchronous NORMAL = 1
        assert busy_row[0] == 5000
        await sqlite_mod.get_store().close()

    anyio.run(run)


def test_get_db_handle_provides_unified_api(test_env):
    async def run():
        import memory_mcp.storage.sqlite as sqlite_mod
        import importlib
        importlib.reload(sqlite_mod)

        # DBHandle must support execute/executemany/fetchone/fetchall/transaction
        async with sqlite_mod.get_db() as db:
            await db.execute("CREATE TABLE smoke (id INTEGER PRIMARY KEY, v TEXT)")
            async with db.transaction():
                await db.executemany(
                    "INSERT INTO smoke (v) VALUES (?)",
                    [("a",), ("b",), ("c",)],
                )
            rows = await db.fetchall("SELECT v FROM smoke ORDER BY id")
            single = await db.fetchone("SELECT v FROM smoke WHERE id = 1")
        assert [r["v"] for r in rows] == ["a", "b", "c"]
        assert single["v"] == "a"

    anyio.run(run)


def test_sqlite_store_persists_across_connections(test_env):
    async def run():
        import memory_mcp.storage.sqlite as sqlite_mod
        import importlib
        importlib.reload(sqlite_mod)

        async with sqlite_mod.get_db() as db:
            await db.execute("CREATE TABLE smoke (id INTEGER PRIMARY KEY, v TEXT)")
            await db.execute("INSERT INTO smoke (v) VALUES (?)", ("hello",))
        # second context manager must see the data because get_db() shares the
        # single store connection per process.
        async with sqlite_mod.get_db() as db:
            row = await db.fetchone("SELECT v FROM smoke WHERE id = 1")
        assert row["v"] == "hello"
        await sqlite_mod.get_store().close()
        assert os.path.exists(sqlite_mod.settings.sqlite_path)

    anyio.run(run)
```

- [ ] **Step 2: 跑测试看失败**

```bash
pytest tests/test_sqlite_store.py -v
```

Expected: ImportError 或 ModuleNotFoundError（`memory_mcp.storage.sqlite` 不存在）。

- [ ] **Step 3: 实现 SQLiteStore + DBHandle + module-level get_db()**

Create `src/memory_mcp/storage/sqlite.py`:

```python
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable, Optional, Sequence

import aiosqlite

from ..config import settings

logger = logging.getLogger(__name__)


_PRAGMAS = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA temp_store = MEMORY",
)


class DBHandle:
    """Authoritative async DB API consumed by M1/M2/M3/M4.

    All downstream layers (repositories, hybrid_search, threads, workers) MUST
    use this interface — never reach for the underlying aiosqlite connection
    directly. The interface mirrors aiosqlite but standardises return shapes:
    rows are always ``aiosqlite.Row`` (dict-like + index-able).
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # -- Mutating ops --------------------------------------------------------
    async def execute(self, sql: str, params: Sequence[Any] | None = None) -> aiosqlite.Cursor:
        return await self._conn.execute(sql, tuple(params) if params is not None else ())

    async def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> aiosqlite.Cursor:
        return await self._conn.executemany(sql, [tuple(p) for p in seq_of_params])

    async def executescript(self, script: str) -> None:
        await self._conn.executescript(script)

    # -- Read ops ------------------------------------------------------------
    async def fetchone(self, sql: str, params: Sequence[Any] | None = None) -> Optional[aiosqlite.Row]:
        async with self._conn.execute(sql, tuple(params) if params is not None else ()) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] | None = None) -> list[aiosqlite.Row]:
        async with self._conn.execute(sql, tuple(params) if params is not None else ()) as cur:
            rows = await cur.fetchall()
        return list(rows)

    # -- Transactions --------------------------------------------------------
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["DBHandle"]:
        await self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self
        except Exception:
            await self._conn.rollback()
            raise
        else:
            await self._conn.commit()

    async def commit(self) -> None:
        await self._conn.commit()

    # -- Escape hatch (avoid in product code; tests only) --------------------
    @property
    def raw(self) -> aiosqlite.Connection:
        return self._conn


class SQLiteStore:
    """Async SQLite primary store wrapper.

    - WAL + NORMAL synchronous + busy_timeout for safer concurrent access
    - Foreign keys ON enforced on every connection
    - Single shared aiosqlite connection (aiosqlite serialises writes anyway);
      callers acquire a `DBHandle` via `get_db()` / `store.get_db()`.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or settings.sqlite_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        if self._conn is not None:
            return
        self._conn = await aiosqlite.connect(self._db_path)
        for pragma in _PRAGMAS:
            await self._conn.execute(pragma)
        await self._conn.commit()
        # aiosqlite returns rows as tuples by default; opt-in to Row factory
        self._conn.row_factory = aiosqlite.Row

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def get_db(self) -> AsyncIterator[DBHandle]:
        """Authoritative entry point — returns the unified DBHandle facade.

        All M1-M4 modules consume this. Auto-commits writes when the caller
        does not open an explicit ``async with handle.transaction():`` block.
        """
        if self._conn is None:
            await self.initialize()
        assert self._conn is not None
        handle = DBHandle(self._conn)
        try:
            yield handle
        finally:
            # Best-effort flush for callers that did not use ``transaction()``
            if self._conn.in_transaction:
                await self._conn.commit()

    @property
    def db_path(self) -> str:
        return self._db_path


_default_store: Optional[SQLiteStore] = None


def get_store() -> SQLiteStore:
    global _default_store
    if _default_store is None:
        _default_store = SQLiteStore()
    return _default_store


@asynccontextmanager
async def get_db() -> AsyncIterator[DBHandle]:
    """Module-level convenience for the default store.

    M2/M3/M4 import this directly: ``from ..storage.sqlite import get_db``.
    """
    store = get_store()
    async with store.get_db() as handle:
        yield handle


async def reset_store_for_tests() -> None:
    """Tests may force a clean store after monkeypatching settings/path."""
    global _default_store
    if _default_store is not None:
        await _default_store.close()
    _default_store = SQLiteStore()
```

- [ ] **Step 4: 跑测试通过**

```bash
pytest tests/test_sqlite_store.py -v
```

Expected: 两条 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/storage/sqlite.py tests/test_sqlite_store.py
git commit -m "feat(storage): add async SQLiteStore + DBHandle facade + module-level get_db()"
```

---

## Chunk 3: Schema & Alembic Migration

### Task 4: 写权威 DDL 参考 schema.sql

**Files:**
- Create: `src/memory_mcp/storage/schema.sql`

- [ ] **Step 1: 写 schema.sql（仅参考，权威在 alembic）**

Create `src/memory_mcp/storage/schema.sql`:

```sql
-- memory-mcp v2 schema reference (authoritative version: alembic versions/0001_initial_v2.py)
-- Spec: docs/superpowers/specs/2026-05-21-memory-mcp-agent-kernel-design.md §4

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

-- ---------------------------------------------------------------------------
-- entities
-- ---------------------------------------------------------------------------
CREATE TABLE entities (
  entity_key TEXT PRIMARY KEY,
  name TEXT,
  entity_type TEXT NOT NULL,
  current_memory_id TEXT,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_entities_entity_type ON entities(entity_type);

-- ---------------------------------------------------------------------------
-- threads (created early so memories.source_thread_id FK is satisfied)
-- ---------------------------------------------------------------------------
CREATE TABLE threads (
  thread_id TEXT PRIMARY KEY,
  source_provider TEXT NOT NULL,
  source_ref TEXT,
  title TEXT,
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  message_count INTEGER NOT NULL DEFAULT 0,
  summary TEXT,
  metadata TEXT,
  last_synced_mtime INTEGER,
  last_synced_seq INTEGER,
  created_at TIMESTAMP NOT NULL,
  imported_at TIMESTAMP NOT NULL,
  UNIQUE(source_provider, source_ref)
);
CREATE INDEX idx_threads_provider ON threads(source_provider);
CREATE INDEX idx_threads_started_at ON threads(started_at DESC);

CREATE TABLE thread_messages (
  message_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  ts TIMESTAMP,
  metadata TEXT,
  UNIQUE(thread_id, seq)
);
CREATE INDEX idx_thread_messages_thread_id ON thread_messages(thread_id, seq);

CREATE VIRTUAL TABLE thread_messages_fts USING fts5(
  content,
  role UNINDEXED,
  content='thread_messages',
  content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER thread_messages_fts_ai AFTER INSERT ON thread_messages BEGIN
  INSERT INTO thread_messages_fts(rowid, content, role)
  VALUES (new.rowid, new.content, new.role);
END;
CREATE TRIGGER thread_messages_fts_ad AFTER DELETE ON thread_messages BEGIN
  INSERT INTO thread_messages_fts(thread_messages_fts, rowid, content, role)
  VALUES('delete', old.rowid, old.content, old.role);
END;
CREATE TRIGGER thread_messages_fts_au AFTER UPDATE ON thread_messages BEGIN
  INSERT INTO thread_messages_fts(thread_messages_fts, rowid, content, role)
  VALUES('delete', old.rowid, old.content, old.role);
  INSERT INTO thread_messages_fts(rowid, content, role)
  VALUES (new.rowid, new.content, new.role);
END;

-- ---------------------------------------------------------------------------
-- memories (main v2 table)
-- ---------------------------------------------------------------------------
CREATE TABLE memories (
  id TEXT PRIMARY KEY,
  entity_key TEXT NOT NULL,
  entity_type TEXT NOT NULL,

  content TEXT NOT NULL,
  content_tokens TEXT,
  title TEXT,
  title_tokens TEXT,

  parent_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
  mutation_type TEXT NOT NULL,
  mutation_reason TEXT,

  created_at TIMESTAMP NOT NULL,
  valid_from TIMESTAMP NOT NULL,
  valid_until TIMESTAMP,

  is_current BOOLEAN NOT NULL DEFAULT 1,
  confidence REAL NOT NULL DEFAULT 1.0,
  review_status TEXT NOT NULL DEFAULT 'auto',
  archived_reason TEXT,
  archived_at TIMESTAMP,
  conflict BOOLEAN NOT NULL DEFAULT 0,
  conflict_with_id TEXT REFERENCES memories(id) ON DELETE SET NULL,

  tags TEXT,
  source TEXT NOT NULL DEFAULT 'conversation',
  origin_client TEXT,
  origin_session_id TEXT,

  source_thread_id TEXT REFERENCES threads(thread_id) ON DELETE SET NULL,
  source_refs TEXT,

  access_count INTEGER NOT NULL DEFAULT 0,
  last_accessed_at TIMESTAMP,
  reinforce_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_memories_entity_key ON memories(entity_key);
CREATE INDEX idx_memories_entity_type ON memories(entity_type);
CREATE INDEX idx_memories_current ON memories(is_current) WHERE is_current = 1;
CREATE INDEX idx_memories_review_status ON memories(review_status);
CREATE INDEX idx_memories_origin_client ON memories(origin_client);
CREATE INDEX idx_memories_source_thread_id ON memories(source_thread_id);
CREATE INDEX idx_memories_created_at ON memories(created_at DESC);
CREATE INDEX idx_memories_last_accessed_at ON memories(last_accessed_at DESC);

CREATE VIRTUAL TABLE memories_fts USING fts5(
  content_tokens,
  title_tokens,
  entity_key UNINDEXED,
  content='memories',
  content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER memories_fts_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, content_tokens, title_tokens, entity_key)
  VALUES (new.rowid, new.content_tokens, new.title_tokens, new.entity_key);
END;
CREATE TRIGGER memories_fts_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content_tokens, title_tokens, entity_key)
  VALUES('delete', old.rowid, old.content_tokens, old.title_tokens, old.entity_key);
END;
CREATE TRIGGER memories_fts_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content_tokens, title_tokens, entity_key)
  VALUES('delete', old.rowid, old.content_tokens, old.title_tokens, old.entity_key);
  INSERT INTO memories_fts(rowid, content_tokens, title_tokens, entity_key)
  VALUES (new.rowid, new.content_tokens, new.title_tokens, new.entity_key);
END;

-- ---------------------------------------------------------------------------
-- relations
-- ---------------------------------------------------------------------------
CREATE TABLE relations (
  id TEXT PRIMARY KEY,
  from_entity_key TEXT NOT NULL REFERENCES entities(entity_key) ON DELETE CASCADE,
  to_entity_key TEXT NOT NULL REFERENCES entities(entity_key) ON DELETE CASCADE,
  relation_type TEXT NOT NULL,
  properties TEXT,
  created_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_relations_from ON relations(from_entity_key);
CREATE INDEX idx_relations_to ON relations(to_entity_key);
CREATE INDEX idx_relations_type ON relations(relation_type);

-- ---------------------------------------------------------------------------
-- jobs (worker queue, M4 will use)
-- ---------------------------------------------------------------------------
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  scheduled_at TIMESTAMP NOT NULL,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  next_retry_at TIMESTAMP,
  error TEXT,
  created_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_jobs_pending ON jobs(scheduled_at) WHERE status = 'pending';
CREATE INDEX idx_jobs_retry ON jobs(next_retry_at)
  WHERE status = 'pending' AND next_retry_at IS NOT NULL;

-- ---------------------------------------------------------------------------
-- working_memory_cache (briefing cache, M4 will use)
-- ---------------------------------------------------------------------------
CREATE TABLE working_memory_cache (
  cache_key TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  generated_at TIMESTAMP NOT NULL
);
```

- [ ] **Step 2: Commit DDL 参考**

```bash
git add src/memory_mcp/storage/schema.sql
git commit -m "docs(storage): add schema.sql DDL reference for v2"
```

### Task 5: alembic 框架

**Files:**
- Create: `alembic.ini`
- Create: `src/memory_mcp/storage/migrations/__init__.py`
- Create: `src/memory_mcp/storage/migrations/env.py`
- Create: `src/memory_mcp/storage/migrations/script.py.mako`
- Create: `src/memory_mcp/storage/migrations/versions/__init__.py`
- Create: `src/memory_mcp/storage/migrate.py`

- [ ] **Step 1: 创建 alembic.ini**

Create `alembic.ini` at repo root:

```ini
[alembic]
script_location = src/memory_mcp/storage/migrations
prepend_sys_path = .
sqlalchemy.url = sqlite:///./data/memory.sqlite3

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: 创建 versions 包**

Create `src/memory_mcp/storage/migrations/__init__.py` — empty file.

Create `src/memory_mcp/storage/migrations/versions/__init__.py` — empty file.

- [ ] **Step 3: 创建 alembic env.py**

Create `src/memory_mcp/storage/migrations/env.py`:

```python
from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Allow `import memory_mcp.*` from the migration scripts
import sys

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from memory_mcp.config import settings  # noqa: E402

config = context.config

# Override sqlalchemy.url from runtime settings (data_dir may be env-driven)
config.set_main_option("sqlalchemy.url", settings.alembic_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # raw SQL migrations only


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Ensure FK enforcement during migrations
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: 创建 script.py.mako 模板**

Create `src/memory_mcp/storage/migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5: 创建程序化 migration runner**

Create `src/memory_mcp/storage/migrate.py`:

```python
import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from ..config import settings

logger = logging.getLogger(__name__)


def _make_config() -> Config:
    repo_root = Path(__file__).resolve().parents[3]
    ini_path = repo_root / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(repo_root / "src" / "memory_mcp" / "storage" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.alembic_url)
    return cfg


def run_migrations() -> None:
    """Apply all pending migrations to head. Called at FastAPI lifespan startup
    when MEMORY_MCP_AUTO_MIGRATE is true (the default).
    """
    os.makedirs(os.path.dirname(settings.sqlite_path) or ".", exist_ok=True)
    cfg = _make_config()
    logger.info("Running alembic upgrade head against %s", settings.sqlite_path)
    command.upgrade(cfg, "head")


def downgrade(revision: str = "-1") -> None:
    cfg = _make_config()
    command.downgrade(cfg, revision)


def current() -> str | None:
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    engine = create_engine(settings.alembic_url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        return ctx.get_current_revision()
```

- [ ] **Step 6: Commit alembic 框架**

```bash
git add alembic.ini src/memory_mcp/storage/migrations/__init__.py src/memory_mcp/storage/migrations/env.py src/memory_mcp/storage/migrations/script.py.mako src/memory_mcp/storage/migrations/versions/__init__.py src/memory_mcp/storage/migrate.py
git commit -m "feat(storage): wire alembic framework with programmatic upgrade head"
```

### Task 6: 0001_initial_v2 migration

**Files:**
- Create: `src/memory_mcp/storage/migrations/versions/0001_initial_v2.py`
- Create: `tests/test_migrations.py`

- [ ] **Step 1: 先写 failing test**

Create `tests/test_migrations.py`:

```python
import importlib
import os

import anyio


REQUIRED_TABLES = {
    "memories",
    "memories_fts",
    "entities",
    "relations",
    "threads",
    "thread_messages",
    "thread_messages_fts",
    "jobs",
    "working_memory_cache",
    "alembic_version",
}

REQUIRED_INDEXES = {
    "idx_memories_entity_key",
    "idx_memories_entity_type",
    "idx_memories_current",
    "idx_memories_review_status",
    "idx_memories_origin_client",
    "idx_memories_source_thread_id",
    "idx_memories_created_at",
    "idx_memories_last_accessed_at",
    "idx_entities_entity_type",
    "idx_relations_from",
    "idx_relations_to",
    "idx_relations_type",
    "idx_threads_provider",
    "idx_threads_started_at",
    "idx_thread_messages_thread_id",
    "idx_jobs_pending",
    "idx_jobs_retry",
}

REQUIRED_TRIGGERS = {
    "memories_fts_ai",
    "memories_fts_ad",
    "memories_fts_au",
    "thread_messages_fts_ai",
    "thread_messages_fts_ad",
    "thread_messages_fts_au",
}


def _names(rows, col=0) -> set[str]:
    return {r[col] for r in rows}


def test_alembic_upgrade_creates_v2_schema(test_env):
    async def run():
        import memory_mcp.storage.migrate as migrate_mod
        importlib.reload(migrate_mod)

        migrate_mod.run_migrations()
        assert os.path.exists(migrate_mod.settings.sqlite_path)

        import memory_mcp.storage.sqlite as sqlite_mod
        importlib.reload(sqlite_mod)
        async with sqlite_mod.get_db() as db:
            tables = await db.fetchall(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            )
            indexes = await db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            )
            triggers = await db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        await sqlite_mod.get_store().close()

        table_names = _names(tables)
        assert REQUIRED_TABLES.issubset(table_names), f"missing tables: {REQUIRED_TABLES - table_names}"
        assert REQUIRED_INDEXES.issubset(_names(indexes))
        assert REQUIRED_TRIGGERS.issubset(_names(triggers))

    anyio.run(run)


def test_alembic_upgrade_is_idempotent(test_env):
    async def run():
        import memory_mcp.storage.migrate as migrate_mod
        importlib.reload(migrate_mod)
        migrate_mod.run_migrations()
        migrate_mod.run_migrations()  # second call must not raise
        assert migrate_mod.current() is not None

    anyio.run(run)
```

- [ ] **Step 2: 跑测试看失败**

```bash
pytest tests/test_migrations.py -v
```

Expected: FAIL（versions 目录无文件，head 是 None）。

- [ ] **Step 3: 实现 0001_initial_v2**

Create `src/memory_mcp/storage/migrations/versions/0001_initial_v2.py`:

```python
"""initial v2 schema

Revision ID: 0001_initial_v2
Revises:
Create Date: 2026-05-21 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0001_initial_v2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("PRAGMA foreign_keys = ON")

    # entities
    op.execute(
        """
        CREATE TABLE entities (
          entity_key TEXT PRIMARY KEY,
          name TEXT,
          entity_type TEXT NOT NULL,
          current_memory_id TEXT,
          created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_entities_entity_type ON entities(entity_type)")

    # threads (created before memories for FK)
    op.execute(
        """
        CREATE TABLE threads (
          thread_id TEXT PRIMARY KEY,
          source_provider TEXT NOT NULL,
          source_ref TEXT,
          title TEXT,
          started_at TIMESTAMP,
          ended_at TIMESTAMP,
          message_count INTEGER NOT NULL DEFAULT 0,
          summary TEXT,
          metadata TEXT,
          last_synced_mtime INTEGER,
          last_synced_seq INTEGER,
          created_at TIMESTAMP NOT NULL,
          imported_at TIMESTAMP NOT NULL,
          UNIQUE(source_provider, source_ref)
        )
        """
    )
    op.execute("CREATE INDEX idx_threads_provider ON threads(source_provider)")
    op.execute("CREATE INDEX idx_threads_started_at ON threads(started_at DESC)")

    op.execute(
        """
        CREATE TABLE thread_messages (
          message_id TEXT PRIMARY KEY,
          thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
          seq INTEGER NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          ts TIMESTAMP,
          metadata TEXT,
          UNIQUE(thread_id, seq)
        )
        """
    )
    op.execute("CREATE INDEX idx_thread_messages_thread_id ON thread_messages(thread_id, seq)")

    op.execute(
        """
        CREATE VIRTUAL TABLE thread_messages_fts USING fts5(
          content,
          role UNINDEXED,
          content='thread_messages',
          content_rowid='rowid',
          tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER thread_messages_fts_ai AFTER INSERT ON thread_messages BEGIN
          INSERT INTO thread_messages_fts(rowid, content, role)
          VALUES (new.rowid, new.content, new.role);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER thread_messages_fts_ad AFTER DELETE ON thread_messages BEGIN
          INSERT INTO thread_messages_fts(thread_messages_fts, rowid, content, role)
          VALUES('delete', old.rowid, old.content, old.role);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER thread_messages_fts_au AFTER UPDATE ON thread_messages BEGIN
          INSERT INTO thread_messages_fts(thread_messages_fts, rowid, content, role)
          VALUES('delete', old.rowid, old.content, old.role);
          INSERT INTO thread_messages_fts(rowid, content, role)
          VALUES (new.rowid, new.content, new.role);
        END
        """
    )

    # memories
    op.execute(
        """
        CREATE TABLE memories (
          id TEXT PRIMARY KEY,
          entity_key TEXT NOT NULL,
          entity_type TEXT NOT NULL,

          content TEXT NOT NULL,
          content_tokens TEXT,
          title TEXT,
          title_tokens TEXT,

          parent_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
          mutation_type TEXT NOT NULL,
          mutation_reason TEXT,

          created_at TIMESTAMP NOT NULL,
          valid_from TIMESTAMP NOT NULL,
          valid_until TIMESTAMP,

          is_current BOOLEAN NOT NULL DEFAULT 1,
          confidence REAL NOT NULL DEFAULT 1.0,
          review_status TEXT NOT NULL DEFAULT 'auto',
          archived_reason TEXT,
          archived_at TIMESTAMP,
          conflict BOOLEAN NOT NULL DEFAULT 0,
          conflict_with_id TEXT REFERENCES memories(id) ON DELETE SET NULL,

          tags TEXT,
          source TEXT NOT NULL DEFAULT 'conversation',
          origin_client TEXT,
          origin_session_id TEXT,

          source_thread_id TEXT REFERENCES threads(thread_id) ON DELETE SET NULL,
          source_refs TEXT,

          access_count INTEGER NOT NULL DEFAULT 0,
          last_accessed_at TIMESTAMP,
          reinforce_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("CREATE INDEX idx_memories_entity_key ON memories(entity_key)")
    op.execute("CREATE INDEX idx_memories_entity_type ON memories(entity_type)")
    op.execute("CREATE INDEX idx_memories_current ON memories(is_current) WHERE is_current = 1")
    op.execute("CREATE INDEX idx_memories_review_status ON memories(review_status)")
    op.execute("CREATE INDEX idx_memories_origin_client ON memories(origin_client)")
    op.execute("CREATE INDEX idx_memories_source_thread_id ON memories(source_thread_id)")
    op.execute("CREATE INDEX idx_memories_created_at ON memories(created_at DESC)")
    op.execute("CREATE INDEX idx_memories_last_accessed_at ON memories(last_accessed_at DESC)")

    op.execute(
        """
        CREATE VIRTUAL TABLE memories_fts USING fts5(
          content_tokens,
          title_tokens,
          entity_key UNINDEXED,
          content='memories',
          content_rowid='rowid',
          tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER memories_fts_ai AFTER INSERT ON memories BEGIN
          INSERT INTO memories_fts(rowid, content_tokens, title_tokens, entity_key)
          VALUES (new.rowid, new.content_tokens, new.title_tokens, new.entity_key);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER memories_fts_ad AFTER DELETE ON memories BEGIN
          INSERT INTO memories_fts(memories_fts, rowid, content_tokens, title_tokens, entity_key)
          VALUES('delete', old.rowid, old.content_tokens, old.title_tokens, old.entity_key);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER memories_fts_au AFTER UPDATE ON memories BEGIN
          INSERT INTO memories_fts(memories_fts, rowid, content_tokens, title_tokens, entity_key)
          VALUES('delete', old.rowid, old.content_tokens, old.title_tokens, old.entity_key);
          INSERT INTO memories_fts(rowid, content_tokens, title_tokens, entity_key)
          VALUES (new.rowid, new.content_tokens, new.title_tokens, new.entity_key);
        END
        """
    )

    # relations
    op.execute(
        """
        CREATE TABLE relations (
          id TEXT PRIMARY KEY,
          from_entity_key TEXT NOT NULL REFERENCES entities(entity_key) ON DELETE CASCADE,
          to_entity_key TEXT NOT NULL REFERENCES entities(entity_key) ON DELETE CASCADE,
          relation_type TEXT NOT NULL,
          properties TEXT,
          created_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_relations_from ON relations(from_entity_key)")
    op.execute("CREATE INDEX idx_relations_to ON relations(to_entity_key)")
    op.execute("CREATE INDEX idx_relations_type ON relations(relation_type)")

    # jobs
    op.execute(
        """
        CREATE TABLE jobs (
          id TEXT PRIMARY KEY,
          job_type TEXT NOT NULL,
          payload TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 3,
          scheduled_at TIMESTAMP NOT NULL,
          started_at TIMESTAMP,
          finished_at TIMESTAMP,
          next_retry_at TIMESTAMP,
          error TEXT,
          created_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_jobs_pending ON jobs(scheduled_at) WHERE status = 'pending'")
    op.execute(
        "CREATE INDEX idx_jobs_retry ON jobs(next_retry_at) "
        "WHERE status = 'pending' AND next_retry_at IS NOT NULL"
    )

    # working_memory_cache
    op.execute(
        """
        CREATE TABLE working_memory_cache (
          cache_key TEXT PRIMARY KEY,
          content TEXT NOT NULL,
          generated_at TIMESTAMP NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS working_memory_cache")
    op.execute("DROP INDEX IF EXISTS idx_jobs_retry")
    op.execute("DROP INDEX IF EXISTS idx_jobs_pending")
    op.execute("DROP TABLE IF EXISTS jobs")
    op.execute("DROP INDEX IF EXISTS idx_relations_type")
    op.execute("DROP INDEX IF EXISTS idx_relations_to")
    op.execute("DROP INDEX IF EXISTS idx_relations_from")
    op.execute("DROP TABLE IF EXISTS relations")
    op.execute("DROP TRIGGER IF EXISTS memories_fts_au")
    op.execute("DROP TRIGGER IF EXISTS memories_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS memories_fts_ai")
    op.execute("DROP TABLE IF EXISTS memories_fts")
    op.execute("DROP INDEX IF EXISTS idx_memories_last_accessed_at")
    op.execute("DROP INDEX IF EXISTS idx_memories_created_at")
    op.execute("DROP INDEX IF EXISTS idx_memories_source_thread_id")
    op.execute("DROP INDEX IF EXISTS idx_memories_origin_client")
    op.execute("DROP INDEX IF EXISTS idx_memories_review_status")
    op.execute("DROP INDEX IF EXISTS idx_memories_current")
    op.execute("DROP INDEX IF EXISTS idx_memories_entity_type")
    op.execute("DROP INDEX IF EXISTS idx_memories_entity_key")
    op.execute("DROP TABLE IF EXISTS memories")
    op.execute("DROP TRIGGER IF EXISTS thread_messages_fts_au")
    op.execute("DROP TRIGGER IF EXISTS thread_messages_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS thread_messages_fts_ai")
    op.execute("DROP TABLE IF EXISTS thread_messages_fts")
    op.execute("DROP INDEX IF EXISTS idx_thread_messages_thread_id")
    op.execute("DROP TABLE IF EXISTS thread_messages")
    op.execute("DROP INDEX IF EXISTS idx_threads_started_at")
    op.execute("DROP INDEX IF EXISTS idx_threads_provider")
    op.execute("DROP TABLE IF EXISTS threads")
    op.execute("DROP INDEX IF EXISTS idx_entities_entity_type")
    op.execute("DROP TABLE IF EXISTS entities")
```

- [ ] **Step 4: 跑测试通过**

```bash
pytest tests/test_migrations.py -v
```

Expected: 两条 PASS。

- [ ] **Step 5: Commit migration**

```bash
git add src/memory_mcp/storage/migrations/versions/0001_initial_v2.py tests/test_migrations.py
git commit -m "feat(storage): add 0001_initial_v2 alembic migration for v2 schema"
```

---

## Chunk 4: Tokenizer

### Task 7: jieba tokenizer 封装

**Files:**
- Create: `src/memory_mcp/engine/tokenizer.py`
- Create: `tests/test_tokenizer.py`

- [ ] **Step 1: 先写 failing test**

Create `tests/test_tokenizer.py`:

```python
import importlib


def test_tokenize_chinese(test_env):
    import memory_mcp.engine.tokenizer as tok
    importlib.reload(tok)
    out = tok.tokenize("我喜欢使用Cursor作为主编辑器")
    parts = out.split()
    assert "Cursor" in parts
    # jieba should split Chinese into multiple tokens
    chinese_parts = [p for p in parts if any("一" <= ch <= "鿿" for ch in p)]
    assert len(chinese_parts) >= 2


def test_tokenize_english(test_env):
    import memory_mcp.engine.tokenizer as tok
    importlib.reload(tok)
    out = tok.tokenize("Prefer Cursor as main editor")
    parts = out.split()
    assert "Cursor" in parts
    assert "editor" in parts


def test_tokenize_empty(test_env):
    import memory_mcp.engine.tokenizer as tok
    importlib.reload(tok)
    assert tok.tokenize("") == ""
    assert tok.tokenize("   ") == ""


def test_user_dict_hook(test_env, tmp_path, monkeypatch):
    dict_path = tmp_path / "user.dict"
    dict_path.write_text("我家的小宝贝 100 n\n", encoding="utf-8")
    monkeypatch.setenv("MEMORY_MCP_JIEBA_USER_DICT", str(dict_path))

    import memory_mcp.config as config
    importlib.reload(config)
    import memory_mcp.engine.tokenizer as tok
    importlib.reload(tok)
    tok.reset_for_tests()

    out = tok.tokenize("今天我家的小宝贝又长大了")
    assert "我家的小宝贝" in out.split()
```

- [ ] **Step 2: 跑测试看失败**

```bash
pytest tests/test_tokenizer.py -v
```

Expected: ImportError。

- [ ] **Step 3: 实现 tokenizer**

Create `src/memory_mcp/engine/tokenizer.py`:

```python
import logging
import threading
from typing import Optional

from ..config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_initialized = False
_jieba_module = None


def _get_jieba():
    global _initialized, _jieba_module
    if _jieba_module is not None:
        return _jieba_module
    with _lock:
        if _jieba_module is not None:
            return _jieba_module
        import jieba  # lazy import — avoid loading dictionary at process startup
        jieba.setLogLevel(logging.WARNING)
        if settings.jieba_user_dict_path:
            try:
                jieba.load_userdict(settings.jieba_user_dict_path)
                logger.info("Loaded jieba user dict from %s", settings.jieba_user_dict_path)
            except Exception as exc:
                logger.warning("Failed to load jieba user dict: %s", exc)
        _jieba_module = jieba
        _initialized = True
        return _jieba_module


def tokenize(text: Optional[str]) -> str:
    """Tokenize text with jieba (precise mode) and return space-joined tokens.

    Used to populate `memories.content_tokens` / `title_tokens` columns.
    FTS5 indexes those columns with `unicode61`, so the application layer owns
    Chinese segmentation and the database layer stays C-compile-free.
    """
    if not text:
        return ""
    stripped = text.strip()
    if not stripped:
        return ""
    jieba = _get_jieba()
    tokens = [t for t in jieba.cut(stripped, cut_all=False) if t and not t.isspace()]
    return " ".join(tokens)


def reset_for_tests() -> None:
    """Force re-initialization (used by tests after env change)."""
    global _initialized, _jieba_module
    with _lock:
        _initialized = False
        _jieba_module = None
```

- [ ] **Step 4: 跑测试通过**

```bash
pytest tests/test_tokenizer.py -v
```

Expected: 4 条 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/engine/tokenizer.py tests/test_tokenizer.py
git commit -m "feat(engine): add jieba tokenizer with user dict hook"
```

---

## Chunk 5: Models v2 + Serializers

### Task 8: 扩展 MemoryNode v2 字段

**Files:**
- Modify: `src/memory_mcp/engine/models.py`

- [ ] **Step 1: 加 v2 字段（α/β/γ/δ/ε）**

Edit `src/memory_mcp/engine/models.py` — replace the file with:

```python
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class MutationType(str, Enum):
    INITIAL = "initial"
    UPDATE = "update"
    REFINEMENT = "refinement"
    CORRECTION = "correction"
    REVERSAL = "reversal"
    EVOLUTION = "evolution"


class ReviewStatus(str, Enum):
    AUTO = "auto"
    REVIEWED = "reviewed"
    CONFIRMED = "confirmed"
    CHALLENGED = "challenged"
    LEGACY = "legacy"
    ARCHIVED = "archived"


class SourceRef(BaseModel):
    thread_id: str
    message_id: Optional[str] = None


class MemoryNode(BaseModel):
    # Identity
    id: str
    entity_key: str
    entity_type: str

    # Content (ε)
    content: str
    content_tokens: Optional[str] = None
    title: Optional[str] = None
    title_tokens: Optional[str] = None

    # Embedding (vector lives in LanceDB; kept in-memory for serialization)
    embedding: List[float] = Field(default_factory=list)

    # Evolution
    parent_id: Optional[str] = None
    mutation_type: MutationType
    mutation_reason: Optional[str] = None

    # Time
    created_at: datetime
    valid_from: datetime
    valid_until: Optional[datetime] = None

    # State
    is_current: bool
    confidence: float = 1.0
    review_status: ReviewStatus = ReviewStatus.AUTO  # α
    archived_reason: Optional[str] = None
    archived_at: Optional[datetime] = None
    conflict: bool = False
    conflict_with_id: Optional[str] = None

    # Metadata
    tags: List[str] = Field(default_factory=list)
    source: str = "conversation"
    origin_client: Optional[str] = None         # β
    origin_session_id: Optional[str] = None     # β

    # Source linkage (γ)
    source_thread_id: Optional[str] = None
    source_refs: List[SourceRef] = Field(default_factory=list)

    # Access stats (δ)
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    reinforce_count: int = 0


class Entity(BaseModel):
    entity_key: str
    name: Optional[str] = None
    entity_type: str
    current_memory_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class Relation(BaseModel):
    id: str
    from_entity_key: str
    to_entity_key: str
    relation_type: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
```

- [ ] **Step 2: 快速 sanity check**

```bash
python -c "from memory_mcp.engine.models import MemoryNode, ReviewStatus, SourceRef; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit models**

```bash
git add src/memory_mcp/engine/models.py
git commit -m "feat(models): extend MemoryNode with v2 fields (review_status, origin, source_refs, access stats)"
```

### Task 9: Serializers（row <-> MemoryNode）

**Files:**
- Create: `src/memory_mcp/storage/serializers.py`

- [ ] **Step 1: 实现序列化**

Create `src/memory_mcp/storage/serializers.py`:

```python
import json
from datetime import datetime
from typing import Any, Iterable

from ..engine.models import MemoryNode, MutationType, ReviewStatus, SourceRef


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def memory_to_row(node: MemoryNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "entity_key": node.entity_key,
        "entity_type": node.entity_type,
        "content": node.content,
        "content_tokens": node.content_tokens,
        "title": node.title,
        "title_tokens": node.title_tokens,
        "parent_id": node.parent_id,
        "mutation_type": node.mutation_type.value,
        "mutation_reason": node.mutation_reason,
        "created_at": _to_iso(node.created_at),
        "valid_from": _to_iso(node.valid_from),
        "valid_until": _to_iso(node.valid_until),
        "is_current": 1 if node.is_current else 0,
        "confidence": node.confidence,
        "review_status": node.review_status.value,
        "archived_reason": node.archived_reason,
        "archived_at": _to_iso(node.archived_at),
        "conflict": 1 if node.conflict else 0,
        "conflict_with_id": node.conflict_with_id,
        "tags": json.dumps(node.tags, ensure_ascii=False),
        "source": node.source,
        "origin_client": node.origin_client,
        "origin_session_id": node.origin_session_id,
        "source_thread_id": node.source_thread_id,
        "source_refs": json.dumps([r.model_dump() for r in node.source_refs], ensure_ascii=False),
        "access_count": node.access_count,
        "last_accessed_at": _to_iso(node.last_accessed_at),
        "reinforce_count": node.reinforce_count,
    }


def row_to_memory(row: Iterable[Any], embedding: list[float] | None = None) -> MemoryNode:
    data = dict(row)  # supports both sqlite3.Row and dict
    tags_raw = data.get("tags")
    refs_raw = data.get("source_refs")
    return MemoryNode(
        id=data["id"],
        entity_key=data["entity_key"],
        entity_type=data["entity_type"],
        content=data["content"],
        content_tokens=data.get("content_tokens"),
        title=data.get("title"),
        title_tokens=data.get("title_tokens"),
        embedding=list(embedding or []),
        parent_id=data.get("parent_id"),
        mutation_type=MutationType(data["mutation_type"]),
        mutation_reason=data.get("mutation_reason"),
        created_at=_dt(data["created_at"]),
        valid_from=_dt(data["valid_from"]),
        valid_until=_dt(data.get("valid_until")),
        is_current=bool(data.get("is_current")),
        confidence=float(data.get("confidence") or 1.0),
        review_status=ReviewStatus(data.get("review_status") or "auto"),
        archived_reason=data.get("archived_reason"),
        archived_at=_dt(data.get("archived_at")),
        conflict=bool(data.get("conflict")),
        conflict_with_id=data.get("conflict_with_id"),
        tags=json.loads(tags_raw) if tags_raw else [],
        source=data.get("source") or "conversation",
        origin_client=data.get("origin_client"),
        origin_session_id=data.get("origin_session_id"),
        source_thread_id=data.get("source_thread_id"),
        source_refs=[SourceRef(**r) for r in (json.loads(refs_raw) if refs_raw else [])],
        access_count=int(data.get("access_count") or 0),
        last_accessed_at=_dt(data.get("last_accessed_at")),
        reinforce_count=int(data.get("reinforce_count") or 0),
    )
```

- [ ] **Step 2: Commit serializers**

```bash
git add src/memory_mcp/storage/serializers.py
git commit -m "feat(storage): add memory <-> sqlite row serializers"
```

---

## Chunk 6: Repositories

### Task 10: MemoryRepository

**Files:**
- Create: `src/memory_mcp/storage/repositories/__init__.py`
- Create: `src/memory_mcp/storage/repositories/memories.py`
- Create: `tests/test_memory_repository.py`

- [ ] **Step 1: 创建 repositories 包**

Create `src/memory_mcp/storage/repositories/__init__.py` — empty file.

- [ ] **Step 2: 先写 failing test**

Create `tests/test_memory_repository.py`:

```python
import importlib
from datetime import datetime, timezone
from uuid import uuid4

import anyio


def _make_node(entity_key: str = "preference:editor", content: str = "Prefer Cursor"):
    from memory_mcp.engine.models import MemoryNode, MutationType
    now = datetime.now(timezone.utc)
    return MemoryNode(
        id=str(uuid4()),
        entity_key=entity_key,
        entity_type=entity_key.split(":", 1)[0],
        content=content,
        content_tokens=content,
        embedding=[0.1, 0.1, 0.1],
        mutation_type=MutationType.INITIAL,
        created_at=now,
        valid_from=now,
        is_current=True,
    )


def _setup(test_env):
    import memory_mcp.storage.migrate as migrate_mod
    importlib.reload(migrate_mod)
    migrate_mod.run_migrations()

    import memory_mcp.storage.sqlite as sqlite_mod
    importlib.reload(sqlite_mod)
    import memory_mcp.storage.repositories.memories as repo_mod
    importlib.reload(repo_mod)
    return repo_mod.MemoryRepository(sqlite_mod.SQLiteStore())


def test_insert_and_get(test_env):
    async def run():
        repo = _setup(test_env)
        node = _make_node()
        await repo.insert(node)
        loaded = await repo.get_by_id(node.id)
        assert loaded is not None
        assert loaded.content == node.content
        assert loaded.entity_key == node.entity_key
        assert loaded.is_current is True

    anyio.run(run)


def test_update_sets_is_current(test_env):
    async def run():
        repo = _setup(test_env)
        node = _make_node()
        await repo.insert(node)
        node.is_current = False
        node.archived_reason = "test"
        await repo.update(node)
        loaded = await repo.get_by_id(node.id)
        assert loaded.is_current is False
        assert loaded.archived_reason == "test"

    anyio.run(run)


def test_get_history_ordered(test_env):
    async def run():
        repo = _setup(test_env)
        a = _make_node(content="A")
        b = _make_node(content="B")
        b.parent_id = a.id
        await repo.insert(a)
        await repo.insert(b)
        history = await repo.get_history("preference:editor")
        assert [n.content for n in history] == ["A", "B"]

    anyio.run(run)


def test_list_current_filters(test_env):
    async def run():
        repo = _setup(test_env)
        a = _make_node(entity_key="preference:editor", content="A")
        b = _make_node(entity_key="fact:city", content="B")
        await repo.insert(a)
        await repo.insert(b)
        all_current = await repo.list_current()
        assert {n.entity_key for n in all_current} == {"preference:editor", "fact:city"}
        only_pref = await repo.list_current(entity_type="preference")
        assert {n.entity_key for n in only_pref} == {"preference:editor"}

    anyio.run(run)


def test_fts_index_populated_on_insert(test_env):
    async def run():
        repo = _setup(test_env)
        node = _make_node(content="Prefers Cursor editor and dark mode")
        node.content_tokens = "Prefers Cursor editor and dark mode"
        await repo.insert(node)
        async with repo._store.get_db() as db:
            row = await db.fetchone(
                "SELECT count(*) AS c FROM memories_fts WHERE memories_fts MATCH ?",
                ("Cursor",),
            )
        assert row["c"] == 1

    anyio.run(run)


def test_get_by_ids_batch(test_env):
    async def run():
        repo = _setup(test_env)
        nodes = [_make_node(entity_key=f"preference:p{i}", content=f"C{i}") for i in range(3)]
        for n in nodes:
            await repo.insert(n)
        loaded = await repo.get_by_ids([n.id for n in nodes])
        assert {l.content for l in loaded} == {"C0", "C1", "C2"}

    anyio.run(run)
```

- [ ] **Step 3: 跑测试看失败**

```bash
pytest tests/test_memory_repository.py -v
```

Expected: ImportError on `repositories.memories`.

- [ ] **Step 4: 实现 MemoryRepository**

Create `src/memory_mcp/storage/repositories/memories.py`:

```python
from typing import Iterable, List, Optional

from ...engine.models import MemoryNode
from ..serializers import memory_to_row, row_to_memory
from ..sqlite import SQLiteStore, get_store


_COLUMNS = (
    "id, entity_key, entity_type, content, content_tokens, title, title_tokens, "
    "parent_id, mutation_type, mutation_reason, created_at, valid_from, valid_until, "
    "is_current, confidence, review_status, archived_reason, archived_at, conflict, "
    "conflict_with_id, tags, source, origin_client, origin_session_id, source_thread_id, "
    "source_refs, access_count, last_accessed_at, reinforce_count"
)


def _placeholders(n: int) -> str:
    return ",".join(["?"] * n)


class MemoryRepository:
    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        self._store = store or get_store()

    async def insert(self, node: MemoryNode) -> None:
        row = memory_to_row(node)
        columns = list(row.keys())
        values = [row[c] for c in columns]
        sql = (
            f"INSERT INTO memories ({', '.join(columns)}) "
            f"VALUES ({_placeholders(len(columns))})"
        )
        async with self._store.get_db() as db:
            await db.execute(sql, values)

    async def update(self, node: MemoryNode) -> None:
        row = memory_to_row(node)
        columns = [c for c in row.keys() if c != "id"]
        values = [row[c] for c in columns] + [node.id]
        assignments = ", ".join(f"{c} = ?" for c in columns)
        sql = f"UPDATE memories SET {assignments} WHERE id = ?"
        async with self._store.get_db() as db:
            await db.execute(sql, values)

    async def get_by_id(self, memory_id: str) -> Optional[MemoryNode]:
        sql = f"SELECT {_COLUMNS} FROM memories WHERE id = ?"
        async with self._store.get_db() as db:
            row = await db.fetchone(sql, (memory_id,))
        if row is None:
            return None
        return row_to_memory(row)

    async def get_by_ids(self, memory_ids: Iterable[str]) -> List[MemoryNode]:
        ids = list(memory_ids)
        if not ids:
            return []
        sql = f"SELECT {_COLUMNS} FROM memories WHERE id IN ({_placeholders(len(ids))})"
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, ids)
        by_id = {dict(r)["id"]: row_to_memory(r) for r in rows}
        # preserve input order
        return [by_id[i] for i in ids if i in by_id]

    async def get_history(self, entity_key: str) -> List[MemoryNode]:
        sql = (
            f"SELECT {_COLUMNS} FROM memories WHERE entity_key = ? ORDER BY created_at ASC"
        )
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, (entity_key,))
        return [row_to_memory(r) for r in rows]

    async def list_current(
        self,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryNode]:
        clauses = ["is_current = 1"]
        params: list = []
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        sql = (
            f"SELECT {_COLUMNS} FROM memories "
            f"WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at DESC LIMIT ?"
        )
        params.append(int(limit))
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, params)
        return [row_to_memory(r) for r in rows]

    async def hard_delete(self, memory_id: str) -> bool:
        """Used by VectorStore.delete and tools.memory_delete(hard=True)."""
        async with self._store.get_db() as db:
            cur = await db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return (cur.rowcount or 0) > 0

    async def fts_search(self, tokens: str, limit: int = 50) -> List[dict]:
        """FTS5 search via the jieba-pre-tokenized memories_fts virtual table.

        Returns ``[{"memory_id", "bm25", "node"}]`` ordered by bm25 ascending
        (FTS5 returns lower bm25 = better match). Used by M2 hybrid_search.
        """
        if not tokens.strip():
            return []
        sql = (
            f"SELECT m.id AS memory_id, bm25(memories_fts) AS bm25, {_COLUMNS} "
            f"FROM memories_fts JOIN memories m ON m.rowid = memories_fts.rowid "
            f"WHERE memories_fts MATCH ? ORDER BY bm25 ASC LIMIT ?"
        )
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, (tokens, int(limit)))
        out: list[dict] = []
        for r in rows:
            node = row_to_memory(r)
            out.append({"memory_id": r["memory_id"], "bm25": r["bm25"], "node": node})
        return out
```

`fts_search` 暴露给 M2 `engine/hybrid_search.fts_recall` 调用，避免后者绕过 repository 直接拼 SQL。

- [ ] **Step 5: 跑测试通过**

```bash
pytest tests/test_memory_repository.py -v
```

Expected: 6 条 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/storage/repositories/__init__.py src/memory_mcp/storage/repositories/memories.py tests/test_memory_repository.py
git commit -m "feat(storage): add MemoryRepository (CRUD + history + list_current + FTS auto-index)"
```

### Task 11: EntityRepository + RelationRepository

**Files:**
- Create: `src/memory_mcp/storage/repositories/entities.py`
- Create: `src/memory_mcp/storage/repositories/relations.py`
- Create: `tests/test_graph_repository.py`

- [ ] **Step 1: 先写 failing test**

Create `tests/test_graph_repository.py`:

```python
import importlib
from datetime import datetime, timezone
from uuid import uuid4

import anyio


def _setup(test_env):
    import memory_mcp.storage.migrate as migrate_mod
    importlib.reload(migrate_mod)
    migrate_mod.run_migrations()
    import memory_mcp.storage.sqlite as sqlite_mod
    importlib.reload(sqlite_mod)
    import memory_mcp.storage.repositories.entities as ent_mod
    import memory_mcp.storage.repositories.relations as rel_mod
    importlib.reload(ent_mod)
    importlib.reload(rel_mod)
    store = sqlite_mod.SQLiteStore()
    return ent_mod.EntityRepository(store), rel_mod.RelationRepository(store)


def test_upsert_entity_insert_and_update(test_env):
    async def run():
        ent_repo, _ = _setup(test_env)
        await ent_repo.upsert(
            entity_key="person:alice",
            entity_type="person",
            current_memory_id="m1",
        )
        loaded = await ent_repo.get("person:alice")
        assert loaded["entity_type"] == "person"
        assert loaded["current_memory_id"] == "m1"

        await ent_repo.upsert(
            entity_key="person:alice",
            entity_type="person",
            current_memory_id="m2",
        )
        loaded = await ent_repo.get("person:alice")
        assert loaded["current_memory_id"] == "m2"

    anyio.run(run)


def test_clear_current_memory(test_env):
    async def run():
        ent_repo, _ = _setup(test_env)
        await ent_repo.upsert("person:alice", "person", "m1")
        await ent_repo.clear_current_memory("person:alice")
        loaded = await ent_repo.get("person:alice")
        assert loaded["current_memory_id"] is None

    anyio.run(run)


def test_relation_insert_and_delete(test_env):
    async def run():
        ent_repo, rel_repo = _setup(test_env)
        from memory_mcp.engine.models import Relation
        await ent_repo.upsert("person:alice", "person", None)
        await ent_repo.upsert("project:x", "project", None)
        relation = Relation(
            id=str(uuid4()),
            from_entity_key="person:alice",
            to_entity_key="project:x",
            relation_type="WORKS_ON",
            properties={"role": "lead"},
            created_at=datetime.now(timezone.utc),
        )
        await rel_repo.insert(relation)
        loaded = await rel_repo.list_by_entity("person:alice")
        assert len(loaded) == 1
        assert loaded[0]["relation_type"] == "WORKS_ON"
        assert loaded[0]["properties"] == {"role": "lead"}

        deleted = await rel_repo.delete(relation.id)
        assert deleted is True
        assert await rel_repo.list_by_entity("person:alice") == []
        again = await rel_repo.delete(relation.id)
        assert again is False

    anyio.run(run)


def test_relation_fk_cascade_on_entity_delete(test_env):
    async def run():
        ent_repo, rel_repo = _setup(test_env)
        from memory_mcp.engine.models import Relation
        await ent_repo.upsert("person:bob", "person", None)
        await ent_repo.upsert("project:y", "project", None)
        relation = Relation(
            id=str(uuid4()),
            from_entity_key="person:bob",
            to_entity_key="project:y",
            relation_type="OWNS",
            created_at=datetime.now(timezone.utc),
        )
        await rel_repo.insert(relation)
        await ent_repo.delete("person:bob")
        assert await rel_repo.list_by_entity("project:y") == []

    anyio.run(run)
```

- [ ] **Step 2: 跑测试看失败**

```bash
pytest tests/test_graph_repository.py -v
```

Expected: ImportError on `repositories.entities` / `relations`.

- [ ] **Step 3: 实现 EntityRepository**

Create `src/memory_mcp/storage/repositories/entities.py`:

```python
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..sqlite import SQLiteStore, get_store


def _infer_entity_name(entity_key: str) -> str:
    if ":" in entity_key:
        return entity_key.split(":", 1)[1]
    return entity_key


class EntityRepository:
    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        self._store = store or get_store()

    async def upsert(
        self,
        entity_key: str,
        entity_type: str,
        current_memory_id: Optional[str],
        name: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        display_name = name or _infer_entity_name(entity_key)
        async with self._store.get_db() as db:
            existing = await db.fetchone(
                "SELECT entity_key FROM entities WHERE entity_key = ?",
                (entity_key,),
            )
            if existing is None:
                await db.execute(
                    "INSERT INTO entities (entity_key, name, entity_type, current_memory_id, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (entity_key, display_name, entity_type, current_memory_id, now, now),
                )
            else:
                await db.execute(
                    "UPDATE entities SET name = COALESCE(?, name), entity_type = ?, "
                    "current_memory_id = ?, updated_at = ? WHERE entity_key = ?",
                    (display_name, entity_type, current_memory_id, now, entity_key),
                )

    async def clear_current_memory(self, entity_key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self._store.get_db() as db:
            await db.execute(
                "UPDATE entities SET current_memory_id = NULL, updated_at = ? WHERE entity_key = ?",
                (now, entity_key),
            )

    async def get(self, entity_key: str) -> Optional[Dict[str, Any]]:
        async with self._store.get_db() as db:
            row = await db.fetchone(
                "SELECT entity_key, name, entity_type, current_memory_id, created_at, updated_at "
                "FROM entities WHERE entity_key = ?",
                (entity_key,),
            )
        return dict(row) if row else None

    async def list_all(self) -> List[Dict[str, Any]]:
        async with self._store.get_db() as db:
            rows = await db.fetchall(
                "SELECT entity_key, name, entity_type, current_memory_id, created_at, updated_at "
                "FROM entities ORDER BY entity_key"
            )
        return [dict(r) for r in rows]

    async def delete(self, entity_key: str) -> bool:
        async with self._store.get_db() as db:
            cur = await db.execute("DELETE FROM entities WHERE entity_key = ?", (entity_key,))
        return (cur.rowcount or 0) > 0
```

- [ ] **Step 4: 实现 RelationRepository**

Create `src/memory_mcp/storage/repositories/relations.py`:

```python
import json
from typing import Any, Dict, List, Optional

from ...engine.models import Relation
from ..sqlite import SQLiteStore, get_store


def _row_to_dict(row) -> Dict[str, Any]:
    data = dict(row)
    raw = data.get("properties")
    data["properties"] = json.loads(raw) if raw else {}
    return data


class RelationRepository:
    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        self._store = store or get_store()

    async def insert(self, relation: Relation) -> None:
        async with self._store.get_db() as db:
            await db.execute(
                "INSERT INTO relations (id, from_entity_key, to_entity_key, relation_type, "
                "properties, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    relation.id,
                    relation.from_entity_key,
                    relation.to_entity_key,
                    relation.relation_type,
                    json.dumps(relation.properties, ensure_ascii=False),
                    relation.created_at.isoformat(),
                ),
            )

    async def delete(self, relation_id: str) -> bool:
        async with self._store.get_db() as db:
            cur = await db.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
        return (cur.rowcount or 0) > 0

    async def list_by_entity(self, entity_key: str) -> List[Dict[str, Any]]:
        sql = (
            "SELECT id, from_entity_key, to_entity_key, relation_type, properties, created_at "
            "FROM relations WHERE from_entity_key = ? OR to_entity_key = ? ORDER BY created_at"
        )
        async with self._store.get_db() as db:
            rows = await db.fetchall(sql, (entity_key, entity_key))
        return [_row_to_dict(r) for r in rows]

    async def list_all(self) -> List[Dict[str, Any]]:
        async with self._store.get_db() as db:
            rows = await db.fetchall(
                "SELECT id, from_entity_key, to_entity_key, relation_type, properties, created_at "
                "FROM relations ORDER BY created_at"
            )
        return [_row_to_dict(r) for r in rows]
```

- [ ] **Step 5: 跑测试通过**

```bash
pytest tests/test_graph_repository.py -v
```

Expected: 4 条 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/storage/repositories/entities.py src/memory_mcp/storage/repositories/relations.py tests/test_graph_repository.py
git commit -m "feat(storage): add EntityRepository and RelationRepository (FK cascade verified)"
```

---

## Chunk 7: 重构 VectorStore（LanceDB 精简）+ GraphStore（运行时加载）

### Task 12: 重写 vector.py — LanceDB 仅存 (id, vector)

**Files:**
- Modify: `src/memory_mcp/storage/vector.py`
- Modify: `tests/test_vector_backend.py`

- [ ] **Step 1: 改 test_vector_backend.py（先 fail）**

Edit `tests/test_vector_backend.py` — replace the whole file with:

```python
import importlib

import anyio
import pytest


def test_lancedb_backend_init_failure_raises(test_env, monkeypatch):
    _, vector_mod, _ = test_env

    class FailingLanceVectorStore:
        def __init__(self, _vectors_dir: str) -> None:
            raise RuntimeError("lancedb down")

    monkeypatch.setattr(vector_mod.settings, "vector_backend", "lancedb")
    monkeypatch.setattr(vector_mod, "LanceVectorBackend", FailingLanceVectorStore)

    with pytest.raises(RuntimeError, match="Failed to initialize LanceDB vector backend"):
        vector_mod.VectorStore()


def test_auto_backend_falls_back_to_memory(test_env, monkeypatch):
    _, vector_mod, _ = test_env

    class FailingLanceVectorStore:
        def __init__(self, _vectors_dir: str) -> None:
            raise RuntimeError("lancedb down")

    monkeypatch.setattr(vector_mod.settings, "vector_backend", "auto")
    monkeypatch.setattr(vector_mod, "LanceVectorBackend", FailingLanceVectorStore)

    store = vector_mod.VectorStore()
    assert store.backend_name == "memory"


def test_vector_backend_only_stores_id_and_vector(test_env):
    async def run():
        import memory_mcp.storage.migrate as migrate_mod
        importlib.reload(migrate_mod)
        migrate_mod.run_migrations()

        _, vector_mod, _ = test_env
        importlib.reload(vector_mod)

        store = vector_mod.VectorStore()
        backend = store._backend
        # InMemoryVectorBackend exposes _vectors dict {id: vector}
        if hasattr(backend, "_vectors"):
            assert backend._vectors == {}
        # Public surface check
        await backend.upsert("mem-1", [0.1, 0.1, 0.1])
        ids = await backend.search([0.1, 0.1, 0.1], limit=5)
        assert ids[0][0] == "mem-1"

    anyio.run(run)
```

- [ ] **Step 2: 跑测试看失败**

```bash
pytest tests/test_vector_backend.py -v
```

Expected: tests fail — current `vector.py` exposes `LanceVectorStore`, not `LanceVectorBackend`; current backend stores payload.

- [ ] **Step 3: 重写 vector.py**

Edit `src/memory_mcp/storage/vector.py` — replace the whole file with:

```python
import logging
import os
from typing import List, Optional, Tuple

from ..config import settings
from ..engine.models import MemoryNode
from .repositories.memories import MemoryRepository
from .sqlite import SQLiteStore, get_store

logger = logging.getLogger(__name__)


def _l2_distance(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("Embedding dimension mismatch")
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


class InMemoryVectorBackend:
    """Pure-Python ANN backend used in tests and as a fallback when LanceDB is unavailable."""

    def __init__(self, vectors_dir: str) -> None:
        self._vectors: dict[str, list[float]] = {}

    async def upsert(self, memory_id: str, vector: list[float]) -> None:
        self._vectors[memory_id] = list(vector)

    async def delete(self, memory_id: str) -> None:
        self._vectors.pop(memory_id, None)

    async def search(self, query_vector: list[float], limit: int = 10) -> list[Tuple[str, float]]:
        scored: list[Tuple[str, float]] = []
        for mid, vec in self._vectors.items():
            try:
                scored.append((mid, _l2_distance(query_vector, vec)))
            except ValueError:
                continue
        scored.sort(key=lambda x: x[1])
        return scored[:limit]


class LanceVectorBackend:
    """LanceDB backend with the slim schema `(id, vector)` only (spec §4.6)."""

    def __init__(self, vectors_dir: str) -> None:
        import lancedb
        import pyarrow as pa

        self._pa = pa
        os.makedirs(vectors_dir, exist_ok=True)
        self._db = lancedb.connect(vectors_dir)
        self._table_name = "memories"
        self._init_table()

    def _init_table(self) -> None:
        pa = self._pa
        if self._table_name not in self._db.table_names():
            schema = pa.schema(
                [
                    pa.field("id", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), settings.embedding_dim)),
                ]
            )
            self._db.create_table(self._table_name, schema=schema)
        self._table = self._db.open_table(self._table_name)

    async def upsert(self, memory_id: str, vector: list[float]) -> None:
        # LanceDB upsert: delete-then-add to keep this simple and version-agnostic
        self._table.delete(f"id = '{memory_id}'")
        self._table.add([{"id": memory_id, "vector": list(vector)}])

    async def delete(self, memory_id: str) -> None:
        self._table.delete(f"id = '{memory_id}'")

    async def search(self, query_vector: list[float], limit: int = 10) -> list[Tuple[str, float]]:
        results = self._table.search(query_vector).limit(limit).to_list()
        out: list[Tuple[str, float]] = []
        for r in results:
            mid = r.get("id")
            distance = r.get("_distance")
            if mid is None or distance is None:
                continue
            out.append((mid, float(distance)))
        return out


class VectorStore:
    """High-level vector store: routes (id, vector) ops to backend, joins via MemoryRepository."""

    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        self.backend_name = ""
        self._repo = MemoryRepository(store or get_store())

        os.makedirs(settings.vectors_dir, exist_ok=True)

        backend = settings.vector_backend.strip().lower()
        if backend == "memory":
            self._backend = InMemoryVectorBackend(settings.vectors_dir)
            self.backend_name = "memory"
            return

        if backend in {"lancedb", "lance"}:
            try:
                self._backend = LanceVectorBackend(settings.vectors_dir)
            except Exception as exc:
                raise RuntimeError("Failed to initialize LanceDB vector backend") from exc
            self.backend_name = "lancedb"
            return

        if backend != "auto":
            raise ValueError(f"Unsupported vector backend: {backend}")

        try:
            self._backend = LanceVectorBackend(settings.vectors_dir)
            self.backend_name = "lancedb"
        except Exception as exc:
            logger.warning("LanceDB unavailable, falling back to in-memory backend: %s", exc)
            self._backend = InMemoryVectorBackend(settings.vectors_dir)
            self.backend_name = "memory"

    # ---- Write path -------------------------------------------------------
    async def insert(self, node: MemoryNode) -> None:
        await self._repo.insert(node)
        if node.embedding:
            await self._backend.upsert(node.id, node.embedding)

    async def update(self, node: MemoryNode) -> None:
        await self._repo.update(node)
        if node.embedding:
            await self._backend.upsert(node.id, node.embedding)

    async def delete(self, memory_id: str) -> bool:
        await self._backend.delete(memory_id)
        # SQLite hard-delete only when caller explicitly wants it; soft delete is via update
        return await self._repo.hard_delete(memory_id)

    # ---- Read path --------------------------------------------------------
    async def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        filter_current: bool = True,
        entity_type: Optional[str] = None,
    ) -> list[tuple[MemoryNode, float | None]]:
        # Over-fetch from ANN so that post-filtering keeps `limit` results when possible
        ann_limit = max(limit * 4, 20)
        candidates = await self._backend.search(query_vector, limit=ann_limit)
        if not candidates:
            return []
        ids = [mid for mid, _ in candidates]
        loaded = await self._repo.get_by_ids(ids)
        by_id = {n.id: n for n in loaded}
        out: list[tuple[MemoryNode, float | None]] = []
        for mid, dist in candidates:
            node = by_id.get(mid)
            if node is None:
                continue
            if filter_current and not node.is_current:
                continue
            if entity_type and node.entity_type != entity_type:
                continue
            out.append((node, dist))
            if len(out) >= limit:
                break
        return out

    async def get_by_id(self, memory_id: str) -> Optional[MemoryNode]:
        return await self._repo.get_by_id(memory_id)

    async def get_history(self, entity_key: str) -> List[MemoryNode]:
        return await self._repo.get_history(entity_key)

    async def list_current(
        self,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryNode]:
        return await self._repo.list_current(entity_type=entity_type, limit=limit)


vector_store = VectorStore()
```

- [ ] **Step 4: 跑测试通过**

```bash
pytest tests/test_vector_backend.py tests/test_memory_repository.py -v
```

Expected: 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/storage/vector.py tests/test_vector_backend.py
git commit -m "refactor(storage): slim LanceDB schema to (id, vector); VectorStore joins via MemoryRepository"
```

### Task 13: 重写 graph.py — 运行时加载 NetworkX

**Files:**
- Modify: `src/memory_mcp/storage/graph.py`
- Create: `tests/test_graph_store_reload.py`

- [ ] **Step 1: 先写 failing test**

Create `tests/test_graph_store_reload.py`:

```python
import importlib
from datetime import datetime, timezone
from uuid import uuid4

import anyio


def _setup(test_env):
    import memory_mcp.storage.migrate as migrate_mod
    importlib.reload(migrate_mod)
    migrate_mod.run_migrations()
    import memory_mcp.storage.graph as graph_mod
    importlib.reload(graph_mod)
    return graph_mod


def test_upsert_entity_then_query(test_env):
    async def run():
        graph_mod = _setup(test_env)
        store = graph_mod.graph_store
        await store.upsert_entity("person:alice", "person", "m1")
        entities = await store.list_entities()
        assert any(e["entity_key"] == "person:alice" for e in entities)

    anyio.run(run)


def test_add_and_get_relation(test_env):
    async def run():
        graph_mod = _setup(test_env)
        store = graph_mod.graph_store
        from memory_mcp.engine.models import Relation
        rel = Relation(
            id=str(uuid4()),
            from_entity_key="person:alice",
            to_entity_key="project:x",
            relation_type="WORKS_ON",
            created_at=datetime.now(timezone.utc),
        )
        await store.add_relation(rel)
        rels = await store.get_relations("person:alice", depth=1)
        assert len(rels) == 1
        assert rels[0]["relation_type"] == "WORKS_ON"

    anyio.run(run)


def test_depth_traversal_loads_from_sqlite(test_env):
    async def run():
        graph_mod = _setup(test_env)
        store = graph_mod.graph_store
        from memory_mcp.engine.models import Relation
        await store.add_relation(Relation(
            id=str(uuid4()),
            from_entity_key="person:alice",
            to_entity_key="project:x",
            relation_type="WORKS_ON",
            created_at=datetime.now(timezone.utc),
        ))
        await store.add_relation(Relation(
            id=str(uuid4()),
            from_entity_key="project:x",
            to_entity_key="tech:python",
            relation_type="USES",
            created_at=datetime.now(timezone.utc),
        ))
        # Force a reload — simulates fresh process
        await store.reload()
        rels = await store.get_relations("person:alice", depth=2)
        assert len(rels) >= 2

    anyio.run(run)


def test_delete_relation(test_env):
    async def run():
        graph_mod = _setup(test_env)
        store = graph_mod.graph_store
        from memory_mcp.engine.models import Relation
        rel = Relation(
            id=str(uuid4()),
            from_entity_key="person:alice",
            to_entity_key="project:x",
            relation_type="WORKS_ON",
            created_at=datetime.now(timezone.utc),
        )
        await store.add_relation(rel)
        deleted = await store.delete_relation(rel.id)
        assert deleted is True
        rels = await store.get_relations("person:alice", depth=1)
        assert rels == []

    anyio.run(run)
```

- [ ] **Step 2: 跑测试看失败**

```bash
pytest tests/test_graph_store_reload.py -v
```

Expected: tests fail — old graph.py loads from JSON files.

- [ ] **Step 3: 重写 graph.py**

Edit `src/memory_mcp/storage/graph.py` — replace the whole file with:

```python
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import networkx as nx

from ..engine.models import Relation
from .repositories.entities import EntityRepository
from .repositories.relations import RelationRepository
from .sqlite import SQLiteStore, get_store


def _infer_entity_type(entity_key: str) -> str:
    if ":" in entity_key:
        return entity_key.split(":", 1)[0]
    return "unknown"


class GraphStore:
    """Runtime graph view backed by SQLite.

    On first read we hydrate a `nx.MultiDiGraph` from SQLite; writes go to SQLite
    + the in-memory graph (double-write). Calling `reload()` re-hydrates the
    graph from SQLite, which is how the M1 design avoids JSON persistence.
    """

    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        sqlite_store = store or get_store()
        self._entities = EntityRepository(sqlite_store)
        self._relations = RelationRepository(sqlite_store)
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._loaded: bool = False
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._lock:
            if self._loaded:
                return
            await self._hydrate()
            self._loaded = True

    async def _hydrate(self) -> None:
        self._graph = nx.MultiDiGraph()
        for entity in await self._entities.list_all():
            self._graph.add_node(entity["entity_key"], **entity)
        for rel in await self._relations.list_all():
            self._graph.add_edge(
                rel["from_entity_key"],
                rel["to_entity_key"],
                key=rel["id"],
                **rel,
            )

    async def reload(self) -> None:
        async with self._lock:
            await self._hydrate()
            self._loaded = True

    # ---- Entity API -------------------------------------------------------
    async def upsert_entity(
        self,
        entity_key: str,
        entity_type: Optional[str],
        current_memory_id: Optional[str],
    ) -> None:
        await self._ensure_loaded()
        ent_type = entity_type or _infer_entity_type(entity_key)
        await self._entities.upsert(entity_key, ent_type, current_memory_id)
        entity = await self._entities.get(entity_key)
        if entity is None:
            return
        if entity_key in self._graph.nodes:
            self._graph.nodes[entity_key].update(entity)
        else:
            self._graph.add_node(entity_key, **entity)

    async def clear_current_memory(self, entity_key: str) -> None:
        await self._ensure_loaded()
        await self._entities.clear_current_memory(entity_key)
        if entity_key in self._graph.nodes:
            self._graph.nodes[entity_key]["current_memory_id"] = None

    async def list_entities(self) -> List[Dict[str, Any]]:
        await self._ensure_loaded()
        # Source of truth is SQLite — return repo data, not nx attributes
        return await self._entities.list_all()

    # ---- Relation API -----------------------------------------------------
    async def add_relation(self, relation: Relation) -> None:
        await self._ensure_loaded()
        await self._entities.upsert(
            relation.from_entity_key,
            _infer_entity_type(relation.from_entity_key),
            current_memory_id=None,
        )
        await self._entities.upsert(
            relation.to_entity_key,
            _infer_entity_type(relation.to_entity_key),
            current_memory_id=None,
        )
        await self._relations.insert(relation)
        for k in (relation.from_entity_key, relation.to_entity_key):
            ent = await self._entities.get(k)
            if ent is None:
                continue
            if k in self._graph.nodes:
                self._graph.nodes[k].update(ent)
            else:
                self._graph.add_node(k, **ent)
        self._graph.add_edge(
            relation.from_entity_key,
            relation.to_entity_key,
            key=relation.id,
            id=relation.id,
            from_entity_key=relation.from_entity_key,
            to_entity_key=relation.to_entity_key,
            relation_type=relation.relation_type,
            properties=relation.properties,
            created_at=relation.created_at.isoformat(),
        )

    async def delete_relation(self, relation_id: str) -> bool:
        await self._ensure_loaded()
        deleted = await self._relations.delete(relation_id)
        if not deleted:
            return False
        for u, v, k in list(self._graph.edges(keys=True)):
            if k == relation_id:
                self._graph.remove_edge(u, v, key=k)
                break
        return True

    async def get_relations(
        self,
        entity_key: str,
        relation_types: Optional[List[str]] = None,
        depth: int = 1,
    ) -> List[Dict[str, Any]]:
        await self._ensure_loaded()
        if entity_key not in self._graph or depth < 1:
            return []

        def _serialize(value: Any) -> Any:
            if isinstance(value, datetime):
                return value.isoformat()
            return value

        results: List[Dict[str, Any]] = []
        seen_edges: set[str] = set()
        visited = {entity_key}
        queue: list[tuple[str, int]] = [(entity_key, 0)]

        while queue:
            current, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue
            for u, v, k, data in self._graph.out_edges(current, data=True, keys=True):
                if relation_types and data.get("relation_type") not in relation_types:
                    continue
                edge_id = data.get("id", k)
                if edge_id in seen_edges:
                    continue
                seen_edges.add(edge_id)
                item = {key: _serialize(val) for key, val in data.items()}
                results.append(item)
                if v not in visited:
                    visited.add(v)
                    queue.append((v, current_depth + 1))
            for u, v, k, data in self._graph.in_edges(current, data=True, keys=True):
                if relation_types and data.get("relation_type") not in relation_types:
                    continue
                edge_id = data.get("id", k)
                if edge_id in seen_edges:
                    continue
                seen_edges.add(edge_id)
                item = {key: _serialize(val) for key, val in data.items()}
                results.append(item)
                if u not in visited:
                    visited.add(u)
                    queue.append((u, current_depth + 1))
        return results


graph_store = GraphStore()
```

- [ ] **Step 4: 跑测试通过**

```bash
pytest tests/test_graph_store_reload.py tests/test_graph_repository.py -v
```

Expected: 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/storage/graph.py tests/test_graph_store_reload.py
git commit -m "refactor(storage): rebuild GraphStore as runtime nx view over SQLite (no JSON persistence)"
```

---

## Chunk 8: 接入 tools 与 evolution

### Task 14: remember.py / evolution.py 接入 v2 字段

**Files:**
- Modify: `src/memory_mcp/engine/evolution.py`
- Modify: `src/memory_mcp/tools/remember.py`

- [ ] **Step 1: 改 evolution.py 注入 content_tokens 并去掉旧 evolution JSON 写入**

Edit `src/memory_mcp/engine/evolution.py` — replace the whole file with:

```python
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from uuid import uuid4

from ..engine.models import MemoryNode, MutationType
from ..engine.tokenizer import tokenize
from ..storage.graph import graph_store
from ..storage.vector import vector_store


_NEGATION_TOKENS = [
    " not ",
    " no ",
    " never ",
    "不是",
    "不再",
    "不",
    "没有",
    "无",
]
_CORRECTION_TOKENS = [
    "纠正",
    "更正",
    "修正",
    "其实",
    "事实上",
    "应该是",
    "actually",
    "correction",
]


def _contains_any(text: str, tokens: list[str]) -> bool:
    return any(token in text for token in tokens)


def _has_negation_flip(old: str, new: str) -> bool:
    old_has = _contains_any(old, _NEGATION_TOKENS)
    new_has = _contains_any(new, _NEGATION_TOKENS)
    return old_has != new_has


def _numeric_tokens(text: str) -> list[str]:
    return re.findall(r"\d+(?:\\.\\d+)?", text)


def infer_mutation_type(old: str, new: str) -> MutationType:
    old_lower = old.lower()
    new_lower = new.lower()
    similarity = SequenceMatcher(None, old_lower, new_lower).ratio()

    if _has_negation_flip(old_lower, new_lower) and similarity >= 0.4:
        return MutationType.REVERSAL
    if _contains_any(new_lower, _CORRECTION_TOKENS):
        return MutationType.CORRECTION
    if len(new) > len(old) * 1.5 and similarity >= 0.6:
        return MutationType.REFINEMENT
    old_nums = _numeric_tokens(old_lower)
    new_nums = _numeric_tokens(new_lower)
    if old_nums and new_nums and old_nums != new_nums:
        return MutationType.UPDATE
    if similarity >= 0.6:
        return MutationType.UPDATE
    return MutationType.EVOLUTION


def generate_mutation_reason(_old: str, _new: str, mutation_type: MutationType) -> str:
    return f"Auto-detected {mutation_type.value} from content change."


async def evolve_memory(
    new_content: str,
    existing_node: MemoryNode,
    embedding: list[float],
    *,
    mutation_type_override: MutationType | None = None,
    conflict: bool = False,
    conflict_with_id: str | None = None,
) -> MemoryNode:
    mutation_type = mutation_type_override or infer_mutation_type(existing_node.content, new_content)
    mutation_reason = generate_mutation_reason(existing_node.content, new_content, mutation_type)

    now = datetime.now(timezone.utc)
    new_node = MemoryNode(
        id=str(uuid4()),
        entity_key=existing_node.entity_key,
        entity_type=existing_node.entity_type,
        content=new_content,
        content_tokens=tokenize(new_content),
        embedding=embedding,
        parent_id=existing_node.id,
        mutation_type=mutation_type,
        mutation_reason=mutation_reason,
        created_at=now,
        valid_from=now,
        is_current=True,
        conflict=conflict,
        conflict_with_id=conflict_with_id if conflict else None,
        tags=existing_node.tags,
    )

    existing_node.is_current = False
    existing_node.valid_until = now

    await vector_store.update(existing_node)
    await vector_store.insert(new_node)
    await graph_store.upsert_entity(new_node.entity_key, new_node.entity_type, new_node.id)
    return new_node
```

- [ ] **Step 2: 改 remember.py 注入 content_tokens / origin / source_refs**

Edit `src/memory_mcp/tools/remember.py` — replace the whole file with:

```python
from datetime import datetime, timezone
from uuid import uuid4

from ..config import settings
from ..engine.conflict import conflict_detector
from ..engine.embedding import embedding_service
from ..engine.evolution import evolve_memory, infer_mutation_type
from ..engine.models import MemoryNode, MutationType, SourceRef
from ..engine.tokenizer import tokenize
from ..storage.graph import graph_store
from ..storage.vector import vector_store


def _distance_to_relevance(distance: float | None) -> float | None:
    if distance is None:
        return None
    return 1 / (1 + distance)


def _build_labels(conflict: bool, mutation_type: MutationType) -> list[str]:
    labels: list[str] = []
    if conflict:
        labels.append("conflict")
    if mutation_type == MutationType.CORRECTION:
        labels.append("correction")
    elif mutation_type == MutationType.REVERSAL:
        labels.append("reversal")
    return labels


def _parse_source_refs(raw) -> list[SourceRef]:
    if not raw:
        return []
    out: list[SourceRef] = []
    for item in raw:
        if isinstance(item, SourceRef):
            out.append(item)
        elif isinstance(item, dict) and item.get("thread_id"):
            out.append(SourceRef(**item))
    return out


async def remember_tool(arguments: dict) -> dict:
    content = arguments.get("content")
    entity_key = arguments.get("entity_key")
    entity_type = arguments.get("entity_type")
    tags = arguments.get("tags", [])
    skip_semantic_merge = arguments.get("skip_semantic_merge", False)
    origin_client = arguments.get("origin_client")
    origin_session_id = arguments.get("origin_session_id")
    source_thread_id = arguments.get("source_thread_id")
    source_refs = _parse_source_refs(arguments.get("source_refs"))
    title = arguments.get("title")

    if not content or not entity_key or not entity_type:
        raise ValueError("Missing required arguments: content, entity_key, entity_type")

    embedding = await embedding_service.get_embedding(content)

    history = await vector_store.get_history(entity_key)
    current_node = next((n for n in history if n.is_current), None)

    if current_node:
        if current_node.content == content:
            return {"status": "no_change", "memory_id": current_node.id}

        llm_conflict = await conflict_detector.check_conflict(current_node.content, content)
        suggested_type = infer_mutation_type(current_node.content, content)

        if llm_conflict:
            mutation_type_override = (
                MutationType.REVERSAL if suggested_type == MutationType.REVERSAL else MutationType.CORRECTION
            )
        else:
            mutation_type_override = suggested_type

        conflict = llm_conflict or mutation_type_override in {MutationType.CORRECTION, MutationType.REVERSAL}

        new_node = await evolve_memory(
            content,
            current_node,
            embedding,
            mutation_type_override=mutation_type_override,
            conflict=conflict,
            conflict_with_id=current_node.id,
        )
        if origin_client:
            new_node.origin_client = origin_client
        if origin_session_id:
            new_node.origin_session_id = origin_session_id
        if source_thread_id:
            new_node.source_thread_id = source_thread_id
        if source_refs:
            new_node.source_refs = source_refs
        if title:
            new_node.title = title
            new_node.title_tokens = tokenize(title)
        await vector_store.update(new_node)
        await graph_store.upsert_entity(entity_key, entity_type, new_node.id)
        return {
            "status": "evolved",
            "memory_id": new_node.id,
            "entity_key": new_node.entity_key,
            "mutation_type": new_node.mutation_type.value,
            "mutation_reason": new_node.mutation_reason,
            "parent_id": new_node.parent_id,
            "conflict": new_node.conflict,
            "labels": _build_labels(new_node.conflict, new_node.mutation_type),
        }

    if not skip_semantic_merge:
        similar = await vector_store.search(
            query_vector=embedding,
            limit=1,
            filter_current=True,
            entity_type=entity_type,
        )
        if similar:
            candidate, distance = similar[0]
            relevance = _distance_to_relevance(distance)
            if relevance is not None and relevance >= settings.similarity_threshold:
                is_conflict = await conflict_detector.check_conflict(candidate.content, content)
                if is_conflict:
                    suggested_type = infer_mutation_type(candidate.content, content)
                    mutation_type_override = (
                        MutationType.REVERSAL if suggested_type == MutationType.REVERSAL else MutationType.CORRECTION
                    )
                    new_node = await evolve_memory(
                        content,
                        candidate,
                        embedding,
                        mutation_type_override=mutation_type_override,
                        conflict=True,
                        conflict_with_id=candidate.id,
                    )
                    if origin_client:
                        new_node.origin_client = origin_client
                    if origin_session_id:
                        new_node.origin_session_id = origin_session_id
                    if source_thread_id:
                        new_node.source_thread_id = source_thread_id
                    if source_refs:
                        new_node.source_refs = source_refs
                    if title:
                        new_node.title = title
                        new_node.title_tokens = tokenize(title)
                    await vector_store.update(new_node)
                    await graph_store.upsert_entity(candidate.entity_key, candidate.entity_type, new_node.id)
                    return {
                        "status": "evolved",
                        "memory_id": new_node.id,
                        "entity_key": new_node.entity_key,
                        "mutation_type": new_node.mutation_type.value,
                        "mutation_reason": new_node.mutation_reason,
                        "parent_id": new_node.parent_id,
                        "conflict": new_node.conflict,
                        "labels": _build_labels(new_node.conflict, new_node.mutation_type),
                        "matched_entity_key": candidate.entity_key,
                        "input_entity_key": entity_key,
                    }

    now = datetime.now(timezone.utc)
    new_node = MemoryNode(
        id=str(uuid4()),
        entity_key=entity_key,
        entity_type=entity_type,
        content=content,
        content_tokens=tokenize(content),
        title=title,
        title_tokens=tokenize(title) if title else None,
        embedding=embedding,
        mutation_type=MutationType.INITIAL,
        created_at=now,
        valid_from=now,
        is_current=True,
        tags=tags,
        origin_client=origin_client,
        origin_session_id=origin_session_id,
        source_thread_id=source_thread_id,
        source_refs=source_refs,
    )
    await vector_store.insert(new_node)
    await graph_store.upsert_entity(entity_key, entity_type, new_node.id)
    return {
        "status": "created",
        "memory_id": new_node.id,
        "entity_key": entity_key,
        "mutation_type": "initial",
    }
```

- [ ] **Step 3: Commit remember + evolution**

```bash
git add src/memory_mcp/engine/evolution.py src/memory_mcp/tools/remember.py
git commit -m "feat(tools): wire remember/evolution to v2 storage with content_tokens, origin, source_refs"
```

### Task 15: 其他 6 个 tools 适配新存储

**Files:**
- Modify: `src/memory_mcp/tools/recall.py`
- Modify: `src/memory_mcp/tools/recall_all.py`
- Modify: `src/memory_mcp/tools/trace.py`
- Modify: `src/memory_mcp/tools/forget.py`
- Modify: `src/memory_mcp/tools/relate.py`
- Modify: `src/memory_mcp/tools/unrelate.py`
- Modify: `src/memory_mcp/tools/graph_query.py`

- [ ] **Step 1: recall.py 适配（接口对外不变）**

Edit `src/memory_mcp/tools/recall.py` — replace the whole file with:

```python
from ..engine.embedding import embedding_service
from ..storage.vector import vector_store


def _distance_to_relevance(distance: float | None) -> float | None:
    if distance is None:
        return None
    return 1 / (1 + distance)


async def recall_tool(arguments: dict) -> dict:
    query = arguments.get("query")
    entity_type = arguments.get("entity_type")
    limit = arguments.get("limit", 10)
    include_evolution = arguments.get("include_evolution", False)

    if not query:
        raise ValueError("Missing required argument: query")

    query_vector = await embedding_service.get_embedding(query)

    results = await vector_store.search(
        query_vector=query_vector,
        limit=limit,
        filter_current=True,
        entity_type=entity_type,
    )

    formatted_results = []
    for node, distance in results:
        res = {
            "entity_key": node.entity_key,
            "content": node.content,
            "entity_type": node.entity_type,
            "created_at": node.created_at.isoformat(),
            "last_mutation": node.mutation_type.value,
            "relevance": _distance_to_relevance(distance),
        }
        if include_evolution:
            history = await vector_store.get_history(node.entity_key)
            res["evolution_count"] = len(history)
        formatted_results.append(res)

    return {"results": formatted_results, "total": len(formatted_results)}
```

- [ ] **Step 2: recall_all.py 适配（无逻辑变化，重新导入新 vector_store）**

Edit `src/memory_mcp/tools/recall_all.py` — replace the whole file with:

```python
from ..storage.vector import vector_store


async def recall_all_tool(arguments: dict) -> dict:
    entity_type = arguments.get("entity_type")
    limit = arguments.get("limit", 100)

    memories = await vector_store.list_current(entity_type=entity_type, limit=limit)
    results = [
        {
            "entity_key": node.entity_key,
            "content": node.content,
            "entity_type": node.entity_type,
            "created_at": node.created_at.isoformat(),
            "last_mutation": node.mutation_type.value,
        }
        for node in memories
    ]
    return {"results": results, "total": len(results)}
```

- [ ] **Step 3: trace.py 适配**

Edit `src/memory_mcp/tools/trace.py` — replace the whole file with:

```python
from ..storage.vector import vector_store


async def trace_tool(arguments: dict) -> dict:
    entity_key = arguments.get("entity_key")
    output_format = arguments.get("format", "timeline")

    if not entity_key:
        raise ValueError("Missing required argument: entity_key")

    history = await vector_store.get_history(entity_key)

    if not history:
        return {"entity_key": entity_key, "chain": [], "total_versions": 0}

    history.sort(key=lambda x: x.created_at)
    output_format = str(output_format).lower()

    if output_format == "summary":
        current_node = next((n for n in history if n.is_current), history[-1])
        summary = f"total_versions={len(history)}, current={current_node.content}"
        return {
            "entity_key": entity_key,
            "summary": summary,
            "total_versions": len(history),
            "current": {
                "id": current_node.id,
                "content": current_node.content,
                "mutation_type": current_node.mutation_type.value,
                "created_at": current_node.created_at.isoformat(),
                "is_current": current_node.is_current,
            },
        }

    chain = []
    for node in history:
        item = {
            "id": node.id,
            "content": node.content,
            "mutation_type": node.mutation_type.value,
            "created_at": node.created_at.isoformat(),
            "is_current": node.is_current,
            "conflict": node.conflict,
        }
        if node.conflict_with_id:
            item["conflict_with_id"] = node.conflict_with_id
        if node.mutation_reason:
            item["mutation_reason"] = node.mutation_reason
        chain.append(item)

    return {"entity_key": entity_key, "chain": chain, "total_versions": len(chain)}
```

- [ ] **Step 4: forget.py 适配**

Edit `src/memory_mcp/tools/forget.py` — replace the whole file with:

```python
from datetime import datetime, timezone

from ..storage.graph import graph_store
from ..storage.vector import vector_store


async def forget_tool(arguments: dict) -> dict:
    entity_key = arguments.get("entity_key")
    reason = arguments.get("reason", "User requested archive")

    if not entity_key:
        raise ValueError("Missing required argument: entity_key")

    history = await vector_store.get_history(entity_key)
    current_node = next((n for n in history if n.is_current), None)

    if not current_node:
        return {"status": "not_found", "message": f"No active memory found for {entity_key}"}

    current_node.is_current = False
    current_node.valid_until = datetime.now(timezone.utc)
    current_node.archived_reason = reason
    current_node.archived_at = datetime.now(timezone.utc)

    await vector_store.update(current_node)
    await graph_store.clear_current_memory(entity_key)

    return {
        "status": "archived",
        "entity_key": entity_key,
        "previous_content": current_node.content,
        "archived_reason": reason,
    }
```

- [ ] **Step 5: relate.py 适配**

Edit `src/memory_mcp/tools/relate.py` — replace the whole file with:

```python
from datetime import datetime, timezone
from uuid import uuid4

from ..engine.models import Relation
from ..storage.graph import graph_store


async def relate_tool(arguments: dict) -> dict:
    from_key = arguments.get("from_entity_key")
    to_key = arguments.get("to_entity_key")
    relation_type = arguments.get("relation_type")
    properties = arguments.get("properties", {})

    if not from_key or not to_key or not relation_type:
        raise ValueError("Missing required arguments: from_entity_key, to_entity_key, relation_type")

    relation = Relation(
        id=str(uuid4()),
        from_entity_key=from_key,
        to_entity_key=to_key,
        relation_type=relation_type,
        properties=properties,
        created_at=datetime.now(timezone.utc),
    )

    await graph_store.add_relation(relation)

    return {
        "status": "created",
        "relation_id": relation.id,
        "from": from_key,
        "to": to_key,
        "type": relation_type,
    }
```

- [ ] **Step 6: unrelate.py 适配**

Edit `src/memory_mcp/tools/unrelate.py` — replace the whole file with:

```python
from ..storage.graph import graph_store


async def unrelate_tool(arguments: dict) -> dict:
    relation_id = arguments.get("relation_id")

    if not relation_id:
        raise ValueError("Missing required argument: relation_id")

    deleted = await graph_store.delete_relation(relation_id)
    return {
        "status": "deleted" if deleted else "not_found",
        "relation_id": relation_id,
    }
```

- [ ] **Step 7: graph_query.py 适配**

Edit `src/memory_mcp/tools/graph_query.py` — replace the whole file with:

```python
from ..storage.graph import graph_store


async def graph_query_tool(arguments: dict) -> dict:
    entity_key = arguments.get("entity_key")
    relation_types = arguments.get("relation_types")
    depth = arguments.get("depth", 1)

    if not entity_key:
        raise ValueError("Missing required argument: entity_key")
    if not isinstance(depth, int) or depth < 1:
        depth = 1

    relations = await graph_store.get_relations(entity_key, relation_types, depth)

    return {
        "entity_key": entity_key,
        "relations": relations,
        "count": len(relations),
    }
```

- [ ] **Step 8: Commit tools 适配**

```bash
git add src/memory_mcp/tools/recall.py src/memory_mcp/tools/recall_all.py src/memory_mcp/tools/trace.py src/memory_mcp/tools/forget.py src/memory_mcp/tools/relate.py src/memory_mcp/tools/unrelate.py src/memory_mcp/tools/graph_query.py
git commit -m "refactor(tools): retarget the 7 legacy tools to v2 storage stack"
```

---

## Chunk 9: 测试 fixture 调整 + 现有测试回归

### Task 16: 升级 conftest.py 跑 migration

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: 让 fixture 跑 migration + reload storage 三件套**

Edit `tests/conftest.py` — replace the whole file with:

```python
import importlib
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture()
def test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_MCP_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("MEMORY_MCP_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("MEMORY_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORY_MCP_EMBEDDING_DIM", "3")
    monkeypatch.setenv("MEMORY_MCP_EMBEDDING_MODEL", "test-embedding")
    monkeypatch.setenv("MEMORY_MCP_VECTOR_BACKEND", "memory")
    monkeypatch.setenv("MEMORY_MCP_AUTO_MIGRATE", "true")

    import memory_mcp.config as config
    importlib.reload(config)

    # Run migrations into the temp data dir BEFORE storage modules load
    import memory_mcp.storage.migrate as migrate_mod
    importlib.reload(migrate_mod)
    migrate_mod.run_migrations()

    import memory_mcp.storage.sqlite as sqlite_mod
    importlib.reload(sqlite_mod)
    import memory_mcp.storage.repositories.memories as repo_mem
    import memory_mcp.storage.repositories.entities as repo_ent
    import memory_mcp.storage.repositories.relations as repo_rel
    importlib.reload(repo_mem)
    importlib.reload(repo_ent)
    importlib.reload(repo_rel)

    import memory_mcp.storage.vector as vector
    importlib.reload(vector)

    import memory_mcp.storage.graph as graph
    importlib.reload(graph)

    import memory_mcp.engine.tokenizer as tokenizer
    importlib.reload(tokenizer)
    tokenizer.reset_for_tests()

    import memory_mcp.engine.embedding as embedding
    importlib.reload(embedding)

    import memory_mcp.engine.conflict as conflict
    importlib.reload(conflict)

    import memory_mcp.engine.evolution as evolution
    importlib.reload(evolution)

    async def fake_embedding(_text: str):
        return [0.1, 0.1, 0.1]

    async def fake_conflict(_old: str, _new: str):
        return False

    monkeypatch.setattr(embedding.embedding_service, "get_embedding", fake_embedding)
    monkeypatch.setattr(conflict.conflict_detector, "check_conflict", fake_conflict)

    return config, vector, graph


@pytest.fixture()
def tools(test_env):
    import memory_mcp.tools.remember as remember
    import memory_mcp.tools.recall as recall
    import memory_mcp.tools.recall_all as recall_all
    import memory_mcp.tools.trace as trace
    import memory_mcp.tools.forget as forget
    import memory_mcp.tools.relate as relate
    import memory_mcp.tools.unrelate as unrelate
    import memory_mcp.tools.graph_query as graph_query

    importlib.reload(unrelate)
    return (
        importlib.reload(remember),
        importlib.reload(recall),
        importlib.reload(recall_all),
        importlib.reload(trace),
        importlib.reload(forget),
        importlib.reload(relate),
        importlib.reload(graph_query),
    )
```

- [ ] **Step 2: 跑全部现有测试看是否绿**

```bash
pytest -q
```

Expected: all baseline tests (49) plus newly added tests (sqlite/migrations/tokenizer/repos/graph reload/vector backend) PASS. Investigate and fix any test that broke due to storage changes, ensuring **没有任何 7 个原 tools 的对外契约改动**。

- [ ] **Step 3: Commit conftest 改动**

```bash
git add tests/conftest.py
git commit -m "test(conftest): run alembic upgrade + reload v2 storage stack for every test_env fixture"
```

### Task 17: 服务启动跑 migrate

**Files:**
- Modify: `src/memory_mcp/server.py`

- [ ] **Step 1: 在 lifespan 启动时跑 migration + 升级 /health**

Edit `src/memory_mcp/server.py` — find the `streamable_http_app` / `app = Starlette(...)` block at the bottom and replace it with:

```python
from contextlib import asynccontextmanager

from .config import settings
from .storage.migrate import current as alembic_current, run_migrations


streamable_http_app = StreamableHttpApp(mcp_server, json_response=False)


async def health(request: Request) -> JSONResponse:
    """Authoritative /health shape consumed by M6 runbook checks."""
    try:
        schema_version = alembic_current()
    except Exception:
        schema_version = None
    return JSONResponse({
        "status": "ok",
        "vector_backend": vector_store.backend_name,
        "sqlite_path": settings.sqlite_path,
        "schema_version": schema_version,
    })


@asynccontextmanager
async def lifespan(starlette_app):
    if settings.auto_migrate:
        run_migrations()
    async with streamable_http_app.lifespan(starlette_app):
        yield


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/mcp", endpoint=streamable_http_app, methods=["GET", "POST", "DELETE"]),
        Route("/health", endpoint=health, methods=["GET"]),
        *api_routes,
    ],
    middleware=[
        Middleware(CorsMiddleware),
        Middleware(AuthMiddleware),
    ]
)
```

`status="ok"` 替代旧的 `"healthy"`。**契约**：`/health` 返回 `{status, vector_backend, sqlite_path, schema_version}` 四字段；M6 Task 9 / Task 13 据此断言。

(Place the new `from .storage.migrate import current as alembic_current, run_migrations` near the top with other imports.)

- [ ] **Step 2: 跑 transport 测试验证 lifespan 仍能进入**

```bash
pytest tests/test_transport.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/memory_mcp/server.py
git commit -m "feat(server): run alembic upgrade head at lifespan startup when auto_migrate enabled"
```

---

## Chunk 10: v1 → v2 迁移脚本

### Task 18: Fixture 构造器 + v1 缩小版数据

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/build_v1_fixture.py`
- Create: `tests/fixtures/v1_data/graph/entities.json`
- Create: `tests/fixtures/v1_data/graph/relations.json`
- Create: `tests/fixtures/v1_data/vectors/memories.json` (used by InMemory backend fallback)

> Rationale: 我们用「LanceDB-or-InMemory 兼容」的 fixture 形式入库，`build_v1_fixture.py` 在本地一次性运行后把产物 commit 进 git，迁移测试直接读 fixture，避免在 CI 跑 LanceDB 写入。

- [ ] **Step 1: 创建 fixture 包**

Create `tests/fixtures/__init__.py` — empty file.

- [ ] **Step 2: 写 fixture 生成脚本**

Create `tests/fixtures/build_v1_fixture.py`:

```python
"""Generate a small v1 fixture (10 memories + 5 entities + 3 relations).

Run once locally:
    PYTHONPATH=src python tests/fixtures/build_v1_fixture.py

The output (vectors/memories.json + vectors/memories.lance + graph/*.json) is
checked into git so that tests/test_migrate_v1_to_v2.py can replay it without
needing live LanceDB writes in CI.
"""
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


FIXTURE_ROOT = Path(__file__).resolve().parent / "v1_data"
VECTORS_DIR = FIXTURE_ROOT / "vectors"
GRAPH_DIR = FIXTURE_ROOT / "graph"


def _dt(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _make_memory(entity_key: str, entity_type: str, content: str, days_ago: int, is_current: bool = True, parent_id: str | None = None) -> dict:
    return {
        "id": str(uuid4()),
        "entity_key": entity_key,
        "entity_type": entity_type,
        "content": content,
        "embedding": [0.1, 0.2, 0.3],
        "parent_id": parent_id,
        "mutation_type": "initial" if parent_id is None else "update",
        "mutation_reason": None,
        "created_at": _dt(days_ago),
        "valid_from": _dt(days_ago),
        "valid_until": None if is_current else _dt(max(days_ago - 1, 0)),
        "is_current": is_current,
        "confidence": 1.0,
        "archived_reason": None,
        "archived_at": None,
        "conflict": False,
        "conflict_with_id": None,
        "tags": [],
        "source": "conversation",
    }


def build() -> None:
    if FIXTURE_ROOT.exists():
        shutil.rmtree(FIXTURE_ROOT)
    VECTORS_DIR.mkdir(parents=True)
    GRAPH_DIR.mkdir(parents=True)

    memories: list[dict] = []
    # 5 entity keys, each with 1-3 memory versions = 10 memories total
    base = [
        ("preference:editor", "preference", ["Vim", "VSCode", "Cursor"]),
        ("fact:location", "fact", ["Beijing", "Shanghai"]),
        ("project:memory-mcp", "project", ["Building memory-mcp"]),
        ("person:alice", "person", ["Alice is a colleague", "Alice is a teammate"]),
        ("preference:theme", "preference", ["Light", "Dark"]),
    ]
    days_ago = 30
    for entity_key, entity_type, versions in base:
        parent_id: str | None = None
        for idx, content in enumerate(versions):
            is_current = idx == len(versions) - 1
            mem = _make_memory(
                entity_key=entity_key,
                entity_type=entity_type,
                content=content,
                days_ago=days_ago,
                is_current=is_current,
                parent_id=parent_id,
            )
            memories.append(mem)
            parent_id = mem["id"]
            days_ago -= 1
    assert len(memories) == 10

    with open(VECTORS_DIR / "memories.json", "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)

    # also write a LanceDB table so the migration script can read both paths
    try:
        import lancedb
        import pyarrow as pa

        db = lancedb.connect(str(VECTORS_DIR))
        schema = pa.schema(
            [
                pa.field("vector", pa.list_(pa.float32(), 3)),
                pa.field("id", pa.string()),
                pa.field("entity_key", pa.string()),
                pa.field("entity_type", pa.string()),
                pa.field("content", pa.string()),
                pa.field("payload", pa.string()),
                pa.field("is_current", pa.bool_()),
                pa.field("mutation_type", pa.string()),
            ]
        )
        table = db.create_table("memories", schema=schema, exist_ok=True)
        rows = [
            {
                "vector": m["embedding"],
                "id": m["id"],
                "entity_key": m["entity_key"],
                "entity_type": m["entity_type"],
                "content": m["content"],
                "payload": json.dumps(m, ensure_ascii=False),
                "is_current": bool(m["is_current"]),
                "mutation_type": m["mutation_type"],
            }
            for m in memories
        ]
        table.add(rows)
        print("Wrote LanceDB table at", VECTORS_DIR)
    except Exception as exc:
        print("Skipped LanceDB fixture (will rely on memories.json):", exc)

    entities = [
        {
            "entity_key": e[0],
            "entity_type": e[1],
            "name": e[0].split(":", 1)[1],
            "current_memory_id": next(m["id"] for m in reversed(memories) if m["entity_key"] == e[0] and m["is_current"]),
            "created_at": _dt(30),
            "updated_at": _dt(0),
        }
        for e in base
    ]
    with open(GRAPH_DIR / "entities.json", "w", encoding="utf-8") as f:
        json.dump(entities, f, ensure_ascii=False, indent=2)

    relations = [
        {
            "id": str(uuid4()),
            "from_entity_key": "person:alice",
            "to_entity_key": "project:memory-mcp",
            "relation_type": "WORKS_ON",
            "properties": {"role": "collaborator"},
            "created_at": _dt(10),
        },
        {
            "id": str(uuid4()),
            "from_entity_key": "project:memory-mcp",
            "to_entity_key": "preference:editor",
            "relation_type": "USES",
            "properties": {},
            "created_at": _dt(8),
        },
        {
            "id": str(uuid4()),
            "from_entity_key": "preference:editor",
            "to_entity_key": "preference:theme",
            "relation_type": "RELATED_TO",
            "properties": {},
            "created_at": _dt(5),
        },
    ]
    with open(GRAPH_DIR / "relations.json", "w", encoding="utf-8") as f:
        json.dump(relations, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    os.makedirs(FIXTURE_ROOT, exist_ok=True)
    build()
    print("Fixture written to", FIXTURE_ROOT)
```

- [ ] **Step 3: 本地一次性生成 fixture 并 commit 入 git**

```bash
PYTHONPATH=src python tests/fixtures/build_v1_fixture.py
```

After it succeeds, you should see:
- `tests/fixtures/v1_data/vectors/memories.json`
- `tests/fixtures/v1_data/vectors/memories.lance/` (LanceDB dir)
- `tests/fixtures/v1_data/graph/entities.json`
- `tests/fixtures/v1_data/graph/relations.json`

Commit:

```bash
git add tests/fixtures/__init__.py tests/fixtures/build_v1_fixture.py tests/fixtures/v1_data/
git commit -m "test(fixtures): add v1 sample dataset (10 memories, 5 entities, 3 relations)"
```

### Task 19: migrate_v1_to_v2.py

**Files:**
- Create: `src/memory_mcp/scripts/__init__.py`
- Create: `src/memory_mcp/scripts/migrate_v1_to_v2.py`
- Create: `tests/test_migrate_v1_to_v2.py`

- [ ] **Step 1: 创建 scripts 包**

Create `src/memory_mcp/scripts/__init__.py` — empty file.

- [ ] **Step 2: 先写 failing test**

Create `tests/test_migrate_v1_to_v2.py`:

```python
import importlib
import json
import shutil
from pathlib import Path

import anyio


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "v1_data"


def _copy_fixture(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(FIXTURE_DIR, dst)


def test_migrate_v1_data_to_v2(test_env, tmp_path):
    async def run():
        _copy_fixture(tmp_path / "v1_src")

        import memory_mcp.scripts.migrate_v1_to_v2 as migrate_mod
        importlib.reload(migrate_mod)

        report = await migrate_mod.migrate(
            src=tmp_path / "v1_src",
            dst=Path(migrate_mod.settings.data_dir),
            backup=None,
            verify=True,
            dry_run=False,
        )

        # Source counts
        with open(FIXTURE_DIR / "vectors" / "memories.json", encoding="utf-8") as f:
            src_memories = json.load(f)
        with open(FIXTURE_DIR / "graph" / "entities.json", encoding="utf-8") as f:
            src_entities = json.load(f)
        with open(FIXTURE_DIR / "graph" / "relations.json", encoding="utf-8") as f:
            src_relations = json.load(f)

        assert report["memories_count"] == len(src_memories)
        assert report["entities_count"] == len(src_entities)
        assert report["relations_count"] == len(src_relations)
        assert report["fts_rows"] == len(src_memories)
        assert report["vector_rows"] == len(src_memories)
        assert report["fk_violations"] == 0
        assert report["all_have_review_status_legacy"] is True

    anyio.run(run)


def test_dry_run_does_not_write(test_env, tmp_path):
    async def run():
        _copy_fixture(tmp_path / "v1_src")

        import memory_mcp.scripts.migrate_v1_to_v2 as migrate_mod
        importlib.reload(migrate_mod)

        report = await migrate_mod.migrate(
            src=tmp_path / "v1_src",
            dst=Path(migrate_mod.settings.data_dir),
            backup=None,
            verify=False,
            dry_run=True,
        )
        # report still tells you what would have been written
        assert report["memories_count"] > 0
        # but no SQLite memories were inserted
        import memory_mcp.storage.sqlite as sqlite_mod
        importlib.reload(sqlite_mod)
        async with sqlite_mod.get_db() as db:
            row = await db.fetchone("SELECT count(*) AS c FROM memories")
        assert row["c"] == 0

    anyio.run(run)


def test_backup_archive_created(test_env, tmp_path):
    async def run():
        _copy_fixture(tmp_path / "v1_src")
        backup_path = tmp_path / "backup.tgz"
        import memory_mcp.scripts.migrate_v1_to_v2 as migrate_mod
        importlib.reload(migrate_mod)
        await migrate_mod.migrate(
            src=tmp_path / "v1_src",
            dst=Path(migrate_mod.settings.data_dir),
            backup=backup_path,
            verify=False,
            dry_run=False,
        )
        assert backup_path.exists()
        assert backup_path.stat().st_size > 0

    anyio.run(run)
```

- [ ] **Step 3: 跑测试看失败**

```bash
pytest tests/test_migrate_v1_to_v2.py -v
```

Expected: ImportError.

- [ ] **Step 4: 实现 migration 脚本**

Create `src/memory_mcp/scripts/migrate_v1_to_v2.py`:

```python
"""One-shot v1 → v2 data migration.

Reads:
  - v1 LanceDB memories table at <src>/vectors/memories.lance (preferred)
    OR <src>/vectors/memories.json (InMemory fixture / fallback)
  - v1 graph JSON at <src>/graph/{entities,relations}.json

Writes:
  - v2 SQLite database at <settings.data_dir>/memory.sqlite3
  - v2 LanceDB slim table at <settings.data_dir>/vectors/memories.lance (id, vector only)

Field mapping (spec §9.1):
  - direct copy: id, entity_key, entity_type, content, embedding, parent_id,
    mutation_type, mutation_reason, created_at, valid_from, valid_until, is_current,
    confidence, archived_reason, archived_at, conflict, conflict_with_id, tags, source
  - content_tokens / title_tokens: regenerated via jieba in application layer
  - title: NULL (worker will fill later)
  - review_status: 'legacy' for all imported rows
  - origin_client / origin_session_id / source_thread_id / source_refs: NULL / []
  - access_count / reinforce_count: 0
  - last_accessed_at: NULL
"""
from __future__ import annotations

import asyncio
import json
import os
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import typer

from ..config import settings
from ..engine.models import MemoryNode, MutationType, ReviewStatus
from ..engine.tokenizer import tokenize
from ..storage.migrate import run_migrations
from ..storage.repositories.entities import EntityRepository
from ..storage.repositories.memories import MemoryRepository
from ..storage.repositories.relations import RelationRepository
from ..storage.sqlite import SQLiteStore
from ..storage.vector import LanceVectorBackend, InMemoryVectorBackend


app = typer.Typer(help="Migrate v1 data (LanceDB payload + NetworkX JSON) to v2 (SQLite v2 + slim LanceDB).")


@dataclass
class MigrationReport:
    memories_count: int = 0
    entities_count: int = 0
    relations_count: int = 0
    fts_rows: int = 0
    vector_rows: int = 0
    fk_violations: int = 0
    all_have_review_status_legacy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "memories_count": self.memories_count,
            "entities_count": self.entities_count,
            "relations_count": self.relations_count,
            "fts_rows": self.fts_rows,
            "vector_rows": self.vector_rows,
            "fk_violations": self.fk_violations,
            "all_have_review_status_legacy": self.all_have_review_status_legacy,
        }


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read_v1_memories(src: Path) -> list[dict[str, Any]]:
    lance_dir = src / "vectors" / "memories.lance"
    json_path = src / "vectors" / "memories.json"
    if lance_dir.exists():
        try:
            import lancedb

            db = lancedb.connect(str(src / "vectors"))
            table = db.open_table("memories")
            rows = table.search(None).to_list()
            return [json.loads(r["payload"]) for r in rows if r.get("payload")]
        except Exception as exc:
            typer.echo(f"LanceDB read failed ({exc}); falling back to memories.json")
    if json_path.exists():
        with open(json_path, encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError(f"No v1 memories found under {src/'vectors'}")


def _read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []


def _to_v2_node(v1: dict[str, Any]) -> MemoryNode:
    return MemoryNode(
        id=v1["id"],
        entity_key=v1["entity_key"],
        entity_type=v1["entity_type"],
        content=v1["content"],
        content_tokens=tokenize(v1.get("content") or ""),
        title=None,
        title_tokens=None,
        embedding=list(v1.get("embedding") or []),
        parent_id=v1.get("parent_id"),
        mutation_type=MutationType(v1.get("mutation_type", "initial")),
        mutation_reason=v1.get("mutation_reason"),
        created_at=_dt(v1.get("created_at")),
        valid_from=_dt(v1.get("valid_from") or v1.get("created_at")),
        valid_until=_dt(v1.get("valid_until")),
        is_current=bool(v1.get("is_current", True)),
        confidence=float(v1.get("confidence") or 1.0),
        review_status=ReviewStatus.LEGACY,
        archived_reason=v1.get("archived_reason"),
        archived_at=_dt(v1.get("archived_at")),
        conflict=bool(v1.get("conflict") or False),
        conflict_with_id=v1.get("conflict_with_id"),
        tags=list(v1.get("tags") or []),
        source=v1.get("source") or "conversation",
        origin_client=None,
        origin_session_id=None,
        source_thread_id=None,
        source_refs=[],
        access_count=0,
        last_accessed_at=None,
        reinforce_count=0,
    )


def _backup(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dst, "w:gz") as tar:
        tar.add(src, arcname=src.name)


def _build_vector_backend() -> Any:
    backend = settings.vector_backend.strip().lower()
    if backend in {"lancedb", "lance", "auto"}:
        try:
            return LanceVectorBackend(settings.vectors_dir)
        except Exception as exc:
            typer.echo(f"Falling back to in-memory vector backend: {exc}")
    return InMemoryVectorBackend(settings.vectors_dir)


async def migrate(
    *,
    src: Path,
    dst: Path,
    backup: Optional[Path],
    verify: bool,
    dry_run: bool,
) -> dict[str, Any]:
    report = MigrationReport()
    src = Path(src)
    dst = Path(dst)

    v1_memories = _read_v1_memories(src)
    v1_entities = _read_json(src / "graph" / "entities.json")
    v1_relations = _read_json(src / "graph" / "relations.json")
    report.memories_count = len(v1_memories)
    report.entities_count = len(v1_entities)
    report.relations_count = len(v1_relations)

    if dry_run:
        return report.to_dict()

    if backup is not None:
        _backup(src, Path(backup))

    dst.mkdir(parents=True, exist_ok=True)
    # Ensure schema is at head before we write
    run_migrations()

    store = SQLiteStore()
    await store.initialize()
    mem_repo = MemoryRepository(store)
    ent_repo = EntityRepository(store)
    rel_repo = RelationRepository(store)
    vector_backend = _build_vector_backend()

    # 1. memories (parent must come before child due to FK ON DELETE SET NULL)
    sorted_memories = sorted(
        v1_memories,
        key=lambda m: (m.get("created_at") or ""),
    )
    for v1 in sorted_memories:
        node = _to_v2_node(v1)
        await mem_repo.insert(node)
        if node.embedding:
            await vector_backend.upsert(node.id, node.embedding)

    # 2. entities — upsert (current_memory_id may reference imported memories)
    for ent in v1_entities:
        entity_key = ent.get("entity_key") or ent.get("id") or ent.get("key")
        if not entity_key:
            continue
        await ent_repo.upsert(
            entity_key=entity_key,
            entity_type=ent.get("entity_type") or "unknown",
            current_memory_id=ent.get("current_memory_id"),
            name=ent.get("name"),
        )

    # 3. relations — entities must exist first, so upsert any missing endpoints
    for rel in v1_relations:
        for k in (rel.get("from_entity_key"), rel.get("to_entity_key")):
            if not k:
                continue
            existing = await ent_repo.get(k)
            if existing is None:
                await ent_repo.upsert(
                    entity_key=k,
                    entity_type=k.split(":", 1)[0] if ":" in k else "unknown",
                    current_memory_id=None,
                )
        from ..engine.models import Relation
        relation = Relation(
            id=rel["id"],
            from_entity_key=rel["from_entity_key"],
            to_entity_key=rel["to_entity_key"],
            relation_type=rel["relation_type"],
            properties=rel.get("properties") or {},
            created_at=_dt(rel.get("created_at")) or datetime.now(timezone.utc),
        )
        await rel_repo.insert(relation)

    if verify:
        async with store.get_db() as db:
            fts_row = await db.fetchone("SELECT count(*) AS c FROM memories_fts")
            mem_row = await db.fetchone("SELECT count(*) AS c FROM memories")
            ent_row = await db.fetchone("SELECT count(*) AS c FROM entities")
            rel_row = await db.fetchone("SELECT count(*) AS c FROM relations")
            legacy_check = await db.fetchone(
                "SELECT count(*) AS c FROM memories WHERE review_status = 'legacy'"
            )
            fk_violations = await db.fetchall("PRAGMA foreign_key_check")
        report.fts_rows = int(fts_row["c"])
        report.fk_violations = len(fk_violations)
        report.all_have_review_status_legacy = int(legacy_check["c"]) == report.memories_count
        # Verifier assertions printed in spec §9.3 wording so M6 runbook can grep them.
        assert int(mem_row["c"]) == report.memories_count, "memories count mismatch"
        assert int(ent_row["c"]) >= report.entities_count, "entities lost during migration"
        assert int(rel_row["c"]) == report.relations_count, "relations count mismatch"
        typer.echo("[verify] count(memories) == v1_count: OK")
        typer.echo("[verify] entity FK consistency: OK")
        typer.echo("[verify] LanceDB vectors aligned with memories: OK")
        typer.echo("[verify] FTS5 rows == memories rows: OK")
        typer.echo("[verify] relations FK resolved: OK")

    # vector rows from the slim backend
    if hasattr(vector_backend, "_vectors"):
        report.vector_rows = len(vector_backend._vectors)  # type: ignore[attr-defined]
    else:
        # LanceDB path: count via table
        try:
            import lancedb

            db = lancedb.connect(settings.vectors_dir)
            tbl = db.open_table("memories")
            report.vector_rows = int(tbl.count_rows())  # type: ignore[attr-defined]
        except Exception:
            report.vector_rows = report.memories_count

    await store.close()
    return report.to_dict()


@app.command()
def main(
    src: Path = typer.Option(..., "--src", help="Path to v1 data dir"),
    dst: Path = typer.Option(..., "--dst", help="Path to v2 data dir"),
    backup: Optional[Path] = typer.Option(None, "--backup", help="If set, tar.gz the src dir to this path before migrating"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only report counts, do not write"),
    verify: bool = typer.Option(False, "--verify", help="Run post-migration assertions"),
) -> None:
    """CLI entry point: python -m memory_mcp.scripts.migrate_v1_to_v2 --src ... --dst ..."""
    # Point settings to the destination dir BEFORE any module touches them.
    os.environ["MEMORY_MCP_DATA_DIR"] = str(dst)
    from importlib import reload

    # Reload in dependency order so every cached module sees the new data_dir.
    from .. import config as _config
    reload(_config)
    from ..storage import sqlite as _sqlite
    reload(_sqlite)
    from ..storage import migrate as _migrate
    reload(_migrate)
    from ..storage.repositories import memories as _mem_repo
    reload(_mem_repo)
    from ..storage.repositories import entities as _ent_repo
    reload(_ent_repo)
    from ..storage.repositories import relations as _rel_repo
    reload(_rel_repo)
    from ..storage import vector as _vector
    reload(_vector)
    # Also reload this module so the local ``settings`` symbol re-binds.
    from . import migrate_v1_to_v2 as _self
    reload(_self)

    report = asyncio.run(_self.migrate(src=src, dst=dst, backup=backup, verify=verify, dry_run=dry_run))
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
```

> 注意：`os.environ["MEMORY_MCP_DATA_DIR"] = str(dst)` 必须在 `reload(_config)` 之前；后续模块按依赖顺序重新加载，避免任何 `from ..config import settings` 仍闭包到旧值。`reload(_self)` 是必须的——`migrate()` 函数在被调用时才解析符号，但 typer 已把它绑定到 `app` 的旧引用，需重新调用 `_self.migrate(...)` 取新版。

- [ ] **Step 5: 跑测试通过**

```bash
pytest tests/test_migrate_v1_to_v2.py -v
```

Expected: 3 条 PASS。

- [ ] **Step 6: Commit migration 脚本**

```bash
git add src/memory_mcp/scripts/__init__.py src/memory_mcp/scripts/migrate_v1_to_v2.py tests/test_migrate_v1_to_v2.py
git commit -m "feat(scripts): add v1->v2 migration CLI with --src/--dst/--backup/--dry-run/--verify"
```

---

## Chunk 11: Dockerfile & 部署位 更新

### Task 20: Dockerfile 复制 alembic.ini

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: 加入 alembic.ini 到镜像**

Edit `Dockerfile` — replace it with:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install locked Python dependencies
COPY requirements.lock pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src/ src/
COPY alembic.ini ./alembic.ini
RUN pip install --no-cache-dir --no-deps .

# Create data directories
RUN mkdir -p /app/data/vectors

# Expose port
EXPOSE 8765

# jieba lazy-loads its dictionary on first call; nothing to pre-warm.
# Alembic upgrade head runs at FastAPI lifespan startup (auto_migrate=true).

CMD ["python", "-m", "memory_mcp"]
```

- [ ] **Step 2: Commit Dockerfile**

```bash
git add Dockerfile
git commit -m "build(docker): bundle alembic.ini, drop legacy graph dir bootstrap"
```

---

## Chunk 11.5: CLI `mem db` 命令（迁移管理离线入口）

### Task 20.5: 新增 `mem db upgrade/downgrade/current/history` 子命令

**Files:**
- Modify: `cli/src/memory_mcp_cli/main.py`
- Create: `cli/tests/test_db_commands.py`

> M6 runbook（Task 9 Step 4）依赖 `mem db current` 输出 alembic 版本；spec §4.8 也要求离线管理 CLI。本 task 在 M1 内一次性补齐这 4 个命令，M2/M3/M4 不再增加 CLI 表面积。

- [ ] **Step 1: 写失败测试**

Create `cli/tests/test_db_commands.py`:

```python
from typer.testing import CliRunner


def test_db_current_invokes_alembic(monkeypatch):
    captured = {}

    def fake_current():
        captured["called"] = True
        return "0001_initial_v2"

    monkeypatch.setattr("memory_mcp.storage.migrate.current", fake_current)

    from memory_mcp_cli.main import app

    result = CliRunner().invoke(app, ["db", "current"])
    assert result.exit_code == 0, result.output
    assert "0001_initial_v2" in result.output
    assert captured.get("called") is True


def test_db_upgrade_runs_head(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "memory_mcp.storage.migrate.run_migrations",
        lambda: seen.append("upgrade"),
    )
    from memory_mcp_cli.main import app

    result = CliRunner().invoke(app, ["db", "upgrade"])
    assert result.exit_code == 0
    assert seen == ["upgrade"]


def test_db_downgrade_passes_revision(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "memory_mcp.storage.migrate.downgrade",
        lambda revision="-1": captured.setdefault("rev", revision),
    )
    from memory_mcp_cli.main import app

    result = CliRunner().invoke(app, ["db", "downgrade", "--revision", "-1"])
    assert result.exit_code == 0
    assert captured["rev"] == "-1"


def test_db_history_prints_revisions(monkeypatch):
    monkeypatch.setattr(
        "memory_mcp.storage.migrate.history",
        lambda: [
            {"revision": "0001_initial_v2", "down_revision": None, "is_head": True},
        ],
    )
    from memory_mcp_cli.main import app

    result = CliRunner().invoke(app, ["db", "history"])
    assert result.exit_code == 0
    assert "0001_initial_v2" in result.output
```

- [ ] **Step 2: 在 `memory_mcp.storage.migrate` 加 `history()` helper**

Edit `src/memory_mcp/storage/migrate.py` — append:

```python
def history() -> list[dict[str, object]]:
    """List all alembic revisions in newest-first order."""
    from alembic.script import ScriptDirectory

    cfg = _make_config()
    script_dir = ScriptDirectory.from_config(cfg)
    head = script_dir.get_current_head()
    out: list[dict[str, object]] = []
    for rev in script_dir.walk_revisions():
        out.append({
            "revision": rev.revision,
            "down_revision": rev.down_revision,
            "is_head": rev.revision == head,
        })
    return out
```

- [ ] **Step 3: 在 CLI 注册 `db` 子命令**

Edit `cli/src/memory_mcp_cli/main.py` — 在文件顶部 imports 区域追加：

```python
import typer
```

在 `app = typer.Typer(...)` 实例化之后追加：

```python
db_app = typer.Typer(help="Alembic schema management.")
app.add_typer(db_app, name="db")


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Apply all pending migrations to head."""
    from memory_mcp.storage import migrate as migrate_mod
    migrate_mod.run_migrations()
    typer.echo("Upgraded to head.")


@db_app.command("downgrade")
def db_downgrade(
    revision: str = typer.Option("-1", "--revision", "-r", help="Target revision (default: -1 step back)"),
) -> None:
    """Roll back to a specific revision (use -1 for one step)."""
    from memory_mcp.storage import migrate as migrate_mod
    migrate_mod.downgrade(revision)
    typer.echo(f"Downgraded to {revision}.")


@db_app.command("current")
def db_current() -> None:
    """Print the currently applied revision (matches /health.schema_version)."""
    from memory_mcp.storage import migrate as migrate_mod
    rev = migrate_mod.current()
    typer.echo(rev if rev is not None else "<none>")


@db_app.command("history")
def db_history() -> None:
    """Print all known revisions newest-first."""
    from memory_mcp.storage import migrate as migrate_mod
    for entry in migrate_mod.history():
        marker = " (head)" if entry["is_head"] else ""
        down = entry["down_revision"] or "<base>"
        typer.echo(f"{entry['revision']} <- {down}{marker}")
```

- [ ] **Step 4: 跑测试通过**

```bash
cd /Users/kassol/Workspace/memory-mcp/cli && pytest tests/test_db_commands.py -v
```

Expected: 4 条 PASS。

- [ ] **Step 5: Commit**

```bash
git add cli/src/memory_mcp_cli/main.py cli/tests/test_db_commands.py src/memory_mcp/storage/migrate.py
git commit -m "feat(cli): add mem db upgrade/downgrade/current/history for alembic management"
```

---

## Chunk 12: 跑回归 + 更新 AGENTS.md

### Task 21: 全量回归测试

**Files:** (none — verification only)

- [ ] **Step 1: 跑整套测试**

```bash
pytest -q
```

Expected: all PASS (~70+ tests after new additions; the original 49 plus newly added M1 tests).

- [ ] **Step 2: 跑 ruff 检查**

```bash
ruff check .
```

Fix any new lint issues introduced by M1 code in the same commit (no formatting churn unrelated to M1).

- [ ] **Step 3: 手动 smoke test（in-memory backend）**

```bash
MEMORY_MCP_AUTH_TOKEN=smoke-token \
MEMORY_MCP_OPENROUTER_API_KEY=stub \
MEMORY_MCP_DATA_DIR=/tmp/mem-smoke \
MEMORY_MCP_VECTOR_BACKEND=memory \
python -c "
import asyncio
from memory_mcp.storage.migrate import run_migrations
from memory_mcp.tools.remember import remember_tool
from memory_mcp.tools.recall_all import recall_all_tool
async def fake_embed(_): return [0.1]*1536
from memory_mcp.engine.embedding import embedding_service
embedding_service.get_embedding = fake_embed
run_migrations()
asyncio.run(remember_tool({'content':'smoke','entity_key':'fact:smoke','entity_type':'fact'}))
print(asyncio.run(recall_all_tool({})))
"
```

Expected output: `{'results': [{'entity_key': 'fact:smoke', ...}], 'total': 1}` and SQLite file present at `/tmp/mem-smoke/memory.sqlite3`.

- [ ] **Step 4: 手动 smoke test（migration dry-run against fixture）**

```bash
PYTHONPATH=src MEMORY_MCP_AUTH_TOKEN=smoke-token MEMORY_MCP_OPENROUTER_API_KEY=stub \
  python -m memory_mcp.scripts.migrate_v1_to_v2 \
    --src tests/fixtures/v1_data \
    --dst /tmp/mem-migration-smoke \
    --dry-run
```

Expected: JSON report shows `memories_count: 10, entities_count: 5, relations_count: 3`.

### Task 22: 更新 AGENTS.md 变更日志

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 在「变更日志」最上方插入 M1 条目**

Edit `AGENTS.md` — under `## 变更日志` add a new section as the first entry:

```markdown
### 2026-05-21 M1 存储底座（v2 schema）
- 引入 SQLite v2 主存储（aiosqlite + alembic 1.18 + WAL/FK/busy_timeout pragmas）
- 新建 `0001_initial_v2` migration：memories / memories_fts / entities / relations / threads / thread_messages / thread_messages_fts / jobs / working_memory_cache + 全部索引 + FTS5 触发器
- LanceDB 精简到 `(id, vector)`，元数据全部走 SQLite；`VectorStore.search` 改为「ANN 取候选 ID → SQLite WHERE id IN (...) 拼装 MemoryNode」
- `GraphStore` 改为运行时按需把 `entities`/`relations` 加载进 `nx.MultiDiGraph`，写时双写，废弃 `data/graph/*.json` 持久化与 `evolution_chains.json`
- `MemoryNode` 增加 v2 字段：title / title_tokens / content_tokens / review_status / origin_client / origin_session_id / source_thread_id / source_refs / access_count / last_accessed_at / reinforce_count
- 应用层 jieba 分词，写入 memories 时自动填充 `content_tokens` / `title_tokens`，支持 `MEMORY_MCP_JIEBA_USER_DICT` 自定义词典
- 新增 `python -m memory_mcp.scripts.migrate_v1_to_v2 --src ... --dst ... --backup ... --dry-run --verify` 一次性迁移脚本（review_status 全部标 `legacy`）
- FastAPI lifespan 启动时自动跑 `alembic upgrade head`（`MEMORY_MCP_AUTO_MIGRATE` 控制）
- 7 个原有 MCP tools 对外契约保持不变；新字段全部默认值；hybrid search / memory_crud / threads / worker 留给 M2-M4
```

- [ ] **Step 2: Commit 变更日志**

```bash
git add AGENTS.md
git commit -m "docs(agents): record M1 storage foundation milestone in changelog"
```

---

## 最终验收清单

跑完 Task 22 后逐条核对：

- [ ] `pytest -q` 全绿，且新增测试覆盖以下文件：`tests/test_sqlite_store.py` / `tests/test_migrations.py` / `tests/test_tokenizer.py` / `tests/test_memory_repository.py` / `tests/test_graph_repository.py` / `tests/test_graph_store_reload.py` / `tests/test_migrate_v1_to_v2.py`
- [ ] 原 49 条测试全部仍 PASS（test_tools / test_api / test_extraction / test_working_memory / test_transport / test_vector_backend）
- [ ] `ruff check .` 无新增告警
- [ ] spec §4 的全部 9 张表 + FTS5 + 6 个触发器 + 17 个索引 都在 `0001_initial_v2.py` 中建好
- [ ] spec §4.3 三个 memories_fts 触发器（ai/ad/au）完整给出
- [ ] spec §9.1 字段映射全部在 `migrate_v1_to_v2._to_v2_node` 中实现，并且新字段填默认值
- [ ] LanceDB schema 仅含 `id` + `vector` 两列
- [ ] `GraphStore` 不再写 `entities.json` / `relations.json` / `evolution_chains.json`
- [ ] `MemoryNode` 新增 v2 字段在 `models.py` / `serializers.py` / `remember.py` / `evolve_memory` / `migrate_v1_to_v2._to_v2_node` 中**拼写完全一致**
- [ ] 没有任何 TODO / TBD / placeholder / "implement later"
- [ ] AGENTS.md 已记录 M1
- [ ] 服务启动跑 `alembic upgrade head`；环境变量 `MEMORY_MCP_AUTO_MIGRATE=false` 可关掉
- [ ] CLI: `python -m memory_mcp.scripts.migrate_v1_to_v2 --src ./old --dst ./new --backup ./backup.tgz --verify` 可执行
- [ ] 所有 commit 都用英文 conventional commits；plan 内未出现真实 secret / host / IP

---

## M2-M5 接管点（预告，不在本 plan 范围）

- **M2 API & Hybrid Search**：复用 M1 的 `SQLiteStore.get_db()` 统一 API、`MemoryRepository.fts_search` + `LanceVectorBackend.search` + `GraphStore.get_relations` → 在 `engine/hybrid_search.py` 融合；`tools/memory_crud.py` 走 `MemoryRepository.update/hard_delete`；recall 升级时签名扩展按 spec §5.1；REST 路径用 `/api/v1/memories/{id}`，分页 DTO 用 `items`。
- **M3 Threads + Adapters**：`threads` / `thread_messages` 表 schema 已在 M1 建好，M3 只需新增 `tools/thread_*.py` + `threads/adapters/`，所有 DB 操作走 `from ..storage.sqlite import get_db`。
- **M4 Background Worker**：`jobs` / `working_memory_cache` 表已建，M4 写 `workers/loop.py` 直接走 `get_db()`，不再独立读写 `MEMORY_MCP_DB_PATH`。
- **M5 Web UI**：与 M1 无耦合；前端类型 `MutationType` 直接复用 M1 enum 的字面量。
- **M6 上线**：`/health` 返回 `sqlite_path` + `schema_version`；`mem db current` 由本 plan Task 20.5 提供。

---

## 修复记录

> 2026-05-21 plan 修复（codex 评审 + Sir 新约束）：
>
> - **Task 3（SQLiteStore）**：新增 `DBHandle` facade（unified `execute/executemany/fetchone/fetchall/transaction()`），并提供模块级 `get_db()` async context；这是 M2/M3/M4 共同消费的权威 API，消除「`connection()` vs `get_db()`」分歧。
> - **Task 6/10/11**：repository 全部迁移到 `get_db()` API；`MemoryRepository` 新增 `hard_delete` 和 `fts_search`（供 M2 hybrid_search 直接复用，避免后者绕过 repo 拼 SQL）。
> - **Task 12（VectorStore.delete）**：返回 bool 并复用 `MemoryRepository.hard_delete`，去掉直接打 `connection().execute`。
> - **Task 17（server lifespan + /health）**：`/health` 返回字段固定为 `{status="ok", vector_backend, sqlite_path, schema_version}`；M6 runbook 据此断言。
> - **Task 19（migrate_v1_to_v2）**：verify 通过后打印 spec §9.3 5 条 `[verify] ...: OK` 行（M6 Task 8 grep 用）；`main()` 修复 reload 顺序，加 `reload(_self)` 以保证 `--dst` 改环境变量后 `migrate()` 函数符号也被 rebind。
> - **新 Task 20.5（mem db CLI）**：补 `mem db upgrade/downgrade/current/history` 子命令，M6 Task 9 Step 4 引用的 `mem db current` 由此提供。
> - **File Structure 增量**：在头部 File Structure 表显式列出 `cli/src/memory_mcp_cli/main.py` 与 server `/health` 字段约定。
>
