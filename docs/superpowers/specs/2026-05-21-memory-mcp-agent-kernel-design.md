# Memory MCP Agent Kernel — Phase 1 Design

**Date**: 2026-05-21
**Status**: Draft
**Author**: Claude (architect) + Kassol (decisions)
**Supersedes**: 在 [2026-03-24 extension design](./2026-03-24-memory-mcp-extension-design.md) 基础上演进

---

## 0. 摘要

把 `memory-mcp` 从 Nowledge Mem 风格的「本地优先知识 OS」差异化为 **agent-first 的个人记忆内核 / 服务器**。Phase 1 吃掉 Nowledge Mem 最有价值的 60%：跨工具记忆、线程归档、来源追溯、混合检索、知识图谱、Web 治理台、后台异步智能。

差异化定位：开源、自部署、协议清晰、Agent 优先、可审计、可控。不复制桌面端 / Spaces / 浏览器扩展等高维护负担产品壳层。

---

## 1. 目标与非目标

### 1.1 目标

- 收敛存储：SQLite 主 + LanceDB 副，单一 SQL 心智模型
- 升级 schema 到 v2：补齐治理、多 agent 追溯、源回链、访问统计、UI 友好字段
- 提供 Memory CRUD by id 与 Memory Merge，让污染治理可操作
- 混合检索（vector + FTS5/jieba + graph + 时间衰减 + 访问统计）
- Threads 完整归档：per-provider adapter + backfill + incremental sync
- Web UI 治理台：React 19 + TypeScript 6 + Vite 8 + Tailwind v4 + shadcn
- Background Worker（同进程 asyncio + APScheduler + SQLite 队列）
- 生产数据破坏性 v2 迁移（10 分钟级 downtime，备份兜底）

### 1.2 非目标（Phase 2+）

- Library/Source 文档导入（MD/PDF/web chunk）
- mem_fs 虚拟路径（/memories/by-id, /threads, ...）
- 桌面/移动客户端
- 跨设备多用户、Spaces 隔离
- 浏览器扩展
- LLM 自动 rerank

---

## 2. 关键决策记录（Decision Log）

| ID | 决策 | 选项 | 收敛结果 |
|---|---|---|---|
| D1 | 存储后端 | A 现状+ / B SQLite 主+Lance 副 / C 全 sqlite-vec | **B** |
| D2a | 数据迁移策略 | 1 破坏性 v2 / 2 双写 / 3 老冻结 | **1 破坏性，备份兜底** |
| D2b | v2 schema 新增字段 | A 全集 / B 精简 9 字段 / C 最小 4 字段 | **B（α/β/γ/δ/ε 五组）** |
| D3 | Threads 模块 | 1 指针 / 2 选择性快照 / 3 完整归档 / 4 不做 | **3 完整归档** |
| D4 | Phase 1 可选模块 | A Web UI / B Worker / C Library / D mem_fs | **A + B**（C/D 推后） |
| D5 | 前端栈 | A HTMX / B Alpine / C SPA / D Streamlit | **C React 19 SPA** |
| D6 | FTS5 中文分词 | unicode61 / jieba | **jieba** |
| D7 | LanceDB 角色 | 含 payload / 只存 (id, vector) | **只存 (id, vector)** |
| D8 | Hybrid 融合 | 加权和 / RRF | **RRF (k=60)** |
| D9 | Web UI 鉴权 | 全程 Bearer / cookie session | **cookie session（同时保留 Bearer）** |
| D10 | Worker 部署 | 同进程 / 独立容器 | **同进程（asyncio + lifespan）** |
| D11 | Sync 模式 | 服务端扫描 / 本地 CLI 推送 | **本地 CLI 推送**（服务端只接收） |

---

## 3. 总体架构

```
┌──────────────────────────────────────────────────────────────────┐
│  传输层  │  MCP /mcp  │  REST /api/v1/*  │  CLI mem  │  Web UI  │
└──────────────────────────────────────────────────────────────────┘
                                │
┌──────────────────────────────────────────────────────────────────┐
│  业务层  │  tools (remember/recall/trace/forget/relate/...)     │
│         │  + memory_crud (get/update/delete/merge by id)        │
│         │  + thread_search / thread_get / thread_import         │
│         │  + hybrid_search                                       │
└──────────────────────────────────────────────────────────────────┘
                                │
┌──────────────────────────────────────────────────────────────────┐
│  引擎层  │  embedding │ conflict │ evolution │ extraction       │
│         │  working_memory │ reinforce │ thread_adapters         │
└──────────────────────────────────────────────────────────────────┘
                                │
┌──────────────────────────────────────────────────────────────────┐
│  存储层  │  SQLite (主)                  │  LanceDB (副)         │
│         │  Entity/Relation/Memory       │  (id, vector)         │
│         │  Thread/ThreadMessage/FTS5    │                       │
└──────────────────────────────────────────────────────────────────┘
                                │
┌──────────────────────────────────────────────────────────────────┐
│  后台层  │  worker (asyncio + APScheduler，同进程)               │
│         │  extraction queue / reinforce / wm refresh / sync     │
└──────────────────────────────────────────────────────────────────┘
```

**架构约束**

