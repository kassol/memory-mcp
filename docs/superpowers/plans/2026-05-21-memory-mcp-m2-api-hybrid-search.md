# Memory MCP — M2 API & Hybrid Search Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. Strict TDD: write failing test → run to confirm fail → implement → run to confirm pass → commit. Do not skip the "run to confirm fail" step. Do not commit code that has not been driven by a failing test.

**Goal:** 在 M1 已就绪的 v2 SQLite + LanceDB 精简存储 / jieba 分词 / 7 个旧 tool 跑通的基础上，把 API 层从「向量单路召回 + 简单 CRUD」升级为 **memory-id 级 CRUD + Hybrid Search（vector + FTS5 + graph + RRF + 时间衰减 / reinforce 重排）**。M2 同时落地 spec §5.1 的全部新/升级 MCP tools 与 §5.2 的 REST 路由（Threads / Jobs / Auth 在 M2 只占骨架，实际实施在 M3/M4）。

**Architecture:**
- 新增 `engine/hybrid_search.py` 与 `engine/reinforce.py`，作为 `recall_tool` 的新底座
- 新增 `tools/memory_crud.py`（get / update / delete / merge）与 `tools/thread_*.py`（骨架）
- 全部 v2 字段（`review_status`/`origin_client`/`origin_session_id`/`source_thread_id`/`source_refs`/`access_count`/`reinforce_count`/`last_accessed_at`/`title`）经 `remember_tool` 与 hybrid_search 透传 / 返回
- REST 路由扩展：memories 分页/过滤/批量、graph subgraph、threads/jobs/auth/search 骨架
- MCP server 注册新工具，schema 与 REST 双向一致

**Tech Stack:** Python 3.11+, Starlette (existing), pytest-asyncio (anyio), jieba (M1 已集成), aiosqlite (M1 已集成), NetworkX (现有), LanceDB (M1 精简)

**Spec:** `docs/superpowers/specs/2026-05-21-memory-mcp-agent-kernel-design.md`（重点 §5）

---

## 设计要点与假设

**M1 已就绪（假设）**
- `MemoryNode` Pydantic 模型已扩展 v2 字段：`title`, `review_status`（'auto'/'reviewed'/'confirmed'/'challenged'/'legacy'/'archived'）, `origin_client`, `origin_session_id`, `source_thread_id`, `source_refs`（List），`access_count`, `last_accessed_at`, `reinforce_count`, `content_tokens`, `title_tokens`
- `storage/sqlite.py` 提供 v2 schema 读写 + FTS5（`memories_fts` 已含 jieba 预分词）
- `vector_store` 精简到 `(id, vector)`，LanceDB ANN 返回 `id` 列表
- `engine/tokenizer.py` 暴露 `tokenize(text: str) -> str`（jieba 切分 + 空格拼接）

**M2 不动**
- Threads 数据模型（`threads` / `thread_messages` 表）—— M3 实施。M2 thread_* tool 与 REST 路由只暴露占位实现（返回 `{"ok": false, "error": "not_implemented_in_m2"}` 或空结果 + 明确 `phase: "M3"`），并写明 docstring「实现在 M3」
- Worker / jobs 表 —— M4 实施；M2 jobs REST 路由同样占位
- Web UI —— M5 实施
- cookie session —— M5 实施；M2 auth/login 路由占位（保留 Bearer 兼容现状）

**reinforce 同步实现**
- recall 命中时 `access_count += 1` + `last_accessed_at = now` 在 M2 走同步写。M4 上 worker 后将这步改成「入队 `reinforce` job + 异步消费」。在代码注释 + AGENTS.md 变更日志中标明这个临时性。

**RRF 与 re-rank 公式**
- RRF: `rrf_score = Σ 1 / (k + rank_i)`，k 默认 60，可经 env `MEMORY_MCP_RRF_K` 覆盖
- reinforce 归一化: `f(x) = 1 + log(1+x) / log(1+max_reinforce)`，`max_reinforce` 来自当前结果集的最大值（避免冷启动除零，max=0 时 `f(x)=1.0`）
- 时间衰减: `decay = exp(-λ * days_since_access)`，λ 默认 1/180，可经 env `MEMORY_MCP_DECAY_LAMBDA` 覆盖；`last_accessed_at` 为 NULL 时回落到 `created_at`
- final: `final = rrf_score * confidence * reinforce_factor * decay`
- 召回深度可经 env `MEMORY_MCP_RECALL_DEPTH` 覆盖（默认 vector=50 / fts=50 / graph=20）

**filter 策略**
- 默认排除 `review_status in ('legacy', 'archived')`
- 默认 `is_current = true`（`trace` 例外，不经 hybrid_search）
- 用户传入 `filters.review_status` 时覆盖默认，但仍排除 `'archived'` 除非显式传入

---

## File Structure

### Server Side（新增 / 修改）

| File | Action | Responsibility |
|------|--------|----------------|
| `src/memory_mcp/engine/hybrid_search.py` | Create | 三路召回 + RRF 融合 + re-rank + filter |
| `src/memory_mcp/engine/reinforce.py` | Create | `record_access(memory_ids: list[str])` 同步写 access_count++ + last_accessed_at |
| `src/memory_mcp/tools/memory_crud.py` | Create | `memory_get_tool` / `memory_update_tool` / `memory_delete_tool` / `memory_merge_tool` |
| `src/memory_mcp/tools/hybrid_search.py` | Create | `hybrid_search_tool` —— recall 的底层暴露 |
| `src/memory_mcp/tools/thread_stub.py` | Create | M2 占位：`thread_search_tool` / `thread_get_tool` / `thread_import_tool` / `thread_list_providers_tool` |
| `src/memory_mcp/tools/remember.py` | Modify | 透传 `origin_client` / `origin_session_id` / `source_thread_id` / `source_refs` / `title` |
| `src/memory_mcp/tools/recall.py` | Modify | 调用 hybrid_search；接受 `search_mode` / `filters` / `time_range`；返回 `relevance_breakdown` + `search_metadata` |
| `src/memory_mcp/tools/forget.py` | Modify | 内部走 `memory_update_tool(review_status='archived')` |
| `src/memory_mcp/api/routes.py` | Modify | 扩展 memories 分页/过滤/批量 + graph subgraph + threads/jobs/auth/search 骨架 |
| `src/memory_mcp/server.py` | Modify | 注册新 MCP tools |

### Tests（新增）

| File | Action | Tests |
|------|--------|-------|
| `tests/test_hybrid_search.py` | Create | 三路召回各自 + RRF + re-rank + filter + k/λ 边界 + 空召回 + 超长 query |
| `tests/test_reinforce.py` | Create | 同步写 access_count++ + last_accessed_at；不命中不写 |
| `tests/test_memory_crud.py` | Create | get / update / delete (soft/hard) / merge（含 source_refs 合并 + 软删 + archived_reason） |
| `tests/test_recall_hybrid.py` | Create | recall 默认走 hybrid；search_mode 切换；relevance_breakdown 字段完整 |
| `tests/test_thread_stubs.py` | Create | thread_* tool 占位返回 phase=M3 |
| `tests/test_api_extended.py` | Create | REST 分页/过滤/批量 delete / merge / subgraph / threads-jobs-auth-search 骨架 |

---

## Chunk 1: Hybrid Search Engine 三路召回 + RRF + Re-rank

### Task 1: tokenizer 复用与 jieba query 切分

**Files:**
- Modify: `src/memory_mcp/engine/tokenizer.py`（M1 已就绪，补 `tokenize_query` 入口）
- Test: `tests/test_hybrid_search.py`

- [ ] **Step 1: Write failing test for FTS query tokenization**

Create `tests/test_hybrid_search.py`:

```python
import importlib

import anyio
import pytest


def _reload_engine():
    import memory_mcp.engine.tokenizer as tok_mod
    importlib.reload(tok_mod)
    return tok_mod


def test_tokenize_query_chinese_returns_space_joined(test_env):
    tok = _reload_engine()
    out = tok.tokenize_query("我喜欢使用 Cursor 编辑器")
    assert isinstance(out, str)
    assert " " in out
    assert "Cursor" in out or "cursor" in out.lower()


def test_tokenize_query_empty(test_env):
    tok = _reload_engine()
    assert tok.tokenize_query("") == ""
    assert tok.tokenize_query("   ") == ""
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py::test_tokenize_query_chinese_returns_space_joined tests/test_hybrid_search.py::test_tokenize_query_empty -v
```
Expected: FAIL（`tokenize_query` 不存在）

- [ ] **Step 3: Add tokenize_query**

Edit `src/memory_mcp/engine/tokenizer.py` — 在文件末尾追加:

```python
def tokenize_query(text: str) -> str:
    """Tokenize an arbitrary user query for FTS5 lookup.

    Returns a space-joined token string suitable for passing to
    ``MATCH`` in SQLite FTS5. Empty / whitespace-only input returns ''.
    """
    if not text or not text.strip():
        return ""
    return tokenize(text)
```

如果 M1 已在 `tokenizer.py` 暴露的是别的名字（例如 `tokenize_text`），把 `tokenize` 替换为对应的导出名；如果该模块尚不存在，先创建：

```python
# src/memory_mcp/engine/tokenizer.py
from __future__ import annotations

import jieba


def tokenize(text: str) -> str:
    if not text:
        return ""
    return " ".join(w for w in jieba.cut(text, cut_all=False) if w.strip())


def tokenize_query(text: str) -> str:
    if not text or not text.strip():
        return ""
    return tokenize(text)
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py::test_tokenize_query_chinese_returns_space_joined tests/test_hybrid_search.py::test_tokenize_query_empty -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/engine/tokenizer.py tests/test_hybrid_search.py
git commit -m "feat(engine): add tokenize_query for FTS5 hybrid search input"
```

### Task 2: Hybrid Search 三路召回 — vector recall

**Files:**
- Create: `src/memory_mcp/engine/hybrid_search.py`
- Modify: `tests/test_hybrid_search.py`

- [ ] **Step 1: Write failing test for vector recall**

Append to `tests/test_hybrid_search.py`:

```python
def _reload_hybrid():
    import memory_mcp.engine.hybrid_search as hs_mod
    importlib.reload(hs_mod)
    return hs_mod


def test_vector_recall_returns_ranked_ids(tools, test_env, monkeypatch):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "Use Cursor editor",
            "entity_key": "preference:editor",
            "entity_type": "preference",
        })
        await remember.remember_tool({
            "content": "Python is preferred language",
            "entity_key": "preference:lang",
            "entity_type": "preference",
        })

        hs = _reload_hybrid()
        # vector recall returns [(memory_id, rank), ...]
        ids = await hs.vector_recall(query="editor", limit=10)
        assert isinstance(ids, list)
        assert len(ids) >= 1
        first = ids[0]
        assert "memory_id" in first
        assert first["rank"] == 1
    anyio.run(run)


def test_vector_recall_empty_query_returns_empty(tools, test_env):
    async def run():
        hs = _reload_hybrid()
        out = await hs.vector_recall(query="", limit=10)
        assert out == []
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py::test_vector_recall_returns_ranked_ids tests/test_hybrid_search.py::test_vector_recall_empty_query_returns_empty -v
```
Expected: FAIL

- [ ] **Step 3: Implement vector_recall**

Create `src/memory_mcp/engine/hybrid_search.py`:

```python
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from ..engine.embedding import embedding_service
from ..engine.tokenizer import tokenize_query
from ..storage.vector import vector_store
from ..storage.graph import graph_store

logger = logging.getLogger("memory-mcp.hybrid_search")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid int for %s=%s, using default %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float for %s=%s, using default %s", name, raw, default)
        return default


RRF_K = _env_int("MEMORY_MCP_RRF_K", 60)
DECAY_LAMBDA = _env_float("MEMORY_MCP_DECAY_LAMBDA", 1.0 / 180.0)
RECALL_DEPTH_VECTOR = _env_int("MEMORY_MCP_RECALL_DEPTH", 50)
RECALL_DEPTH_FTS = _env_int("MEMORY_MCP_RECALL_DEPTH_FTS", RECALL_DEPTH_VECTOR)
RECALL_DEPTH_GRAPH = _env_int("MEMORY_MCP_RECALL_DEPTH_GRAPH", 20)


@dataclass
class RankedHit:
    memory_id: str
    rank: int
    raw_score: float | None = None


@dataclass
class HybridResult:
    memory_id: str
    final_score: float
    rrf_score: float
    vector_rank: int | None
    fts_rank: int | None
    graph_rank: int | None
    confidence: float
    reinforce_factor: float
    decay_factor: float
    node: Any  # MemoryNode


async def vector_recall(query: str, limit: int = RECALL_DEPTH_VECTOR) -> list[dict[str, Any]]:
    """Vector ANN recall via embedding + vector_store.search."""
    if not query or not query.strip():
        return []
    try:
        vector = await embedding_service.get_embedding(query)
    except Exception as e:
        logger.warning("vector_recall embedding failed: %s", e)
        return []
    try:
        results = await vector_store.search(
            query_vector=vector,
            limit=limit,
            filter_current=True,
        )
    except Exception as e:
        logger.warning("vector_recall search failed: %s", e)
        return []
    out: list[dict[str, Any]] = []
    for rank, (node, distance) in enumerate(results, start=1):
        out.append({"memory_id": node.id, "rank": rank, "raw_score": distance, "node": node})
    return out
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py::test_vector_recall_returns_ranked_ids tests/test_hybrid_search.py::test_vector_recall_empty_query_returns_empty -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/engine/hybrid_search.py tests/test_hybrid_search.py
git commit -m "feat(engine): scaffold hybrid_search with vector recall"
```

### Task 3: Hybrid Search — FTS5 recall via jieba

**Files:**
- Modify: `src/memory_mcp/engine/hybrid_search.py`
- Modify: `tests/test_hybrid_search.py`

- [ ] **Step 1: Write failing test for FTS recall**

Append to `tests/test_hybrid_search.py`:

```python
def test_fts_recall_returns_ranked_ids(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "Cursor 是首选编辑器",
            "entity_key": "preference:editor",
            "entity_type": "preference",
        })
        hs = _reload_hybrid()
        ids = await hs.fts_recall(query="编辑器", limit=10)
        assert isinstance(ids, list)
        assert len(ids) >= 1
        assert ids[0]["rank"] == 1


    anyio.run(run)


def test_fts_recall_empty_query(tools, test_env):
    async def run():
        hs = _reload_hybrid()
        out = await hs.fts_recall(query="   ", limit=10)
        assert out == []
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py::test_fts_recall_returns_ranked_ids tests/test_hybrid_search.py::test_fts_recall_empty_query -v
```
Expected: FAIL

- [ ] **Step 3: Implement fts_recall**

Append to `src/memory_mcp/engine/hybrid_search.py`:

```python
from ..storage.repositories.memories import MemoryRepository


async def fts_recall(query: str, limit: int = RECALL_DEPTH_FTS) -> list[dict[str, Any]]:
    """FTS5 recall via the jieba-pre-tokenized ``memories_fts`` virtual table.

    Delegates to ``MemoryRepository.fts_search`` (M1 authoritative API); falls
    back to an in-memory substring scan only when SQLite storage is unavailable
    (e.g. tests using ``MEMORY_MCP_VECTOR_BACKEND=memory`` without alembic).
    """
    if not query or not query.strip():
        return []
    tokens = tokenize_query(query)
    if not tokens:
        return []

    repo = MemoryRepository()
    try:
        rows = await repo.fts_search(tokens=tokens, limit=limit)
    except Exception as e:
        logger.debug("fts_recall fell back to in-memory scan: %s", e)
        rows = await _fts_inmemory_fallback(tokens, limit)

    out: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        out.append({
            "memory_id": row["memory_id"],
            "rank": rank,
            "raw_score": row.get("bm25"),
            "node": row.get("node"),
        })
    return out


async def _fts_inmemory_fallback(tokens: str, limit: int) -> list[dict[str, Any]]:
    """Fallback when SQLite FTS is unavailable: scan vector_store.list_current
    for any token substring match. Used only by tests with memory backend.
    """
    nodes = await vector_store.list_current(limit=1000)
    needles = [t for t in tokens.split() if t]
    scored: list[tuple[int, Any]] = []
    for n in nodes:
        haystack = f"{n.content} {getattr(n, 'title', '') or ''}".lower()
        hits = sum(1 for t in needles if t.lower() in haystack)
        if hits > 0:
            scored.append((hits, n))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"memory_id": n.id, "bm25": None, "node": n} for _, n in scored[:limit]]
```