- 单向依赖：传输→业务→引擎→存储；后台层依赖业务+引擎
- 所有 tool 函数仍是单一函数+JSON 字符串返回，MCP/REST/CLI/Web 复用
- 后台 worker 与主进程同进程（asyncio task），不引入 Redis/Celery
- 服务端不做文件系统扫描，transcript 同步由本地 CLI 推送

### 3.1 模块清单

| 路径 | 类型 | 说明 |
|---|---|---|
| `src/memory_mcp/storage/sqlite.py` | 新 | SQLite 主存储 + FTS5 |
| `src/memory_mcp/storage/vector.py` | 重构 | LanceDB 精简：只存 `(id, vector)` |
| `src/memory_mcp/storage/graph.py` | 重构 | 关系运行时从 SQLite 加载到 NetworkX |
| `src/memory_mcp/storage/schema.sql` | 新 | DDL（仅作参考，权威在 alembic migration） |
| `src/memory_mcp/storage/migrations/` | 新 | alembic 版本化迁移 |
| `src/memory_mcp/scripts/migrate_v1_to_v2.py` | 新 | 生产数据一次性迁移脚本 |
| `src/memory_mcp/engine/hybrid_search.py` | 新 | vector + FTS + graph + 排序融合 |
| `src/memory_mcp/engine/reinforce.py` | 新 | access_count / reinforce / decay |
| `src/memory_mcp/engine/tokenizer.py` | 新 | jieba 分词封装（含自定义词典 hook） |
| `src/memory_mcp/tools/memory_crud.py` | 新 | memory_get/update/delete/merge |
| `src/memory_mcp/tools/thread_*.py` | 新 | thread_search/get/import/list |
| `src/memory_mcp/threads/adapters/` | 新 | base / claude_code / codex / chatwise / manual |
| `src/memory_mcp/threads/sync.py` | 新 | upsert + 增量协议 |
| `src/memory_mcp/workers/` | 新 | jobs 表 + worker loop + handlers |
| `src/memory_mcp/api/auth.py` | 改 | cookie session middleware（叠加 Bearer） |
| `src/memory_mcp/api/routes.py` | 扩展 | 分页/过滤/批量/graph/threads/jobs/sync-status |
| `cli/src/memory_mcp_cli/sync.py` | 新 | 本地 transcript 推送 |
| `claude-code-plugin/hooks/` | 改 | stop hook 双步：同步 thread + extraction with refs |
| `web/` | 新 | Vite + React + TS + Tailwind v4 + shadcn SPA |

---

## 4. 存储与 Schema 设计

### 4.1 表清单

| 表 | 用途 |
|---|---|
| `memories` | v2 主表 |
| `memories_fts` | FTS5 全文索引（content_tokens + title_tokens） |
| `entities` | 实体表 |
| `relations` | 关系边 |
| `threads` | 会话归档 |
| `thread_messages` | 会话消息 |
| `thread_messages_fts` | FTS5 全文索引 |
| `jobs` | Background Worker 队列 |
| `working_memory_cache` | wm briefing 预生成缓存 |
| `alembic_version` | migration 版本 |

**废弃**：`evolution_chains.json` 表（`parent_id` 已能完整追溯，冗余）。

### 4.2 memories 主表 DDL

```sql
CREATE TABLE memories (
  id TEXT PRIMARY KEY,
  entity_key TEXT NOT NULL,
  entity_type TEXT NOT NULL,

  content TEXT NOT NULL,
  content_tokens TEXT,                         -- jieba 分词结果（空格分隔）
  title TEXT,                                  -- ε 短标题，nullable
  title_tokens TEXT,                           -- title 的 jieba 分词

  parent_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
  mutation_type TEXT NOT NULL,
  mutation_reason TEXT,

  created_at TIMESTAMP NOT NULL,
  valid_from TIMESTAMP NOT NULL,
  valid_until TIMESTAMP,

  is_current BOOLEAN NOT NULL DEFAULT 1,
  confidence REAL NOT NULL DEFAULT 1.0,
  review_status TEXT NOT NULL DEFAULT 'auto',  -- α: auto/reviewed/confirmed/challenged/legacy
  archived_reason TEXT,
  archived_at TIMESTAMP,
  conflict BOOLEAN NOT NULL DEFAULT 0,
  conflict_with_id TEXT REFERENCES memories(id) ON DELETE SET NULL,

  tags TEXT,                                   -- JSON array
  source TEXT NOT NULL DEFAULT 'conversation',
  origin_client TEXT,                          -- β: claude-code / codex / chatwise / manual-cli / ...
  origin_session_id TEXT,                      -- β

  source_thread_id TEXT REFERENCES threads(thread_id) ON DELETE SET NULL,  -- γ
  source_refs TEXT,                            -- γ JSON [{thread_id, message_id}, ...]

  access_count INTEGER NOT NULL DEFAULT 0,     -- δ
  last_accessed_at TIMESTAMP,                  -- δ
  reinforce_count INTEGER NOT NULL DEFAULT 0   -- δ
);

CREATE INDEX idx_memories_entity_key ON memories(entity_key);
CREATE INDEX idx_memories_entity_type ON memories(entity_type);
CREATE INDEX idx_memories_current ON memories(is_current) WHERE is_current = 1;
CREATE INDEX idx_memories_review_status ON memories(review_status);
CREATE INDEX idx_memories_origin_client ON memories(origin_client);
CREATE INDEX idx_memories_source_thread_id ON memories(source_thread_id);
CREATE INDEX idx_memories_created_at ON memories(created_at DESC);
CREATE INDEX idx_memories_last_accessed_at ON memories(last_accessed_at DESC);
```

### 4.3 FTS5 索引与触发器

```sql
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
```

**分词策略**：应用层用 `jieba.cut(text, cut_all=False)` 切，连接空格后存 `content_tokens`/`title_tokens` 字段；FTS5 用 `unicode61` 即可命中。无 C 编译依赖，词典定制灵活。

### 4.4 entities / relations / threads / thread_messages

```sql
CREATE TABLE entities (
  entity_key TEXT PRIMARY KEY,
  name TEXT,
  entity_type TEXT NOT NULL,
  current_memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_entities_entity_type ON entities(entity_type);

CREATE TABLE relations (
  id TEXT PRIMARY KEY,
  from_entity_key TEXT NOT NULL REFERENCES entities(entity_key) ON DELETE CASCADE,
  to_entity_key TEXT NOT NULL REFERENCES entities(entity_key) ON DELETE CASCADE,
  relation_type TEXT NOT NULL,
  properties TEXT,                             -- JSON
  created_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_relations_from ON relations(from_entity_key);
CREATE INDEX idx_relations_to ON relations(to_entity_key);
CREATE INDEX idx_relations_type ON relations(relation_type);

CREATE TABLE threads (
  thread_id TEXT PRIMARY KEY,
  source_provider TEXT NOT NULL,               -- claude-code / codex / chatwise / gemini / manual
  source_ref TEXT,                             -- 原始路径或 URL 指针
  title TEXT,
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  message_count INTEGER NOT NULL DEFAULT 0,
  summary TEXT,
  metadata TEXT,                               -- JSON: project, cwd, model 等
  last_synced_mtime INTEGER,                   -- D11 增量同步状态
  last_synced_seq INTEGER,                     -- D11
  created_at TIMESTAMP NOT NULL,
  imported_at TIMESTAMP NOT NULL,
  UNIQUE(source_provider, source_ref)
);
CREATE INDEX idx_threads_provider ON threads(source_provider);
CREATE INDEX idx_threads_started_at ON threads(started_at DESC);

CREATE TABLE thread_messages (
  message_id TEXT PRIMARY KEY,                 -- {thread_id}:{seq:06d}
  thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  ts TIMESTAMP,
  metadata TEXT,                               -- JSON: tool_use / tool_result / attachments
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
-- 触发器同 memories_fts 模板
```

### 4.5 jobs / working_memory_cache

```sql
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,                      -- extraction / title_gen / summary_gen / reinforce_decay / wm_refresh
  payload TEXT NOT NULL,                       -- JSON
  status TEXT NOT NULL DEFAULT 'pending',      -- pending / running / done / failed
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

CREATE TABLE working_memory_cache (
  cache_key TEXT PRIMARY KEY,                  -- 例：'briefing:default'
  content TEXT NOT NULL,
  generated_at TIMESTAMP NOT NULL
);
```

### 4.6 LanceDB 精简 schema

```python
pa.schema([
    pa.field("id", pa.string()),                            # 与 SQLite memories.id 对齐
    pa.field("vector", pa.list_(pa.float32(), 1536)),
])
```

**检索流程**

1. LanceDB ANN 拿候选 `id` 列表（默认 top 50）
2. SQLite `WHERE id IN (...)` 拿元数据 + 应用过滤
3. Hybrid Search 阶段融合 FTS5 / Graph / access stats

LanceDB 角色被压到最薄，没有 payload duplication，无两边数据不一致问题。备份 SQLite 是真相源；LanceDB 可在最坏情况下从 SQLite + embedding API 重建。

### 4.7 SQLite 启动 pragmas

```python
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;       # 并发写友好
PRAGMA synchronous = NORMAL;     # 性能与持久性平衡
PRAGMA busy_timeout = 5000;      # 防瞬时锁
```

### 4.8 Alembic Migration

- `src/memory_mcp/storage/migrations/versions/0001_initial_v2.py` 建全部表 / FTS5 / 触发器 / 索引
- 后续 schema 变更追加版本文件
- 服务启动时自动 `alembic upgrade head`
- 离线管理：`mem db upgrade` / `mem db downgrade <rev>` / `mem db current` / `mem db history`

---

## 5. API 与 Hybrid Search

### 5.1 MCP Tools 变更

| Tool | 状态 | 签名要点 |
|---|---|---|
| `remember` | 升级 | 增加 `origin_client?`, `origin_session_id?`, `source_thread_id?`, `source_refs?` 透传 |
| `recall` | 升级 | 增加 `search_mode`, `filters`, `time_range`，返回 `relevance_breakdown` |
| `recall_all` | 保留 | 不变 |
| `trace` | 保留 | 不变 |
| `forget` | 保留 | 等价于 `memory_update(review_status='archived')` |
| `relate` / `unrelate` / `graph_query` | 保留 | 不变 |
| `memory_get` | 新 | `(memory_id) → MemoryNode` |
| `memory_update` | 新 | `(memory_id, content?, title?, tags?, review_status?, ...)` |
| `memory_delete` | 新 | `(memory_id, hard=False)` 默认软删 |
| `memory_merge` | 新 | `(source_ids: [str], target_id: str)` 合并污染记忆 |
| `thread_search` | 新 | `(query, provider?, time_range?, limit?)` |
| `thread_get` | 新 | `(thread_id, with_messages=False)` |
| `thread_import` | 新 | `(provider, path, options?)` |
| `thread_list_providers` | 新 | 返回已支持 provider 列表 |
| `hybrid_search` | 新 | `recall` 的低层暴露 |