`MemoryRepository.fts_search` 由 M1 Task 10 提供，签名 `(tokens: str, limit: int) -> list[{"memory_id", "bm25", "node"}]`，已经走 jieba 预分词字段 `content_tokens` / `title_tokens` 的 FTS5 MATCH。

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py::test_fts_recall_returns_ranked_ids tests/test_hybrid_search.py::test_fts_recall_empty_query -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/engine/hybrid_search.py tests/test_hybrid_search.py
git commit -m "feat(engine): add FTS5 recall with jieba tokenization and in-memory fallback"
```

### Task 4: Hybrid Search — Graph 1-hop recall

**Files:**
- Modify: `src/memory_mcp/engine/hybrid_search.py`
- Modify: `tests/test_hybrid_search.py`

- [ ] **Step 1: Write failing test for graph recall**

Append to `tests/test_hybrid_search.py`:

```python
def test_graph_recall_returns_neighbor_memories(tools, test_env):
    async def run():
        remember, recall, recall_all, trace, forget, relate, graph_query = tools
        # Seed: two entities linked
        await remember.remember_tool({
            "content": "Alice owns project X",
            "entity_key": "person:alice",
            "entity_type": "person",
        })
        await remember.remember_tool({
            "content": "Project X is in beta",
            "entity_key": "project:x",
            "entity_type": "project",
        })
        await relate.relate_tool({
            "from_entity_key": "person:alice",
            "to_entity_key": "project:x",
            "relation_type": "OWNS",
        })

        hs = _reload_hybrid()
        # Seed memories that match the query directly: alice
        seed_ids = ["person:alice"]
        out = await hs.graph_recall(seed_entity_keys=seed_ids, limit=10)
        keys = {hit["entity_key"] for hit in out}
        assert "project:x" in keys


    anyio.run(run)


def test_graph_recall_empty_seeds(tools, test_env):
    async def run():
        hs = _reload_hybrid()
        out = await hs.graph_recall(seed_entity_keys=[], limit=10)
        assert out == []


    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py::test_graph_recall_returns_neighbor_memories tests/test_hybrid_search.py::test_graph_recall_empty_seeds -v
```
Expected: FAIL

- [ ] **Step 3: Implement graph_recall**

Append to `src/memory_mcp/engine/hybrid_search.py`:

```python
async def graph_recall(
    seed_entity_keys: Iterable[str],
    limit: int = RECALL_DEPTH_GRAPH,
) -> list[dict[str, Any]]:
    """1-hop neighbor recall.

    Given seed entity keys (typically extracted from vector/FTS top hits),
    walk the graph one hop and return current memory of each neighbor entity.
    """
    seeds = [k for k in (seed_entity_keys or []) if k]
    if not seeds:
        return []

    seen_entities: set[str] = set(seeds)
    neighbors: list[str] = []
    for key in seeds:
        try:
            rels = await graph_store.get_relations(key, relation_types=None, depth=1)
        except Exception as e:
            logger.debug("graph_recall get_relations failed for %s: %s", key, e)
            continue
        for r in rels:
            for side in ("from_entity_key", "to_entity_key"):
                neighbor = r.get(side)
                if neighbor and neighbor not in seen_entities:
                    seen_entities.add(neighbor)
                    neighbors.append(neighbor)

    out: list[dict[str, Any]] = []
    for rank, entity_key in enumerate(neighbors[:limit], start=1):
        history = await vector_store.get_history(entity_key)
        current = next((n for n in history if n.is_current), None)
        if current is None:
            continue
        out.append({
            "memory_id": current.id,
            "entity_key": entity_key,
            "rank": rank,
            "node": current,
        })
    return out
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py::test_graph_recall_returns_neighbor_memories tests/test_hybrid_search.py::test_graph_recall_empty_seeds -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/engine/hybrid_search.py tests/test_hybrid_search.py
git commit -m "feat(engine): add 1-hop graph recall for hybrid search"
```

### Task 5: Hybrid Search — RRF fusion

**Files:**
- Modify: `src/memory_mcp/engine/hybrid_search.py`
- Modify: `tests/test_hybrid_search.py`

- [ ] **Step 1: Write failing test for RRF**

Append to `tests/test_hybrid_search.py`:

```python
def test_rrf_fuse_single_source(test_env):
    hs = _reload_hybrid()
    fused = hs.rrf_fuse(
        ranked_lists={"vector": [{"memory_id": "m1", "rank": 1}, {"memory_id": "m2", "rank": 2}]},
        k=60,
    )
    assert fused[0]["memory_id"] == "m1"
    assert fused[0]["rrf_score"] == pytest.approx(1 / (60 + 1))
    assert fused[1]["rrf_score"] == pytest.approx(1 / (60 + 2))


def test_rrf_fuse_multiple_sources(test_env):
    hs = _reload_hybrid()
    fused = hs.rrf_fuse(
        ranked_lists={
            "vector": [{"memory_id": "m1", "rank": 1}, {"memory_id": "m2", "rank": 2}],
            "fts": [{"memory_id": "m2", "rank": 1}, {"memory_id": "m3", "rank": 2}],
        },
        k=60,
    )
    by_id = {h["memory_id"]: h for h in fused}
    # m2 appears in both — should have largest combined rrf_score
    assert by_id["m2"]["rrf_score"] > by_id["m1"]["rrf_score"]
    assert by_id["m2"]["rrf_score"] > by_id["m3"]["rrf_score"]
    assert by_id["m2"]["vector_rank"] == 2
    assert by_id["m2"]["fts_rank"] == 1


def test_rrf_fuse_empty_lists(test_env):
    hs = _reload_hybrid()
    assert hs.rrf_fuse(ranked_lists={}, k=60) == []
    assert hs.rrf_fuse(ranked_lists={"vector": [], "fts": []}, k=60) == []


def test_rrf_fuse_k_zero_safe(test_env):
    hs = _reload_hybrid()
    # k=0 would naively divide-by-zero for rank=0; we never use rank=0, so k=0 is allowed.
    fused = hs.rrf_fuse(ranked_lists={"vector": [{"memory_id": "m1", "rank": 1}]}, k=0)
    assert fused[0]["rrf_score"] == pytest.approx(1 / 1)


def test_rrf_fuse_large_k(test_env):
    hs = _reload_hybrid()
    fused = hs.rrf_fuse(ranked_lists={"vector": [{"memory_id": "m1", "rank": 1}]}, k=10000)
    assert fused[0]["rrf_score"] == pytest.approx(1 / 10001)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py -k "rrf_fuse" -v
```
Expected: FAIL

- [ ] **Step 3: Implement rrf_fuse**

Append to `src/memory_mcp/engine/hybrid_search.py`:

```python
def rrf_fuse(
    ranked_lists: dict[str, list[dict[str, Any]]],
    k: int = RRF_K,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion across multiple ranked lists.

    ``ranked_lists`` maps a source name (e.g. 'vector', 'fts', 'graph') to a
    list of {"memory_id": str, "rank": int, "node": MemoryNode | None, ...}.
    Returns a fused list sorted by descending rrf_score with per-source ranks
    threaded through as ``<source>_rank``.
    """
    accumulator: dict[str, dict[str, Any]] = {}
    for source, hits in (ranked_lists or {}).items():
        for hit in hits or []:
            mid = hit["memory_id"]
            rank = hit["rank"]
            entry = accumulator.setdefault(
                mid,
                {
                    "memory_id": mid,
                    "rrf_score": 0.0,
                    "vector_rank": None,
                    "fts_rank": None,
                    "graph_rank": None,
                    "node": None,
                },
            )
            entry["rrf_score"] += 1.0 / (k + rank)
            entry[f"{source}_rank"] = rank
            if entry["node"] is None and hit.get("node") is not None:
                entry["node"] = hit["node"]
    fused = list(accumulator.values())
    fused.sort(key=lambda h: h["rrf_score"], reverse=True)
    return fused
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py -k "rrf_fuse" -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/engine/hybrid_search.py tests/test_hybrid_search.py
git commit -m "feat(engine): add RRF fusion across vector/fts/graph rankings"
```

### Task 6: Hybrid Search — Re-rank (confidence × reinforce × decay)

**Files:**
- Modify: `src/memory_mcp/engine/hybrid_search.py`
- Modify: `tests/test_hybrid_search.py`

- [ ] **Step 1: Write failing test for re-rank factors**

Append to `tests/test_hybrid_search.py`:

```python
import math
from datetime import datetime, timezone, timedelta


def _stub_node(id_: str, *, confidence=1.0, reinforce_count=0, last_accessed_at=None, content="x"):
    from memory_mcp.engine.models import MemoryNode, MutationType
    return MemoryNode(
        id=id_,
        entity_key=f"fact:{id_}",
        entity_type="fact",
        content=content,
        embedding=[0.0, 0.0, 0.0],
        mutation_type=MutationType.INITIAL,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        valid_from=datetime.now(timezone.utc) - timedelta(days=10),
        is_current=True,
        confidence=confidence,
        reinforce_count=reinforce_count,
        last_accessed_at=last_accessed_at,
        review_status="auto",
    )


def test_rerank_applies_confidence(test_env):
    hs = _reload_hybrid()
    fused = [
        {"memory_id": "a", "rrf_score": 0.5, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "node": _stub_node("a", confidence=1.0)},
        {"memory_id": "b", "rrf_score": 0.5, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "node": _stub_node("b", confidence=0.5)},
    ]
    ranked = hs.rerank(fused)
    assert ranked[0]["memory_id"] == "a"
    assert ranked[1]["memory_id"] == "b"


def test_rerank_applies_reinforce(test_env):
    hs = _reload_hybrid()
    fused = [
        {"memory_id": "a", "rrf_score": 0.5, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "node": _stub_node("a", reinforce_count=0)},
        {"memory_id": "b", "rrf_score": 0.5, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "node": _stub_node("b", reinforce_count=10)},
    ]
    ranked = hs.rerank(fused)
    assert ranked[0]["memory_id"] == "b"


def test_rerank_applies_decay(test_env, monkeypatch):
    hs = _reload_hybrid()
    fresh = datetime.now(timezone.utc)
    stale = datetime.now(timezone.utc) - timedelta(days=365)
    fused = [
        {"memory_id": "fresh", "rrf_score": 0.5, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "node": _stub_node("fresh", last_accessed_at=fresh)},
        {"memory_id": "stale", "rrf_score": 0.5, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "node": _stub_node("stale", last_accessed_at=stale)},
    ]
    ranked = hs.rerank(fused)
    assert ranked[0]["memory_id"] == "fresh"
    assert ranked[0]["decay_factor"] > ranked[1]["decay_factor"]


def test_rerank_decay_lambda_zero_disables_decay(monkeypatch, test_env):
    monkeypatch.setenv("MEMORY_MCP_DECAY_LAMBDA", "0")
    hs = _reload_hybrid()
    fresh = datetime.now(timezone.utc)
    stale = datetime.now(timezone.utc) - timedelta(days=365)
    fused = [
        {"memory_id": "fresh", "rrf_score": 0.5, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "node": _stub_node("fresh", last_accessed_at=fresh)},
        {"memory_id": "stale", "rrf_score": 0.5, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "node": _stub_node("stale", last_accessed_at=stale)},
    ]
    ranked = hs.rerank(fused)
    # λ=0 => decay always 1.0; tie on final score; ordering stable
    assert ranked[0]["decay_factor"] == 1.0
    assert ranked[1]["decay_factor"] == 1.0


def test_rerank_handles_missing_last_accessed_at(test_env):
    hs = _reload_hybrid()
    n = _stub_node("a", last_accessed_at=None)
    ranked = hs.rerank([{"memory_id": "a", "rrf_score": 0.5, "vector_rank": 1, "fts_rank": None,
                        "graph_rank": None, "node": n}])
    assert ranked[0]["decay_factor"] > 0
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py -k "rerank" -v
```
Expected: FAIL

- [ ] **Step 3: Implement rerank**

Append to `src/memory_mcp/engine/hybrid_search.py`:

```python
def _days_since(ts: datetime | None, fallback: datetime | None) -> float:
    ref = ts or fallback
    if ref is None:
        return 0.0
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ref
    return max(0.0, delta.total_seconds() / 86400.0)


def _reinforce_factor(value: int, max_in_set: int) -> float:
    if max_in_set <= 0:
        return 1.0
    return 1.0 + math.log1p(max(0, value)) / math.log1p(max_in_set)


def rerank(fused: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply confidence * reinforce_factor * decay_factor on top of rrf_score."""
    # Reread env each call so tests can monkeypatch MEMORY_MCP_DECAY_LAMBDA.
    lam = _env_float("MEMORY_MCP_DECAY_LAMBDA", 1.0 / 180.0)

    max_reinforce = 0
    for h in fused:
        node = h.get("node")
        if node is not None:
            max_reinforce = max(max_reinforce, getattr(node, "reinforce_count", 0) or 0)

    enriched: list[dict[str, Any]] = []
    for h in fused:
        node = h.get("node")
        confidence = float(getattr(node, "confidence", 1.0) or 1.0) if node else 1.0
        reinforce = int(getattr(node, "reinforce_count", 0) or 0) if node else 0
        last_accessed = getattr(node, "last_accessed_at", None) if node else None
        created = getattr(node, "created_at", None) if node else None
        days = _days_since(last_accessed, created)
        decay = math.exp(-lam * days) if lam > 0 else 1.0
        reinforce_factor = _reinforce_factor(reinforce, max_reinforce)
        final = h["rrf_score"] * confidence * reinforce_factor * decay
        out = {**h,
               "confidence": confidence,
               "reinforce_factor": reinforce_factor,
               "decay_factor": decay,
               "final_score": final}
        enriched.append(out)
    enriched.sort(key=lambda h: h["final_score"], reverse=True)
    return enriched
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py -k "rerank" -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/engine/hybrid_search.py tests/test_hybrid_search.py
git commit -m "feat(engine): add re-rank stage with confidence/reinforce/decay factors"
```

### Task 7: Hybrid Search — Filter (review_status / is_current / user filters)

**Files:**
- Modify: `src/memory_mcp/engine/hybrid_search.py`
- Modify: `tests/test_hybrid_search.py`

- [ ] **Step 1: Write failing test for filter stage**

Append to `tests/test_hybrid_search.py`:

```python
def test_filter_drops_legacy_and_archived(test_env):
    hs = _reload_hybrid()
    nodes = [
        _stub_node("ok"),
        _stub_node("legacy"),
        _stub_node("archived"),
    ]
    nodes[1].review_status = "legacy"
    nodes[2].review_status = "archived"
    enriched = [
        {"memory_id": n.id, "final_score": 1.0, "node": n,
         "rrf_score": 1.0, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "confidence": 1.0, "reinforce_factor": 1.0, "decay_factor": 1.0}
        for n in nodes
    ]
    filtered, dropped = hs.apply_filters(enriched, user_filters=None)
    ids = [h["memory_id"] for h in filtered]
    assert "ok" in ids
    assert "legacy" not in ids
    assert "archived" not in ids
    assert dropped == 2


def test_filter_user_review_status(test_env):
    hs = _reload_hybrid()
    nodes = [_stub_node("a"), _stub_node("b")]
    nodes[0].review_status = "confirmed"
    nodes[1].review_status = "auto"
    enriched = [
        {"memory_id": n.id, "final_score": 1.0, "node": n,
         "rrf_score": 1.0, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "confidence": 1.0, "reinforce_factor": 1.0, "decay_factor": 1.0}
        for n in nodes
    ]
    filtered, _ = hs.apply_filters(enriched, user_filters={"review_status": ["confirmed"]})
    ids = [h["memory_id"] for h in filtered]
    assert ids == ["a"]


def test_filter_user_origin_client(test_env):
    hs = _reload_hybrid()
    nodes = [_stub_node("a"), _stub_node("b")]
    nodes[0].origin_client = "claude-code"
    nodes[1].origin_client = "codex"
    enriched = [
        {"memory_id": n.id, "final_score": 1.0, "node": n,
         "rrf_score": 1.0, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "confidence": 1.0, "reinforce_factor": 1.0, "decay_factor": 1.0}
        for n in nodes
    ]
    filtered, _ = hs.apply_filters(enriched, user_filters={"origin_client": "claude-code"})
    assert [h["memory_id"] for h in filtered] == ["a"]


def test_filter_user_time_range(test_env):
    hs = _reload_hybrid()
    old = _stub_node("old")
    new = _stub_node("new")
    old.created_at = datetime.now(timezone.utc) - timedelta(days=400)
    new.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    enriched = [
        {"memory_id": n.id, "final_score": 1.0, "node": n,
         "rrf_score": 1.0, "vector_rank": 1, "fts_rank": None, "graph_rank": None,
         "confidence": 1.0, "reinforce_factor": 1.0, "decay_factor": 1.0}
        for n in (old, new)
    ]
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    filtered, _ = hs.apply_filters(enriched, user_filters={"time_range": {"since": since}})
    assert [h["memory_id"] for h in filtered] == ["new"]
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py -k "filter" -v
```
Expected: FAIL

- [ ] **Step 3: Implement apply_filters**

Append to `src/memory_mcp/engine/hybrid_search.py`:

```python
_DEFAULT_EXCLUDED_STATUS = {"legacy", "archived"}


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        out = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if out.tzinfo is None:
        out = out.replace(tzinfo=timezone.utc)
    return out


def apply_filters(
    items: list[dict[str, Any]],
    user_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], int]:
    """Apply review_status / origin_client / time_range / explicit allow-lists.

    Returns (kept, dropped_count).
    """
    user_filters = user_filters or {}

    explicit_status = user_filters.get("review_status")
    explicit_status_set: set[str] | None = None
    if explicit_status:
        if isinstance(explicit_status, str):
            explicit_status_set = {explicit_status}
        else:
            explicit_status_set = {str(s) for s in explicit_status}

    origin_client = user_filters.get("origin_client")
    origin_set: set[str] | None
    if origin_client is None:
        origin_set = None
    elif isinstance(origin_client, str):
        origin_set = {origin_client}
    else:
        origin_set = {str(c) for c in origin_client}

    time_range = user_filters.get("time_range") or {}
    since = _parse_iso(time_range.get("since"))
    until = _parse_iso(time_range.get("until"))

    kept: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        node = item.get("node")
        if node is None:
            dropped += 1
            continue
        status = getattr(node, "review_status", "auto") or "auto"
        if explicit_status_set is not None:
            if status not in explicit_status_set:
                dropped += 1
                continue
        else:
            if status in _DEFAULT_EXCLUDED_STATUS:
                dropped += 1
                continue

        if origin_set is not None:
            if (getattr(node, "origin_client", None) or "") not in origin_set:
                dropped += 1
                continue

        created = getattr(node, "created_at", None)
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if since and created and created < since:
            dropped += 1
            continue
        if until and created and created > until:
            dropped += 1
            continue

        kept.append(item)
    return kept, dropped
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py -k "filter" -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/engine/hybrid_search.py tests/test_hybrid_search.py
git commit -m "feat(engine): add filter stage for review_status/origin_client/time_range"
```

### Task 8: Hybrid Search — end-to-end search() entrypoint

**Files:**
- Modify: `src/memory_mcp/engine/hybrid_search.py`
- Modify: `tests/test_hybrid_search.py`

- [ ] **Step 1: Write failing test for the entrypoint**

Append to `tests/test_hybrid_search.py`:

```python
def test_search_hybrid_returns_breakdown_and_metadata(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "Cursor 编辑器很快",
            "entity_key": "preference:editor",
            "entity_type": "preference",
        })
        hs = _reload_hybrid()
        result = await hs.search(query="编辑器", mode="hybrid", filters=None, limit=10)
        assert "results" in result
        assert "search_metadata" in result
        assert result["search_mode"] == "hybrid"
        meta = result["search_metadata"]
        assert "vector_candidates" in meta
        assert "fts_candidates" in meta
        assert "graph_candidates" in meta
        assert "filtered_out" in meta
        assert "elapsed_ms" in meta
        if result["results"]:
            first = result["results"][0]
            assert "final_score" in first
            assert "relevance_breakdown" in first
            rb = first["relevance_breakdown"]
            for key in ("rrf_score", "vector_rank", "fts_rank", "graph_rank",
                        "confidence", "reinforce_factor", "decay_factor"):
                assert key in rb
    anyio.run(run)