### 5.2 REST API 扩展

```
# memories
GET    /api/v1/memories?page=&size=&entity_type=&review_status=&origin_client=&q=
GET    /api/v1/memories/{id}
PATCH  /api/v1/memories/{id}
DELETE /api/v1/memories/{id}?hard=
POST   /api/v1/memories/bulk-delete           # body: {ids: [...]}
POST   /api/v1/memories/bulk-merge            # body: {source_ids: [...], target_id}

# graph
GET    /api/v1/entities
GET    /api/v1/entities/{key}/graph?depth=&relation_types=
GET    /api/v1/graph/subgraph?entity_key=&depth=2

# threads
GET    /api/v1/threads?page=&size=&provider=&q=
GET    /api/v1/threads/{id}
GET    /api/v1/threads/{id}/messages?page=
POST   /api/v1/threads/import                 # body: {provider, path|content, options}
POST   /api/v1/threads/incremental            # body: {batches: [{provider, source_ref, thread_meta, messages}]}
GET    /api/v1/threads/sync-status?provider=&refs=

# jobs
GET    /api/v1/jobs?status=&job_type=&page=
GET    /api/v1/jobs/{id}
POST   /api/v1/jobs/{id}/retry
POST   /api/v1/jobs/{id}/cancel

# auth (cookie session)
POST   /api/v1/auth/login                     # body: {token} → Set-Cookie mem_session
POST   /api/v1/auth/logout
GET    /api/v1/auth/me

# search
POST   /api/v1/search                         # body: {query, mode, filters, limit}
```

`/mcp` 保持不变。

### 5.3 Hybrid Search 算法

```
        ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
        │ Vector (Lance)│   │ FTS5 (jieba)  │   │ Graph (NX)    │
        │ top 50 by ANN │   │ top 50 by BM25│   │ 1-hop neighbor│
        └────────┬──────┘   └────────┬──────┘   └────────┬──────┘
                 │                   │                   │
                 └──────────┬────────┴───────────┬──────┘
                            ▼                    ▼
                  ┌──────────────────────────────────┐
                  │ Fusion: RRF (k=60)               │
                  │ score = Σ 1/(k + rank_i)         │
                  └──────────────────┬───────────────┘
                                     ▼
                  ┌──────────────────────────────────┐
                  │ Re-rank:                         │
                  │ final = rrf_score                │
                  │       * confidence               │
                  │       * f(reinforce_count)       │
                  │       * exp(-λ·days_since_access)│
                  └──────────────────┬───────────────┘
                                     ▼
                  ┌──────────────────────────────────┐
                  │ Filter:                          │
                  │ - review_status ∉ {legacy}       │
                  │ - is_current = true（trace 除外）│
                  │ - 用户传入 filters               │
                  └──────────────────┬───────────────┘
                                     ▼
                            top N final results
```

**参数默认值**

- RRF `k = 60`（Elasticsearch/OpenSearch 通用）
- 召回深度 `top 50` each
- reinforce 归一化 `f(x) = 1 + log(1+x)/log(1+max_reinforce_in_table)`
- 时间衰减 `λ = 1/180`（半衰期 ~125 天）

全部参数可通过环境变量覆盖：`MEMORY_MCP_RRF_K` / `MEMORY_MCP_DECAY_LAMBDA` / `MEMORY_MCP_RECALL_DEPTH`。

### 5.4 recall 响应结构

```json
{
  "results": [
    {
      "memory_id": "...",
      "entity_key": "preference:editor",
      "content": "...",
      "title": "...",
      "final_score": 0.87,
      "relevance_breakdown": {
        "rrf_score": 0.65,
        "vector_rank": 3,
        "fts_rank": 1,
        "graph_rank": null,
        "confidence": 1.0,
        "reinforce_factor": 1.2,
        "decay_factor": 0.91
      },
      "review_status": "auto",
      "origin_client": "claude-code",
      "source_thread_id": "...",
      "evolution_count": 3
    }
  ],
  "total": 1,
  "search_mode": "hybrid",
  "search_metadata": {
    "vector_candidates": 50,
    "fts_candidates": 50,
    "graph_candidates": 8,
    "filtered_out": 12,
    "elapsed_ms": 23
  }
}
```

---

## 6. Threads 模块与 Provider 适配器

### 6.1 适配器架构

```
threads/
├── adapters/
│   ├── base.py              # ThreadAdapter ABC + ParsedThread / ParsedMessage 标准化数据类
│   ├── claude_code.py       # ~/.claude/projects/**/*.jsonl
│   ├── codex.py             # 数据源路径实施时校准（Sir 提供 fixture）
│   ├── chatwise.py          # 数据源实施时校准（Sir 提供 fixture）
│   └── manual.py            # CLI 导入：markdown / json / plaintext
├── sync.py                  # upsert + 增量协议（服务端被动接收）
├── registry.py              # provider → adapter 注册表
└── ids.py                   # message_id 复合规则
```

### 6.2 ThreadAdapter 接口

```python
class ThreadAdapter(ABC):
    provider: ClassVar[str]

    @abstractmethod
    def discover(self, root: Path) -> Iterator[ThreadSource]: ...

    @abstractmethod
    def parse(self, source: ThreadSource) -> ParsedThread: ...

    @abstractmethod
    def incremental_payload(self, raw_event: dict) -> ParsedThreadDelta | None: ...

@dataclass
class ParsedThread:
    thread_id: str
    source_provider: str
    source_ref: str
    title: str | None
    started_at: datetime | None
    ended_at: datetime | None
    metadata: dict
    messages: list[ParsedMessage]

@dataclass
class ParsedMessage:
    seq: int                                              # 严格递增
    role: str                                             # user / assistant / tool / system
    content: str
    ts: datetime | None
    metadata: dict
```

**message_id 规则**

```
message_id = f"{thread_id}:{seq:06d}"     # 例：claude_abc-123:000042
```

复合 ID 易读、可推断、跨表 JOIN 友好。`UNIQUE(thread_id, seq)` 兜底防重。

### 6.3 分布式 Sync 架构

```
┌─────────────────────────────────┐         ┌──────────────────────────┐
│      本地工作机（开发者侧）       │  HTTPS  │     远程 server          │
│                                 │  Bearer │                          │
│  - claude-code stop hook        │  ───→   │  /api/v1/threads/        │
│    (实时增量)                    │         │     incremental (POST)   │
│  - mem thread sync              │         │     sync-status (GET)    │
│    (launchd / cron, 5min)       │         │     import (POST)        │
│  - mem thread import-history    │         │                          │
│    (一次性 backfill)             │         │  worker (asyncio):       │
│                                 │         │  - extraction queue      │
│                                 │         │  - reinforce / decay     │
│                                 │         │  - wm refresh            │
│                                 │         │  - title / summary 生成   │
│                                 │         │  ★ 不做文件系统扫描        │
└─────────────────────────────────┘         └──────────────────────────┘
```

**Sync 协议**

```python
# 本地 CLI sync 流程
1. 扫 local root → 拿到本地所有 transcript 文件列表
2. GET /api/v1/threads/sync-status?provider=<p>&refs=...
   → {ref: {last_synced_mtime, last_synced_seq}}
3. 对每个本地文件:
   if local_mtime > server.last_synced_mtime:
     parsed = adapter.parse(file)
     delta_messages = [m for m in parsed.messages if m.seq > server.last_synced_seq]
     if delta_messages:
       batch.append({ref, thread_meta, messages: delta_messages})
4. POST /api/v1/threads/incremental {batches: [...]}
5. server upsert + 返回 {ref: {new_last_synced_mtime, new_last_synced_seq}}
```

### 6.4 Provider 关键约定

| Provider | 数据源 | thread_id | 增量信号 |
|---|---|---|---|
| **claude-code** | `~/.claude/projects/<project-encoded>/*.jsonl` | jsonl 文件名（去后缀） | stop hook 推送最后 N 条 |
| **codex** | 实施时 grep `~/.codex` 或 `~/.config/codex`，Sir 提供 fixture 后定型 | session 文件名 | 本地 CLI sync（hook 取决于 Codex 支持） |
| **chatwise** | 本地存储路径实施时确认，Sir 提供 fixture 后定型 | conversation ID | 本地 CLI sync |
| manual | 用户 CLI 提供路径或内容 | UUID 或文件名派生 | n/a |

**Phase 1 优先 claude-code**（数据源最清楚、Sir 主力使用）。codex/chatwise 在 Phase 1 内分阶段实施，不阻塞 M4/M5。

### 6.5 本地 CLI 配置

```toml
# ~/.config/mem/config.toml
[server]
url = "https://memory-mcp.<your-domain>"
token_env = "MEMORY_MCP_AUTH_TOKEN"           # 从环境变量读，不写 token 进文件

[sync.claude-code]
roots = ["~/.claude/projects"]
auto = true

[sync.codex]
roots = ["~/.codex/sessions"]                 # 实施时校准
auto = false

[sync.chatwise]
roots = ["~/Library/Application Support/ChatWise/data"]   # 实施时校准
auto = false
```

### 6.6 CLI 命令

```bash
mem thread sync                              # auto=true 的 provider
mem thread sync --provider claude-code
mem thread sync --provider codex --root <path-override>
mem thread import-history --provider claude-code --since 2026-01-01
mem thread import-history --provider claude-code --dry-run
mem thread import --file ./notes.md --format markdown --provider manual --title "..."
```

### 6.7 调度模板

macOS launchd：

```xml
<!-- ~/Library/LaunchAgents/dev.memory-mcp.sync.plist -->
<plist version="1.0">
<dict>
  <key>Label</key><string>dev.memory-mcp.sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/mem</string>
    <string>thread</string>
    <string>sync</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>MEMORY_MCP_AUTH_TOKEN</key>
    <string><!-- 用 launchctl setenv 在外部注入，不入文件 --></string>
  </dict>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/Users/$USER/Library/Logs/mem-sync.log</string>
  <key>StandardErrorPath</key><string>/Users/$USER/Library/Logs/mem-sync.err</string>
</dict>
</plist>
```

简单 cron：