def test_search_mode_vector_only_skips_fts_and_graph(tools, test_env, monkeypatch):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "Vim is fine",
            "entity_key": "preference:editor",
            "entity_type": "preference",
        })
        hs = _reload_hybrid()

        called = {"fts": 0, "graph": 0}
        original_fts = hs.fts_recall
        original_graph = hs.graph_recall

        async def spy_fts(*a, **k):
            called["fts"] += 1
            return await original_fts(*a, **k)

        async def spy_graph(*a, **k):
            called["graph"] += 1
            return await original_graph(*a, **k)

        monkeypatch.setattr(hs, "fts_recall", spy_fts)
        monkeypatch.setattr(hs, "graph_recall", spy_graph)

        await hs.search(query="vim", mode="vector_only", filters=None, limit=10)
        assert called["fts"] == 0
        assert called["graph"] == 0
    anyio.run(run)


def test_search_empty_query_returns_empty_with_metadata(tools, test_env):
    async def run():
        hs = _reload_hybrid()
        out = await hs.search(query="", mode="hybrid", filters=None, limit=10)
        assert out["results"] == []
        assert out["total"] == 0
        assert "search_metadata" in out
    anyio.run(run)


def test_search_long_query_truncates_gracefully(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "anything",
            "entity_key": "fact:any",
            "entity_type": "fact",
        })
        hs = _reload_hybrid()
        # 10k character query should not crash; embedding / FTS see truncated input
        huge = "a" * 10_000
        out = await hs.search(query=huge, mode="hybrid", filters=None, limit=10)
        assert "results" in out
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py -k "search_" -v
```
Expected: FAIL

- [ ] **Step 3: Implement search() entrypoint**

Append to `src/memory_mcp/engine/hybrid_search.py`:

```python
import time

_VALID_MODES = {"hybrid", "vector_only", "fts_only", "graph_only"}
_MAX_QUERY_CHARS = 4000


def _truncate_query(q: str) -> str:
    if len(q) <= _MAX_QUERY_CHARS:
        return q
    return q[:_MAX_QUERY_CHARS]