```cron
*/5 * * * * /usr/local/bin/mem thread sync >> ~/Library/Logs/mem-sync.log 2>&1
```

### 6.8 stop hook 升级（双步）

```bash
# claude-code-plugin/hooks/stop.sh
1. POST /api/v1/threads/incremental
   {provider: "claude-code", source_ref, thread_meta, messages: [...]}
   → 服务端返回 {thread_id, new_message_ids: [...]}

2. POST /api/v1/extract
   {messages, source_thread_id: thread_id, source_refs: [...]}
   → 抽到的每条 memory 自带 source_thread_id + source_refs
```

抽到的每条 memory 自动回链到 thread + 具体 message。Web UI 「源回链」面板的实现基础。

---

## 7. Web UI 治理台

### 7.1 路由

```
/                      → 重定向到 /memories
/login                 → Bearer Token 输入
/memories              → 列表（搜索 / 过滤 / 批量选 / 合并）
/memories/:id          → 详情（编辑 / 演化链 / 源回链）
/memories/new          → 手工创建
/threads               → 列表（按 provider / time 过滤）
/threads/:id           → 消息流 + 关联 memory 标记
/graph                 → 知识图谱（react-flow，节点点击跳 memory）
/sources               → Library/Source（Phase 1 占位）
/jobs                  → Background Worker 监控
/settings              → token 管理 / stats / sync 状态
```

### 7.2 组件清单

```
web/src/
├── components/
│   ├── MemoryList.tsx              # 虚拟列表 + 多选 + 批量 toolbar
│   ├── MemoryDetail.tsx            # 编辑 review_status / title / tags / content
│   ├── MemoryMergeDialog.tsx       # 选 source_ids → target，预览
│   ├── EvolutionTimeline.tsx       # 演化链可视化
│   ├── SourceRefsPanel.tsx         # 跳转到 thread + 高亮 message
│   ├── ThreadMessages.tsx          # 虚拟化消息流 + 标记被抽取过的 message
│   ├── GraphView.tsx               # react-flow + dagre layout
│   ├── RelevanceBreakdown.tsx      # 显示 vector / fts / graph 排名贡献
│   ├── SyncStatusCard.tsx          # 每个 provider 上次同步时间
│   └── JobsTable.tsx               # Worker 任务监控
├── pages/                          # 路由 entry
├── api/                            # TanStack Query hooks
└── lib/                            # auth / cookie / utils
```

### 7.3 鉴权

MCP/REST/CLI 现有 Bearer Token 不动；Web UI 走 cookie session：

```
POST /api/v1/auth/login    {token}    → 验证 → Set-Cookie: mem_session=<signed>
                                              HttpOnly; Secure; SameSite=Strict
POST /api/v1/auth/logout              → 清 cookie
GET  /api/v1/auth/me                  → 验证当前 session
```

`AuthMiddleware` 同时接受 `Authorization: Bearer` 与 cookie。session 用 `itsdangerous` 签名，secret 从 env `MEMORY_MCP_SESSION_SECRET` 注入。

### 7.4 部署形态（单服务）

```
FastAPI app:
  /                   StaticFiles(directory="web/dist")  ← SPA build 产物
  /mcp                MCP Streamable HTTP
  /api/v1/*           REST API
  /health             health check
```

### 7.5 多阶段 Dockerfile

```dockerfile
FROM node:22-alpine AS web-builder
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY web/ .
RUN pnpm build                                    # → /web/dist

FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY src/ src/
COPY --from=web-builder /web/dist /app/web/dist
ENV WEB_DIST_DIR=/app/web/dist
CMD ["python", "-m", "memory_mcp"]
```

宿主机无需装 Node.js。

### 7.6 前端版本清单（写入 web/package.json）

| 库 | 版本 |
|---|---|
| react / react-dom | 19.2.x |
| typescript | 6.0.x |
| vite | 8.0.x |
| tailwindcss | 4.3.x（CSS-based 配置） |
| shadcn (CLI) | 4.7.x |
| react-router-dom | 7.15.x（declarative mode） |
| @tanstack/react-query | 5.100.x |
| @tanstack/react-table | 8.21.x |
| zustand | 5.0.x |
| @xyflow/react | 12.10.x（替代 reactflow） |
| lucide-react | 1.16.x |
| itsdangerous（后端） | latest |

---

## 8. Background Worker

### 8.1 技术栈

- asyncio + APScheduler + SQLite-backed queue
- 与 FastAPI 同进程，lifespan 管理生命周期
- 不引入 Redis/Celery

### 8.2 任务清单

| job_type | 触发 | 频率 | 内容 |
|---|---|---|---|
| `extraction` | `/threads/incremental` 推送后入队 | 实时 | LLM 抽 memory candidate，自动带 source_thread_id + source_refs |
| `title_gen` | memory 新建且无 title 时入队 | 实时 | LLM 生成 10-20 字短 title |
| `summary_gen` | thread 新增 messages，5min debounce | 实时 | 整 thread 摘要 |
| `reinforce_decay` | APScheduler cron | 每日 03:00 | 重算 reinforce 因子、time decay |
| `wm_refresh` | APScheduler cron | 每 30min | 预生成 working memory briefing → working_memory_cache |

### 8.3 worker 主循环

```python
async def worker_loop():
    while not shutdown_event.is_set():
        async with db_transaction() as tx:
            jobs = await fetch_and_lock(tx, limit=5)
            # SELECT id FROM jobs WHERE status='pending' AND (next_retry_at IS NULL OR next_retry_at <= now())
            #   ORDER BY scheduled_at LIMIT 5;
            # UPDATE jobs SET status='running', started_at=now() WHERE id IN (...);
        for job in jobs:
            try:
                handler = JOB_HANDLERS[job.job_type]
                await asyncio.wait_for(handler(job.payload), timeout=120)
                await mark_done(job.id)
            except Exception as e:
                await mark_failed_or_retry(job.id, e)
                # 指数退避 1min → 5min → 25min；超过 max_attempts → 'failed'
        await asyncio.sleep(1)
```

### 8.4 生命周期

```python
# FastAPI lifespan
@asynccontextmanager
async def lifespan(app):
    # startup
    await init_db()
    await run_alembic_upgrade_head()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(reinforce_decay_job, 'cron', hour=3)
    scheduler.add_job(wm_refresh_job, 'interval', minutes=30)
    scheduler.start()
    worker_task = asyncio.create_task(worker_loop())
    try:
        yield
    finally:
        # shutdown: graceful drain
        shutdown_event.set()
        scheduler.shutdown(wait=False)
        await asyncio.wait_for(worker_task, timeout=30)
```

### 8.5 失败与重试

- 单次任务最长 120s 超时
- 指数退避：1min, 5min, 25min
- `max_attempts` 默认 3，超过标 `failed`
- Web UI `/jobs` 提供手动 retry / cancel

---

## 9. v1 → v2 数据迁移

### 9.1 字段映射

| v2 字段 | 映射来源 |
|---|---|
| id / entity_key / entity_type / content / embedding / parent_id / mutation_type / mutation_reason / created_at / valid_from / valid_until / is_current / confidence / archived_* / conflict* / tags / source | 直接 copy |
| `content_tokens` / `title_tokens` | 应用层 jieba 重新生成 |
| `title` | `NULL`（worker 后续异步生成） |
| `review_status` | `'legacy'`（标记历史数据，便于查询过滤） |
| `origin_client` / `origin_session_id` | `NULL`（v1 未记录） |
| `source_thread_id` / `source_refs` | `NULL`（无 Thread 回链） |
| `access_count` / `reinforce_count` | `0` |
| `last_accessed_at` | `NULL` |

### 9.2 脚本

```bash
python -m memory_mcp.scripts.migrate_v1_to_v2 \
    --src ./data \
    --dst ./data \
    --backup ./backups/v1-data-<ts>.tgz \
    --dry-run            # 只统计不写
    --verify             # 写完后跑断言
```

### 9.3 断言

- `count(memories) == v1_count`
- 每个 entity 至少能查到，FK 一致
- 每条 memory 在 LanceDB 必有对应 vector
- FTS5 索引行数 == memories 行数
- relations FK 全部解析成功

### 9.4 生产上线流程

```bash
# 0. 预演：dev 环境跑完整 migration + 全量回归测试

# 1. 通知 Sir：开始约 10min downtime

ssh <DEPLOY_HOST>
cd ~/memory-mcp
git fetch && git checkout <v2-release-tag>

# 2. 停服 + 备份（data + .env）
docker compose down
mkdir -p backups
tar -czf "backups/v1-data-$(date +%F-%H%M).tgz" data/ .env

# 3. 构建 + 迁移
docker compose build memory-mcp
docker compose run --rm memory-mcp \
    python -m memory_mcp.scripts.migrate_v1_to_v2 --verify

# 4. 启动
docker compose up -d
sleep 5 && curl -fs https://<MEMORY_MCP_HOST>/health | jq

# 5. 回归测试（Sir 在本地用 mem CLI 做几个 recall/remember 测试）

# 6. 灰度观察 24h → 全量切换
```

### 9.5 Rollback

```bash
docker compose down
rm -rf data/
tar -xzf backups/v1-data-<ts>.tgz
git checkout <v1-tag>
docker compose up -d --build
```

10 分钟内可完成。

---

## 10. 测试策略

| 层 | 覆盖范围 | 工具 |
|---|---|---|
| 单元 | 每个 tool / adapter parse / hybrid search 三阶段 / jieba 分词 / migration 字段映射 | pytest + pytest-asyncio |
| 集成 | MCP/REST/CLI 端到端 / stop hook → extraction → memory 写入回链 | pytest + httpx.AsyncClient |
| migration | fixture v1 → 跑 migration → 断言 | pytest |
| Web UI 人工 | Phase 1 关键路径：登录 / 搜索 / 编辑 / 合并 / 删除 / 图谱 | 浏览器 |
| Web UI 自动 | Phase 1.5 加 Playwright | — |

**Baseline**：现有 57 pytest 通过；Phase 1 完成时目标 200+。

**Fixture**

```
tests/fixtures/
├── v1_data/                       # 缩小版 v1（10-20 memory + 5 entity + 3 relation）
│   ├── vectors/memories.lance/
│   └── graph/*.json
└── threads/
    ├── claude-code/               # 真实 jsonl 缩小样本
    ├── codex/                     # Sir 提供
    └── chatwise/                  # Sir 提供
```

---

## 11. 实施顺序