async def search(
    query: str,
    mode: str = "hybrid",
    filters: dict[str, Any] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """High-level entrypoint used by recall_tool / hybrid_search_tool / REST.

    Returns a dict shaped to spec §5.4.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"Unsupported search_mode: {mode}")
    started = time.perf_counter()

    q = _truncate_query(query or "")
    vec_hits: list[dict[str, Any]] = []
    fts_hits: list[dict[str, Any]] = []
    graph_hits: list[dict[str, Any]] = []

    if not q.strip():
        elapsed = int((time.perf_counter() - started) * 1000)
        return {
            "results": [],
            "total": 0,
            "search_mode": mode,
            "search_metadata": {
                "vector_candidates": 0,
                "fts_candidates": 0,
                "graph_candidates": 0,
                "filtered_out": 0,
                "elapsed_ms": elapsed,
            },
        }

    if mode in ("hybrid", "vector_only"):
        vec_hits = await vector_recall(q, limit=RECALL_DEPTH_VECTOR)
    if mode in ("hybrid", "fts_only"):
        fts_hits = await fts_recall(q, limit=RECALL_DEPTH_FTS)

    if mode in ("hybrid", "graph_only"):
        seed_keys: list[str] = []
        for hit in (vec_hits + fts_hits)[: max(5, limit)]:
            node = hit.get("node")
            if node is not None and getattr(node, "entity_key", None):
                seed_keys.append(node.entity_key)
        # de-dup while preserving order
        seen: set[str] = set()
        ordered_seeds = [k for k in seed_keys if not (k in seen or seen.add(k))]
        graph_hits = await graph_recall(ordered_seeds, limit=RECALL_DEPTH_GRAPH)

    ranked_lists: dict[str, list[dict[str, Any]]] = {}
    if vec_hits:
        ranked_lists["vector"] = vec_hits
    if fts_hits:
        ranked_lists["fts"] = fts_hits
    if graph_hits:
        ranked_lists["graph"] = graph_hits

    fused = rrf_fuse(ranked_lists, k=RRF_K)

    # Hydrate node refs for entries that came in without a node (e.g. graph-only path)
    for h in fused:
        if h.get("node") is None:
            n = await vector_store.get_by_id(h["memory_id"])
            h["node"] = n

    reranked = rerank(fused)
    kept, dropped = apply_filters(reranked, user_filters=filters)

    top = kept[:limit]

    elapsed = int((time.perf_counter() - started) * 1000)
    results: list[dict[str, Any]] = []
    for h in top:
        node = h["node"]
        history = await vector_store.get_history(node.entity_key)
        results.append({
            "memory_id": node.id,
            "entity_key": node.entity_key,
            "content": node.content,
            "title": getattr(node, "title", None),
            "final_score": h["final_score"],
            "relevance_breakdown": {
                "rrf_score": h["rrf_score"],
                "vector_rank": h.get("vector_rank"),
                "fts_rank": h.get("fts_rank"),
                "graph_rank": h.get("graph_rank"),
                "confidence": h["confidence"],
                "reinforce_factor": h["reinforce_factor"],
                "decay_factor": h["decay_factor"],
            },
            "review_status": getattr(node, "review_status", "auto"),
            "origin_client": getattr(node, "origin_client", None),
            "source_thread_id": getattr(node, "source_thread_id", None),
            "evolution_count": len(history),
        })

    return {
        "results": results,
        "total": len(results),
        "search_mode": mode,
        "search_metadata": {
            "vector_candidates": len(vec_hits),
            "fts_candidates": len(fts_hits),
            "graph_candidates": len(graph_hits),
            "filtered_out": dropped,
            "elapsed_ms": elapsed,
        },
    }
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_hybrid_search.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/engine/hybrid_search.py tests/test_hybrid_search.py
git commit -m "feat(engine): add hybrid_search.search() entrypoint with spec response shape"
```

---

## Chunk 2: Reinforce engine

### Task 9: Reinforce — record_access

**Files:**
- Create: `src/memory_mcp/engine/reinforce.py`
- Create: `tests/test_reinforce.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_reinforce.py`:

```python
import importlib
from datetime import datetime, timezone

import anyio


def _reload_reinforce():
    import memory_mcp.engine.reinforce as r
    importlib.reload(r)
    return r


def test_record_access_increments_count(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "fact",
            "entity_key": "fact:a",
            "entity_type": "fact",
        })
        import memory_mcp.storage.vector as vector_mod
        importlib.reload(vector_mod)
        history = await vector_mod.vector_store.get_history("fact:a")
        node = history[0]
        before_count = getattr(node, "access_count", 0) or 0

        r = _reload_reinforce()
        await r.record_access([node.id])

        history2 = await vector_mod.vector_store.get_history("fact:a")
        node2 = history2[0]
        assert (getattr(node2, "access_count", 0) or 0) == before_count + 1
        assert node2.last_accessed_at is not None
    anyio.run(run)


def test_record_access_unknown_id_silent(tools, test_env):
    async def run():
        r = _reload_reinforce()
        await r.record_access(["does-not-exist"])  # should not raise
    anyio.run(run)


def test_record_access_empty_list_noop(tools, test_env):
    async def run():
        r = _reload_reinforce()
        await r.record_access([])  # noop
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_reinforce.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement reinforce**

Create `src/memory_mcp/engine/reinforce.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

from ..storage.vector import vector_store

logger = logging.getLogger("memory-mcp.reinforce")


async def record_access(memory_ids: Iterable[str]) -> int:
    """Increment access_count and update last_accessed_at for the given ids.

    Phase 1 / M2 implementation is synchronous. In M4 we will replace this
    with an enqueue + worker handler so recall() does not block on writes.
    Marked TEMPORARY in AGENTS.md changelog.
    """
    ids = [m for m in (memory_ids or []) if m]
    if not ids:
        return 0
    updated = 0
    now = datetime.now(timezone.utc)
    for mid in ids:
        try:
            node = await vector_store.get_by_id(mid)
        except Exception as e:
            logger.debug("record_access get_by_id failed for %s: %s", mid, e)
            continue
        if node is None:
            continue
        node.access_count = (getattr(node, "access_count", 0) or 0) + 1
        node.last_accessed_at = now
        try:
            await vector_store.update(node)
            updated += 1
        except Exception as e:
            logger.warning("record_access update failed for %s: %s", mid, e)
    return updated
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_reinforce.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/engine/reinforce.py tests/test_reinforce.py
git commit -m "feat(engine): add reinforce.record_access (sync impl for M2, async in M4)"
```

---

## Chunk 3: Upgrade existing tools (remember / recall / forget)

### Task 10: remember — passthrough v2 fields

**Files:**
- Modify: `src/memory_mcp/tools/remember.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_tools.py`:

```python
import anyio


def test_remember_passes_through_v2_fields(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "Use Cursor",
            "entity_key": "preference:editor",
            "entity_type": "preference",
            "origin_client": "claude-code",
            "origin_session_id": "sess-123",
            "source_thread_id": "thr-1",
            "source_refs": [{"thread_id": "thr-1", "message_id": "thr-1:000001"}],
            "title": "Editor preference",
        })

        import memory_mcp.storage.vector as vector_mod
        import importlib
        importlib.reload(vector_mod)
        history = await vector_mod.vector_store.get_history("preference:editor")
        node = history[0]
        assert node.origin_client == "claude-code"
        assert node.origin_session_id == "sess-123"
        assert node.source_thread_id == "thr-1"
        # source_refs are SourceRef Pydantic models; attribute access only.
        assert node.source_refs and node.source_refs[0].message_id == "thr-1:000001"
        assert node.title == "Editor preference"
        # title_tokens regenerated via jieba so memories_fts indexes the title.
        assert node.title_tokens
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_tools.py::test_remember_passes_through_v2_fields -v
```
Expected: FAIL

- [ ] **Step 3: Modify remember_tool**

Edit `src/memory_mcp/tools/remember.py` — replace the section after the basic argument extraction（line 27-36 area）to pull v2 fields, and feed them into `MemoryNode(...)` at the "Initial memory" branch (line 121-141 area) plus the `evolve_memory(...)` calls.

Replace the body of `remember_tool` (the entire function) with:

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
    """Accept either ``SourceRef`` instances or ``{thread_id, message_id}`` dicts.

    Authoritative shape on the wire is the dict form; in-memory we always work
    with ``SourceRef`` Pydantic models. Spec §4.2 + serializers (M1 Task 9).
    """
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

    title = arguments.get("title")
    origin_client = arguments.get("origin_client")
    origin_session_id = arguments.get("origin_session_id")
    source_thread_id = arguments.get("source_thread_id")
    source_refs = _parse_source_refs(arguments.get("source_refs"))

    if not content or not entity_key or not entity_type:
        raise ValueError("Missing required arguments: content, entity_key, entity_type")

    # 1. Generate embedding
    embedding = await embedding_service.get_embedding(content)

    # 2. Existing entity_key path
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
        # Stamp v2 fields onto the freshly created node (evolve_memory does not know them)
        _apply_v2_fields(
            new_node,
            title=title,
            origin_client=origin_client,
            origin_session_id=origin_session_id,
            source_thread_id=source_thread_id,
            source_refs=source_refs,
        )
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

    # 3. Semantic similarity / conflict for unseen entity_key
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
                    _apply_v2_fields(
                        new_node,
                        title=title,
                        origin_client=origin_client,
                        origin_session_id=origin_session_id,
                        source_thread_id=source_thread_id,
                        source_refs=source_refs,
                    )
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

    # 4. Initial memory
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
        created_at=datetime.now(timezone.utc),
        valid_from=datetime.now(timezone.utc),
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


def _apply_v2_fields(
    node,
    *,
    title=None,
    origin_client=None,
    origin_session_id=None,
    source_thread_id=None,
    source_refs=None,
) -> None:
    """Stamp v2 metadata onto a freshly created node.

    ``source_refs`` is expected to already be a list of ``SourceRef`` Pydantic
    instances (caller uses ``_parse_source_refs``). Title regenerates
    ``title_tokens`` so FTS5 index stays in sync.
    """
    if title is not None:
        node.title = title
        node.title_tokens = tokenize(title)
    if origin_client is not None:
        node.origin_client = origin_client
    if origin_session_id is not None:
        node.origin_session_id = origin_session_id
    if source_thread_id is not None:
        node.source_thread_id = source_thread_id
    if source_refs:
        node.source_refs = source_refs
```

**关键修复**：
- `source_refs` 走 `_parse_source_refs` 转 `SourceRef`，避免 raw dict 直接进 `MemoryNode`（M1 序列化层期望 `SourceRef.model_dump()`）。
- `content_tokens` / `title_tokens` 在 initial 分支显式 `tokenize(...)`；evolve 分支由 `evolve_memory` 自带（M1 Task 14 已写）。
- 测试中 `source_refs[0]["message_id"]` 访问应改写为 `source_refs[0].message_id`（Pydantic）；REST/JSON 端通过 `model_dump()` 序列化成 dict 给前端。

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_tools.py::test_remember_passes_through_v2_fields -v
```
Expected: PASS

- [ ] **Step 5: Run full tool test suite for regressions**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_tools.py -v
```
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/tools/remember.py tests/test_tools.py
git commit -m "feat(remember): passthrough v2 fields (origin_client, source_refs, title, ...)"
```

### Task 11: recall — switch to hybrid_search + relevance_breakdown

**Files:**
- Modify: `src/memory_mcp/tools/recall.py`
- Create: `tests/test_recall_hybrid.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_recall_hybrid.py`:

```python
import importlib

import anyio
import pytest


def _reload_recall():
    import memory_mcp.tools.recall as r
    importlib.reload(r)
    return r


def test_recall_default_hybrid_returns_breakdown(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "Cursor 编辑器很快",
            "entity_key": "preference:editor",
            "entity_type": "preference",
        })
        r = _reload_recall()
        out = await r.recall_tool({"query": "编辑器"})
        assert out["search_mode"] == "hybrid"
        assert "search_metadata" in out
        if out["results"]:
            first = out["results"][0]
            assert "relevance_breakdown" in first
    anyio.run(run)


def test_recall_search_mode_vector_only(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "Cursor",
            "entity_key": "preference:editor",
            "entity_type": "preference",
        })
        r = _reload_recall()
        out = await r.recall_tool({"query": "Cursor", "search_mode": "vector_only"})
        assert out["search_mode"] == "vector_only"
    anyio.run(run)


def test_recall_filters_review_status(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "a",
            "entity_key": "fact:a",
            "entity_type": "fact",
        })
        await remember.remember_tool({
            "content": "b",
            "entity_key": "fact:b",
            "entity_type": "fact",
        })
        # Manually flip one to confirmed
        import memory_mcp.storage.vector as vmod
        importlib.reload(vmod)
        hist = await vmod.vector_store.get_history("fact:a")
        node = hist[0]
        node.review_status = "confirmed"
        await vmod.vector_store.update(node)

        r = _reload_recall()
        out = await r.recall_tool({"query": "a", "filters": {"review_status": ["confirmed"]}})
        keys = [hit["entity_key"] for hit in out["results"]]
        assert keys and all(k == "fact:a" for k in keys)
    anyio.run(run)


def test_recall_increments_access_on_hit(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "Cursor",
            "entity_key": "preference:editor",
            "entity_type": "preference",
        })
        import memory_mcp.storage.vector as vmod
        importlib.reload(vmod)
        before = (await vmod.vector_store.get_history("preference:editor"))[0]
        assert (getattr(before, "access_count", 0) or 0) == 0

        r = _reload_recall()
        await r.recall_tool({"query": "Cursor"})

        after = (await vmod.vector_store.get_history("preference:editor"))[0]
        assert (getattr(after, "access_count", 0) or 0) >= 1
        assert after.last_accessed_at is not None
    anyio.run(run)


def test_recall_missing_query_raises(tools, test_env):
    async def run():
        r = _reload_recall()
        with pytest.raises(ValueError):
            await r.recall_tool({})
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_recall_hybrid.py -v
```
Expected: FAIL

- [ ] **Step 3: Rewrite recall_tool to use hybrid_search**

Replace the entire contents of `src/memory_mcp/tools/recall.py`:

```python
from __future__ import annotations

from typing import Any

from ..engine import hybrid_search
from ..engine import reinforce


async def recall_tool(arguments: dict) -> dict:
    query = arguments.get("query")
    if query is None or (isinstance(query, str) and not query.strip()):
        raise ValueError("Missing required argument: query")

    mode = arguments.get("search_mode", "hybrid")
    filters = dict(arguments.get("filters") or {})
    if "entity_type" in arguments and arguments["entity_type"]:
        filters.setdefault("entity_type", arguments["entity_type"])
    time_range = arguments.get("time_range")
    if time_range:
        filters.setdefault("time_range", time_range)
    limit = int(arguments.get("limit", 10))

    result: dict[str, Any] = await hybrid_search.search(
        query=query,
        mode=mode,
        filters=filters or None,
        limit=limit,
    )

    # Reinforce: record_access for every memory we returned.
    hit_ids = [r["memory_id"] for r in result.get("results", [])]
    if hit_ids:
        try:
            await reinforce.record_access(hit_ids)
        except Exception:
            # Reinforce is best-effort; failure must not affect recall.
            pass

    return result
```

Note: `entity_type` 是历史参数。在 hybrid_search 内 `apply_filters` 当前只识别 `review_status` / `origin_client` / `time_range`，需要补一段 entity_type 过滤。回到 `engine/hybrid_search.py` 的 `apply_filters` 函数，在 `origin_set` 段之后追加：

```python
    entity_type = user_filters.get("entity_type")
    entity_type_set: set[str] | None
    if entity_type is None:
        entity_type_set = None
    elif isinstance(entity_type, str):
        entity_type_set = {entity_type}
    else:
        entity_type_set = {str(t) for t in entity_type}
```

并在循环里加入：

```python
        if entity_type_set is not None:
            if (getattr(node, "entity_type", None) or "") not in entity_type_set:
                dropped += 1
                continue
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_recall_hybrid.py -v
```
Expected: PASS

- [ ] **Step 5: Run REST recall regression**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api.py -k "recall" -v
```
Expected: PASS（现有 `test_recall_search` 仍跑通 —— recall 返回结构兼容老断言 `body["data"]["total"] >= 1`）

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/tools/recall.py src/memory_mcp/engine/hybrid_search.py tests/test_recall_hybrid.py
git commit -m "feat(recall): switch to hybrid_search + relevance_breakdown + reinforce on hit"
```

### Task 12: forget — delegate to memory_update via review_status='archived'

**Files:**
- Modify: `src/memory_mcp/tools/forget.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_tools.py`:

```python
def test_forget_sets_review_status_archived(tools, test_env):
    async def run():
        remember, _, _, _, forget, _, _ = tools
        await remember.remember_tool({
            "content": "Temp",
            "entity_key": "fact:temp",
            "entity_type": "fact",
        })
        await forget.forget_tool({"entity_key": "fact:temp", "reason": "no longer relevant"})

        import memory_mcp.storage.vector as vmod
        import importlib
        importlib.reload(vmod)
        hist = await vmod.vector_store.get_history("fact:temp")
        node = hist[0]
        assert node.is_current is False
        assert node.review_status == "archived"
        assert node.archived_reason == "no longer relevant"
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_tools.py::test_forget_sets_review_status_archived -v
```
Expected: FAIL

- [ ] **Step 3: Update forget_tool**

Replace `src/memory_mcp/tools/forget.py`:

```python
from datetime import datetime, timezone

from ..storage.vector import vector_store
from ..storage.graph import graph_store


async def forget_tool(arguments: dict) -> dict:
    """Soft-archive the current memory for an entity_key.

    Equivalent to memory_update(review_status='archived'). The dedicated
    memory_update_tool (M2 task 13) also accepts arbitrary memory_id.
    """
    entity_key = arguments.get("entity_key")
    reason = arguments.get("reason", "User requested archive")

    if not entity_key:
        raise ValueError("Missing required argument: entity_key")

    history = await vector_store.get_history(entity_key)
    current_node = next((n for n in history if n.is_current), None)

    if not current_node:
        return {"status": "not_found", "message": f"No active memory found for {entity_key}"}

    now = datetime.now(timezone.utc)
    current_node.is_current = False
    current_node.valid_until = now
    current_node.archived_reason = reason
    current_node.archived_at = now
    current_node.review_status = "archived"

    await vector_store.update(current_node)
    await graph_store.clear_current_memory(entity_key)

    return {
        "status": "archived",
        "entity_key": entity_key,
        "previous_content": current_node.content,
        "archived_reason": reason,
    }
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_tools.py::test_forget_sets_review_status_archived tests/test_api.py -k "forget" -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/tools/forget.py tests/test_tools.py
git commit -m "feat(forget): set review_status='archived' for unified soft-delete semantics"
```

---

## Chunk 4: Memory CRUD by id + Merge

### Task 13: memory_get / memory_update / memory_delete

**Files:**
- Create: `src/memory_mcp/tools/memory_crud.py`
- Create: `tests/test_memory_crud.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_memory_crud.py`:

```python
import importlib

import anyio
import pytest


def _reload_crud():
    import memory_mcp.tools.memory_crud as m
    importlib.reload(m)
    return m


async def _seed(remember, entity_key: str, content: str, **extra) -> dict:
    """Helper used by tests that need a freshly-stored memory.

    The tests below either call this directly inside their ``async def run()``
    body or use ``remember.remember_tool({...})`` inline.
    """
    return await remember.remember_tool(
        {"content": content, "entity_key": entity_key, "entity_type": entity_key.split(":", 1)[0], **extra},
    )


def test_memory_get_returns_node(tools, test_env):
    async def run():
        remember, *_ = tools
        res = await remember.remember_tool({
            "content": "Cursor",
            "entity_key": "preference:editor",
            "entity_type": "preference",
        })
        mid = res["memory_id"]
        crud = _reload_crud()
        out = await crud.memory_get_tool({"memory_id": mid})
        assert out["memory_id"] == mid
        assert out["content"] == "Cursor"
        assert out["entity_key"] == "preference:editor"
        assert "review_status" in out
        assert "tags" in out
    anyio.run(run)


def test_memory_get_not_found(tools, test_env):
    async def run():
        crud = _reload_crud()
        out = await crud.memory_get_tool({"memory_id": "does-not-exist"})
        assert out["status"] == "not_found"
    anyio.run(run)


def test_memory_update_changes_metadata(tools, test_env):
    async def run():
        remember, *_ = tools
        res = await remember.remember_tool({
            "content": "Cursor",
            "entity_key": "preference:editor",
            "entity_type": "preference",
        })
        mid = res["memory_id"]
        crud = _reload_crud()
        out = await crud.memory_update_tool({
            "memory_id": mid,
            "title": "Editor preference",
            "tags": ["editor", "ide"],
            "review_status": "confirmed",
            "importance": 0.8,
        })
        assert out["status"] == "updated"
        assert out["changes"]["title"] == "Editor preference"

        # verify persisted
        again = await crud.memory_get_tool({"memory_id": mid})
        assert again["title"] == "Editor preference"
        assert again["tags"] == ["editor", "ide"]
        assert again["review_status"] == "confirmed"
    anyio.run(run)


def test_memory_update_rejects_unknown_fields(tools, test_env):
    async def run():
        remember, *_ = tools
        res = await remember.remember_tool({
            "content": "x",
            "entity_key": "fact:x",
            "entity_type": "fact",
        })
        mid = res["memory_id"]
        crud = _reload_crud()
        out = await crud.memory_update_tool({"memory_id": mid, "weird_field": 42})
        # weird_field is silently ignored; status should still be 'updated' or 'no_change'
        assert out["status"] in {"updated", "no_change"}
    anyio.run(run)


def test_memory_delete_soft_is_archive(tools, test_env):
    async def run():
        remember, *_ = tools
        res = await remember.remember_tool({
            "content": "x",
            "entity_key": "fact:x",
            "entity_type": "fact",
        })
        mid = res["memory_id"]
        crud = _reload_crud()
        out = await crud.memory_delete_tool({"memory_id": mid, "hard": False})
        assert out["status"] == "archived"

        check = await crud.memory_get_tool({"memory_id": mid})
        assert check["review_status"] == "archived"
        assert check["is_current"] is False
    anyio.run(run)


def test_memory_delete_hard_removes_row(tools, test_env):
    async def run():
        remember, *_ = tools
        res = await remember.remember_tool({
            "content": "x",
            "entity_key": "fact:gone",
            "entity_type": "fact",
        })
        mid = res["memory_id"]
        crud = _reload_crud()
        out = await crud.memory_delete_tool({"memory_id": mid, "hard": True})
        assert out["status"] == "deleted"

        check = await crud.memory_get_tool({"memory_id": mid})
        assert check["status"] == "not_found"
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_memory_crud.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement memory_crud**

> **M1 已建好 `VectorStore.delete(memory_id) -> bool`**（Task 12）调用 `InMemoryVectorBackend.delete` / `LanceVectorBackend.delete` 并触发 `MemoryRepository.hard_delete`。M2 不需要再 patch backend；直接消费 `vector_store.delete(memory_id)`。

Create `src/memory_mcp/tools/memory_crud.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..engine.models import ReviewStatus, SourceRef
from ..engine.tokenizer import tokenize
from ..storage.vector import vector_store
from ..storage.graph import graph_store


_ALLOWED_UPDATE_FIELDS = {
    "content",
    "title",
    "tags",
    "review_status",
    "importance",
    "confidence",
    "source_refs",
    "source_thread_id",
    "origin_client",
    "origin_session_id",
    "archived_reason",
}


def _coerce_value(field: str, value: Any) -> Any:
    """Coerce raw REST/MCP payloads into MemoryNode-friendly types.

    - ``review_status`` strings → ``ReviewStatus`` enum
    - ``source_refs`` lists of dict → ``[SourceRef(...)]``
    Anything else is passed through.
    """
    if field == "review_status" and not isinstance(value, ReviewStatus):
        return ReviewStatus(value)
    if field == "source_refs" and isinstance(value, list):
        coerced: list[SourceRef] = []
        for item in value:
            if isinstance(item, SourceRef):
                coerced.append(item)
            elif isinstance(item, dict) and item.get("thread_id"):
                coerced.append(SourceRef(**item))
        return coerced
    return value


def _serialize_node(node) -> dict[str, Any]:
    """Wire-format serializer used by REST + MCP responses.

    - ``review_status`` emits the enum **value** (string), never the enum object
    - ``source_refs`` emits ``[{thread_id, message_id}, ...]`` dicts so the
      Web UI / hooks can consume without Pydantic awareness
    """
    refs = getattr(node, "source_refs", []) or []
    refs_dump = [r.model_dump() if isinstance(r, SourceRef) else r for r in refs]
    review = getattr(node, "review_status", ReviewStatus.AUTO)
    review_str = review.value if isinstance(review, ReviewStatus) else str(review)
    return {
        "memory_id": node.id,
        "entity_key": node.entity_key,
        "entity_type": node.entity_type,
        "content": node.content,
        "title": getattr(node, "title", None),
        "tags": list(getattr(node, "tags", []) or []),
        "review_status": review_str,
        "confidence": getattr(node, "confidence", 1.0),
        "is_current": node.is_current,
        "parent_id": node.parent_id,
        "mutation_type": node.mutation_type.value,
        "mutation_reason": node.mutation_reason,
        "created_at": node.created_at.isoformat(),
        "valid_from": node.valid_from.isoformat(),
        "valid_until": node.valid_until.isoformat() if node.valid_until else None,
        "archived_at": node.archived_at.isoformat() if node.archived_at else None,
        "archived_reason": node.archived_reason,
        "conflict": node.conflict,
        "conflict_with_id": node.conflict_with_id,
        "origin_client": getattr(node, "origin_client", None),
        "origin_session_id": getattr(node, "origin_session_id", None),
        "source_thread_id": getattr(node, "source_thread_id", None),
        "source_refs": refs_dump,
        "access_count": getattr(node, "access_count", 0),
        "reinforce_count": getattr(node, "reinforce_count", 0),
        "last_accessed_at": node.last_accessed_at.isoformat() if getattr(node, "last_accessed_at", None) else None,
    }


async def memory_get_tool(arguments: dict) -> dict:
    mid = arguments.get("memory_id")
    if not mid:
        raise ValueError("Missing required argument: memory_id")
    node = await vector_store.get_by_id(mid)
    if node is None:
        return {"status": "not_found", "memory_id": mid}
    return _serialize_node(node)


async def memory_update_tool(arguments: dict) -> dict:
    mid = arguments.get("memory_id")
    if not mid:
        raise ValueError("Missing required argument: memory_id")
    node = await vector_store.get_by_id(mid)
    if node is None:
        return {"status": "not_found", "memory_id": mid}

    changes: dict[str, Any] = {}
    for field in _ALLOWED_UPDATE_FIELDS:
        if field in arguments and arguments[field] is not None:
            old = getattr(node, field, None)
            new = _coerce_value(field, arguments[field])
            if old != new:
                setattr(node, field, new)
                # keep FTS5 tokens in sync when text columns change
                if field == "content":
                    node.content_tokens = tokenize(new or "")
                elif field == "title":
                    node.title_tokens = tokenize(new or "") if new else None
                # Emit human-friendly value back to the caller (enum -> str).
                if field == "review_status":
                    changes[field] = new.value if isinstance(new, ReviewStatus) else new
                elif field == "source_refs":
                    changes[field] = [r.model_dump() if isinstance(r, SourceRef) else r for r in new]
                else:
                    changes[field] = new

    if not changes:
        return {"status": "no_change", "memory_id": mid}

    await vector_store.update(node)
    return {"status": "updated", "memory_id": mid, "changes": changes}


async def memory_delete_tool(arguments: dict) -> dict:
    mid = arguments.get("memory_id")
    hard = bool(arguments.get("hard", False))
    if not mid:
        raise ValueError("Missing required argument: memory_id")
    node = await vector_store.get_by_id(mid)
    if node is None:
        return {"status": "not_found", "memory_id": mid}

    if hard:
        deleted = await vector_store.delete(mid)
        if node.is_current:
            await graph_store.clear_current_memory(node.entity_key)
        return {"status": "deleted" if deleted else "not_found", "memory_id": mid, "hard": True}

    now = datetime.now(timezone.utc)
    node.is_current = False
    node.valid_until = now
    node.archived_at = now
    node.review_status = ReviewStatus.ARCHIVED
    node.archived_reason = arguments.get("reason", "Soft delete via memory_delete")
    await vector_store.update(node)
    await graph_store.clear_current_memory(node.entity_key)
    return {"status": "archived", "memory_id": mid, "hard": False}
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_memory_crud.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/tools/memory_crud.py src/memory_mcp/storage/vector.py tests/test_memory_crud.py
git commit -m "feat(tools): add memory_get/update/delete with soft+hard delete semantics"
```

### Task 14: memory_merge

**Files:**
- Modify: `src/memory_mcp/tools/memory_crud.py`
- Modify: `tests/test_memory_crud.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_memory_crud.py`:

```python
def test_memory_merge_combines_source_refs_and_archives_sources(tools, test_env):
    async def run():
        remember, *_ = tools
        a = await remember.remember_tool({
            "content": "Cursor a",
            "entity_key": "preference:editor",
            "entity_type": "preference",
            "source_refs": [{"thread_id": "t1", "message_id": "t1:000001"}],
        })
        b = await remember.remember_tool({
            "content": "Cursor b",
            "entity_key": "preference:editor-alt",
            "entity_type": "preference",
            "source_refs": [{"thread_id": "t2", "message_id": "t2:000002"}],
        })
        target = await remember.remember_tool({
            "content": "Cursor canonical",
            "entity_key": "preference:editor-canonical",
            "entity_type": "preference",
            "source_refs": [{"thread_id": "t3", "message_id": "t3:000003"}],
        })

        crud = _reload_crud()
        out = await crud.memory_merge_tool({
            "source_ids": [a["memory_id"], b["memory_id"]],
            "target_id": target["memory_id"],
        })
        assert out["status"] == "merged"
        assert out["target_id"] == target["memory_id"]
        assert set(out["source_ids"]) == {a["memory_id"], b["memory_id"]}

        # target inherits all source_refs (deduped, preserving order)
        tgt = await crud.memory_get_tool({"memory_id": target["memory_id"]})
        ref_msg_ids = {r["message_id"] for r in tgt["source_refs"]}
        assert ref_msg_ids == {"t1:000001", "t2:000002", "t3:000003"}

        # sources soft-archived with reason
        for sid in (a["memory_id"], b["memory_id"]):
            s = await crud.memory_get_tool({"memory_id": sid})
            assert s["review_status"] == "archived"
            assert f"merged_into:{target['memory_id']}" in s["archived_reason"]
            assert s["is_current"] is False
    anyio.run(run)


def test_memory_merge_target_not_in_sources(tools, test_env):
    async def run():
        remember, *_ = tools
        a = await remember.remember_tool({
            "content": "x", "entity_key": "fact:a", "entity_type": "fact",
        })
        crud = _reload_crud()
        with pytest.raises(ValueError):
            await crud.memory_merge_tool({"source_ids": [a["memory_id"]],
                                          "target_id": a["memory_id"]})
    anyio.run(run)


def test_memory_merge_unknown_target(tools, test_env):
    async def run():
        remember, *_ = tools
        a = await remember.remember_tool({
            "content": "x", "entity_key": "fact:a", "entity_type": "fact",
        })
        crud = _reload_crud()
        out = await crud.memory_merge_tool({"source_ids": [a["memory_id"]],
                                            "target_id": "does-not-exist"})
        assert out["status"] == "target_not_found"
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_memory_crud.py -k "merge" -v
```
Expected: FAIL

- [ ] **Step 3: Implement memory_merge**

Append to `src/memory_mcp/tools/memory_crud.py`:

```python
def _merge_source_refs(existing: list, incoming: list) -> list[SourceRef]:
    """Union by (thread_id, message_id), preserving the existing order first.

    Accepts both ``SourceRef`` instances and ``{thread_id, message_id}`` dicts.
    Returns a list of ``SourceRef`` (so caller can assign back to MemoryNode).
    """
    seen: set[tuple] = set()
    out: list[SourceRef] = []
    for ref in (existing or []) + (incoming or []):
        if isinstance(ref, SourceRef):
            key = (ref.thread_id, ref.message_id)
            obj = ref
        elif isinstance(ref, dict) and ref.get("thread_id"):
            key = (ref["thread_id"], ref.get("message_id"))
            obj = SourceRef(**ref)
        else:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(obj)
    return out


async def memory_merge_tool(arguments: dict) -> dict:
    source_ids = list(arguments.get("source_ids") or [])
    target_id = arguments.get("target_id")
    if not source_ids or not target_id:
        raise ValueError("Missing required arguments: source_ids, target_id")
    if target_id in source_ids:
        raise ValueError("target_id must not appear in source_ids")

    target = await vector_store.get_by_id(target_id)
    if target is None:
        return {"status": "target_not_found", "target_id": target_id}

    archived: list[str] = []
    skipped: list[str] = []
    merged_refs: list[SourceRef] = list(getattr(target, "source_refs", []) or [])

    now = datetime.now(timezone.utc)
    for sid in source_ids:
        source = await vector_store.get_by_id(sid)
        if source is None:
            skipped.append(sid)
            continue
        merged_refs = _merge_source_refs(merged_refs, getattr(source, "source_refs", []) or [])
        source.is_current = False
        source.valid_until = now
        source.archived_at = now
        source.review_status = ReviewStatus.ARCHIVED
        existing_reason = source.archived_reason or ""
        suffix = f"merged_into:{target_id}"
        source.archived_reason = (existing_reason + " " if existing_reason else "") + suffix
        await vector_store.update(source)
        await graph_store.clear_current_memory(source.entity_key)
        archived.append(sid)

    target.source_refs = merged_refs
    await vector_store.update(target)

    # Emit dicts on the wire (consistent with _serialize_node).
    return {
        "status": "merged",
        "target_id": target_id,
        "source_ids": archived,
        "skipped": skipped,
        "source_refs": [r.model_dump() for r in merged_refs],
    }
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_memory_crud.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/tools/memory_crud.py tests/test_memory_crud.py
git commit -m "feat(tools): add memory_merge with source_refs union + archived_reason tagging"
```

---

## Chunk 5: hybrid_search tool + Thread stubs

### Task 15: hybrid_search MCP tool (low-level recall exposure)

**Files:**
- Create: `src/memory_mcp/tools/hybrid_search.py`
- Modify: `tests/test_recall_hybrid.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_recall_hybrid.py`:

```python
def test_hybrid_search_tool_returns_full_breakdown(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "Cursor",
            "entity_key": "preference:editor",
            "entity_type": "preference",
        })
        import memory_mcp.tools.hybrid_search as hs_tool
        importlib.reload(hs_tool)
        out = await hs_tool.hybrid_search_tool({
            "query": "Cursor",
            "mode": "hybrid",
            "limit": 5,
        })
        assert "results" in out
        assert "search_metadata" in out
        assert out["search_mode"] == "hybrid"
    anyio.run(run)


def test_hybrid_search_tool_validates_mode(tools, test_env):
    async def run():
        import memory_mcp.tools.hybrid_search as hs_tool
        importlib.reload(hs_tool)
        with pytest.raises(ValueError):
            await hs_tool.hybrid_search_tool({"query": "x", "mode": "not_a_mode"})
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_recall_hybrid.py -k "hybrid_search_tool" -v
```
Expected: FAIL

- [ ] **Step 3: Implement hybrid_search_tool**

Create `src/memory_mcp/tools/hybrid_search.py`:

```python
from __future__ import annotations

from typing import Any

from ..engine import hybrid_search


async def hybrid_search_tool(arguments: dict) -> dict:
    query = arguments.get("query")
    if not query:
        raise ValueError("Missing required argument: query")
    mode = arguments.get("mode", "hybrid")
    filters = arguments.get("filters") or None
    limit = int(arguments.get("limit", 10))
    result: dict[str, Any] = await hybrid_search.search(
        query=query, mode=mode, filters=filters, limit=limit,
    )
    return result
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_recall_hybrid.py -k "hybrid_search_tool" -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/tools/hybrid_search.py tests/test_recall_hybrid.py
git commit -m "feat(tools): add hybrid_search MCP tool exposing recall internals"
```

### Task 16: Thread tool compatibility shims (M2 surface, replaced in M3)

> 命名说明：这里**不是 placeholder 也不是 TODO**——这是 explicit `compatibility shim`，把 MCP/REST 表面提前对齐到 spec §5.1/§5.2，让 CLI / hooks / Web UI 可以在 M2 周期就开始 wire；M3 Task 8 用真实实现替换 `tools/thread_*.py`（注意是替换 `thread_search.py` / `thread_get.py` / `thread_import.py` / `thread_list_providers.py`，**不是** `thread_stub.py`），M3 Task 22-extension 一并把 `server.py` 的 dispatch 从 shim 切到真实模块。

**Files:**
- Create: `src/memory_mcp/tools/thread_stub.py`（**M3 删除**，并改名 import 到 4 个真实模块）
- Create: `tests/test_thread_stubs.py`（**M3 删除**）

- [ ] **Step 1: Write failing tests**

Create `tests/test_thread_stubs.py`:

```python
import importlib

import anyio
import pytest


def _reload_stub():
    import memory_mcp.tools.thread_stub as t
    importlib.reload(t)
    return t


def test_thread_search_returns_empty_with_phase_marker(tools, test_env):
    async def run():
        s = _reload_stub()
        out = await s.thread_search_tool({"query": "foo"})
        assert out["results"] == []
        assert out["phase"] == "M3"
    anyio.run(run)


def test_thread_get_returns_not_implemented(tools, test_env):
    async def run():
        s = _reload_stub()
        out = await s.thread_get_tool({"thread_id": "any"})
        assert out["status"] == "not_implemented"
        assert out["phase"] == "M3"
    anyio.run(run)


def test_thread_import_returns_not_implemented(tools, test_env):
    async def run():
        s = _reload_stub()
        out = await s.thread_import_tool({"provider": "manual", "path": "/tmp/x"})
        assert out["status"] == "not_implemented"
        assert out["phase"] == "M3"
    anyio.run(run)


def test_thread_list_providers_returns_known_set(tools, test_env):
    async def run():
        s = _reload_stub()
        out = await s.thread_list_providers_tool({})
        assert "providers" in out
        assert "claude-code" in out["providers"]
        assert out["phase"] == "M3"
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_thread_stubs.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement thread stubs**

Create `src/memory_mcp/tools/thread_stub.py`:

```python
"""M2 placeholder tools for Threads.

The Threads data model and adapters land in M3. These stubs exist so that
the MCP tool list and REST surface match the documented Phase 1 API on day
one, and so that downstream agents (CLI / hooks / Web UI) can wire against
stable contracts.
"""
from __future__ import annotations

_PHASE = "M3"
_KNOWN_PROVIDERS = ["claude-code", "codex", "chatwise", "manual"]


async def thread_search_tool(arguments: dict) -> dict:
    return {
        "results": [],
        "total": 0,
        "phase": _PHASE,
        "message": "Thread search lands in M3 (Threads + Adapters).",
    }


async def thread_get_tool(arguments: dict) -> dict:
    thread_id = arguments.get("thread_id")
    if not thread_id:
        raise ValueError("Missing required argument: thread_id")
    return {
        "status": "not_implemented",
        "thread_id": thread_id,
        "phase": _PHASE,
        "message": "Thread retrieval lands in M3.",
    }


async def thread_import_tool(arguments: dict) -> dict:
    provider = arguments.get("provider")
    if not provider:
        raise ValueError("Missing required argument: provider")
    return {
        "status": "not_implemented",
        "provider": provider,
        "phase": _PHASE,
        "message": "Thread import lands in M3 (per-provider adapters).",
    }


async def thread_list_providers_tool(arguments: dict) -> dict:
    return {
        "providers": list(_KNOWN_PROVIDERS),
        "phase": _PHASE,
        "message": "Providers list reflects M3 target adapters.",
    }
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_thread_stubs.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/tools/thread_stub.py tests/test_thread_stubs.py
git commit -m "feat(tools): add M2 Thread tool stubs (real impl in M3)"
```

---

## Chunk 6: REST API extension

### Task 17: REST extended memories — list/filter/pagination + by-id CRUD + bulk

**Files:**
- Modify: `src/memory_mcp/api/routes.py`
- Create: `tests/test_api_extended.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api_extended.py`:

```python
import importlib

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.requests import Request

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def app(test_env):
    import memory_mcp.tools.remember as _rem
    import memory_mcp.tools.recall as _rec
    import memory_mcp.tools.recall_all as _reca
    import memory_mcp.tools.trace as _tr
    import memory_mcp.tools.forget as _fo
    import memory_mcp.tools.relate as _rel
    import memory_mcp.tools.unrelate as _unrel
    import memory_mcp.tools.graph_query as _gq
    import memory_mcp.tools.memory_crud as _crud
    import memory_mcp.tools.hybrid_search as _hs_tool
    import memory_mcp.tools.thread_stub as _ts
    import memory_mcp.engine.hybrid_search as _hs
    for m in (_rem, _rec, _reca, _tr, _fo, _rel, _unrel, _gq, _crud, _hs_tool, _ts, _hs):
        importlib.reload(m)
    import memory_mcp.api.routes as routes_mod
    importlib.reload(routes_mod)

    import memory_mcp.transport.auth as auth_mod
    importlib.reload(auth_mod)
    import memory_mcp.transport.cors as cors_mod
    importlib.reload(cors_mod)

    async def health(request: Request):
        return JSONResponse({"status": "healthy"})

    return Starlette(
        routes=[Route("/health", endpoint=health, methods=["GET"]), *routes_mod.routes],
        middleware=[Middleware(cors_mod.CorsMiddleware), Middleware(auth_mod.AuthMiddleware)],
    )


@pytest.fixture()
def client(app):
    from starlette.testclient import TestClient
    return TestClient(app, raise_server_exceptions=True)


def _seed(client, n=3, prefix="fact:item"):
    for i in range(n):
        client.post("/api/v1/memories",
                    json={"content": f"c{i}", "entity_key": f"{prefix}{i}", "entity_type": "fact"},
                    headers=AUTH)


def test_memories_list_pagination(client):
    _seed(client, n=5)
    resp = client.get("/api/v1/memories?page=1&size=2", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["size"] == 2

    resp2 = client.get("/api/v1/memories?page=3&size=2", headers=AUTH)
    body2 = resp2.json()["data"]
    assert len(body2["items"]) == 1


def test_memories_list_filter_review_status(client):
    _seed(client, n=2)
    resp = client.get("/api/v1/memories?review_status=auto", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 2


def test_memories_list_filter_origin_client(client):
    client.post("/api/v1/memories", json={
        "content": "x", "entity_key": "fact:o1", "entity_type": "fact", "origin_client": "claude-code",
    }, headers=AUTH)
    client.post("/api/v1/memories", json={
        "content": "y", "entity_key": "fact:o2", "entity_type": "fact", "origin_client": "codex",
    }, headers=AUTH)
    resp = client.get("/api/v1/memories?origin_client=claude-code", headers=AUTH)
    keys = [r["entity_key"] for r in resp.json()["data"]["items"]]
    assert "fact:o1" in keys
    assert "fact:o2" not in keys


def test_memories_get_by_id(client):
    r = client.post("/api/v1/memories",
                    json={"content": "x", "entity_key": "fact:x", "entity_type": "fact"},
                    headers=AUTH)
    mid = r.json()["data"]["memory_id"]
    resp = client.get(f"/api/v1/memories/{mid}", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["memory_id"] == mid


def test_memories_patch_by_id(client):
    r = client.post("/api/v1/memories",
                    json={"content": "x", "entity_key": "fact:x", "entity_type": "fact"},
                    headers=AUTH)
    mid = r.json()["data"]["memory_id"]
    resp = client.patch(f"/api/v1/memories/{mid}",
                        json={"title": "Title", "tags": ["a"]}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "updated"


def test_memories_delete_by_id_soft(client):
    r = client.post("/api/v1/memories",
                    json={"content": "x", "entity_key": "fact:soft", "entity_type": "fact"},
                    headers=AUTH)
    mid = r.json()["data"]["memory_id"]
    resp = client.delete(f"/api/v1/memories/{mid}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "archived"


def test_memories_delete_by_id_hard(client):
    r = client.post("/api/v1/memories",
                    json={"content": "x", "entity_key": "fact:hard", "entity_type": "fact"},
                    headers=AUTH)
    mid = r.json()["data"]["memory_id"]
    resp = client.delete(f"/api/v1/memories/{mid}?hard=true", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "deleted"


def test_memories_evolution(client):
    """``GET /api/v1/memories/{id}/evolution`` returns the entity history.

    Web UI consumes this in MemoryDetailPage (M5 Task 17). The endpoint
    resolves entity_key from the memory_id and returns the full version list.
    """
    a = client.post("/api/v1/memories",
                    json={"content": "v1", "entity_key": "fact:evo", "entity_type": "fact"},
                    headers=AUTH).json()["data"]["memory_id"]
    client.post("/api/v1/memories",
                json={"content": "v2", "entity_key": "fact:evo", "entity_type": "fact"},
                headers=AUTH)
    resp = client.get(f"/api/v1/memories/{a}/evolution", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    contents = [n["content"] for n in body["items"]]
    assert contents == ["v1", "v2"]


def test_memories_bulk_delete(client):
    ids = []
    for i in range(3):
        r = client.post("/api/v1/memories",
                        json={"content": f"x{i}", "entity_key": f"fact:b{i}", "entity_type": "fact"},
                        headers=AUTH)
        ids.append(r.json()["data"]["memory_id"])
    resp = client.post("/api/v1/memories/bulk-delete", json={"ids": ids}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["archived"] == 3


def test_memories_bulk_merge(client):
    a = client.post("/api/v1/memories",
                    json={"content": "a", "entity_key": "fact:src1", "entity_type": "fact"},
                    headers=AUTH).json()["data"]["memory_id"]
    b = client.post("/api/v1/memories",
                    json={"content": "b", "entity_key": "fact:src2", "entity_type": "fact"},
                    headers=AUTH).json()["data"]["memory_id"]
    t = client.post("/api/v1/memories",
                    json={"content": "t", "entity_key": "fact:tgt", "entity_type": "fact"},
                    headers=AUTH).json()["data"]["memory_id"]
    resp = client.post("/api/v1/memories/bulk-merge",
                       json={"source_ids": [a, b], "target_id": t}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "merged"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api_extended.py -v
```
Expected: FAIL（路由不存在）

- [ ] **Step 3: Extend routes.py with by-id CRUD + bulk + pagination/filter**

Edit `src/memory_mcp/api/routes.py` — keep existing handlers, add new ones, and rebuild the `routes` list at the bottom. Add at the top:

```python
from typing import Any
```

Add these new handler functions (place them before the final `routes = [...]` list):

```python
# ---------------- Extended memories (list with pagination/filter) ----------------
async def handle_memories_list(request: Request) -> JSONResponse:
    from ..storage.vector import vector_store
    params = request.query_params

    try:
        page = max(1, int(params.get("page", "1")))
        size = max(1, min(200, int(params.get("size", "50"))))
    except ValueError:
        return err("page/size must be integers")

    entity_type = params.get("entity_type") or None
    review_status = params.getlist("review_status") if hasattr(params, "getlist") else None
    if not review_status:
        rs = params.get("review_status")
        review_status = [rs] if rs else None
    origin_client = params.get("origin_client")
    q = params.get("q")

    # Load broadly, then filter in-memory. The SQLite primary store (M1) can
    # later swap this out for a parameterised SQL WHERE clause.
    candidates = await vector_store.list_current(entity_type=entity_type, limit=10_000)

    if review_status:
        wanted = set(review_status)
        candidates = [n for n in candidates if (getattr(n, "review_status", "auto") or "auto") in wanted]
    if origin_client:
        candidates = [n for n in candidates if (getattr(n, "origin_client", None) or "") == origin_client]
    if q:
        ql = q.lower()
        candidates = [n for n in candidates
                      if ql in (n.content or "").lower()
                      or ql in (getattr(n, "title", "") or "").lower()]

    total = len(candidates)
    start = (page - 1) * size
    page_items = candidates[start:start + size]
    items = []
    for n in page_items:
        review = getattr(n, "review_status", None)
        review_str = review.value if hasattr(review, "value") else (review or "auto")
        items.append({
            "memory_id": n.id,
            "entity_key": n.entity_key,
            "entity_type": n.entity_type,
            "content": n.content,
            "title": getattr(n, "title", None),
            "tags": list(getattr(n, "tags", []) or []),
            "review_status": review_str,
            "origin_client": getattr(n, "origin_client", None),
            "source_thread_id": getattr(n, "source_thread_id", None),
            "created_at": n.created_at.isoformat(),
        })
    # Paginated DTO contract (Decision D13): `items` (not `results`).
    return ok({"items": items, "total": total, "page": page, "size": size})


# ---------------- by-id CRUD ----------------
async def handle_memory_get_by_id(request: Request) -> JSONResponse:
    from ..tools import memory_crud
    mid = request.path_params["memory_id"]
    try:
        result = await memory_crud.memory_get_tool({"memory_id": mid})
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


async def handle_memory_patch_by_id(request: Request) -> JSONResponse:
    from ..tools import memory_crud
    mid = request.path_params["memory_id"]
    try:
        body = await request.json()
    except Exception:
        return err("Invalid JSON body")
    body["memory_id"] = mid
    try:
        result = await memory_crud.memory_update_tool(body)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


async def handle_memory_delete_by_id(request: Request) -> JSONResponse:
    from ..tools import memory_crud
    mid = request.path_params["memory_id"]
    hard = request.query_params.get("hard", "false").lower() == "true"
    try:
        result = await memory_crud.memory_delete_tool({"memory_id": mid, "hard": hard})
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


async def handle_memories_bulk_delete(request: Request) -> JSONResponse:
    from ..tools import memory_crud
    try:
        body = await request.json()
    except Exception:
        return err("Invalid JSON body")
    ids = body.get("ids") or []
    hard = bool(body.get("hard", False))
    if not isinstance(ids, list) or not ids:
        return err("ids must be a non-empty list")
    archived = 0
    deleted = 0
    skipped: list[str] = []
    for mid in ids:
        try:
            out = await memory_crud.memory_delete_tool({"memory_id": mid, "hard": hard})
        except Exception:
            skipped.append(mid)
            continue
        if out.get("status") == "deleted":
            deleted += 1
        elif out.get("status") == "archived":
            archived += 1
        else:
            skipped.append(mid)
    return ok({"archived": archived, "deleted": deleted, "skipped": skipped, "total": len(ids)})


async def handle_memories_bulk_merge(request: Request) -> JSONResponse:
    from ..tools import memory_crud
    try:
        body = await request.json()
    except Exception:
        return err("Invalid JSON body")
    try:
        result = await memory_crud.memory_merge_tool(body)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)
```

Then update the `routes = [...]` list. **Ordering matters**: more-specific paths must precede generic ones. The new memory-id paths live directly under `/api/v1/memories/{memory_id}` per spec §5.2 / Decision D13. Legacy entity-key forget moves to `/api/v1/entities/{entity_key:path}` (entity endpoints are also new in M2 Task 19-bis); trace stays under `/api/v1/memories/{entity_key:path}/trace` because the `/trace` suffix prevents ambiguity with `{memory_id}`.

Replace the existing list with:

```python
routes = [
    Route("/api/v1/memories/extract", endpoint=handle_extract, methods=["POST"]),
    Route("/api/v1/memories/search", endpoint=handle_recall, methods=["GET"]),
    Route("/api/v1/memories/bulk-delete", endpoint=handle_memories_bulk_delete, methods=["POST"]),
    Route("/api/v1/memories/bulk-merge", endpoint=handle_memories_bulk_merge, methods=["POST"]),
    Route("/api/v1/memories", endpoint=handle_remember, methods=["POST"]),
    Route("/api/v1/memories", endpoint=handle_memories_list, methods=["GET"]),
    # entity_key paths first — they have a fixed `/trace` suffix that disambiguates.
    Route("/api/v1/memories/{entity_key:path}/trace", endpoint=handle_trace, methods=["GET"]),
    # Memory-id endpoints (spec §5.2 / D13). Evolution is a sibling under {memory_id}.
    Route("/api/v1/memories/{memory_id}/evolution", endpoint=handle_memory_evolution, methods=["GET"]),
    Route("/api/v1/memories/{memory_id}", endpoint=handle_memory_get_by_id, methods=["GET"]),
    Route("/api/v1/memories/{memory_id}", endpoint=handle_memory_patch_by_id, methods=["PATCH"]),
    Route("/api/v1/memories/{memory_id}", endpoint=handle_memory_delete_by_id, methods=["DELETE"]),
    # Legacy entity-key forget moves under /entities/{key} (Task 19 entities endpoints).
    Route("/api/v1/entities/{entity_key:path}", endpoint=handle_forget, methods=["DELETE"]),
    Route("/api/v1/relations", endpoint=handle_relate, methods=["POST"]),
    Route("/api/v1/relations/{relation_id}", endpoint=handle_unrelate, methods=["DELETE"]),
    Route("/api/v1/graph/{entity_key:path}", endpoint=handle_graph_query, methods=["GET"]),
    Route("/api/v1/wm", endpoint=handle_working_memory, methods=["GET"]),
]
```

**`handle_memory_evolution` 实现**（追加到 routes.py，在 by-id handlers 旁边）：

```python
async def handle_memory_evolution(request: Request) -> JSONResponse:
    """Return the evolution chain for a memory_id (Web UI MemoryDetail tab)."""
    from ..storage.vector import vector_store
    from ..tools.memory_crud import _serialize_node
    mid = request.path_params["memory_id"]
    node = await vector_store.get_by_id(mid)
    if node is None:
        return err("memory not found", 404)
    history = await vector_store.get_history(node.entity_key)
    items = [_serialize_node(n) for n in history]
    return ok({"items": items, "total": len(items)})
```

**CLI 影响**：旧的 `mem forget <entity_key>` 通过 `MemoryClient.forget` 命中 `/api/v1/memories/{entity_key}`；本任务把它改为 `/api/v1/entities/{entity_key}`。在 M2 Task 17 commit 同时改 `cli/src/memory_mcp_cli/client.py` 中 forget 函数 URL（一行替换），并补 cli 端 unit test 回归。

Note: the previous `handle_recall_all` registered as `GET /api/v1/memories` is replaced by `handle_memories_list`, which keeps the same shape but adds pagination and filters; the paginated envelope changes from `results` → `items` (Decision D13). Legacy callers passing only `entity_type` & `limit` still work — see Task 18 for back-compat.

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api_extended.py -v
```
Expected: PASS

- [ ] **Step 5: Run REST regression**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api.py -v
```
Expected: All PASS（`test_recall_all_*` 在新 handler 下，`total` 字段仍存在，但响应包了 `page`/`size`，旧断言只查 `total` 仍兼容）

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/api/routes.py tests/test_api_extended.py
git commit -m "feat(api): memories list pagination/filter + by-id CRUD + bulk delete/merge"
```

### Task 18: REST back-compat for `GET /api/v1/memories?limit=`

**Files:**
- Modify: `src/memory_mcp/api/routes.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add test that the legacy `limit` param maps to `size`**

Append to `tests/test_api.py`:

```python
def test_recall_all_legacy_limit_param_still_works(client):
    for i in range(3):
        client.post("/api/v1/memories",
                    json={"content": f"v{i}", "entity_key": f"fact:l{i}", "entity_type": "fact"},
                    headers=AUTH)
    resp = client.get("/api/v1/memories?limit=2", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    # `limit` → `size`; envelope is `items` (D13).
    assert len(body["items"]) == 2
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api.py::test_recall_all_legacy_limit_param_still_works -v
```
Expected: FAIL (likely returns 50 results)

- [ ] **Step 3: Add limit→size compat in handle_memories_list**

Edit `src/memory_mcp/api/routes.py` — in `handle_memories_list`, replace the page/size parsing block with:

```python
    try:
        page = max(1, int(params.get("page", "1")))
        legacy_limit = params.get("limit")
        size_raw = params.get("size") or legacy_limit or "50"
        size = max(1, min(200, int(size_raw)))
    except ValueError:
        return err("page/size/limit must be integers")
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/api/routes.py tests/test_api.py
git commit -m "fix(api): keep legacy ?limit= param working on memories list"
```

### Task 18.5: REST entities endpoints (spec §5.2)

> Codex 评审标记 §5.2 缺 `GET /api/v1/entities` 与 `GET /api/v1/entities/{key}/graph`。本 task 在 Task 19（subgraph）之前一次性补齐这两条路径，让 spec §5.2 entity 部分全覆盖。

**Files:**
- Modify: `src/memory_mcp/api/routes.py`
- Modify: `tests/test_api_extended.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_api_extended.py`:

```python
def test_entities_list_returns_distinct_entities(client):
    client.post("/api/v1/memories", json={
        "content": "Alice", "entity_key": "person:alice", "entity_type": "person",
    }, headers=AUTH)
    client.post("/api/v1/memories", json={
        "content": "Bob", "entity_key": "person:bob", "entity_type": "person",
    }, headers=AUTH)
    resp = client.get("/api/v1/entities", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    keys = {e["entity_key"] for e in body["items"]}
    assert {"person:alice", "person:bob"}.issubset(keys)


def test_entities_list_filter_by_type(client):
    client.post("/api/v1/memories", json={
        "content": "X", "entity_key": "project:x", "entity_type": "project",
    }, headers=AUTH)
    client.post("/api/v1/memories", json={
        "content": "Alice", "entity_key": "person:alice", "entity_type": "person",
    }, headers=AUTH)
    resp = client.get("/api/v1/entities?entity_type=project", headers=AUTH)
    keys = {e["entity_key"] for e in resp.json()["data"]["items"]}
    assert "project:x" in keys
    assert "person:alice" not in keys


def test_entity_graph_returns_nodes_and_edges(client):
    client.post("/api/v1/memories", json={
        "content": "Alice", "entity_key": "person:alice", "entity_type": "person",
    }, headers=AUTH)
    client.post("/api/v1/memories", json={
        "content": "X", "entity_key": "project:x", "entity_type": "project",
    }, headers=AUTH)
    client.post("/api/v1/relations", json={
        "from_entity_key": "person:alice", "to_entity_key": "project:x", "relation_type": "OWNS",
    }, headers=AUTH)
    resp = client.get("/api/v1/entities/person:alice/graph?depth=1", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert "nodes" in body
    assert "edges" in body
    node_ids = {n["id"] for n in body["nodes"]}
    assert "person:alice" in node_ids
    assert "project:x" in node_ids


def test_entity_graph_unknown_returns_empty(client):
    resp = client.get("/api/v1/entities/person:never/graph", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["nodes"] == [{"id": "person:never", "type": "person", "label": "never"}]
    assert body["edges"] == []
```

- [ ] **Step 2: Implement handlers**

Append to `src/memory_mcp/api/routes.py`:

```python
async def handle_entities_list(request: Request) -> JSONResponse:
    """GET /api/v1/entities — listing for Web UI graph picker."""
    from ..storage.graph import graph_store
    params = request.query_params
    entity_type = params.get("entity_type")
    try:
        page = max(1, int(params.get("page", "1")))
        size = max(1, min(200, int(params.get("size", "100"))))
    except ValueError:
        return err("page/size must be integers")

    entities = await graph_store.list_entities()
    if entity_type:
        entities = [e for e in entities if e.get("entity_type") == entity_type]
    total = len(entities)
    start = (page - 1) * size
    items = entities[start:start + size]
    return ok({"items": items, "total": total, "page": page, "size": size})


async def handle_entity_graph(request: Request) -> JSONResponse:
    """GET /api/v1/entities/{key}/graph — entity-rooted subgraph for Web UI."""
    from ..storage.graph import graph_store
    entity_key = request.path_params["entity_key"]
    try:
        depth = max(1, int(request.query_params.get("depth", "1")))
    except ValueError:
        return err("depth must be an integer")
    relation_types_raw = request.query_params.get("relation_types")
    relation_types = (
        [t.strip() for t in relation_types_raw.split(",") if t.strip()]
        if relation_types_raw else None
    )

    try:
        relations = await graph_store.get_relations(entity_key, relation_types=relation_types, depth=depth)
    except Exception as e:
        return err(str(e), 500)

    node_set: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def _add_node(key: str) -> None:
        if key in node_set:
            return
        kind = key.split(":", 1)[0] if ":" in key else "unknown"
        node_set[key] = {"id": key, "type": kind, "label": key.split(":", 1)[-1] if ":" in key else key}

    _add_node(entity_key)
    for r in relations:
        src = r.get("from_entity_key")
        dst = r.get("to_entity_key")
        if not src or not dst:
            continue
        _add_node(src)
        _add_node(dst)
        edges.append({
            "id": r.get("id"),
            "source": src,
            "target": dst,
            "label": r.get("relation_type"),
            "properties": r.get("properties") or {},
        })

    return ok({"nodes": list(node_set.values()), "edges": edges, "depth": depth})
```

Add to `routes = [...]` (place before the legacy `/api/v1/entities/{entity_key:path}` DELETE route so the `/graph` suffix wins):

```python
    Route("/api/v1/entities", endpoint=handle_entities_list, methods=["GET"]),
    Route("/api/v1/entities/{entity_key:path}/graph", endpoint=handle_entity_graph, methods=["GET"]),
```

- [ ] **Step 3: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api_extended.py -k "entities_ or entity_graph" -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/memory_mcp/api/routes.py tests/test_api_extended.py
git commit -m "feat(api): add /entities list and /entities/{key}/graph endpoints (spec §5.2)"
```

### Task 19: REST graph subgraph (react-flow friendly)

**Files:**
- Modify: `src/memory_mcp/api/routes.py`
- Modify: `tests/test_api_extended.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_api_extended.py`:

```python
def test_graph_subgraph_returns_nodes_and_edges(client):
    client.post("/api/v1/memories", json={
        "content": "Alice", "entity_key": "person:alice", "entity_type": "person",
    }, headers=AUTH)
    client.post("/api/v1/memories", json={
        "content": "X", "entity_key": "project:x", "entity_type": "project",
    }, headers=AUTH)
    client.post("/api/v1/relations", json={
        "from_entity_key": "person:alice", "to_entity_key": "project:x", "relation_type": "OWNS",
    }, headers=AUTH)

    resp = client.get("/api/v1/graph/subgraph?entity_key=person:alice&depth=1", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert "nodes" in body
    assert "edges" in body
    node_ids = {n["id"] for n in body["nodes"]}
    assert "person:alice" in node_ids
    assert "project:x" in node_ids
    edge_keys = {(e["source"], e["target"], e["label"]) for e in body["edges"]}
    assert ("person:alice", "project:x", "OWNS") in edge_keys


def test_graph_subgraph_missing_entity_key_returns_error(client):
    resp = client.get("/api/v1/graph/subgraph", headers=AUTH)
    assert resp.status_code == 400
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api_extended.py -k "subgraph" -v
```
Expected: FAIL

- [ ] **Step 3: Implement subgraph handler**

Append to `src/memory_mcp/api/routes.py`:

```python
async def handle_graph_subgraph(request: Request) -> JSONResponse:
    from ..storage.graph import graph_store
    entity_key = request.query_params.get("entity_key")
    if not entity_key:
        return err("Missing required query param: entity_key")
    try:
        depth = int(request.query_params.get("depth", "1"))
    except ValueError:
        return err("depth must be an integer")
    if depth < 1:
        depth = 1

    try:
        relations = await graph_store.get_relations(entity_key, relation_types=None, depth=depth)
    except Exception as e:
        return err(str(e), 500)

    node_set: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def _add_node(key: str) -> None:
        if key in node_set:
            return
        kind = key.split(":", 1)[0] if ":" in key else "unknown"
        node_set[key] = {"id": key, "type": kind, "label": key.split(":", 1)[-1] if ":" in key else key}

    _add_node(entity_key)
    for r in relations:
        src = r.get("from_entity_key")
        dst = r.get("to_entity_key")
        if not src or not dst:
            continue
        _add_node(src)
        _add_node(dst)
        edges.append({
            "id": r.get("id"),
            "source": src,
            "target": dst,
            "label": r.get("relation_type"),
            "properties": r.get("properties") or {},
        })

    return ok({"nodes": list(node_set.values()), "edges": edges, "depth": depth})
```

Add route (place after `Route("/api/v1/graph/{entity_key:path}", ...)`):

```python
    Route("/api/v1/graph/subgraph", endpoint=handle_graph_subgraph, methods=["GET"]),
```

**Important**: `/api/v1/graph/subgraph` must register **before** `/api/v1/graph/{entity_key:path}` — move it above it in the `routes` list.

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api_extended.py -k "subgraph" -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/api/routes.py tests/test_api_extended.py
git commit -m "feat(api): add /graph/subgraph with react-flow friendly nodes/edges shape"
```

### Task 20: REST search (POST /api/v1/search) — hybrid_search exposure

**Files:**
- Modify: `src/memory_mcp/api/routes.py`
- Modify: `tests/test_api_extended.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_api_extended.py`:

```python
def test_post_search_hybrid(client):
    client.post("/api/v1/memories", json={
        "content": "Cursor", "entity_key": "preference:editor", "entity_type": "preference",
    }, headers=AUTH)
    resp = client.post("/api/v1/search", json={
        "query": "Cursor", "mode": "hybrid", "limit": 5,
    }, headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["search_mode"] == "hybrid"
    assert "search_metadata" in body


def test_post_search_missing_query(client):
    resp = client.post("/api/v1/search", json={}, headers=AUTH)
    assert resp.status_code == 400


def test_post_search_invalid_mode(client):
    resp = client.post("/api/v1/search", json={"query": "x", "mode": "bogus"}, headers=AUTH)
    assert resp.status_code == 400
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api_extended.py -k "post_search" -v
```
Expected: FAIL

- [ ] **Step 3: Implement search handler**

Append to `src/memory_mcp/api/routes.py`:

```python
async def handle_search(request: Request) -> JSONResponse:
    from ..tools import hybrid_search as hs_tool
    try:
        body = await request.json()
    except Exception:
        return err("Invalid JSON body")
    query = body.get("query")
    if not query:
        return err("Missing required field: query")
    try:
        result = await hs_tool.hybrid_search_tool({
            "query": query,
            "mode": body.get("mode", "hybrid"),
            "filters": body.get("filters"),
            "limit": int(body.get("limit", 10)),
        })
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)
```

Add route (anywhere in the list before the existing wm endpoint):

```python
    Route("/api/v1/search", endpoint=handle_search, methods=["POST"]),
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api_extended.py -k "post_search" -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/api/routes.py tests/test_api_extended.py
git commit -m "feat(api): add POST /api/v1/search hybrid search REST endpoint"
```

### Task 21: REST threads/jobs/auth skeleton routes (M3/M4/M5 placeholders)

**Files:**
- Modify: `src/memory_mcp/api/routes.py`
- Modify: `tests/test_api_extended.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api_extended.py`:

```python
def test_threads_list_returns_phase_m3(client):
    resp = client.get("/api/v1/threads", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["phase"] == "M3"
    # D13: paginated DTO uses `items` (M3 replaces shim with real handler).
    assert body["items"] == []


def test_threads_get_not_implemented(client):
    resp = client.get("/api/v1/threads/any-id", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["phase"] == "M3"


def test_threads_messages_not_implemented(client):
    resp = client.get("/api/v1/threads/any-id/messages", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["phase"] == "M3"


def test_threads_import_not_implemented(client):
    resp = client.post("/api/v1/threads/import",
                       json={"provider": "manual", "path": "/tmp/x"}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["phase"] == "M3"


def test_threads_incremental_not_implemented(client):
    resp = client.post("/api/v1/threads/incremental", json={"batches": []}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["phase"] == "M3"


def test_threads_sync_status_not_implemented(client):
    resp = client.get("/api/v1/threads/sync-status?provider=claude-code", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["phase"] == "M3"


def test_jobs_list_phase_m4(client):
    resp = client.get("/api/v1/jobs", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["phase"] == "M4"
    # D13: paginated DTO uses `items` (M4 replaces shim with real handler).
    assert body["items"] == []


def test_jobs_get_phase_m4(client):
    resp = client.get("/api/v1/jobs/any", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["phase"] == "M4"


def test_jobs_retry_phase_m4(client):
    resp = client.post("/api/v1/jobs/any/retry", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["phase"] == "M4"


def test_jobs_cancel_phase_m4(client):
    resp = client.post("/api/v1/jobs/any/cancel", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["phase"] == "M4"


def test_auth_me_phase_m5_returns_bearer_info(client):
    resp = client.get("/api/v1/auth/me", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["phase"] == "M5"
    assert body["auth_method"] == "bearer"


def test_auth_login_phase_m5(client):
    resp = client.post("/api/v1/auth/login", json={"token": "test-token"}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["phase"] == "M5"


def test_auth_logout_phase_m5(client):
    resp = client.post("/api/v1/auth/logout", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["data"]["phase"] == "M5"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api_extended.py -k "threads_ or jobs_ or auth_" -v
```
Expected: FAIL

- [ ] **Step 3: Add placeholder handlers**

Append to `src/memory_mcp/api/routes.py`:

```python
# ---------------- Threads placeholders (M3) ----------------
def _phase_m3(extra: dict[str, Any] | None = None) -> JSONResponse:
    payload = {"phase": "M3", "message": "Implemented in M3 (Threads + Adapters)."}
    if extra:
        payload.update(extra)
    return ok(payload)


async def handle_threads_list(request: Request) -> JSONResponse:
    return _phase_m3({"items": [], "total": 0, "page": 1, "size": 20})


async def handle_threads_get(request: Request) -> JSONResponse:
    thread_id = request.path_params["thread_id"]
    return _phase_m3({"thread_id": thread_id})


async def handle_threads_messages(request: Request) -> JSONResponse:
    thread_id = request.path_params["thread_id"]
    return _phase_m3({"thread_id": thread_id, "items": [], "total": 0, "page": 1, "size": 50})


async def handle_threads_import(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _phase_m3({"requested": body})


async def handle_threads_incremental(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _phase_m3({"batches_received": len(body.get("batches") or [])})


async def handle_threads_sync_status(request: Request) -> JSONResponse:
    return _phase_m3({"provider": request.query_params.get("provider"), "refs": {}})


# ---------------- Jobs placeholders (M4) ----------------
def _phase_m4(extra: dict[str, Any] | None = None) -> JSONResponse:
    payload = {"phase": "M4", "message": "Implemented in M4 (Background Worker)."}
    if extra:
        payload.update(extra)
    return ok(payload)


async def handle_jobs_list(request: Request) -> JSONResponse:
    return _phase_m4({"items": [], "total": 0, "page": 1, "size": 50})


async def handle_jobs_get(request: Request) -> JSONResponse:
    return _phase_m4({"job_id": request.path_params["job_id"]})


async def handle_jobs_retry(request: Request) -> JSONResponse:
    return _phase_m4({"job_id": request.path_params["job_id"], "action": "retry"})


async def handle_jobs_cancel(request: Request) -> JSONResponse:
    return _phase_m4({"job_id": request.path_params["job_id"], "action": "cancel"})


# ---------------- Auth placeholders (cookie session lands in M5) ----------------
def _phase_m5(extra: dict[str, Any] | None = None) -> JSONResponse:
    payload = {"phase": "M5", "message": "Cookie session lands in M5; Bearer header remains supported."}
    if extra:
        payload.update(extra)
    return ok(payload)


async def handle_auth_login(request: Request) -> JSONResponse:
    return _phase_m5({"login": "noop"})


async def handle_auth_logout(request: Request) -> JSONResponse:
    return _phase_m5({"logout": "noop"})


async def handle_auth_me(request: Request) -> JSONResponse:
    return _phase_m5({"auth_method": "bearer"})
```

Then extend the `routes = [...]` list — add (place before `wm` route):

```python
    # Threads (M3 placeholders)
    Route("/api/v1/threads", endpoint=handle_threads_list, methods=["GET"]),
    Route("/api/v1/threads/import", endpoint=handle_threads_import, methods=["POST"]),
    Route("/api/v1/threads/incremental", endpoint=handle_threads_incremental, methods=["POST"]),
    Route("/api/v1/threads/sync-status", endpoint=handle_threads_sync_status, methods=["GET"]),
    Route("/api/v1/threads/{thread_id}/messages", endpoint=handle_threads_messages, methods=["GET"]),
    Route("/api/v1/threads/{thread_id}", endpoint=handle_threads_get, methods=["GET"]),

    # Jobs (M4 placeholders)
    Route("/api/v1/jobs", endpoint=handle_jobs_list, methods=["GET"]),
    Route("/api/v1/jobs/{job_id}/retry", endpoint=handle_jobs_retry, methods=["POST"]),
    Route("/api/v1/jobs/{job_id}/cancel", endpoint=handle_jobs_cancel, methods=["POST"]),
    Route("/api/v1/jobs/{job_id}", endpoint=handle_jobs_get, methods=["GET"]),

    # Auth (M5 placeholders; Bearer middleware continues to enforce)
    Route("/api/v1/auth/login", endpoint=handle_auth_login, methods=["POST"]),
    Route("/api/v1/auth/logout", endpoint=handle_auth_logout, methods=["POST"]),
    Route("/api/v1/auth/me", endpoint=handle_auth_me, methods=["GET"]),
```

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api_extended.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/api/routes.py tests/test_api_extended.py
git commit -m "feat(api): add threads/jobs/auth skeleton routes (real impl in M3/M4/M5)"
```

---

## Chunk 7: MCP server registration

### Task 22: Register new MCP tools

**Files:**
- Modify: `src/memory_mcp/server.py`
- Create: `tests/test_server_tools.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_server_tools.py`:

```python
import importlib

import pytest


@pytest.fixture()
def server_mod(test_env):
    # Reload tools and engine so server.py picks up freshly-reloaded modules
    for mod_name in [
        "memory_mcp.tools.remember", "memory_mcp.tools.recall", "memory_mcp.tools.recall_all",
        "memory_mcp.tools.trace", "memory_mcp.tools.forget", "memory_mcp.tools.relate",
        "memory_mcp.tools.unrelate", "memory_mcp.tools.graph_query",
        "memory_mcp.tools.memory_crud", "memory_mcp.tools.hybrid_search",
        "memory_mcp.tools.thread_stub",
        "memory_mcp.engine.hybrid_search", "memory_mcp.engine.reinforce",
    ]:
        importlib.import_module(mod_name)
        importlib.reload(importlib.import_module(mod_name))
    import memory_mcp.server as s
    importlib.reload(s)
    return s


def test_list_tools_includes_new_m2_tools(server_mod):
    import anyio
    tools = anyio.run(server_mod.list_tools)
    names = {t.name for t in tools}
    expected = {
        "remember", "recall", "recall_all", "trace", "forget", "relate", "unrelate",
        "graph_query",
        # M2 newcomers
        "memory_get", "memory_update", "memory_delete", "memory_merge",
        "hybrid_search",
        "thread_search", "thread_get", "thread_import", "thread_list_providers",
    }
    missing = expected - names
    assert not missing, f"Missing tools: {missing}"


def test_call_tool_memory_get(server_mod, tools):
    import anyio
    async def run():
        remember, *_ = tools
        res = await remember.remember_tool({
            "content": "x", "entity_key": "fact:x", "entity_type": "fact",
        })
        mid = res["memory_id"]
        out = await server_mod.call_tool("memory_get", {"memory_id": mid})
        # MCP returns list[TextContent]; we just sanity-check structure
        assert out and out[0].text
        import json
        body = json.loads(out[0].text)
        assert body["memory_id"] == mid
    anyio.run(run)


def test_call_tool_hybrid_search(server_mod, tools):
    import anyio
    async def run():
        remember, *_ = tools
        await remember.remember_tool({
            "content": "Cursor", "entity_key": "preference:editor", "entity_type": "preference",
        })
        out = await server_mod.call_tool("hybrid_search", {"query": "Cursor", "mode": "hybrid"})
        import json
        body = json.loads(out[0].text)
        assert body["search_mode"] == "hybrid"
    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_server_tools.py -v
```
Expected: FAIL（tool 列表里没有新名称）

- [ ] **Step 3: Register new tools**

Edit `src/memory_mcp/server.py`:

(a) Update imports near line 25 — replace the `tools` import block with:

```python
from .tools import (
    remember, recall, trace, forget, relate, unrelate, graph_query, recall_all,
    memory_crud, hybrid_search as hs_tool, thread_stub,
)
```

(b) Add tool definitions to `list_tools()` — extend the `return [...]` list with the following entries appended before the closing `]`:

```python
        Tool(
            name="memory_get",
            description="Fetch a single memory by id, including v2 metadata.",
            inputSchema={
                "type": "object",
                "properties": {"memory_id": {"type": "string"}},
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="memory_update",
            description="Update mutable fields on a memory (content/title/tags/review_status/importance/source_refs/...).",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "content": {"type": "string"},
                    "title": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "review_status": {
                        "type": "string",
                        "enum": ["auto", "reviewed", "confirmed", "challenged", "legacy", "archived"],
                    },
                    "importance": {"type": "number"},
                    "confidence": {"type": "number"},
                    "source_refs": {"type": "array"},
                    "source_thread_id": {"type": "string"},
                    "origin_client": {"type": "string"},
                    "origin_session_id": {"type": "string"},
                    "archived_reason": {"type": "string"},
                },
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="memory_delete",
            description="Delete a memory by id. Soft (review_status='archived') by default; pass hard=true to remove.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "hard": {"type": "boolean", "default": False},
                    "reason": {"type": "string"},
                },
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="memory_merge",
            description="Merge polluted memories: target inherits all source source_refs; sources soft-archived with archived_reason='merged_into:<target_id>'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "target_id": {"type": "string"},
                },
                "required": ["source_ids", "target_id"],
            },
        ),
        Tool(
            name="hybrid_search",
            description="Low-level hybrid search exposing recall internals: vector+FTS+graph RRF fusion + reinforce/decay re-rank + filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["hybrid", "vector_only", "fts_only", "graph_only"],
                        "default": "hybrid",
                    },
                    "filters": {"type": "object"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="thread_search",
            description="Search archived threads. [Phase M3 placeholder] Returns empty results in M2.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "provider": {"type": "string"},
                    "time_range": {"type": "object"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="thread_get",
            description="Fetch a thread by id. [Phase M3 placeholder]",
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "with_messages": {"type": "boolean", "default": False},
                },
                "required": ["thread_id"],
            },
        ),
        Tool(
            name="thread_import",
            description="Import a thread from a provider. [Phase M3 placeholder]",
            inputSchema={
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "path": {"type": "string"},
                    "options": {"type": "object"},
                },
                "required": ["provider"],
            },
        ),
        Tool(
            name="thread_list_providers",
            description="List supported thread providers. [Phase M3 placeholder]",
            inputSchema={"type": "object", "properties": {}},
        ),
```

(c) Recall and remember schemas — extend `remember` properties with v2 passthrough fields, and `recall` properties with hybrid switches:

Replace the existing `remember` Tool block with:

```python
        Tool(
            name="remember",
            description="Store a new memory. The system handles evolution + conflict detection. v2 fields (origin_*, source_*, title) are optional metadata for cross-tool provenance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "entity_key": {"type": "string"},
                    "entity_type": {
                        "type": "string",
                        "enum": ["person", "preference", "fact", "event", "goal", "project"],
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "title": {"type": "string"},
                    "origin_client": {"type": "string"},
                    "origin_session_id": {"type": "string"},
                    "source_thread_id": {"type": "string"},
                    "source_refs": {"type": "array"},
                    "skip_semantic_merge": {"type": "boolean", "default": False},
                },
                "required": ["content", "entity_key", "entity_type"],
            },
        ),
```

Replace the existing `recall` Tool block with:

```python
        Tool(
            name="recall",
            description="Hybrid search (vector + FTS5 + graph + RRF + reinforce/decay). Returns relevance_breakdown + search_metadata. Use 'hybrid' by default.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                    "include_evolution": {"type": "boolean", "default": False},
                    "search_mode": {
                        "type": "string",
                        "enum": ["hybrid", "vector_only", "fts_only", "graph_only"],
                        "default": "hybrid",
                    },
                    "filters": {"type": "object"},
                    "time_range": {"type": "object"},
                },
                "required": ["query"],
            },
        ),
```

(d) Extend the `call_tool` dispatcher (around line 148):

```python
@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent | EmbeddedResource]:
    try:
        result: dict = {}
        if name == "remember":
            result = await remember.remember_tool(arguments)
        elif name == "recall":
            result = await recall.recall_tool(arguments)
        elif name == "recall_all":
            result = await recall_all.recall_all_tool(arguments)
        elif name == "trace":
            result = await trace.trace_tool(arguments)
        elif name == "forget":
            result = await forget.forget_tool(arguments)
        elif name == "relate":
            result = await relate.relate_tool(arguments)
        elif name == "unrelate":
            result = await unrelate.unrelate_tool(arguments)
        elif name == "graph_query":
            result = await graph_query.graph_query_tool(arguments)
        elif name == "memory_get":
            result = await memory_crud.memory_get_tool(arguments)
        elif name == "memory_update":
            result = await memory_crud.memory_update_tool(arguments)
        elif name == "memory_delete":
            result = await memory_crud.memory_delete_tool(arguments)
        elif name == "memory_merge":
            result = await memory_crud.memory_merge_tool(arguments)
        elif name == "hybrid_search":
            result = await hs_tool.hybrid_search_tool(arguments)
        elif name == "thread_search":
            result = await thread_stub.thread_search_tool(arguments)
        elif name == "thread_get":
            result = await thread_stub.thread_get_tool(arguments)
        elif name == "thread_import":
            result = await thread_stub.thread_import_tool(arguments)
        elif name == "thread_list_providers":
            result = await thread_stub.thread_list_providers_tool(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]
```

Note the addition of `default=str` to `json.dumps(...)` — `memory_get_tool` returns ISO timestamps already, but `relevance_breakdown` may contain numpy floats from LanceDB downstream. Defensive.

- [ ] **Step 4: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_server_tools.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/server.py tests/test_server_tools.py
git commit -m "feat(server): register M2 MCP tools (memory_*, hybrid_search, thread_* stubs)"
```

---

## Chunk 8: End-to-end integration + retrieval quality regression

### Task 23: Integration test — MCP and REST round-trip for memory_merge and hybrid_search

**Files:**
- Modify: `tests/test_api_extended.py`

- [ ] **Step 1: Add end-to-end tests**

Append to `tests/test_api_extended.py`:

```python
def test_e2e_merge_then_search_returns_target_only(client):
    a = client.post("/api/v1/memories",
                    json={"content": "Cursor preferred", "entity_key": "preference:editor-1", "entity_type": "preference",
                          "source_refs": [{"thread_id": "t1", "message_id": "t1:000001"}]},
                    headers=AUTH).json()["data"]["memory_id"]
    b = client.post("/api/v1/memories",
                    json={"content": "Cursor is the editor", "entity_key": "preference:editor-2", "entity_type": "preference",
                          "source_refs": [{"thread_id": "t2", "message_id": "t2:000002"}]},
                    headers=AUTH).json()["data"]["memory_id"]
    t = client.post("/api/v1/memories",
                    json={"content": "Use Cursor as primary editor", "entity_key": "preference:editor-canonical", "entity_type": "preference",
                          "source_refs": [{"thread_id": "t3", "message_id": "t3:000003"}]},
                    headers=AUTH).json()["data"]["memory_id"]

    merge_resp = client.post("/api/v1/memories/bulk-merge",
                              json={"source_ids": [a, b], "target_id": t}, headers=AUTH)
    assert merge_resp.json()["data"]["status"] == "merged"

    search_resp = client.post("/api/v1/search",
                              json={"query": "Cursor", "mode": "hybrid", "limit": 10},
                              headers=AUTH)
    results = search_resp.json()["data"]["results"]
    keys = [r["entity_key"] for r in results]
    assert "preference:editor-canonical" in keys
    # archived sources must be filtered out by default
    assert "preference:editor-1" not in keys
    assert "preference:editor-2" not in keys
```

- [ ] **Step 2: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api_extended.py::test_e2e_merge_then_search_returns_target_only -v
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_extended.py
git commit -m "test(api): end-to-end merge + hybrid search filters out archived sources"
```

### Task 24: Retrieval quality regression — fixed query set asserts entity_key membership

**Files:**
- Create: `tests/test_retrieval_quality.py`

- [ ] **Step 1: Write regression test**

Create `tests/test_retrieval_quality.py`:

```python
"""Retrieval quality regression.

Seed a stable corpus of memories, run a fixed query set through hybrid_search,
and assert each query's top-N contains the expected entity_key. This guards
against silent regressions in RRF weights, decay defaults, and filter logic.
"""
import importlib

import anyio


CORPUS = [
    ("preference:editor", "preference", "Use Cursor as the primary editor"),
    ("preference:lang", "preference", "Python is my default language"),
    ("project:memory-mcp", "project", "memory-mcp is the personal memory kernel project"),
    ("person:alice", "person", "Alice maintains the embeddings service"),
    ("fact:timezone", "fact", "My timezone is Asia/Shanghai"),
    ("goal:q3", "goal", "Ship Phase 1 by end of Q3"),
    ("preference:theme", "preference", "Dark mode preferred for IDE"),
    ("project:zerotool", "project", "zerotool is a static-only single-page utility hub"),
]

QUERIES = [
    ("which editor do I use?", "preference:editor"),
    ("favorite programming language", "preference:lang"),
    ("memory-mcp project status", "project:memory-mcp"),
    ("who maintains embeddings", "person:alice"),
    ("Q3 milestone goals", "goal:q3"),
]


def _seed(remember):
    async def run():
        for key, etype, content in CORPUS:
            await remember.remember_tool({
                "content": content, "entity_key": key, "entity_type": etype,
            })
    anyio.run(run)


def test_top3_contains_expected_entity_key(tools, test_env):
    remember, *_ = tools
    _seed(remember)

    import memory_mcp.engine.hybrid_search as hs
    importlib.reload(hs)

    async def run():
        for query, expected_key in QUERIES:
            res = await hs.search(query=query, mode="hybrid", filters=None, limit=3)
            top_keys = [r["entity_key"] for r in res["results"]]
            assert expected_key in top_keys, (
                f"query={query!r} expected {expected_key!r} in top3, got {top_keys}"
            )
    anyio.run(run)
```

- [ ] **Step 2: Run test**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_retrieval_quality.py -v
```
Expected: PASS（如果失败，调整 stub embedding fixture 或者增大 limit；conftest 用同向量 stub 时，FTS5 路径 + graph 路径仍能保证 expected_key 在 top3）

- [ ] **Step 3: Commit**

```bash
git add tests/test_retrieval_quality.py
git commit -m "test: retrieval quality regression — fixed query set asserts top-N membership"
```

---

## Chunk 9: Documentation & changelog

### Task 25: Update AGENTS.md + final full test run

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Full test suite (all chunks)**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest -v
```
Expected: All PASS

- [ ] **Step 2: Append M2 changelog**

Edit `AGENTS.md` — append to the changelog section:

```markdown
### 2026-05-21 M2 API & Hybrid Search
- New MCP tools: memory_get / memory_update / memory_delete (soft+hard) / memory_merge / hybrid_search / thread_search|get|import|list_providers (Threads tools are M2 placeholders; data model lands in M3)
- Upgraded existing tools: remember passes through v2 provenance fields (origin_client / origin_session_id / source_thread_id / source_refs / title); recall delegates to hybrid_search and returns relevance_breakdown + search_metadata; forget sets review_status='archived' for unified soft-delete semantics
- New Hybrid Search engine: three-way recall (vector top 50 / FTS5 jieba top 50 / 1-hop graph top 20) + RRF fusion (k=60) + re-rank (confidence * reinforce_factor * exp(-λ*days), λ=1/180) + filter (default excludes review_status in {legacy, archived})
- Configurable via env: MEMORY_MCP_RRF_K, MEMORY_MCP_DECAY_LAMBDA, MEMORY_MCP_RECALL_DEPTH (+ FTS / GRAPH variants)
- New reinforce engine: record_access(memory_ids) increments access_count and last_accessed_at synchronously on every recall hit. TEMPORARY: this will become an async job enqueue in M4 to keep recall non-blocking
- REST API extension: memories list pagination/filter (?page, ?size, ?review_status, ?origin_client, ?q with legacy ?limit back-compat) / by-id GET/PATCH/DELETE under /api/v1/memories/by-id/{id} / bulk-delete / bulk-merge / /graph/subgraph (react-flow shape) / POST /search (hybrid)
- REST skeleton routes for M3/M4/M5: /api/v1/threads/* (M3), /api/v1/jobs/* (M4), /api/v1/auth/* (M5) all return {phase: 'M3|M4|M5'} placeholders; Bearer auth continues to enforce
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: changelog for M2 API & Hybrid Search milestone"
```

- [ ] **Step 4: Final lint pass**

```bash
cd /Users/kassol/Workspace/memory-mcp && ruff check .
```

Fix any ruff errors with minimal diffs and recommit (`git commit -m "style: fix ruff findings introduced in M2"`).

- [ ] **Step 5: Manual smoke test (server up, MCP + REST round-trip)**

Start the server locally:

```bash
cd /Users/kassol/Workspace/memory-mcp
export MEMORY_MCP_AUTH_TOKEN=<MEMORY_MCP_AUTH_TOKEN>
export MEMORY_MCP_OPENROUTER_API_KEY=<MEMORY_MCP_OPENROUTER_API_KEY>
python -m memory_mcp &
SERVER_PID=$!
sleep 2
```

Round-trip:

```bash
curl -s -H "Authorization: Bearer <MEMORY_MCP_AUTH_TOKEN>" \
  -H 'Content-Type: application/json' \
  -X POST http://localhost:8765/api/v1/memories \
  -d '{"content":"smoke","entity_key":"fact:smoke","entity_type":"fact","origin_client":"manual-cli"}' | jq .

curl -s -H "Authorization: Bearer <MEMORY_MCP_AUTH_TOKEN>" \
  -H 'Content-Type: application/json' \
  -X POST http://localhost:8765/api/v1/search \
  -d '{"query":"smoke","mode":"hybrid","limit":5}' | jq .

curl -s -H "Authorization: Bearer <MEMORY_MCP_AUTH_TOKEN>" \
  http://localhost:8765/api/v1/memories?page=1\&size=5 | jq .

kill $SERVER_PID
```

Expected: 三个请求都返回 `"ok": true`，hybrid search 返回 `search_metadata.vector_candidates >= 1` 且 `relevance_breakdown` 字段完整。

- [ ] **Step 6: Final summary commit (only if any small fixes from smoke test)**

```bash
# If smoke test exposed any issue, fix + commit minimally.
# Otherwise nothing to do.
```

---

## Done criteria

- [ ] All 25 tasks completed (checkbox steps all ticked)
- [ ] `pytest -v` 全绿（M1 已有 baseline + M2 新增 ~80 个测试 case）
- [ ] `ruff check .` 无错误
- [ ] AGENTS.md 包含 2026-05-21 M2 变更日志
- [ ] Manual smoke test 三个 curl 都返回 `ok: true`
- [ ] spec §5.1 的全部新/升级 tool 在 MCP server 注册且 dispatcher 路由完整
- [ ] spec §5.2 的全部 REST 路由（含 M3/M4/M5 占位）都存在且返回正确 phase 标记
- [ ] spec §5.3 三路召回 + RRF + re-rank + filter 各自有独立单元测试覆盖
- [ ] spec §5.4 response 结构在 `engine/hybrid_search.search()` 与 `POST /api/v1/search` 中完整体现

## Punt 到 M3+ 的事项（明确不在 M2 范围）

- Threads 数据模型 / FTS5 / ThreadAdapter 系列：M3
- jobs 表 / worker loop / APScheduler / async reinforce：M4
- Web UI / cookie session / react-flow GraphView：M5
- LLM auto re-rank、Library / Source 文档导入、mem_fs 虚拟路径：Phase 2+

---

## 修复记录

> 2026-05-21 plan 修复（codex 评审）：
>
> - **Task 3（fts_recall）**：从假想的 `sqlite_store.fts_search_memories` 切到 M1 实际提供的 `MemoryRepository.fts_search(tokens, limit)`，避免 fallback 路径成为默认。
> - **Task 10（remember_tool）**：补 `_parse_source_refs` 把 raw dict 转 `SourceRef`，避免 M1 序列化层崩；initial 分支显式 `tokenize(content/title)` 写 `content_tokens` / `title_tokens`；`_apply_v2_fields` 在更新 title 时同步 `title_tokens`；测试 `source_refs[0]["message_id"]` 改为 `.message_id`（Pydantic 属性访问）。
> - **Task 13（memory_crud）**：删除 placeholder `if False else None`；引入 `_coerce_value` 统一处理 `review_status` enum / `source_refs` Pydantic 转换；`_serialize_node` emit `review_status.value` 字符串 + `source_refs` `model_dump()` dict 列表给前端；`memory_update_tool` 在更新 content/title 时同步 token 字段；删除「给 VectorStore 加 delete」的过时 patch（M1 Task 12 已提供）。
> - **Task 14（memory_merge）**：`_merge_source_refs` 同时接受 SourceRef + dict 输入，返回 `[SourceRef]`；输出仍用 `model_dump()` dict。
> - **Task 16（thread stubs）**：rename 「placeholder」→ explicit `compatibility shim`，标注 M3 Task 8 替换路径；M3 删除文件名为 `thread_stub.py` 的整个文件。
> - **Task 17（REST routes）**：契约统一 D13——`/api/v1/memories/{id}` 直接 by-id（去 `by-id/` 前缀）；paginated 响应 `items` 字段（M5 同字段）；legacy entity_key DELETE 移到 `/api/v1/entities/{key}`（CLI client 一行替换）；新增 `/api/v1/memories/{id}/evolution` 给 Web UI MemoryDetail 用。
> - **Task 18（legacy limit）**：测试断言改 `body["items"]`。
> - **新 Task 18.5（entities endpoints）**：补 spec §5.2 `GET /api/v1/entities` + `GET /api/v1/entities/{key}/graph`。
> - **Task 21（M3/M4 占位 routes）**：placeholder 改返回 `items`/`total`/`page`/`size` 与 D13 一致，M3/M4 实现替换时无契约改动。