5 个 milestone，每个独立可 merge。每个 M 完成的硬要求：pytest 全绿 / AGENTS.md 变更日志更新 / spec 中对应模块标记完成 / 至少一个手动 smoke test。

| Milestone | 内容 |
|---|---|
| **M1 存储底座** | SQLite schema + alembic + LanceDB 精简 + 现有 storage 替换 + v1→v2 migration 脚本 + 现有 7 个 tools 全部跑通 + jieba 集成 + pytest 全绿 |
| **M2 API & Hybrid Search** | v2 字段接入 tools + memory_get/update/delete/merge + recall 升 hybrid + REST 分页/过滤/批量/graph |
| **M3 Threads + Adapters** | threads / thread_messages 表 + FTS5 + ThreadAdapter 基类 + claude_code 适配器 + backfill CLI + incremental sync API + 本地 CLI sync 子命令 + stop hook 升级（含 source_refs） |
| **M4 Background Worker** | jobs 表 + worker loop + 5 个 handler + APScheduler cron + lifespan 集成 + 失败重试 + jobs 监控 API |
| **M5 Web UI** | web/ 初始化（React 19 + TS 6 + Vite 8 + Tailwind v4 + shadcn）+ auth/cookie + Memories/Threads/Graph/Jobs/Settings 页面 + 多阶段 Dockerfile |
| **M6 上线** | 备份 + migration + 灰度 24h + 全量切换 |

**codex / chatwise adapter**：M3 内分阶段实施，Sir 提供 fixture 后开做，不阻塞 M4/M5。

---

## 12. Phase 2+ 路线（不在本 spec 范围）

| 模块 | 价值点 |
|---|---|
| Library / Source 导入 | MD/PDF/网页 chunk 入库，作为 memory 的引用源 |
| mem_fs 虚拟路径 | /memories/by-id, /threads, /sources, /wiki/entities，Agent 用 ls/cat/grep 心智模型探索 |
| LLM 自动 rerank | top-N 结果用 LLM 做最终排序，质量提升但成本高 |
| 知识结晶 / Insight | Mastra 风格的 Observer + Reflector，定期生成跨记忆洞察 |
| 跨设备同步 | Phase 1 单服务模式不支持多用户，未来若需要再考虑 |
| Web UI 自动化测试 | Playwright e2e |
| FTS5 jieba C 扩展 | 若 jieba 应用层分词性能不够，编译进 Dockerfile |
| 多语言 embedding | 中英文之外的多语言支持 |
| 浏览器扩展 | 选页面内容一键 import 到 Library |

---

## 13. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| LanceDB 0.30 vs 旧版 API 差异 | migration / 检索逻辑失败 | M1 阶段先单元测试覆盖 LanceDB 全部用法；找不到等价 API 时降级到 InMemoryVectorStore + 复测 |
| jieba 分词词典对个人术语不友好 | 搜不到 | 应用层封装 + 自定义词典 hook + 后续可换其他分词器 |
| migration 数据丢失 | 致命 | 强制备份；--verify 必须通过；rollback 演练 |
| Web UI cookie session 跨域问题 | 登录失败 | 单域名 deploy（SPA 与 API 同源）；CORS 策略写死 |
| Worker 任务卡死 | 后台静默 | 单任务超时 120s；Web UI jobs 监控；APScheduler health check |
| stop hook 推送失败导致 transcript 丢失 | 回链断 | hook 失败时本地记 retry queue，下次 sync 时补推；本地 CLI `mem thread sync` 兜底 |
| Token 泄露（public repo） | 严重 | spec 全用占位符；`.env` 永远在 `.gitignore`；commit 前 grep 检查 |
| LLM 调用费用 | 成本失控 | extraction / title_gen / summary_gen 都有 max_attempts；jobs 表可观察成本；可配置 LLM model |

---

## 14. 安全提醒

- 所有 secret 通过环境变量注入：`MEMORY_MCP_AUTH_TOKEN` / `MEMORY_MCP_OPENROUTER_API_KEY` / `MEMORY_MCP_SESSION_SECRET` / `CLOUDFLARE_TUNNEL_TOKEN`
- 仓库为 GitHub public repo，commit 前 grep token 关键字
- `.env` 严格 `.gitignore`；`.env.example` 仅含占位符
- Web UI cookie：`HttpOnly` / `Secure` / `SameSite=Strict`
- 服务端不存 transcript 文件路径以外的 PII 推断
- 部署主机名 / Cloudflare tunnel domain 不写入仓库

---

## 15. 附录：核心依赖版本清单

**Python（pyproject.toml）**

| 库 | 版本 |
|---|---|
| fastapi | 0.136.x |
| pydantic / pydantic-settings | 2.13.x / 2.14.x |
| uvicorn / starlette | 0.47.x / 1.0.x |
| lancedb | 0.30.x |
| pyarrow | 24.x |
| networkx | 3.6.x |
| aiosqlite | 0.22.x |
| alembic | 1.18.x |
| apscheduler | 3.11.x |
| jieba | latest |
| itsdangerous | latest |
| typer | 0.25.x |
| httpx | 0.28.x |
| mcp (SDK) | 1.x |
| jinja2 | 3.1.x |

**Web（web/package.json）**：见 §7.6。

---

## 16. 文档协作记录

- 2026-05-21 初稿（Brainstorm 会话：12 个核心决策记录见 §2）
