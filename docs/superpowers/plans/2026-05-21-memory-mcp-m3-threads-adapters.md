# Memory MCP — M3 Threads 模块与 Provider 适配器实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Threads 数据流跑通 — provider adapter 抽象、claude-code 完整实现、incremental sync 协议、CLI sync 子命令、stop hook 升级双步、extraction 透传 source_refs。M3 完成后每条 memory 都能回链到具体 thread + message。

**Architecture:** ThreadAdapter 抽象 + claude-code 完整实现 + codex/chatwise stub（待 Sir 提供 fixture） + manual。本地 CLI 推送增量到服务端（D11），服务端不扫文件系统。stop hook 改双步：先 incremental 拿 thread_id/message_ids，再 extract 透传 source_thread_id + source_refs。

**Tech Stack:** Python 3.11+ / aiosqlite / FTS5 jieba / typer / httpx / pytest-asyncio。

**Spec:** `docs/superpowers/specs/2026-05-21-memory-mcp-agent-kernel-design.md` §6 全部子节、§4.4 threads DDL、§11 M3。

**Prereq:** M1（SQLite 主存储 + alembic + threads/thread_messages 表 + FTS5 触发器已就位）+ M2（v2 字段接入 + memory_get/update/delete/merge + REST 分页/过滤/批量 + threads 路由占位 + MCP thread_* 工具占位）。本 plan 假设 M1/M2 已提供：

- `src/memory_mcp/storage/sqlite.py` 暴露 `get_db()` async context；DDL 已建好。
- `src/memory_mcp/storage/sqlite.py::Database.executemany / fetchall / transaction()`。
- `src/memory_mcp/engine/tokenizer.py::tokenize(text) -> str`（jieba 空格分隔）。
- `src/memory_mcp/tools/__init__.py` 已注册 `thread_*` 占位。

如 M1/M2 接口名实际差异，按本 plan 调整 import 路径即可，核心逻辑不变。

---

## File Structure

### 服务端

| File | Action | Responsibility |
|------|--------|----------------|
| `src/memory_mcp/threads/__init__.py` | Create | 子包入口 |
| `src/memory_mcp/threads/ids.py` | Create | `make_message_id` 复合 ID |
| `src/memory_mcp/threads/models.py` | Create | ParsedThread / ParsedMessage / ParsedThreadDelta / ThreadSource dataclass |
| `src/memory_mcp/threads/adapters/__init__.py` | Create | 适配器子包入口 |
| `src/memory_mcp/threads/adapters/base.py` | Create | `ThreadAdapter` ABC |
| `src/memory_mcp/threads/adapters/claude_code.py` | Create | 完整实现：discover / parse / incremental_payload |
| `src/memory_mcp/threads/adapters/codex.py` | Create | Stub，待 fixture |
| `src/memory_mcp/threads/adapters/chatwise.py` | Create | Stub，待 fixture |
| `src/memory_mcp/threads/adapters/manual.py` | Create | markdown / json / plaintext 完整实现 |
| `src/memory_mcp/threads/registry.py` | Create | provider → adapter 映射 |
| `src/memory_mcp/threads/sync.py` | Create | upsert thread + append messages (幂等) + sync-status 查询 |
| `src/memory_mcp/threads/backfill.py` | Create | 一次性 backfill：discover → parse → push，支持 --dry-run / --resume |
| `src/memory_mcp/tools/thread_search.py` | Modify | 真实实现 thread_search (FTS5) |
| `src/memory_mcp/tools/thread_get.py` | Modify | 真实实现 thread_get |
| `src/memory_mcp/tools/thread_import.py` | Modify | 真实实现 thread_import |
| `src/memory_mcp/tools/thread_list_providers.py` | Modify | 真实实现 thread_list_providers |
| `src/memory_mcp/api/routes.py` | Modify | 接入 threads REST 路由 + incremental + sync-status |
| `src/memory_mcp/engine/extraction.py` | Modify | 接受 `source_thread_id` + `source_refs` 透传 |
| `src/memory_mcp/tools/remember.py` | Modify | 接受 `source_thread_id` + `source_refs` 透传到 MemoryNode |
| `src/memory_mcp/engine/models.py` | Modify | MemoryNode 新增字段（M2 应已加，验证存在） |

### 测试

| File | Action | Tests |
|------|--------|-------|
| `tests/fixtures/threads/claude-code/sample.jsonl` | Create | 12 条真实风格 transcript |
| `tests/fixtures/threads/claude-code/empty.jsonl` | Create | 空文件 fixture |
| `tests/fixtures/threads/claude-code/malformed.jsonl` | Create | 含坏行 fixture |
| `tests/fixtures/threads/manual/sample.md` | Create | manual markdown fixture |
| `tests/fixtures/threads/manual/sample.json` | Create | manual json fixture |
| `tests/test_threads_ids.py` | Create | message_id 复合规则 |
| `tests/test_threads_adapter_claude_code.py` | Create | parse / discover / incremental_payload |
| `tests/test_threads_adapter_manual.py` | Create | markdown/json/plaintext |
| `tests/test_threads_adapter_stubs.py` | Create | codex/chatwise stub NotImplementedError |
| `tests/test_threads_sync.py` | Create | upsert 幂等 / seq 单调 / 长内容截断 |
| `tests/test_threads_api.py` | Create | REST incremental / sync-status / search / get / import |
| `tests/test_threads_tools.py` | Create | MCP thread_* 工具 |
| `tests/test_threads_e2e.py` | Create | stop hook → incremental → extract → memory source_refs 回链 |
| `tests/test_threads_backfill.py` | Create | backfill --dry-run / --resume / 分批 commit |
| `tests/test_extraction_source_refs.py` | Create | extraction 接受 source_thread_id + source_refs |

### CLI

| File | Action | Responsibility |
|------|--------|----------------|
| `cli/src/memory_mcp_cli/config.py` | Modify | 支持 `~/.config/mem/config.toml` 并兼容旧 json |
| `cli/src/memory_mcp_cli/client.py` | Modify | 新增 `threads_incremental` / `sync_status` / `threads_import` / `thread_search` / `thread_get` |
| `cli/src/memory_mcp_cli/sync.py` | Create | 本地扫描 → sync-status → diff → incremental 推送 |
| `cli/src/memory_mcp_cli/adapters/__init__.py` | Create | 入口 |
| `cli/src/memory_mcp_cli/adapters/claude_code.py` | Create | CLI 端 claude-code 扫描（与服务端逻辑对称） |
| `cli/src/memory_mcp_cli/adapters/manual.py` | Create | manual 文件读取 |
| `cli/src/memory_mcp_cli/main.py` | Modify | 新增 `thread sync / import-history / import / search / get` 子命令 |
| `cli/tests/test_sync.py` | Create | sync 协议 5 步 / config.toml 解析 |
| `cli/tests/test_thread_commands.py` | Create | CLI thread 子命令 |

### Plugin

| File | Action | Responsibility |
|------|--------|----------------|
| `claude-code-plugin/hooks/stop.sh` | Rewrite | 双步：incremental → extract（带 source_refs） |
| `claude-code-plugin/hooks/lib/push_thread.sh` | Create | 抽取共用 incremental 推送逻辑 |
| `claude-code-plugin/README.md` | Modify | 补 stop hook 双步说明 |

### 文档

| File | Action | Responsibility |
|------|--------|----------------|
| `AGENTS.md` | Modify | 追加 M3 变更日志 |

---

## Chunk 1: 基础数据契约（ids / models / registry / adapter base）

### Task 1: message_id 复合规则

**Files:**
- Create: `src/memory_mcp/threads/__init__.py`
- Create: `src/memory_mcp/threads/ids.py`
- Create: `tests/test_threads_ids.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_threads_ids.py`:

```python
import pytest


class TestMessageId:
    def test_compose_basic(self):
        from memory_mcp.threads.ids import make_message_id

        assert make_message_id("abc-123", 42) == "abc-123:000042"

    def test_compose_zero(self):
        from memory_mcp.threads.ids import make_message_id

        assert make_message_id("t", 0) == "t:000000"

    def test_compose_large_seq(self):
        from memory_mcp.threads.ids import make_message_id

        assert make_message_id("t", 1_000_000) == "t:1000000"

    def test_split_round_trip(self):
        from memory_mcp.threads.ids import make_message_id, split_message_id

        thread_id, seq = split_message_id(make_message_id("abc-123", 42))
        assert thread_id == "abc-123"
        assert seq == 42

    def test_split_invalid_raises(self):
        from memory_mcp.threads.ids import split_message_id

        with pytest.raises(ValueError):
            split_message_id("no-colon")
        with pytest.raises(ValueError):
            split_message_id("a:b:c")
        with pytest.raises(ValueError):
            split_message_id("a:notnum")

    def test_negative_seq_raises(self):
        from memory_mcp.threads.ids import make_message_id

        with pytest.raises(ValueError):
            make_message_id("t", -1)
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_threads_ids.py -v`
Expected: FAIL — 模块不存在。

- [ ] **Step 3: 实现**

Create `src/memory_mcp/threads/__init__.py`:

```python
"""Threads subsystem — adapters, sync, registry."""
```

Create `src/memory_mcp/threads/ids.py`:

```python
"""Compose / split message_id.

Convention:
    message_id = f"{thread_id}:{seq:06d}"

Pad to 6 digits for lexical sort up to seq=999_999; longer seq still works
but loses lexical ordering for those entries.
"""
from __future__ import annotations


def make_message_id(thread_id: str, seq: int) -> str:
    if seq < 0:
        raise ValueError(f"seq must be >= 0, got {seq}")
    if not thread_id:
        raise ValueError("thread_id must not be empty")
    return f"{thread_id}:{seq:06d}"


def split_message_id(message_id: str) -> tuple[str, int]:
    parts = message_id.split(":")
    if len(parts) != 2:
        raise ValueError(f"invalid message_id: {message_id!r}")
    thread_id, seq_str = parts
    if not thread_id:
        raise ValueError(f"invalid message_id (empty thread_id): {message_id!r}")
    try:
        seq = int(seq_str)
    except ValueError as exc:
        raise ValueError(f"invalid seq in message_id: {message_id!r}") from exc
    return thread_id, seq
```

- [ ] **Step 4: 跑测试 PASS**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_threads_ids.py -v`
Expected: 全绿。

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/threads/__init__.py src/memory_mcp/threads/ids.py tests/test_threads_ids.py
git commit -m "feat(threads): add composite message_id helpers"
```

### Task 2: ParsedThread / ParsedMessage / ThreadSource 数据类

**Files:**
- Create: `src/memory_mcp/threads/models.py`

- [ ] **Step 1: 写测试**

Append to `tests/test_threads_ids.py`（同文件加 `TestModels` 类）：

```python
from datetime import datetime, timezone


class TestParsedModels:
    def test_parsed_message_minimum(self):
        from memory_mcp.threads.models import ParsedMessage

        m = ParsedMessage(seq=0, role="user", content="hi", ts=None, metadata={})
        assert m.role == "user"
        assert m.metadata == {}

    def test_parsed_thread_holds_messages(self):
        from memory_mcp.threads.models import ParsedMessage, ParsedThread

        t = ParsedThread(
            thread_id="t1",
            source_provider="claude-code",
            source_ref="/tmp/t1.jsonl",
            title=None,
            started_at=None,
            ended_at=None,
            metadata={"project": "demo"},
            messages=[
                ParsedMessage(seq=0, role="user", content="x", ts=None, metadata={}),
                ParsedMessage(seq=1, role="assistant", content="y", ts=None, metadata={}),
            ],
        )
        assert len(t.messages) == 2
        assert t.metadata["project"] == "demo"

    def test_thread_source_path_and_mtime(self, tmp_path):
        from memory_mcp.threads.models import ThreadSource

        f = tmp_path / "t.jsonl"
        f.write_text("{}\n")
        src = ThreadSource(provider="claude-code", ref=str(f), path=f, mtime=int(f.stat().st_mtime))
        assert src.provider == "claude-code"
        assert src.path.exists()
```

- [ ] **Step 2: 跑 FAIL**

- [ ] **Step 3: 实现**

Create `src/memory_mcp/threads/models.py`:

```python
"""Standardized dataclasses for thread adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ParsedMessage:
    seq: int                                 # strictly increasing within a thread
    role: str                                # user / assistant / tool / system
    content: str
    ts: datetime | None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Extras like tool_use_id / tool_result / attachments live in metadata.


@dataclass
class ParsedThread:
    thread_id: str
    source_provider: str
    source_ref: str
    title: str | None
    started_at: datetime | None
    ended_at: datetime | None
    metadata: dict[str, Any]
    messages: list[ParsedMessage]


@dataclass
class ParsedThreadDelta:
    """Incremental payload produced from a raw event (e.g. stop hook tail)."""

    thread_id: str
    source_provider: str
    source_ref: str
    thread_meta_patch: dict[str, Any]        # title / metadata partial update
    messages: list[ParsedMessage]            # only new messages (caller decides)


@dataclass
class ThreadSource:
    provider: str
    ref: str                                 # canonical ref stored in DB
    path: Path | None                        # local path (None for non-file sources)
    mtime: int | None                        # epoch seconds, used for sync gating
```

- [ ] **Step 4: 跑 PASS**

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/threads/models.py tests/test_threads_ids.py
git commit -m "feat(threads): add ParsedThread / ParsedMessage / ThreadSource dataclasses"
```

### Task 3: ThreadAdapter ABC + registry 骨架

**Files:**
- Create: `src/memory_mcp/threads/adapters/__init__.py`
- Create: `src/memory_mcp/threads/adapters/base.py`
- Create: `src/memory_mcp/threads/registry.py`
- Create: `tests/test_threads_adapter_stubs.py`（只放 registry 测试）

- [ ] **Step 1: 写测试**

Create `tests/test_threads_adapter_stubs.py`:

```python
import pytest


class TestRegistry:
    def test_get_known_providers(self):
        from memory_mcp.threads.registry import list_providers

        providers = list_providers()
        assert {"claude-code", "codex", "chatwise", "manual"} <= set(providers)

    def test_get_adapter_returns_instance(self):
        from memory_mcp.threads.adapters.base import ThreadAdapter
        from memory_mcp.threads.registry import get_adapter

        a = get_adapter("claude-code")
        assert isinstance(a, ThreadAdapter)
        assert a.provider == "claude-code"

    def test_get_unknown_raises(self):
        from memory_mcp.threads.registry import get_adapter

        with pytest.raises(KeyError):
            get_adapter("not-a-provider")
```

- [ ] **Step 2: 跑 FAIL**

- [ ] **Step 3: 实现 ABC**

Create `src/memory_mcp/threads/adapters/__init__.py`:

```python
"""Thread adapter implementations."""
```

Create `src/memory_mcp/threads/adapters/base.py`:

```python
"""ThreadAdapter base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Iterator

from ..models import ParsedThread, ParsedThreadDelta, ThreadSource


class ThreadAdapter(ABC):
    """Each provider implements scan + parse + incremental conversion."""

    provider: ClassVar[str] = ""

    @abstractmethod
    def discover(self, root: Path) -> Iterator[ThreadSource]:
        """Walk a local root and yield ThreadSource descriptors."""

    @abstractmethod
    def parse(self, source: ThreadSource) -> ParsedThread:
        """Parse a single source into ParsedThread (all messages)."""

    @abstractmethod
    def incremental_payload(self, raw_event: dict[str, Any]) -> ParsedThreadDelta | None:
        """Convert a provider-specific raw event (e.g. stop hook payload) into a delta.

        Returns None if event carries no usable messages.
        """
```

- [ ] **Step 4: 实现 stub 适配器（codex/chatwise）+ registry**

Create `src/memory_mcp/threads/adapters/codex.py`:

```python
"""Codex adapter — stub.

TODO(Sir): provide a fixture (e.g. ~/.codex/sessions/*.jsonl) and we will
implement discover/parse based on the actual format.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from ..models import ParsedThread, ParsedThreadDelta, ThreadSource
from .base import ThreadAdapter


class CodexAdapter(ThreadAdapter):
    provider = "codex"

    def discover(self, root: Path) -> Iterator[ThreadSource]:  # pragma: no cover - stub
        raise NotImplementedError(
            "Codex adapter discover() is not implemented yet; awaiting fixture from Sir."
        )

    def parse(self, source: ThreadSource) -> ParsedThread:  # pragma: no cover - stub
        raise NotImplementedError(
            "Codex adapter parse() is not implemented yet; awaiting fixture from Sir."
        )

    def incremental_payload(self, raw_event: dict[str, Any]) -> ParsedThreadDelta | None:
        # pragma: no cover - stub
        raise NotImplementedError(
            "Codex adapter incremental_payload() is not implemented yet; awaiting fixture from Sir."
        )
```

Create `src/memory_mcp/threads/adapters/chatwise.py` 同模板（provider = "chatwise"）。

Create `src/memory_mcp/threads/registry.py`:

```python
"""Provider name → adapter instance map."""
from __future__ import annotations

from .adapters.base import ThreadAdapter
from .adapters.chatwise import ChatwiseAdapter
from .adapters.claude_code import ClaudeCodeAdapter
from .adapters.codex import CodexAdapter
from .adapters.manual import ManualAdapter

_REGISTRY: dict[str, ThreadAdapter] = {
    "claude-code": ClaudeCodeAdapter(),
    "codex": CodexAdapter(),
    "chatwise": ChatwiseAdapter(),
    "manual": ManualAdapter(),
}


def get_adapter(provider: str) -> ThreadAdapter:
    if provider not in _REGISTRY:
        raise KeyError(f"unknown provider: {provider!r}")
    return _REGISTRY[provider]


def list_providers() -> list[str]:
    return sorted(_REGISTRY.keys())
```

注意此时 `ClaudeCodeAdapter` / `ManualAdapter` 还不存在；先建占位类，让 registry import 不挂：

Create `src/memory_mcp/threads/adapters/claude_code.py`（占位骨架，下个 chunk 写正文）:

```python
"""Claude Code adapter (placeholder — implemented in Chunk 2)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from ..models import ParsedThread, ParsedThreadDelta, ThreadSource
from .base import ThreadAdapter


class ClaudeCodeAdapter(ThreadAdapter):
    provider = "claude-code"

    def discover(self, root: Path) -> Iterator[ThreadSource]:
        raise NotImplementedError("implemented in Chunk 2")

    def parse(self, source: ThreadSource) -> ParsedThread:
        raise NotImplementedError("implemented in Chunk 2")

    def incremental_payload(self, raw_event: dict[str, Any]) -> ParsedThreadDelta | None:
        raise NotImplementedError("implemented in Chunk 2")
```

Create `src/memory_mcp/threads/adapters/manual.py`（占位骨架，下个 chunk 完整实现）:

```python
"""Manual adapter (placeholder — implemented in Chunk 2)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from ..models import ParsedThread, ParsedThreadDelta, ThreadSource
from .base import ThreadAdapter


class ManualAdapter(ThreadAdapter):
    provider = "manual"

    def discover(self, root: Path) -> Iterator[ThreadSource]:
        raise NotImplementedError("implemented in Chunk 2")

    def parse(self, source: ThreadSource) -> ParsedThread:
        raise NotImplementedError("implemented in Chunk 2")

    def incremental_payload(self, raw_event: dict[str, Any]) -> ParsedThreadDelta | None:
        raise NotImplementedError("implemented in Chunk 2")
```

补充 stub 断言测试到 `tests/test_threads_adapter_stubs.py`：

```python
class TestStubAdapters:
    def test_codex_discover_raises(self, tmp_path):
        from memory_mcp.threads.registry import get_adapter

        with pytest.raises(NotImplementedError):
            list(get_adapter("codex").discover(tmp_path))

    def test_chatwise_parse_raises(self, tmp_path):
        from memory_mcp.threads.adapters.base import ThreadAdapter
        from memory_mcp.threads.models import ThreadSource
        from memory_mcp.threads.registry import get_adapter

        f = tmp_path / "x.json"
        f.write_text("{}")
        adapter: ThreadAdapter = get_adapter("chatwise")
        src = ThreadSource(provider="chatwise", ref=str(f), path=f, mtime=0)
        with pytest.raises(NotImplementedError):
            adapter.parse(src)
```

- [ ] **Step 5: 跑 PASS**

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/threads/adapters/ src/memory_mcp/threads/registry.py tests/test_threads_adapter_stubs.py
git commit -m "feat(threads): add ThreadAdapter ABC + registry with stub providers"
```

---

## Chunk 2: claude-code adapter 完整实现 + manual

### Task 4: claude-code parse / discover

**Files:**
- Modify: `src/memory_mcp/threads/adapters/claude_code.py`
- Create: `tests/fixtures/threads/claude-code/sample.jsonl`
- Create: `tests/fixtures/threads/claude-code/empty.jsonl`
- Create: `tests/fixtures/threads/claude-code/malformed.jsonl`
- Create: `tests/test_threads_adapter_claude_code.py`

#### claude-code jsonl 真实格式约定（Phase 1）

服务端读到每行 1 个 JSON object，关键字段：

```jsonc
{
  "type": "user" | "assistant" | "system" | "tool_use" | "tool_result" | "summary",
  "uuid": "msg-uuid",
  "parentUuid": "...",
  "timestamp": "2026-05-21T10:11:12.345Z",
  "sessionId": "session-uuid",
  "cwd": "/path/to/project",
  "version": "2.x.x",
  "gitBranch": "main",
  "message": {
    "role": "user",
    "content": "..." | [ {"type":"text","text":"..."}, {"type":"tool_use", ...} ]
  }
}
```

- `seq` 由 adapter 按解析顺序赋值（行号 - 跳过行）。
- `thread_id` 取 source file 名（去 `.jsonl` 后缀）。
- `cwd` / `gitBranch` / `version` / `sessionId` 收入 `thread.metadata`。
- `summary` 类型抽 `summary` 字段写入 `thread.title`（如无 title 则用首条 user message 前 60 字）。
- `tool_use` / `tool_result` 行 role 标 `tool`，content 转 JSON 文本，原结构存 metadata。
- 无 `message` 或不可解析的行跳过；解析错误不抛、计入 warning 日志。

- [ ] **Step 1: 创建 fixture sample.jsonl**

Create `tests/fixtures/threads/claude-code/sample.jsonl`（12 条混合消息）:

```jsonl
{"type":"summary","summary":"Debug memory-mcp sync flow","leafUuid":"u-001"}
{"type":"user","uuid":"u-001","parentUuid":null,"timestamp":"2026-05-21T10:00:00.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"user","content":"我想调试一下 sync"}}
{"type":"assistant","uuid":"a-001","parentUuid":"u-001","timestamp":"2026-05-21T10:00:01.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"assistant","content":[{"type":"text","text":"好的，我先看一下当前状态"}]}}
{"type":"assistant","uuid":"a-002","parentUuid":"a-001","timestamp":"2026-05-21T10:00:02.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-1","name":"Bash","input":{"command":"ls"}}]}}
{"type":"user","uuid":"u-002","parentUuid":"a-002","timestamp":"2026-05-21T10:00:03.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"tu-1","content":"file1\nfile2"}]}}
{"type":"assistant","uuid":"a-003","parentUuid":"u-002","timestamp":"2026-05-21T10:00:04.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"assistant","content":[{"type":"text","text":"找到两个文件"}]}}
{"type":"user","uuid":"u-003","parentUuid":"a-003","timestamp":"2026-05-21T10:00:05.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"user","content":"那继续"}}
{"type":"assistant","uuid":"a-004","parentUuid":"u-003","timestamp":"2026-05-21T10:00:06.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"assistant","content":[{"type":"text","text":"读取 sync.py"}]}}
{"type":"user","uuid":"u-004","parentUuid":"a-004","timestamp":"2026-05-21T10:00:07.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"user","content":"中文搜索能命中吗"}}
{"type":"assistant","uuid":"a-005","parentUuid":"u-004","timestamp":"2026-05-21T10:00:08.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"assistant","content":[{"type":"text","text":"会，FTS5 + jieba 分词。"}]}}
{"type":"user","uuid":"u-005","parentUuid":"a-005","timestamp":"2026-05-21T10:00:09.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"user","content":"OK 收工"}}
{"type":"assistant","uuid":"a-006","parentUuid":"u-005","timestamp":"2026-05-21T10:00:10.000Z","sessionId":"s-1","cwd":"/Users/test/proj","version":"2.0.0","gitBranch":"main","message":{"role":"assistant","content":[{"type":"text","text":"已完成。"}]}}
```

Create `tests/fixtures/threads/claude-code/empty.jsonl`（空文件）— 0 字节。

Create `tests/fixtures/threads/claude-code/malformed.jsonl`：

```jsonl
{"type":"user","uuid":"u-001","timestamp":"2026-05-21T10:00:00.000Z","message":{"role":"user","content":"good"}}
this is not json
{"type":"assistant","uuid":"a-001","timestamp":"2026-05-21T10:00:01.000Z","message":{"role":"assistant","content":"also good"}}
{"type":"unknown-event"}
{"type":"user","uuid":"u-002","timestamp":"bad-ts","message":{"role":"user","content":"ts parse should not crash"}}
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_threads_adapter_claude_code.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "threads" / "claude-code"


@pytest.fixture()
def adapter():
    from memory_mcp.threads.adapters.claude_code import ClaudeCodeAdapter

    return ClaudeCodeAdapter()


@pytest.fixture()
def sample_path():
    return FIXTURE_DIR / "sample.jsonl"


@pytest.fixture()
def source_for(adapter):
    from memory_mcp.threads.models import ThreadSource

    def _make(path: Path):
        return ThreadSource(
            provider="claude-code",
            ref=path.stem,
            path=path,
            mtime=int(path.stat().st_mtime),
        )

    return _make


class TestParse:
    def test_returns_parsed_thread(self, adapter, source_for, sample_path):
        thread = adapter.parse(source_for(sample_path))
        assert thread.source_provider == "claude-code"
        assert thread.thread_id == sample_path.stem

    def test_messages_have_strictly_increasing_seq(self, adapter, source_for, sample_path):
        thread = adapter.parse(source_for(sample_path))
        seqs = [m.seq for m in thread.messages]
        assert seqs == sorted(set(seqs)) == list(range(len(seqs)))

    def test_roles_normalised(self, adapter, source_for, sample_path):
        thread = adapter.parse(source_for(sample_path))
        assert set(m.role for m in thread.messages) <= {"user", "assistant", "tool", "system"}

    def test_tool_use_role_is_tool(self, adapter, source_for, sample_path):
        thread = adapter.parse(source_for(sample_path))
        tool_msgs = [m for m in thread.messages if m.role == "tool"]
        assert tool_msgs, "expected at least one tool message"
        assert any("tu-1" in m.metadata.get("tool_use_id", "") or
                   "tu-1" in str(m.metadata) for m in tool_msgs)

    def test_text_content_extracted_from_blocks(self, adapter, source_for, sample_path):
        thread = adapter.parse(source_for(sample_path))
        contents = [m.content for m in thread.messages if m.role == "assistant"]
        joined = "\n".join(contents)
        assert "FTS5" in joined or "jieba" in joined

    def test_metadata_carries_project_info(self, adapter, source_for, sample_path):
        thread = adapter.parse(source_for(sample_path))
        assert thread.metadata.get("cwd") == "/Users/test/proj"
        assert thread.metadata.get("sessionId") == "s-1"
        assert thread.metadata.get("gitBranch") == "main"

    def test_summary_becomes_title(self, adapter, source_for, sample_path):
        thread = adapter.parse(source_for(sample_path))
        assert thread.title == "Debug memory-mcp sync flow"

    def test_started_and_ended_at_set(self, adapter, source_for, sample_path):
        thread = adapter.parse(source_for(sample_path))
        assert isinstance(thread.started_at, datetime)
        assert isinstance(thread.ended_at, datetime)
        assert thread.started_at <= thread.ended_at

    def test_empty_file_returns_empty_thread(self, adapter, source_for):
        empty = FIXTURE_DIR / "empty.jsonl"
        thread = adapter.parse(source_for(empty))
        assert thread.messages == []
        assert thread.title is None

    def test_malformed_lines_skipped(self, adapter, source_for):
        bad = FIXTURE_DIR / "malformed.jsonl"
        thread = adapter.parse(source_for(bad))
        # 3 valid user/assistant messages (the 'unknown-event' is dropped, bad-ts kept w/ ts=None)
        roles = [m.role for m in thread.messages]
        assert roles.count("user") >= 2
        assert "assistant" in roles


class TestDiscover:
    def test_discovers_jsonl_files(self, adapter, tmp_path):
        # build a fake claude projects layout
        proj_a = tmp_path / "projects" / "-Users-x-projA"
        proj_a.mkdir(parents=True)
        (proj_a / "abc.jsonl").write_text("{}\n")
        (proj_a / "def.jsonl").write_text("{}\n")
        (proj_a / "ignore.txt").write_text("nope")

        sources = list(adapter.discover(tmp_path / "projects"))
        refs = {s.ref for s in sources}
        assert refs == {"abc", "def"}
        for s in sources:
            assert s.provider == "claude-code"
            assert s.path is not None and s.path.exists()
            assert s.mtime is not None

    def test_discovers_returns_iterator(self, adapter, tmp_path):
        out = adapter.discover(tmp_path)
        # iterator is fine even when empty
        assert list(out) == []


class TestIncrementalPayload:
    def test_basic_payload(self, adapter):
        from memory_mcp.threads.models import ParsedThreadDelta

        payload = {
            "thread_id": "abc",
            "source_ref": "abc",
            "thread_meta": {"cwd": "/p"},
            "messages": [
                {"seq": 5, "role": "user", "content": "hi", "ts": "2026-05-21T10:00:00Z"},
                {"seq": 6, "role": "assistant", "content": "hello", "ts": "2026-05-21T10:00:01Z"},
            ],
        }
        delta = adapter.incremental_payload(payload)
        assert isinstance(delta, ParsedThreadDelta)
        assert delta.thread_id == "abc"
        assert delta.source_provider == "claude-code"
        assert [m.seq for m in delta.messages] == [5, 6]

    def test_empty_messages_returns_none(self, adapter):
        assert adapter.incremental_payload({"thread_id": "x", "messages": []}) is None
        assert adapter.incremental_payload({}) is None
```

- [ ] **Step 3: 跑测试 FAIL**

- [ ] **Step 4: 实现 ClaudeCodeAdapter 正文**

Edit `src/memory_mcp/threads/adapters/claude_code.py`（完整覆盖）:

```python
"""Claude Code transcript adapter.

Reads ~/.claude/projects/<encoded>/*.jsonl, one event per line.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..models import ParsedMessage, ParsedThread, ParsedThreadDelta, ThreadSource
from .base import ThreadAdapter

logger = logging.getLogger("memory-mcp.threads.claude-code")

_THREAD_META_KEYS = ("cwd", "sessionId", "gitBranch", "version")
_VALID_ROLES = {"user", "assistant", "tool", "system"}


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        # Claude Code uses ISO8601 with Z suffix
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalise_role(message_block: dict[str, Any], event_type: str) -> str:
    role = (message_block or {}).get("role") or event_type
    if role in _VALID_ROLES:
        return role
    if role in ("tool_use", "tool_result"):
        return "tool"
    return "system"


def _flatten_content(content: Any) -> tuple[str, dict[str, Any]]:
    """Return (text, extras) — extras hold tool_use / tool_result raw block."""
    if isinstance(content, str):
        return content, {}
    if not isinstance(content, list):
        return json.dumps(content, ensure_ascii=False), {}

    texts: list[str] = []
    extras: dict[str, Any] = {}
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            texts.append(str(block.get("text", "")))
        elif btype == "tool_use":
            extras["tool_use_id"] = block.get("id")
            extras["tool_name"] = block.get("name")
            extras["tool_input"] = block.get("input")
            texts.append(f"[tool_use {block.get('name','?')}] {json.dumps(block.get('input'), ensure_ascii=False)}")
        elif btype == "tool_result":
            extras["tool_use_id"] = block.get("tool_use_id")
            res = block.get("content")
            extras["tool_result"] = res
            texts.append(f"[tool_result] {res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)}")
        else:
            texts.append(json.dumps(block, ensure_ascii=False))
    return "\n".join(t for t in texts if t), extras


def _is_tool_event(event: dict[str, Any]) -> bool:
    msg = event.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result") for b in content)


class ClaudeCodeAdapter(ThreadAdapter):
    provider = "claude-code"

    # ------------------------------------------------------------------ discover
    def discover(self, root: Path) -> Iterator[ThreadSource]:
        root = Path(root).expanduser()
        if not root.exists():
            return
        for path in sorted(root.rglob("*.jsonl")):
            try:
                mtime = int(path.stat().st_mtime)
            except OSError:
                continue
            yield ThreadSource(
                provider=self.provider,
                ref=path.stem,
                path=path,
                mtime=mtime,
            )

    # --------------------------------------------------------------------- parse
    def parse(self, source: ThreadSource) -> ParsedThread:
        path = source.path
        if path is None or not path.exists():
            raise FileNotFoundError(f"claude-code source not found: {source.ref}")

        messages: list[ParsedMessage] = []
        thread_meta: dict[str, Any] = {}
        title: str | None = None
        seq = 0
        ts_min: datetime | None = None
        ts_max: datetime | None = None

        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("claude-code: skipping malformed line %d in %s", line_no, path)
                    continue
                if not isinstance(event, dict):
                    continue

                # capture thread-level metadata from any event
                for k in _THREAD_META_KEYS:
                    if k in event and k not in thread_meta:
                        thread_meta[k] = event[k]

                etype = event.get("type")

                if etype == "summary" and title is None:
                    title = (event.get("summary") or "").strip() or None
                    continue

                msg_block = event.get("message")
                if not isinstance(msg_block, dict):
                    continue

                role = _normalise_role(msg_block, etype or "")
                if _is_tool_event(event):
                    role = "tool"

                content, extras = _flatten_content(msg_block.get("content"))
                if not content and not extras:
                    continue

                ts = _parse_ts(event.get("timestamp"))
                if ts is not None:
                    if ts_min is None or ts < ts_min:
                        ts_min = ts
                    if ts_max is None or ts > ts_max:
                        ts_max = ts

                metadata: dict[str, Any] = {"event_type": etype}
                if "uuid" in event:
                    metadata["uuid"] = event["uuid"]
                if "parentUuid" in event:
                    metadata["parent_uuid"] = event["parentUuid"]
                if extras:
                    metadata.update(extras)

                messages.append(
                    ParsedMessage(seq=seq, role=role, content=content, ts=ts, metadata=metadata)
                )
                seq += 1

        if title is None:
            first_user = next((m for m in messages if m.role == "user"), None)
            if first_user is not None:
                title = first_user.content.strip().splitlines()[0][:60] or None

        return ParsedThread(
            thread_id=source.ref,
            source_provider=self.provider,
            source_ref=source.ref,
            title=title,
            started_at=ts_min,
            ended_at=ts_max,
            metadata=thread_meta,
            messages=messages,
        )

    # ---------------------------------------------------- incremental_payload
    def incremental_payload(self, raw_event: dict[str, Any]) -> ParsedThreadDelta | None:
        if not isinstance(raw_event, dict):
            return None
        msgs_raw = raw_event.get("messages") or []
        if not msgs_raw:
            return None

        thread_id = raw_event.get("thread_id") or raw_event.get("source_ref")
        if not thread_id:
            return None

        messages: list[ParsedMessage] = []
        for m in msgs_raw:
            if not isinstance(m, dict):
                continue
            seq = m.get("seq")
            role = m.get("role", "user")
            content = m.get("content", "")
            if seq is None or not content:
                continue
            ts = _parse_ts(m.get("ts"))
            metadata = m.get("metadata") or {}
            messages.append(
                ParsedMessage(seq=int(seq), role=role, content=str(content), ts=ts, metadata=metadata)
            )

        if not messages:
            return None

        return ParsedThreadDelta(
            thread_id=str(thread_id),
            source_provider=self.provider,
            source_ref=str(raw_event.get("source_ref") or thread_id),
            thread_meta_patch=dict(raw_event.get("thread_meta") or {}),
            messages=messages,
        )
```

- [ ] **Step 5: 跑测试 PASS**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_threads_adapter_claude_code.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/threads/adapters/claude_code.py tests/test_threads_adapter_claude_code.py tests/fixtures/threads/claude-code/
git commit -m "feat(threads): implement claude-code adapter (discover/parse/incremental)"
```

### Task 5: manual adapter (markdown / json / plaintext)

**Files:**
- Modify: `src/memory_mcp/threads/adapters/manual.py`
- Create: `tests/fixtures/threads/manual/sample.md`
- Create: `tests/fixtures/threads/manual/sample.json`
- Create: `tests/fixtures/threads/manual/sample.txt`
- Create: `tests/test_threads_adapter_manual.py`

#### manual 格式约定

- markdown: `## user` / `## assistant` heading 分块，标题前可有 YAML frontmatter（含 `title:` / `provider:` / `started_at:`）。
- json: `{"title":..., "metadata":{}, "messages":[{"role":"user","content":"...","ts":"..."}]}`。
- plaintext: 整文件作为单条 `user` message，title 派生自首行（或 ref filename）。
- thread_id: 优先取 source ref（文件名）；显式 `--thread-id` 覆盖（通过 `ThreadSource.ref` 注入）。

- [ ] **Step 1: 创建 fixtures**

Create `tests/fixtures/threads/manual/sample.md`:

```markdown
---
title: Manual notes about FTS
---

## user
怎么开 FTS5 中文分词？

## assistant
用 jieba 应用层切词，存进 content_tokens 字段，FTS5 配 unicode61。

## user
明白了。
```

Create `tests/fixtures/threads/manual/sample.json`:

```json
{
  "title": "JSON sample",
  "metadata": {"source": "test"},
  "messages": [
    {"role": "user", "content": "first", "ts": "2026-05-21T08:00:00Z"},
    {"role": "assistant", "content": "second", "ts": "2026-05-21T08:00:01Z"}
  ]
}
```

Create `tests/fixtures/threads/manual/sample.txt`:

```text
Just a single user message.
Wrapped over
multiple lines.
```

- [ ] **Step 2: 写测试**

Create `tests/test_threads_adapter_manual.py`:

```python
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "threads" / "manual"


@pytest.fixture()
def adapter():
    from memory_mcp.threads.adapters.manual import ManualAdapter

    return ManualAdapter()


def _source(adapter, path: Path):
    from memory_mcp.threads.models import ThreadSource

    return ThreadSource(provider="manual", ref=path.stem, path=path, mtime=int(path.stat().st_mtime))


class TestParseMarkdown:
    def test_messages_split_by_heading(self, adapter):
        thread = adapter.parse(_source(adapter, FIXTURE_DIR / "sample.md"))
        roles = [m.role for m in thread.messages]
        assert roles == ["user", "assistant", "user"]

    def test_title_from_frontmatter(self, adapter):
        thread = adapter.parse(_source(adapter, FIXTURE_DIR / "sample.md"))
        assert thread.title == "Manual notes about FTS"

    def test_seq_monotonic(self, adapter):
        thread = adapter.parse(_source(adapter, FIXTURE_DIR / "sample.md"))
        assert [m.seq for m in thread.messages] == [0, 1, 2]


class TestParseJson:
    def test_parses_messages(self, adapter):
        thread = adapter.parse(_source(adapter, FIXTURE_DIR / "sample.json"))
        assert thread.title == "JSON sample"
        assert thread.metadata == {"source": "test"}
        assert len(thread.messages) == 2
        assert thread.messages[0].content == "first"
        assert thread.messages[1].ts is not None


class TestParsePlaintext:
    def test_single_user_message(self, adapter):
        thread = adapter.parse(_source(adapter, FIXTURE_DIR / "sample.txt"))
        assert len(thread.messages) == 1
        assert thread.messages[0].role == "user"
        assert "single user message" in thread.messages[0].content
        # title falls back to first line
        assert thread.title and thread.title.startswith("Just a single user message")


class TestDiscover:
    def test_discover_walks_directory(self, adapter, tmp_path):
        (tmp_path / "a.md").write_text("## user\nhi")
        (tmp_path / "b.json").write_text('{"messages":[]}')
        (tmp_path / "c.txt").write_text("plain")
        (tmp_path / "ignore.png").write_bytes(b"\x89PNG")
        refs = {s.ref for s in adapter.discover(tmp_path)}
        assert refs == {"a", "b", "c"}


class TestIncrementalPayload:
    def test_inline_content(self, adapter):
        payload = {
            "thread_id": "manual-x",
            "title": "Inline",
            "messages": [{"seq": 0, "role": "user", "content": "hello"}],
        }
        delta = adapter.incremental_payload(payload)
        assert delta is not None
        assert delta.thread_id == "manual-x"
        assert delta.messages[0].content == "hello"
```

- [ ] **Step 3: 跑 FAIL**

- [ ] **Step 4: 实现 manual adapter**

Edit `src/memory_mcp/threads/adapters/manual.py`（完整覆盖）:

```python
"""Manual adapter — markdown / json / plaintext.

Format detection by file extension:
    .md / .markdown -> markdown
    .json           -> json
    everything else -> plaintext
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from ..models import ParsedMessage, ParsedThread, ParsedThreadDelta, ThreadSource
from .base import ThreadAdapter

_HEADING_RE = re.compile(r"^##\s+(user|assistant|tool|system)\s*$", re.IGNORECASE)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FRONTMATTER_LINE_RE = re.compile(r"^\s*([a-zA-Z_][\w-]*)\s*:\s*(.+?)\s*$")
_VALID_EXTS = {".md", ".markdown", ".json", ".txt", ".text", ""}


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _strip_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        lm = _FRONTMATTER_LINE_RE.match(line)
        if lm:
            meta[lm.group(1)] = lm.group(2).strip().strip('"').strip("'")
    return meta, text[m.end():]


def _parse_markdown(text: str) -> tuple[dict[str, str], list[ParsedMessage]]:
    meta, body = _strip_frontmatter(text)
    messages: list[ParsedMessage] = []
    current_role: str | None = None
    current_lines: list[str] = []
    seq = 0

    def flush():
        nonlocal seq, current_role, current_lines
        if current_role and current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                messages.append(
                    ParsedMessage(seq=seq, role=current_role, content=content, ts=None, metadata={})
                )
                seq += 1
        current_lines = []

    for line in body.splitlines():
        h = _HEADING_RE.match(line.strip())
        if h:
            flush()
            current_role = h.group(1).lower()
        else:
            if current_role is None:
                # ignore text before first heading
                continue
            current_lines.append(line)
    flush()

    return meta, messages


def _parse_json(text: str) -> tuple[str | None, dict[str, Any], list[ParsedMessage]]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("manual json must be an object")
    title = data.get("title")
    metadata = data.get("metadata") or {}
    raw_messages = data.get("messages") or []
    out: list[ParsedMessage] = []
    for idx, m in enumerate(raw_messages):
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if not content:
            continue
        out.append(
            ParsedMessage(
                seq=int(m.get("seq", idx)),
                role=str(m.get("role", "user")),
                content=str(content),
                ts=_parse_ts(m.get("ts")),
                metadata=m.get("metadata") or {},
            )
        )
    return title, metadata, out


def _parse_plaintext(text: str) -> list[ParsedMessage]:
    body = text.strip()
    if not body:
        return []
    return [ParsedMessage(seq=0, role="user", content=body, ts=None, metadata={})]


class ManualAdapter(ThreadAdapter):
    provider = "manual"

    def discover(self, root: Path) -> Iterator[ThreadSource]:
        root = Path(root).expanduser()
        if not root.exists():
            return
        if root.is_file():
            candidates = [root]
        else:
            candidates = [p for p in sorted(root.iterdir()) if p.is_file()]
        for path in candidates:
            if path.suffix.lower() not in _VALID_EXTS:
                continue
            yield ThreadSource(
                provider=self.provider,
                ref=path.stem,
                path=path,
                mtime=int(path.stat().st_mtime),
            )

    def parse(self, source: ThreadSource) -> ParsedThread:
        path = source.path
        if path is None or not path.exists():
            raise FileNotFoundError(f"manual source not found: {source.ref}")
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()

        title: str | None = None
        metadata: dict[str, Any] = {}
        messages: list[ParsedMessage] = []
        started_at: datetime | None = None
        ended_at: datetime | None = None

        if suffix in (".md", ".markdown"):
            meta, messages = _parse_markdown(text)
            title = meta.get("title")
            metadata = {k: v for k, v in meta.items() if k != "title"}
        elif suffix == ".json":
            title, metadata, messages = _parse_json(text)
        else:
            messages = _parse_plaintext(text)
            if messages:
                title = messages[0].content.strip().splitlines()[0][:60]

        if title is None and messages:
            first_user = next((m for m in messages if m.role == "user"), None)
            if first_user is not None:
                title = first_user.content.strip().splitlines()[0][:60]

        ts_values = [m.ts for m in messages if m.ts is not None]
        if ts_values:
            started_at = min(ts_values)
            ended_at = max(ts_values)

        return ParsedThread(
            thread_id=source.ref,
            source_provider=self.provider,
            source_ref=source.ref,
            title=title,
            started_at=started_at,
            ended_at=ended_at,
            metadata=metadata,
            messages=messages,
        )

    def incremental_payload(self, raw_event: dict[str, Any]) -> ParsedThreadDelta | None:
        if not isinstance(raw_event, dict):
            return None
        msgs_raw = raw_event.get("messages") or []
        thread_id = raw_event.get("thread_id") or raw_event.get("source_ref")
        if not thread_id or not msgs_raw:
            return None
        messages: list[ParsedMessage] = []
        for idx, m in enumerate(msgs_raw):
            if not isinstance(m, dict):
                continue
            content = m.get("content")
            if not content:
                continue
            messages.append(
                ParsedMessage(
                    seq=int(m.get("seq", idx)),
                    role=str(m.get("role", "user")),
                    content=str(content),
                    ts=_parse_ts(m.get("ts")),
                    metadata=m.get("metadata") or {},
                )
            )
        if not messages:
            return None
        return ParsedThreadDelta(
            thread_id=str(thread_id),
            source_provider=self.provider,
            source_ref=str(raw_event.get("source_ref") or thread_id),
            thread_meta_patch={"title": raw_event["title"]} if raw_event.get("title") else {},
            messages=messages,
        )
```

- [ ] **Step 5: 跑 PASS**

- [ ] **Step 6: Commit**

```bash
git add src/memory_mcp/threads/adapters/manual.py tests/test_threads_adapter_manual.py tests/fixtures/threads/manual/
git commit -m "feat(threads): implement manual adapter (markdown/json/plaintext)"
```

---

## Chunk 3: sync.py（upsert / 增量 / sync-status）

### Task 6: sync upsert + 幂等

**Files:**
- Create: `src/memory_mcp/threads/sync.py`
- Create: `tests/test_threads_sync.py`

#### sync.py 行为约束

1. `upsert_thread(parsed: ParsedThread | ParsedThreadDelta) -> dict`
   - 若 `(source_provider, source_ref)` 存在：复用 thread_id，更新 title/metadata/last_synced_mtime/last_synced_seq/message_count。
   - 否则创建 thread 行（thread_id 来自 parsed）。
2. `append_messages(thread_id, messages: list[ParsedMessage]) -> list[str]`
   - 只插入 `seq > max(existing seq)`；同 seq 直接丢弃（保证幂等）。
   - 单条 content 超 64KB 截断 + warning，metadata 标 `truncated: true`。
   - 返回 new message_id 列表。
3. `get_sync_status(provider: str, refs: list[str]) -> dict[str, dict]`
   - 返回 `{ref: {last_synced_mtime, last_synced_seq, thread_id}}`，缺失 ref 返回 `{}`。
4. `apply_delta(delta: ParsedThreadDelta) -> dict`
   - 内部组合 upsert_thread + append_messages，更新 last_synced_*。

- [ ] **Step 1: 写失败测试**

Create `tests/test_threads_sync.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def sync_module(test_env):
    import importlib

    import memory_mcp.threads.sync as sync_mod
    importlib.reload(sync_mod)
    return sync_mod


def _make_thread(thread_id="t1", ref="ref-1", n_msgs=3, start_seq=0):
    from datetime import datetime, timezone

    from memory_mcp.threads.models import ParsedMessage, ParsedThread

    return ParsedThread(
        thread_id=thread_id,
        source_provider="claude-code",
        source_ref=ref,
        title="hello",
        started_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        metadata={"cwd": "/p"},
        messages=[
            ParsedMessage(seq=start_seq + i, role="user", content=f"m{i}", ts=None, metadata={})
            for i in range(n_msgs)
        ],
    )


class TestUpsertThread:
    async def test_new_thread_creates_row(self, sync_module):
        parsed = _make_thread()
        result = await sync_module.apply_full_thread(parsed)
        assert result["thread_id"] == "t1"
        assert result["new_message_ids"] == [f"t1:{i:06d}" for i in range(3)]
        assert result["created"] is True

    async def test_reapply_same_thread_is_idempotent(self, sync_module):
        parsed = _make_thread()
        first = await sync_module.apply_full_thread(parsed)
        second = await sync_module.apply_full_thread(parsed)
        assert second["new_message_ids"] == []
        assert second["created"] is False
        assert first["thread_id"] == second["thread_id"]

    async def test_append_only_new_seq(self, sync_module):
        parsed = _make_thread(n_msgs=2)
        await sync_module.apply_full_thread(parsed)
        bigger = _make_thread(n_msgs=4)
        result = await sync_module.apply_full_thread(bigger)
        # only seq 2 and 3 should appear
        assert result["new_message_ids"] == ["t1:000002", "t1:000003"]

    async def test_long_content_truncated(self, sync_module):
        from memory_mcp.threads.models import ParsedMessage, ParsedThread
        from datetime import datetime, timezone

        big = "x" * (70 * 1024)
        parsed = ParsedThread(
            thread_id="t-big", source_provider="claude-code", source_ref="r",
            title=None, started_at=None, ended_at=None, metadata={},
            messages=[ParsedMessage(seq=0, role="user", content=big, ts=None, metadata={})],
        )
        result = await sync_module.apply_full_thread(parsed)
        rows = await sync_module._fetch_messages_for_test("t-big")
        assert len(rows[0]["content"]) <= 64 * 1024
        assert rows[0]["metadata"].get("truncated") is True


class TestSyncStatus:
    async def test_returns_empty_for_unknown(self, sync_module):
        out = await sync_module.get_sync_status("claude-code", ["nope"])
        assert out == {}

    async def test_returns_mtime_seq_after_apply(self, sync_module):
        from memory_mcp.threads.models import ParsedThreadDelta, ParsedMessage

        parsed = _make_thread(thread_id="t-status", ref="ref-status", n_msgs=2)
        await sync_module.apply_full_thread(parsed, mtime=1717000000)
        out = await sync_module.get_sync_status("claude-code", ["ref-status"])
        assert "ref-status" in out
        assert out["ref-status"]["last_synced_seq"] == 1
        assert out["ref-status"]["last_synced_mtime"] == 1717000000


class TestApplyDelta:
    async def test_delta_appends_correctly(self, sync_module):
        from memory_mcp.threads.models import ParsedMessage, ParsedThreadDelta

        # seed
        await sync_module.apply_full_thread(_make_thread(thread_id="td", ref="rd", n_msgs=2))
        delta = ParsedThreadDelta(
            thread_id="td",
            source_provider="claude-code",
            source_ref="rd",
            thread_meta_patch={},
            messages=[
                ParsedMessage(seq=2, role="assistant", content="more", ts=None, metadata={}),
            ],
        )
        out = await sync_module.apply_delta(delta, mtime=1717000123)
        assert out["new_message_ids"] == ["td:000002"]
        status = await sync_module.get_sync_status("claude-code", ["rd"])
        assert status["rd"]["last_synced_seq"] == 2
        assert status["rd"]["last_synced_mtime"] == 1717000123

    async def test_delta_with_lower_seq_is_noop(self, sync_module):
        from memory_mcp.threads.models import ParsedMessage, ParsedThreadDelta

        await sync_module.apply_full_thread(_make_thread(thread_id="t-lo", ref="rlo", n_msgs=3))
        delta = ParsedThreadDelta(
            thread_id="t-lo",
            source_provider="claude-code",
            source_ref="rlo",
            thread_meta_patch={},
            messages=[ParsedMessage(seq=1, role="user", content="dup", ts=None, metadata={})],
        )
        out = await sync_module.apply_delta(delta)
        assert out["new_message_ids"] == []
```

- [ ] **Step 2: 跑 FAIL**

- [ ] **Step 3: 实现 sync.py**

Create `src/memory_mcp/threads/sync.py`:

```python
"""Threads sync — upsert + incremental + status.

Server-side only; CLI pushes here via REST. Idempotent.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from ..engine.tokenizer import tokenize
from ..storage.sqlite import get_db
from .ids import make_message_id
from .models import ParsedMessage, ParsedThread, ParsedThreadDelta

logger = logging.getLogger("memory-mcp.threads.sync")

MAX_CONTENT_BYTES = 64 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _truncate(content: str, metadata: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    encoded = content.encode("utf-8")
    if len(encoded) <= MAX_CONTENT_BYTES:
        return content, metadata
    truncated = encoded[:MAX_CONTENT_BYTES].decode("utf-8", errors="ignore")
    logger.warning(
        "thread message content truncated from %d to %d bytes", len(encoded), len(truncated.encode("utf-8"))
    )
    new_meta = dict(metadata)
    new_meta["truncated"] = True
    new_meta["original_bytes"] = len(encoded)
    return truncated, new_meta


async def _max_seq(db, thread_id: str) -> int:
    row = await db.fetchone(
        "SELECT COALESCE(MAX(seq), -1) AS max_seq FROM thread_messages WHERE thread_id = ?",
        (thread_id,),
    )
    return int(row["max_seq"]) if row else -1


async def _thread_exists(db, provider: str, source_ref: str) -> dict | None:
    return await db.fetchone(
        "SELECT thread_id, last_synced_mtime, last_synced_seq FROM threads "
        "WHERE source_provider = ? AND source_ref = ?",
        (provider, source_ref),
    )


async def _insert_messages(
    db,
    thread_id: str,
    messages: Iterable[ParsedMessage],
    start_seq_exclusive: int,
) -> list[str]:
    new_ids: list[str] = []
    rows = []
    for m in messages:
        if m.seq <= start_seq_exclusive:
            continue
        content, meta = _truncate(m.content, m.metadata)
        msg_id = make_message_id(thread_id, m.seq)
        ts_iso = m.ts.astimezone(timezone.utc).isoformat() if m.ts else None
        rows.append(
            (
                msg_id,
                thread_id,
                m.seq,
                m.role,
                content,
                ts_iso,
                json.dumps(meta, ensure_ascii=False),
            )
        )
        new_ids.append(msg_id)
    if rows:
        await db.executemany(
            "INSERT OR IGNORE INTO thread_messages "
            "(message_id, thread_id, seq, role, content, ts, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return new_ids


async def _upsert_thread_row(
    db,
    *,
    thread_id: str,
    provider: str,
    source_ref: str,
    title: str | None,
    started_at: datetime | None,
    ended_at: datetime | None,
    metadata: dict[str, Any],
    mtime: int | None,
    last_seq: int,
    message_count: int,
    created_at: datetime,
) -> bool:
    existing = await db.fetchone(
        "SELECT thread_id FROM threads WHERE thread_id = ?", (thread_id,)
    )
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
    if existing:
        await db.execute(
            "UPDATE threads SET title = COALESCE(?, title), "
            "started_at = COALESCE(?, started_at), "
            "ended_at = COALESCE(?, ended_at), "
            "metadata = ?, last_synced_mtime = COALESCE(?, last_synced_mtime), "
            "last_synced_seq = ?, message_count = ? "
            "WHERE thread_id = ?",
            (
                title,
                started_at.isoformat() if started_at else None,
                ended_at.isoformat() if ended_at else None,
                metadata_json,
                mtime,
                last_seq,
                message_count,
                thread_id,
            ),
        )
        return False
    await db.execute(
        "INSERT INTO threads "
        "(thread_id, source_provider, source_ref, title, started_at, ended_at, "
        " message_count, summary, metadata, last_synced_mtime, last_synced_seq, "
        " created_at, imported_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)",
        (
            thread_id,
            provider,
            source_ref,
            title,
            started_at.isoformat() if started_at else None,
            ended_at.isoformat() if ended_at else None,
            message_count,
            metadata_json,
            mtime,
            last_seq,
            created_at.isoformat(),
            created_at.isoformat(),
        ),
    )
    return True


async def apply_full_thread(parsed: ParsedThread, *, mtime: int | None = None) -> dict:
    """Idempotent insert/append for a fully parsed thread.

    Insert order matters — ``thread_messages.thread_id`` has a FK to
    ``threads.thread_id`` (spec §4.4), so we MUST upsert the threads row
    first whenever it doesn't already exist, then insert messages.
    """
    async with get_db() as db:
        async with db.transaction():
            existing = await _thread_exists(db, parsed.source_provider, parsed.source_ref)
            created = existing is None
            thread_id = parsed.thread_id if created else existing["thread_id"]

            # 1. Upsert threads row FIRST (FK requirement). For new threads we
            # initialise message_count=0 / last_synced_seq=-1; the second upsert
            # below patches those once messages are inserted.
            await _upsert_thread_row(
                db,
                thread_id=thread_id,
                provider=parsed.source_provider,
                source_ref=parsed.source_ref,
                title=parsed.title,
                started_at=parsed.started_at,
                ended_at=parsed.ended_at,
                metadata=parsed.metadata,
                mtime=mtime,
                last_seq=existing["last_synced_seq"] if existing and existing["last_synced_seq"] is not None else -1,
                message_count=0,
                created_at=_now(),
            )

            # 2. Now safe to insert messages.
            existing_max_seq = -1 if created else await _max_seq(db, thread_id)
            new_ids = await _insert_messages(db, thread_id, parsed.messages, existing_max_seq)

            new_last_seq = (
                max(existing_max_seq, max((m.seq for m in parsed.messages), default=-1))
            )
            new_count = await db.fetchone(
                "SELECT COUNT(*) AS c FROM thread_messages WHERE thread_id = ?",
                (thread_id,),
            )
            count_val = int(new_count["c"]) if new_count else len(new_ids)

            # 3. Patch threads row with final last_synced_seq / message_count.
            await db.execute(
                "UPDATE threads SET last_synced_seq = ?, message_count = ?, "
                "last_synced_mtime = COALESCE(?, last_synced_mtime) WHERE thread_id = ?",
                (new_last_seq, count_val, mtime, thread_id),
            )

    return {
        "thread_id": thread_id,
        "new_message_ids": new_ids,
        "created": created,
        "last_synced_seq": new_last_seq,
        "last_synced_mtime": mtime,
    }


async def apply_delta(delta: ParsedThreadDelta, *, mtime: int | None = None) -> dict:
    """Apply an incremental delta to an existing or new thread.

    Same FK-safe insert order as ``apply_full_thread``: threads row first,
    then messages, then patch counters.
    """
    async with get_db() as db:
        async with db.transaction():
            existing = await _thread_exists(db, delta.source_provider, delta.source_ref)
            created = existing is None
            thread_id = delta.thread_id if created else existing["thread_id"]

            # 1. Upsert threads row FIRST.
            title = delta.thread_meta_patch.get("title")
            await _upsert_thread_row(
                db,
                thread_id=thread_id,
                provider=delta.source_provider,
                source_ref=delta.source_ref,
                title=title,
                started_at=None,
                ended_at=None,
                metadata=delta.thread_meta_patch.get("metadata") or {},
                mtime=mtime,
                last_seq=existing["last_synced_seq"] if existing and existing["last_synced_seq"] is not None else -1,
                message_count=0,
                created_at=_now(),
            )

            # 2. Now safe to insert messages.
            existing_max_seq = -1 if created else await _max_seq(db, thread_id)
            new_ids = await _insert_messages(db, thread_id, delta.messages, existing_max_seq)

            new_last_seq = max(
                existing_max_seq,
                max((m.seq for m in delta.messages), default=existing_max_seq),
            )
            count_row = await db.fetchone(
                "SELECT COUNT(*) AS c FROM thread_messages WHERE thread_id = ?", (thread_id,)
            )
            count_val = int(count_row["c"]) if count_row else len(new_ids)

            # 3. Patch counters.
            await db.execute(
                "UPDATE threads SET last_synced_seq = ?, message_count = ?, "
                "last_synced_mtime = COALESCE(?, last_synced_mtime) WHERE thread_id = ?",
                (new_last_seq, count_val, mtime, thread_id),
            )

    return {
        "thread_id": thread_id,
        "new_message_ids": new_ids,
        "created": created,
        "last_synced_seq": new_last_seq,
        "last_synced_mtime": mtime,
    }


async def get_sync_status(provider: str, refs: list[str]) -> dict[str, dict]:
    if not refs:
        return {}
    placeholders = ",".join("?" * len(refs))
    async with get_db() as db:
        rows = await db.fetchall(
            f"SELECT thread_id, source_ref, last_synced_mtime, last_synced_seq "
            f"FROM threads WHERE source_provider = ? AND source_ref IN ({placeholders})",
            (provider, *refs),
        )
    return {
        r["source_ref"]: {
            "thread_id": r["thread_id"],
            "last_synced_mtime": r["last_synced_mtime"],
            "last_synced_seq": r["last_synced_seq"],
        }
        for r in rows
    }


# helper for tests only — not part of public API
async def _fetch_messages_for_test(thread_id: str) -> list[dict]:
    async with get_db() as db:
        rows = await db.fetchall(
            "SELECT seq, role, content, metadata FROM thread_messages WHERE thread_id = ? ORDER BY seq",
            (thread_id,),
        )
    return [
        {**dict(r), "metadata": json.loads(r["metadata"]) if r["metadata"] else {}}
        for r in rows
    ]
```

Note：测试中 `_fetch_messages_for_test` 命名以下划线开头表明仅供测试。

- [ ] **Step 4: 跑 PASS**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_threads_sync.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/threads/sync.py tests/test_threads_sync.py
git commit -m "feat(threads): add idempotent upsert/apply_delta + sync status"
```

---

## Chunk 4: REST + MCP tools 接入

### Task 7: REST 路由

**Files:**
- Modify: `src/memory_mcp/api/routes.py`
- Create: `tests/test_threads_api.py`

#### 路由设计

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/threads` | 分页 + provider + q (FTS5) |
| GET | `/api/v1/threads/{thread_id}` | 元数据 + with_messages 控制 |
| GET | `/api/v1/threads/{thread_id}/messages` | 消息分页 |
| POST | `/api/v1/threads/import` | 单文件/单 thread 全量导入 |
| POST | `/api/v1/threads/incremental` | 接收 batches 增量推送 |
| GET | `/api/v1/threads/sync-status` | `?provider=X&refs=a,b,c` |

- [ ] **Step 1: 写失败测试**

Create `tests/test_threads_api.py`:

```python
import importlib
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture()
def app(test_env):
    import memory_mcp.server as server_mod
    importlib.reload(server_mod)
    return server_mod.app


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def headers():
    return {"Authorization": "Bearer test-token"}


def _sample_batch(ref="r1", thread_id="t1", n=2, start_seq=0):
    return {
        "provider": "claude-code",
        "source_ref": ref,
        "thread_id": thread_id,
        "thread_meta": {"title": "demo", "metadata": {"cwd": "/p"}},
        "mtime": 1717000000,
        "messages": [
            {"seq": start_seq + i, "role": "user" if i % 2 == 0 else "assistant",
             "content": f"msg-{i}", "ts": None}
            for i in range(n)
        ],
    }


class TestIncrementalAndStatus:
    def test_incremental_creates_thread(self, client, headers):
        resp = client.post(
            "/api/v1/threads/incremental",
            json={"batches": [_sample_batch()]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        results = body["data"]["results"]
        assert len(results) == 1
        assert results[0]["thread_id"] == "t1"
        assert results[0]["new_message_ids"] == ["t1:000000", "t1:000001"]

    def test_sync_status_reflects_apply(self, client, headers):
        client.post(
            "/api/v1/threads/incremental",
            json={"batches": [_sample_batch()]},
            headers=headers,
        )
        resp = client.get(
            "/api/v1/threads/sync-status",
            params={"provider": "claude-code", "refs": "r1,nope"},
            headers=headers,
        )
        body = resp.json()["data"]
        assert "r1" in body["status"]
        assert body["status"]["r1"]["last_synced_seq"] == 1
        assert "nope" not in body["status"]

    def test_incremental_idempotent(self, client, headers):
        client.post("/api/v1/threads/incremental", json={"batches": [_sample_batch()]}, headers=headers)
        resp = client.post(
            "/api/v1/threads/incremental",
            json={"batches": [_sample_batch()]},
            headers=headers,
        )
        assert resp.json()["data"]["results"][0]["new_message_ids"] == []


class TestListAndGet:
    def test_list_and_get_thread(self, client, headers):
        client.post(
            "/api/v1/threads/incremental",
            json={"batches": [_sample_batch()]},
            headers=headers,
        )
        resp = client.get("/api/v1/threads", headers=headers)
        body = resp.json()["data"]
        assert body["total"] >= 1
        assert any(t["thread_id"] == "t1" for t in body["items"])

        resp2 = client.get("/api/v1/threads/t1", headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["data"]["thread_id"] == "t1"

    def test_messages_pagination(self, client, headers):
        client.post(
            "/api/v1/threads/incremental",
            json={"batches": [_sample_batch(n=5)]},
            headers=headers,
        )
        resp = client.get(
            "/api/v1/threads/t1/messages",
            params={"page": 1, "size": 2},
            headers=headers,
        )
        body = resp.json()["data"]
        assert body["total"] == 5
        assert len(body["items"]) == 2

    def test_search_with_fts(self, client, headers):
        client.post(
            "/api/v1/threads/incremental",
            json={"batches": [_sample_batch()]},
            headers=headers,
        )
        resp = client.get(
            "/api/v1/threads",
            params={"q": "msg"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1


class TestImport:
    def test_import_inline_markdown(self, client, headers):
        body = {
            "provider": "manual",
            "content": "## user\nhello there",
            "format": "markdown",
            "thread_id": "manual-1",
        }
        resp = client.post("/api/v1/threads/import", json=body, headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["thread_id"] == "manual-1"

    def test_import_file_path(self, client, headers, tmp_path):
        p = tmp_path / "n.md"
        p.write_text("## user\nfrom file")
        resp = client.post(
            "/api/v1/threads/import",
            json={"provider": "manual", "path": str(p)},
            headers=headers,
        )
        assert resp.status_code == 200
```

- [ ] **Step 2: 跑 FAIL**

- [ ] **Step 3: 实现 REST 路由**

> **替换 M2 placeholder**：M2 Task 21 在 `routes` 列表里注册了 6 个 `_phase_m3()` placeholder（threads list/get/messages/import/incremental/sync-status）。M3 删除这 6 行 + `_phase_m3` helper + 对应 handler 后再追加下面的真实实现，避免双重注册。

Edit `src/memory_mcp/api/routes.py` — 先删除 M2 的 6 条 placeholder route 与 `handle_threads_*` 占位 handler、`_phase_m3` helper（M3 这块全部接管）。然后在文件底部 `routes = [...]` 之前追加真实 handler，并在 `routes` 列表中插入对应 `Route`。

Append handlers:

```python
# ============================================================================
# threads
# ============================================================================

from ..threads import sync as threads_sync
from ..threads.adapters.base import ThreadAdapter
from ..threads.models import ParsedMessage, ParsedThread, ParsedThreadDelta, ThreadSource
from ..threads.registry import get_adapter, list_providers as registry_list_providers


def _coerce_batch_to_delta(batch: dict) -> ParsedThreadDelta:
    provider = batch.get("provider")
    if not provider:
        raise ValueError("batch.provider is required")
    adapter: ThreadAdapter = get_adapter(provider)
    delta = adapter.incremental_payload(batch)
    if delta is None:
        raise ValueError("batch produced no messages")
    return delta


# POST /api/v1/threads/incremental
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
            results.append({**result, "source_ref": delta.source_ref})
        except KeyError as exc:
            errors.append({"batch_ref": batch.get("source_ref"), "error": f"unknown provider: {exc}"})
        except ValueError as exc:
            errors.append({"batch_ref": batch.get("source_ref"), "error": str(exc)})
        except Exception as exc:
            errors.append({"batch_ref": batch.get("source_ref"), "error": str(exc)})
    return ok({"results": results, "errors": errors})


# GET /api/v1/threads/sync-status?provider=X&refs=a,b,c
async def handle_threads_sync_status(request: Request) -> JSONResponse:
    provider = request.query_params.get("provider")
    refs_param = request.query_params.get("refs", "")
    if not provider:
        return err("Missing required query param: provider")
    refs = [r.strip() for r in refs_param.split(",") if r.strip()]
    status = await threads_sync.get_sync_status(provider, refs)
    return ok({"provider": provider, "status": status})


# GET /api/v1/threads
async def handle_threads_list(request: Request) -> JSONResponse:
    from ..tools import thread_search as thread_search_mod

    params = request.query_params
    arguments = {
        "page": int(params.get("page", "1")),
        "size": int(params.get("size", "20")),
    }
    if "provider" in params:
        arguments["provider"] = params["provider"]
    if "q" in params:
        arguments["q"] = params["q"]
    try:
        result = await thread_search_mod.thread_search_tool(arguments)
    except ValueError as exc:
        return err(str(exc))
    return ok(result)


# GET /api/v1/threads/{thread_id}
async def handle_threads_get(request: Request) -> JSONResponse:
    from ..tools import thread_get as thread_get_mod

    tid = request.path_params["thread_id"]
    args = {"thread_id": tid, "with_messages": request.query_params.get("with_messages", "").lower() == "true"}
    try:
        result = await thread_get_mod.thread_get_tool(args)
    except ValueError as exc:
        return err(str(exc), 404)
    return ok(result)


# GET /api/v1/threads/{thread_id}/messages
async def handle_threads_messages(request: Request) -> JSONResponse:
    from ..tools import thread_get as thread_get_mod

    tid = request.path_params["thread_id"]
    page = int(request.query_params.get("page", "1"))
    size = int(request.query_params.get("size", "50"))
    try:
        result = await thread_get_mod.thread_messages_page(tid, page=page, size=size)
    except ValueError as exc:
        return err(str(exc), 404)
    return ok(result)


# POST /api/v1/threads/import
async def handle_threads_import(request: Request) -> JSONResponse:
    from ..tools import thread_import as thread_import_mod

    try:
        body = await request.json()
    except Exception:
        return err("Invalid JSON body")
    try:
        result = await thread_import_mod.thread_import_tool(body)
    except ValueError as exc:
        return err(str(exc))
    except KeyError as exc:
        return err(f"unknown provider: {exc}")
    return ok(result)


# GET /api/v1/threads/providers
async def handle_threads_providers(request: Request) -> JSONResponse:
    return ok({"providers": registry_list_providers()})
```

Append routes to the `routes = [...]` list（保持 path 顺序：sync-status 在 `{thread_id}` 之前）：

```python
    Route("/api/v1/threads/incremental", endpoint=handle_threads_incremental, methods=["POST"]),
    Route("/api/v1/threads/sync-status", endpoint=handle_threads_sync_status, methods=["GET"]),
    Route("/api/v1/threads/import", endpoint=handle_threads_import, methods=["POST"]),
    Route("/api/v1/threads/providers", endpoint=handle_threads_providers, methods=["GET"]),
    Route("/api/v1/threads", endpoint=handle_threads_list, methods=["GET"]),
    Route("/api/v1/threads/{thread_id}/messages", endpoint=handle_threads_messages, methods=["GET"]),
    Route("/api/v1/threads/{thread_id}", endpoint=handle_threads_get, methods=["GET"]),
```

- [ ] **Step 4: 跑 PASS**

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/api/routes.py tests/test_threads_api.py
git commit -m "feat(api): wire threads REST endpoints (incremental/sync-status/list/get/import)"
```

### Task 8: 实现 4 个 MCP thread_* 工具

**Files:**
- Modify: `src/memory_mcp/tools/thread_search.py`
- Modify: `src/memory_mcp/tools/thread_get.py`
- Modify: `src/memory_mcp/tools/thread_import.py`
- Modify: `src/memory_mcp/tools/thread_list_providers.py`
- Create: `tests/test_threads_tools.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_threads_tools.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def seeded(test_env):
    """Seed one thread via apply_full_thread for downstream tool tests."""
    from datetime import datetime, timezone

    import importlib

    import memory_mcp.threads.sync as sync_mod
    importlib.reload(sync_mod)

    from memory_mcp.threads.models import ParsedMessage, ParsedThread

    parsed = ParsedThread(
        thread_id="t-tool",
        source_provider="claude-code",
        source_ref="r-tool",
        title="Test thread",
        started_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        metadata={"cwd": "/x"},
        messages=[
            ParsedMessage(seq=0, role="user", content="中文搜索 jieba", ts=None, metadata={}),
            ParsedMessage(seq=1, role="assistant", content="支持 unicode61", ts=None, metadata={}),
        ],
    )
    await sync_mod.apply_full_thread(parsed)
    return parsed


class TestThreadListProviders:
    async def test_returns_known_providers(self, test_env):
        from memory_mcp.tools.thread_list_providers import thread_list_providers_tool

        out = await thread_list_providers_tool({})
        assert "claude-code" in out["providers"]
        assert "manual" in out["providers"]


class TestThreadGet:
    async def test_get_metadata_only(self, seeded):
        from memory_mcp.tools.thread_get import thread_get_tool

        out = await thread_get_tool({"thread_id": "t-tool"})
        assert out["thread_id"] == "t-tool"
        assert "messages" not in out

    async def test_get_with_messages(self, seeded):
        from memory_mcp.tools.thread_get import thread_get_tool

        out = await thread_get_tool({"thread_id": "t-tool", "with_messages": True})
        assert len(out["messages"]) == 2

    async def test_get_missing_raises(self, seeded):
        from memory_mcp.tools.thread_get import thread_get_tool

        with pytest.raises(ValueError):
            await thread_get_tool({"thread_id": "nope"})


class TestThreadSearch:
    async def test_search_chinese(self, seeded):
        from memory_mcp.tools.thread_search import thread_search_tool

        out = await thread_search_tool({"q": "中文搜索"})
        assert out["total"] >= 1
        assert any(t["thread_id"] == "t-tool" for t in out["items"])

    async def test_filter_by_provider(self, seeded):
        from memory_mcp.tools.thread_search import thread_search_tool

        out = await thread_search_tool({"provider": "claude-code"})
        assert any(t["thread_id"] == "t-tool" for t in out["items"])


class TestThreadImport:
    async def test_import_inline_markdown(self, test_env):
        from memory_mcp.tools.thread_import import thread_import_tool

        out = await thread_import_tool(
            {"provider": "manual", "content": "## user\nhi", "format": "markdown", "thread_id": "manual-x"}
        )
        assert out["thread_id"] == "manual-x"
        assert out["created"] is True
```

- [ ] **Step 2: 实现 thread_list_providers**

Replace `src/memory_mcp/tools/thread_list_providers.py`:

```python
from ..threads.registry import list_providers


async def thread_list_providers_tool(arguments: dict) -> dict:  # noqa: ARG001
    return {"providers": list_providers()}
```

- [ ] **Step 3: 实现 thread_get**

Replace `src/memory_mcp/tools/thread_get.py`:

```python
"""Thread fetch — metadata only or with paginated messages."""
from __future__ import annotations

import json

from ..storage.sqlite import get_db


async def _row_to_thread(row) -> dict:
    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
    return {
        "thread_id": row["thread_id"],
        "source_provider": row["source_provider"],
        "source_ref": row["source_ref"],
        "title": row["title"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "message_count": row["message_count"],
        "summary": row["summary"],
        "metadata": metadata,
        "last_synced_mtime": row["last_synced_mtime"],
        "last_synced_seq": row["last_synced_seq"],
        "created_at": row["created_at"],
        "imported_at": row["imported_at"],
    }


async def _fetch_extracted_memory_ids(db, message_ids: list[str]) -> dict[str, list[str]]:
    """Return ``{message_id: [memory_id, ...]}`` for any messages a memory cites.

    The mapping is derived from ``memories.source_refs`` JSON column: each ref
    contains ``{thread_id, message_id}``. The Web UI uses this to mark messages
    that produced memories (spec §7.1/§7.2 "关联 memory 标记").
    """
    if not message_ids:
        return {}
    # SQLite JSON1 + each row: scan only current memories. For 10-100 messages
    # per thread page this is cheap; if the corpus grows we'll add a dedicated
    # extraction_links table.
    placeholders = ",".join("?" * len(message_ids))
    rows = await db.fetchall(
        "SELECT id, source_refs FROM memories WHERE source_refs IS NOT NULL "
        "AND EXISTS (SELECT 1 FROM json_each(memories.source_refs) je "
        f"WHERE json_extract(je.value, '$.message_id') IN ({placeholders}))",
        tuple(message_ids),
    )
    out: dict[str, list[str]] = {mid: [] for mid in message_ids}
    for r in rows:
        try:
            refs = json.loads(r["source_refs"]) or []
        except json.JSONDecodeError:
            continue
        for ref in refs:
            msg_id = ref.get("message_id") if isinstance(ref, dict) else None
            if msg_id in out:
                out[msg_id].append(r["id"])
    return out


async def _fetch_messages(db, thread_id: str, *, page: int = 1, size: int = 50) -> dict:
    offset = (page - 1) * size
    rows = await db.fetchall(
        "SELECT message_id, seq, role, content, ts, metadata FROM thread_messages "
        "WHERE thread_id = ? ORDER BY seq LIMIT ? OFFSET ?",
        (thread_id, size, offset),
    )
    total_row = await db.fetchone(
        "SELECT COUNT(*) AS c FROM thread_messages WHERE thread_id = ?", (thread_id,)
    )
    total = int(total_row["c"]) if total_row else 0

    message_ids = [r["message_id"] for r in rows]
    extracted_map = await _fetch_extracted_memory_ids(db, message_ids)

    items = [
        {
            "message_id": r["message_id"],
            "seq": r["seq"],
            "role": r["role"],
            "content": r["content"],
            "ts": r["ts"],
            "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
            # spec §7.1 / Web UI ThreadMessages: empty list when no memory cites it.
            "extracted_memory_ids": extracted_map.get(r["message_id"], []),
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "size": size}


async def thread_get_tool(arguments: dict) -> dict:
    tid = arguments.get("thread_id")
    if not tid:
        raise ValueError("thread_id is required")
    with_messages = bool(arguments.get("with_messages", False))
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT thread_id, source_provider, source_ref, title, started_at, ended_at, "
            "message_count, summary, metadata, last_synced_mtime, last_synced_seq, "
            "created_at, imported_at FROM threads WHERE thread_id = ?",
            (tid,),
        )
        if not row:
            raise ValueError(f"thread not found: {tid}")
        out = await _row_to_thread(row)
        if with_messages:
            paged = await _fetch_messages(db, tid, page=1, size=10_000)
            out["messages"] = paged["items"]
    return out


async def thread_messages_page(thread_id: str, *, page: int = 1, size: int = 50) -> dict:
    async with get_db() as db:
        row = await db.fetchone(
            "SELECT 1 FROM threads WHERE thread_id = ?", (thread_id,)
        )
        if not row:
            raise ValueError(f"thread not found: {thread_id}")
        return await _fetch_messages(db, thread_id, page=page, size=size)
```

- [ ] **Step 4: 实现 thread_search**

Replace `src/memory_mcp/tools/thread_search.py`:

```python
"""Thread list / search with FTS5 (jieba pre-tokenized at write time)."""
from __future__ import annotations

import json

from ..engine.tokenizer import tokenize
from ..storage.sqlite import get_db


async def thread_search_tool(arguments: dict) -> dict:
    page = int(arguments.get("page", 1))
    size = int(arguments.get("size", 20))
    if page < 1 or size < 1 or size > 200:
        raise ValueError("invalid page/size")
    provider = arguments.get("provider")
    q = (arguments.get("q") or "").strip()

    where = []
    params: list = []
    if provider:
        where.append("t.source_provider = ?")
        params.append(provider)

    fts_join = ""
    if q:
        tokenized = tokenize(q)
        match_expr = " ".join(part for part in tokenized.split() if part)
        if match_expr:
            fts_join = (
                "JOIN thread_messages tm ON tm.thread_id = t.thread_id "
                "JOIN thread_messages_fts fts ON fts.rowid = tm.rowid "
            )
            where.append("fts.thread_messages_fts MATCH ?")
            params.append(match_expr)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    async with get_db() as db:
        total_row = await db.fetchone(
            f"SELECT COUNT(DISTINCT t.thread_id) AS c FROM threads t {fts_join} {where_sql}",
            tuple(params),
        )
        total = int(total_row["c"]) if total_row else 0
        rows = await db.fetchall(
            f"SELECT DISTINCT t.thread_id, t.source_provider, t.source_ref, t.title, "
            f"t.started_at, t.ended_at, t.message_count "
            f"FROM threads t {fts_join} {where_sql} "
            f"ORDER BY COALESCE(t.ended_at, t.created_at) DESC LIMIT ? OFFSET ?",
            (*params, size, (page - 1) * size),
        )
    items = [dict(r) for r in rows]
    return {"items": items, "total": total, "page": page, "size": size}
```

- [ ] **Step 5: 实现 thread_import**

Replace `src/memory_mcp/tools/thread_import.py`:

```python
"""Single-shot import: parse a file/inline content and apply_full_thread."""
from __future__ import annotations

import tempfile
from pathlib import Path

from ..threads import sync as threads_sync
from ..threads.models import ThreadSource
from ..threads.registry import get_adapter

_EXT_BY_FORMAT = {
    "markdown": ".md",
    "json": ".json",
    "plaintext": ".txt",
    "text": ".txt",
}


async def thread_import_tool(arguments: dict) -> dict:
    provider = arguments.get("provider")
    if not provider:
        raise ValueError("provider is required")
    adapter = get_adapter(provider)

    path = arguments.get("path")
    content = arguments.get("content")
    if not path and not content:
        raise ValueError("path or content is required")

    fmt = arguments.get("format")
    thread_id = arguments.get("thread_id")

    if path:
        p = Path(path).expanduser()
        if not p.exists():
            raise ValueError(f"path not found: {p}")
        ref = thread_id or p.stem
        source = ThreadSource(
            provider=provider,
            ref=ref,
            path=p,
            mtime=int(p.stat().st_mtime),
        )
    else:
        suffix = _EXT_BY_FORMAT.get(fmt or "markdown", ".md")
        tmp = Path(tempfile.mkstemp(suffix=suffix, prefix="mem-import-")[1])
        tmp.write_text(content, encoding="utf-8")
        ref = thread_id or tmp.stem
        source = ThreadSource(
            provider=provider,
            ref=ref,
            path=tmp,
            mtime=int(tmp.stat().st_mtime),
        )

    parsed = adapter.parse(source)
    # overlay caller-supplied thread_id
    if thread_id:
        parsed.thread_id = thread_id
        parsed.source_ref = thread_id
    if arguments.get("title"):
        parsed.title = arguments["title"]

    return await threads_sync.apply_full_thread(parsed, mtime=source.mtime)
```

- [ ] **Step 6: 跑 PASS**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_threads_tools.py -v`

- [ ] **Step 7: 切换 server dispatcher 从 M2 stub 到真实模块**

M2 Task 22 在 `src/memory_mcp/server.py` 把 thread_* tools 全部 dispatch 到 `tools.thread_stub`；现在 4 个真实模块就绪，删除 stub 引用。

Edit `src/memory_mcp/server.py`:

(a) 改 imports — 把 `thread_stub` 一行替换为：

```python
from .tools import (
    remember, recall, trace, forget, relate, unrelate, graph_query, recall_all,
    memory_crud, hybrid_search as hs_tool,
    thread_search, thread_get, thread_import, thread_list_providers,
)
```

(b) 改 dispatcher 4 个分支：

```python
        elif name == "thread_search":
            result = await thread_search.thread_search_tool(arguments)
        elif name == "thread_get":
            result = await thread_get.thread_get_tool(arguments)
        elif name == "thread_import":
            result = await thread_import.thread_import_tool(arguments)
        elif name == "thread_list_providers":
            result = await thread_list_providers.thread_list_providers_tool(arguments)
```

(c) 删除 `src/memory_mcp/tools/thread_stub.py` 与 `tests/test_thread_stubs.py`（M2 compatibility shim 使命完成）：

```bash
git rm src/memory_mcp/tools/thread_stub.py tests/test_thread_stubs.py
```

(d) 更新 `tests/test_server_tools.py` 的 reload 列表与断言，把 `thread_stub` 改为四个真实模块的导入。

- [ ] **Step 8: Commit**

```bash
git add src/memory_mcp/tools/thread_search.py src/memory_mcp/tools/thread_get.py src/memory_mcp/tools/thread_import.py src/memory_mcp/tools/thread_list_providers.py src/memory_mcp/server.py tests/test_threads_tools.py tests/test_server_tools.py
git commit -m "feat(threads): wire MCP thread_* tools and retire M2 compatibility shim"
```

---

## Chunk 5: extraction 透传 source_refs

### Task 9: extraction 支持 source_thread_id + source_refs

**Files:**
- Modify: `src/memory_mcp/engine/extraction.py`
- Modify: `src/memory_mcp/tools/remember.py`
- Modify: `src/memory_mcp/api/routes.py` (handle_extract)
- Create: `tests/test_extraction_source_refs.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_extraction_source_refs.py`:

```python
import json
from unittest.mock import patch, AsyncMock

import pytest

pytestmark = pytest.mark.asyncio


class TestExtractionRefs:
    async def test_extracted_memory_carries_refs(self, test_env, monkeypatch):
        from memory_mcp.engine import extraction
        from memory_mcp.tools import remember as remember_mod

        # mock LLM
        async def fake_call_llm(messages):
            return json.dumps([
                {"entity_key": "preference:editor", "entity_type": "preference", "content": "Cursor"}
            ])

        monkeypatch.setattr(extraction, "_call_llm", fake_call_llm)

        captured = {}

        async def spy_remember(args):
            captured["args"] = args
            return {"status": "created", "memory_id": "m-1"}

        monkeypatch.setattr(remember_mod, "remember_tool", spy_remember)

        result = await extraction.extract_memories(
            [{"role": "user", "content": "use cursor"}],
            source_thread_id="t-x",
            source_refs=[{"thread_id": "t-x", "message_id": "t-x:000003"}],
            origin_client="claude-code",
            origin_session_id="s-1",
        )
        assert result["total"] == 1
        # the remember_tool call must include the refs and origin info
        args = captured["args"]
        assert args["source_thread_id"] == "t-x"
        assert args["source_refs"] == [{"thread_id": "t-x", "message_id": "t-x:000003"}]
        assert args["origin_client"] == "claude-code"
        assert args["origin_session_id"] == "s-1"


class TestRememberRefsPassthrough:
    async def test_remember_tool_accepts_refs(self, test_env, monkeypatch):
        from memory_mcp.tools import remember as remember_mod

        captured = {}

        async def fake_insert(node):
            captured["node"] = node

        # stub the storage layer
        import memory_mcp.storage.vector as vector
        monkeypatch.setattr(vector.vector_store, "insert", fake_insert)
        monkeypatch.setattr(vector.vector_store, "get_history", AsyncMock(return_value=[]))
        monkeypatch.setattr(vector.vector_store, "search", AsyncMock(return_value=[]))

        result = await remember_mod.remember_tool({
            "content": "x",
            "entity_key": "k",
            "entity_type": "fact",
            "source_thread_id": "t",
            "source_refs": [{"thread_id": "t", "message_id": "t:000001"}],
            "origin_client": "claude-code",
            "origin_session_id": "s-1",
            "skip_semantic_merge": True,
        })
        node = captured["node"]
        assert node.source_thread_id == "t"
        assert node.source_refs == [{"thread_id": "t", "message_id": "t:000001"}]
        assert node.origin_client == "claude-code"
        assert node.origin_session_id == "s-1"
```

- [ ] **Step 2: 跑 FAIL**

- [ ] **Step 3: 修改 extraction.py**

Edit `src/memory_mcp/engine/extraction.py` — 修改 `extract_memories` 签名并将 refs 透传：

```python
async def extract_memories(
    messages: list[dict],
    *,
    source_thread_id: str | None = None,
    source_refs: list[dict] | None = None,
    origin_client: str | None = None,
    origin_session_id: str | None = None,
) -> dict:
    try:
        llm_output = await _call_llm(messages)
    except Exception as exc:
        raise ExtractionError("LLM extraction failed") from exc

    candidates = _parse_llm_output(llm_output)

    results = []
    errors = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        entity_key = candidate.get("entity_key")
        entity_type = candidate.get("entity_type")
        content = candidate.get("content")
        if not entity_key or not entity_type or not content:
            continue
        try:
            payload = {
                "entity_key": entity_key,
                "entity_type": entity_type,
                "content": content,
                "skip_semantic_merge": True,
            }
            if source_thread_id:
                payload["source_thread_id"] = source_thread_id
            if source_refs:
                payload["source_refs"] = source_refs
            if origin_client:
                payload["origin_client"] = origin_client
            if origin_session_id:
                payload["origin_session_id"] = origin_session_id
            result = await remember_tool(payload)
            results.append(result)
        except Exception as exc:
            errors.append(
                {
                    "entity_key": entity_key,
                    "entity_type": entity_type,
                    "content": content,
                    "error": str(exc),
                }
            )

    return {"results": results, "errors": errors, "total": len(results), "failed": len(errors)}
```

- [ ] **Step 4: 修改 remember.py — 接受 source_refs / origin_***

M2 Task 10 already added `_parse_source_refs` + transport of `origin_*` / `source_*` / `title` in `remember_tool`. M3 has nothing to add to that file beyond verifying the contract — `_parse_source_refs` accepts dicts shaped `{thread_id, message_id}`, the same shape this M3 Task 9 extraction handler emits. **No code change needed**; just run the regression below.

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_extraction_source_refs.py tests/test_tools.py -k "remember or source_refs" -v
```

Expected: PASS. If the M2 path was skipped, fall back to the canonical body from M2 Task 10 Step 3 (verbatim copy, do not invent — the function is fully written there).

- [ ] **Step 5: 修改 routes.handle_extract**

Edit `src/memory_mcp/api/routes.py::handle_extract` — 让 REST 路由把额外字段透传：

```python
async def handle_extract(request: Request) -> JSONResponse:
    from ..engine import extraction
    try:
        body = await request.json()
    except Exception:
        return err("Invalid JSON body")
    messages = body.get("messages")
    if not messages or not isinstance(messages, list):
        return err("messages must be a non-empty list")
    try:
        result = await extraction.extract_memories(
            messages,
            source_thread_id=body.get("source_thread_id"),
            source_refs=body.get("source_refs"),
            origin_client=body.get("origin_client"),
            origin_session_id=body.get("origin_session_id"),
        )
    except Exception as e:
        return err(str(e), 500)
    return ok(result)
```

- [ ] **Step 6: 跑测试 PASS**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_extraction_source_refs.py -v`

- [ ] **Step 7: Commit**

```bash
git add src/memory_mcp/engine/extraction.py src/memory_mcp/tools/remember.py src/memory_mcp/api/routes.py tests/test_extraction_source_refs.py
git commit -m "feat(extraction): pass source_thread_id/source_refs through to remember"
```

---

## Chunk 6: CLI sync + thread 子命令

### Task 10: CLI config 支持 toml + 沿用 json 兼容

**Files:**
- Modify: `cli/src/memory_mcp_cli/config.py`
- Create: `cli/tests/test_config_toml.py`

- [ ] **Step 1: 写失败测试**

Create `cli/tests/test_config_toml.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.delenv("MEMORY_MCP_API_URL", raising=False)
    monkeypatch.delenv("MEMORY_MCP_API_KEY", raising=False)
    monkeypatch.delenv("MEMORY_MCP_AUTH_TOKEN", raising=False)
    return tmp_path


def _write_toml(path: Path) -> None:
    path.write_text(
        """
[server]
url = "https://example.invalid"
token_env = "MEMORY_MCP_AUTH_TOKEN"

[sync.claude-code]
roots = ["~/.claude/projects"]
auto = true

[sync.codex]
roots = ["~/.codex"]
auto = false
""".strip()
    )


class TestTomlConfig:
    def test_loads_toml(self, monkeypatch, isolated_env):
        toml_path = isolated_env / "config.toml"
        _write_toml(toml_path)
        monkeypatch.setenv("MEM_CONFIG_PATH", str(toml_path))
        monkeypatch.setenv("MEMORY_MCP_AUTH_TOKEN", "abc")

        from memory_mcp_cli.config import load_config

        cfg = load_config()
        assert cfg["api_url"] == "https://example.invalid"
        assert cfg["api_key"] == "abc"
        assert cfg["sync"]["claude-code"]["auto"] is True
        assert cfg["sync"]["codex"]["auto"] is False

    def test_env_overrides_toml(self, monkeypatch, isolated_env):
        toml_path = isolated_env / "config.toml"
        _write_toml(toml_path)
        monkeypatch.setenv("MEM_CONFIG_PATH", str(toml_path))
        monkeypatch.setenv("MEMORY_MCP_API_URL", "https://override")
        monkeypatch.setenv("MEMORY_MCP_AUTH_TOKEN", "tok")

        from memory_mcp_cli.config import load_config

        cfg = load_config()
        assert cfg["api_url"] == "https://override"

    def test_json_fallback(self, monkeypatch, isolated_env):
        json_path = isolated_env / "config.json"
        json_path.write_text('{"api_url": "http://j", "api_key": "k"}')
        monkeypatch.setenv("MEM_CONFIG_PATH", str(json_path))

        from memory_mcp_cli.config import load_config

        cfg = load_config()
        assert cfg["api_url"] == "http://j"
        assert cfg["api_key"] == "k"
```

- [ ] **Step 2: 跑 FAIL**

- [ ] **Step 3: 实现 config.py**

Replace `cli/src/memory_mcp_cli/config.py`:

```python
"""CLI config loader. Supports TOML (preferred) and legacy JSON.

Resolution order:
    1. MEM_CONFIG_PATH (if set)
    2. ~/.config/mem/config.toml
    3. ~/.config/memory-mcp/config.json (legacy)

Env overrides:
    MEMORY_MCP_API_URL                -> server.url
    MEMORY_MCP_API_KEY                -> server.api_key (preferred)
    MEMORY_MCP_AUTH_TOKEN             -> server.api_key (fallback)
    Or the env var named by server.token_env (TOML only)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore[attr-defined]
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def _candidate_paths() -> list[Path]:
    explicit = os.environ.get("MEM_CONFIG_PATH")
    if explicit:
        return [Path(explicit).expanduser()]
    return [
        Path.home() / ".config" / "mem" / "config.toml",
        Path.home() / ".config" / "memory-mcp" / "config.json",
    ]


def _load_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_token(server_block: dict) -> str:
    token_env = server_block.get("token_env")
    if token_env:
        val = os.environ.get(token_env)
        if val:
            return val
    return ""


def load_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "api_url": "http://localhost:8765",
        "api_key": "",
        "sync": {},
    }

    for path in _candidate_paths():
        if not path.exists():
            continue
        if path.suffix == ".toml":
            data = _load_toml(path)
            server = data.get("server") or {}
            if "url" in server:
                cfg["api_url"] = server["url"]
            token = _resolve_token(server)
            if token:
                cfg["api_key"] = token
            cfg["sync"] = data.get("sync") or {}
        else:
            data = _load_json(path)
            cfg.update({k: v for k, v in data.items() if k in ("api_url", "api_key")})
            cfg["sync"] = data.get("sync") or {}
        break

    # env overrides
    cfg["api_url"] = os.environ.get("MEMORY_MCP_API_URL", cfg["api_url"])
    env_key = os.environ.get("MEMORY_MCP_API_KEY") or os.environ.get("MEMORY_MCP_AUTH_TOKEN")
    if env_key:
        cfg["api_key"] = env_key

    return cfg
```

- [ ] **Step 4: 跑 PASS**

- [ ] **Step 5: Commit**

```bash
git add cli/src/memory_mcp_cli/config.py cli/tests/test_config_toml.py
git commit -m "feat(cli): support ~/.config/mem/config.toml with json fallback"
```

### Task 11: CLI client 新增 threads endpoints

**Files:**
- Modify: `cli/src/memory_mcp_cli/client.py`

- [ ] **Step 1: 直接追加方法（无需独立测试，下个 task 集成测试覆盖）**

Append to `MemoryClient` (cli/src/memory_mcp_cli/client.py):

```python
    def threads_incremental(self, batches: list[dict]) -> dict:
        with httpx.Client(headers=self._headers, timeout=60) as c:
            return self._handle(
                c.post(f"{self._base}/api/v1/threads/incremental", json={"batches": batches})
            )

    def threads_sync_status(self, provider: str, refs: list[str]) -> dict:
        params = {"provider": provider, "refs": ",".join(refs)}
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(f"{self._base}/api/v1/threads/sync-status", params=params))

    def threads_import(self, payload: dict) -> dict:
        with httpx.Client(headers=self._headers, timeout=120) as c:
            return self._handle(c.post(f"{self._base}/api/v1/threads/import", json=payload))

    def threads_list(self, provider: str | None = None, q: str | None = None, page: int = 1, size: int = 20) -> dict:
        params: dict = {"page": page, "size": size}
        if provider:
            params["provider"] = provider
        if q:
            params["q"] = q
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(f"{self._base}/api/v1/threads", params=params))

    def thread_get(self, thread_id: str, with_messages: bool = False) -> dict:
        params = {"with_messages": "true"} if with_messages else {}
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(f"{self._base}/api/v1/threads/{thread_id}", params=params))

    def thread_providers(self) -> dict:
        with httpx.Client(headers=self._headers, timeout=10) as c:
            return self._handle(c.get(f"{self._base}/api/v1/threads/providers"))
```

- [ ] **Step 2: Commit**

```bash
git add cli/src/memory_mcp_cli/client.py
git commit -m "feat(cli): add MemoryClient threads endpoints"
```

### Task 12: CLI adapter 镜像 + sync 模块

**Files:**
- Create: `cli/src/memory_mcp_cli/adapters/__init__.py`
- Create: `cli/src/memory_mcp_cli/adapters/claude_code.py`
- Create: `cli/src/memory_mcp_cli/adapters/manual.py`
- Create: `cli/src/memory_mcp_cli/sync.py`
- Create: `cli/tests/test_sync.py`

> CLI 端复用服务端 adapter 逻辑（直接 import `memory_mcp.threads.adapters.claude_code`），但本 plan 假设 CLI 是独立包不一定能 import 服务端代码。所以 CLI 端做最小本地实现：仅扫文件 + 切到 outbound 字典（不需要服务端的 sync 处理细节）。

#### 设计

`cli/sync.py` 提供 `run_sync(client, provider, root, *, since=None, dry_run=False, resume=False)`:

1. discover 本地源（CLI adapter）
2. 选择待 sync refs（mtime > since 或 since=None；resume 模式跳过 already-current）
3. 批量请求 sync-status
4. 对每个超时/新增源 parse + 算 delta_messages（seq > server.last_synced_seq）
5. POST incremental
6. dry_run 模式只打印 plan、不发请求

- [ ] **Step 1: 写失败测试**

Create `cli/tests/test_sync.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

FIXTURE_DIR = Path(__file__).resolve().parents[1].parent / "tests" / "fixtures" / "threads" / "claude-code"


def _fake_client(status_returns=None, incremental_returns=None):
    client = MagicMock()
    client.threads_sync_status.return_value = {"ok": True, "data": status_returns or {"status": {}}}
    client.threads_incremental.return_value = {"ok": True, "data": incremental_returns or {"results": [], "errors": []}}
    return client


class TestRunSync:
    def test_sync_new_thread(self, tmp_path):
        from memory_mcp_cli.sync import run_sync

        # set up fake claude project dir
        proj = tmp_path / "projects" / "demo"
        proj.mkdir(parents=True)
        (proj / "abc.jsonl").write_text((FIXTURE_DIR / "sample.jsonl").read_text())
        client = _fake_client()

        result = run_sync(client, provider="claude-code", root=tmp_path / "projects")
        assert client.threads_sync_status.called
        assert client.threads_incremental.called
        assert result["pushed"] >= 1

    def test_dry_run_skips_post(self, tmp_path):
        from memory_mcp_cli.sync import run_sync

        proj = tmp_path / "p" / "x"
        proj.mkdir(parents=True)
        (proj / "abc.jsonl").write_text((FIXTURE_DIR / "sample.jsonl").read_text())
        client = _fake_client()

        run_sync(client, provider="claude-code", root=tmp_path / "p", dry_run=True)
        assert client.threads_incremental.call_count == 0

    def test_skips_unchanged_refs(self, tmp_path):
        from memory_mcp_cli.sync import run_sync

        proj = tmp_path / "p" / "x"
        proj.mkdir(parents=True)
        target = proj / "abc.jsonl"
        target.write_text((FIXTURE_DIR / "sample.jsonl").read_text())
        # pretend server already has it
        mtime = int(target.stat().st_mtime)
        client = _fake_client(
            status_returns={"status": {"abc": {"thread_id": "abc", "last_synced_mtime": mtime, "last_synced_seq": 9999}}}
        )

        result = run_sync(client, provider="claude-code", root=tmp_path / "p")
        # status says fully synced -> no incremental call
        assert client.threads_incremental.call_count == 0
        assert result["skipped"] >= 1
```

- [ ] **Step 2: 跑 FAIL**

- [ ] **Step 3: 实现 CLI adapter（claude-code）**

Create `cli/src/memory_mcp_cli/adapters/__init__.py`：

```python
"""CLI-side thread adapters: scan local files + build outbound batches."""
```

Create `cli/src/memory_mcp_cli/adapters/claude_code.py`:

```python
"""CLI mirror of the claude-code adapter — minimal: discover + build batch dict.

Parsing is delegated to the server (POST /threads/import) when full-text is
needed; sync only needs discover + tail-of-file message extraction for delta.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger("mem-cli.adapter.claude-code")


@dataclass
class LocalSource:
    provider: str
    ref: str
    path: Path
    mtime: int


def discover(root: Path) -> Iterator[LocalSource]:
    root = Path(root).expanduser()
    if not root.exists():
        return
    for path in sorted(root.rglob("*.jsonl")):
        try:
            mtime = int(path.stat().st_mtime)
        except OSError:
            continue
        yield LocalSource(provider="claude-code", ref=path.stem, path=path, mtime=mtime)


def _parse_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        logger.debug("skip malformed line")
        return None


def _flatten(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for b in content:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "text":
                parts.append(str(b.get("text", "")))
            elif t == "tool_use":
                parts.append(f"[tool_use {b.get('name','?')}] {json.dumps(b.get('input'), ensure_ascii=False)}")
            elif t == "tool_result":
                res = b.get("content")
                parts.append(f"[tool_result] {res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)}")
            else:
                parts.append(json.dumps(b, ensure_ascii=False))
        return "\n".join(p for p in parts if p)
    return json.dumps(content, ensure_ascii=False)


def build_batch(source: LocalSource, *, since_seq: int = -1) -> dict[str, Any] | None:
    """Walk file, assign seq, return batch dict ready for /threads/incremental."""
    messages: list[dict[str, Any]] = []
    title: str | None = None
    meta: dict[str, Any] = {}
    seq = 0
    with source.path.open("r", encoding="utf-8") as fh:
        for line in fh:
            event = _parse_line(line)
            if not event:
                continue
            etype = event.get("type")
            for k in ("cwd", "sessionId", "gitBranch", "version"):
                if k in event and k not in meta:
                    meta[k] = event[k]
            if etype == "summary" and title is None:
                title = (event.get("summary") or "").strip() or None
                continue
            msg = event.get("message")
            if not isinstance(msg, dict):
                continue
            role = msg.get("role") or etype or "user"
            if role in ("tool_use", "tool_result"):
                role = "tool"
            elif isinstance(msg.get("content"), list) and any(
                isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result")
                for b in msg["content"]
            ):
                role = "tool"
            content = _flatten(msg.get("content"))
            if not content:
                seq += 1
                continue
            ts = event.get("timestamp")
            if seq > since_seq:
                messages.append(
                    {"seq": seq, "role": role, "content": content, "ts": ts, "metadata": {"event_type": etype}}
                )
            seq += 1

    if not messages:
        return None
    return {
        "provider": "claude-code",
        "source_ref": source.ref,
        "thread_id": source.ref,
        "thread_meta": {"title": title, "metadata": meta},
        "mtime": source.mtime,
        "messages": messages,
    }
```

Create `cli/src/memory_mcp_cli/adapters/manual.py`:

```python
"""Manual adapter for CLI — delegate import via REST /threads/import."""
from __future__ import annotations

from pathlib import Path


def file_payload(provider: str, path: Path, *, thread_id: str | None = None, fmt: str | None = None, title: str | None = None) -> dict:
    payload: dict = {"provider": provider, "path": str(path)}
    if thread_id:
        payload["thread_id"] = thread_id
    if fmt:
        payload["format"] = fmt
    if title:
        payload["title"] = title
    return payload


def inline_payload(provider: str, content: str, *, thread_id: str | None = None, fmt: str = "markdown", title: str | None = None) -> dict:
    payload: dict = {"provider": provider, "content": content, "format": fmt}
    if thread_id:
        payload["thread_id"] = thread_id
    if title:
        payload["title"] = title
    return payload
```

- [ ] **Step 4: 实现 sync.py**

Create `cli/src/memory_mcp_cli/sync.py`:

```python
"""Sync orchestrator: discover local → diff vs server → push.

Spec §6.3 5-step protocol:
    1. Discover local sources
    2. GET /threads/sync-status?provider=X&refs=...
    3. For each source: if local_mtime > server.last_synced_mtime
       and parsed.last_seq > server.last_synced_seq → build batch
    4. POST /threads/incremental with batches
    5. Server upsert + returns new sync state
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from .adapters import claude_code as cc_adapter

logger = logging.getLogger("mem-cli.sync")

_ADAPTERS = {
    "claude-code": cc_adapter,
    # codex / chatwise — wired once stubs are filled in
}

BATCH_SIZE = 50


def _discover(provider: str, root: Path) -> Iterable[Any]:
    if provider == "claude-code":
        return cc_adapter.discover(root)
    raise ValueError(f"sync not implemented for provider: {provider}")


def _batch_for(provider: str, source, since_seq: int) -> dict[str, Any] | None:
    if provider == "claude-code":
        return cc_adapter.build_batch(source, since_seq=since_seq)
    return None


def run_sync(
    client,
    *,
    provider: str,
    root: Path,
    since: int | None = None,
    dry_run: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    sources = list(_discover(provider, root))
    if not sources:
        logger.info("no local sources for %s under %s", provider, root)
        return {"pushed": 0, "skipped": 0, "errors": []}

    # step 2: query server status
    refs = [s.ref for s in sources]
    status_payload: dict[str, dict] = {}
    if not dry_run:
        resp = client.threads_sync_status(provider, refs)
        status_payload = resp["data"]["status"]

    pushed = 0
    skipped = 0
    errors: list[dict] = []
    batches: list[dict] = []

    # step 3: filter
    for src in sources:
        srv = status_payload.get(src.ref) or {}
        if since is not None and src.mtime < since:
            skipped += 1
            continue
        srv_mtime = srv.get("last_synced_mtime")
        srv_seq = int(srv.get("last_synced_seq") if srv.get("last_synced_seq") is not None else -1)
        if srv_mtime and src.mtime <= srv_mtime and srv_seq >= 0:
            # nothing newer
            skipped += 1
            continue
        batch = _batch_for(provider, src, since_seq=srv_seq)
        if batch is None:
            skipped += 1
            continue
        if resume and not batch["messages"]:
            skipped += 1
            continue
        batches.append(batch)

    if dry_run:
        logger.info("dry-run: would push %d batches", len(batches))
        return {"pushed": 0, "skipped": skipped, "errors": [], "planned": len(batches)}

    # step 4: chunked POST
    for i in range(0, len(batches), BATCH_SIZE):
        chunk = batches[i : i + BATCH_SIZE]
        resp = client.threads_incremental(chunk)
        data = resp["data"]
        pushed += sum(1 for r in data.get("results", []) if r.get("new_message_ids"))
        errors.extend(data.get("errors", []))

    return {"pushed": pushed, "skipped": skipped, "errors": errors, "planned": len(batches)}
```

- [ ] **Step 5: 跑 PASS**

Run: `cd /Users/kassol/Workspace/memory-mcp/cli && pytest tests/test_sync.py -v`

- [ ] **Step 6: Commit**

```bash
git add cli/src/memory_mcp_cli/adapters/ cli/src/memory_mcp_cli/sync.py cli/tests/test_sync.py
git commit -m "feat(cli): add local thread adapter + sync orchestrator"
```

### Task 13: CLI thread 子命令（sync / import-history / import / search / get）

**Files:**
- Modify: `cli/src/memory_mcp_cli/main.py`
- Create: `cli/tests/test_thread_commands.py`

- [ ] **Step 1: 写测试**

Create `cli/tests/test_thread_commands.py`:

```python
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MEMORY_MCP_API_URL", "http://test:8765")
    monkeypatch.setenv("MEMORY_MCP_API_KEY", "k")


def _mock_client():
    client = MagicMock()
    client.threads_list.return_value = {"ok": True, "data": {"items": [], "total": 0}}
    client.thread_get.return_value = {"ok": True, "data": {"thread_id": "x"}}
    client.threads_import.return_value = {"ok": True, "data": {"thread_id": "y", "created": True}}
    return client


@patch("memory_mcp_cli.main._client")
def test_thread_search(mock_client_factory):
    mock_client_factory.return_value = _mock_client()
    from memory_mcp_cli.main import app

    r = runner.invoke(app, ["thread", "search", "--provider", "claude-code"])
    assert r.exit_code == 0


@patch("memory_mcp_cli.main._client")
def test_thread_get(mock_client_factory):
    mock_client_factory.return_value = _mock_client()
    from memory_mcp_cli.main import app

    r = runner.invoke(app, ["thread", "get", "x"])
    assert r.exit_code == 0


@patch("memory_mcp_cli.main._client")
def test_thread_import_file(mock_client_factory, tmp_path):
    mock_client_factory.return_value = _mock_client()
    p = tmp_path / "n.md"
    p.write_text("## user\nhello")
    from memory_mcp_cli.main import app

    r = runner.invoke(app, ["thread", "import", "--file", str(p), "--provider", "manual"])
    assert r.exit_code == 0


@patch("memory_mcp_cli.main.run_sync")
@patch("memory_mcp_cli.main._client")
def test_thread_sync_invokes(mock_client_factory, mock_run_sync, tmp_path):
    mock_client_factory.return_value = _mock_client()
    mock_run_sync.return_value = {"pushed": 1, "skipped": 0, "errors": []}
    from memory_mcp_cli.main import app

    r = runner.invoke(app, ["thread", "sync", "--provider", "claude-code", "--root", str(tmp_path)])
    assert r.exit_code == 0
    mock_run_sync.assert_called_once()
```

- [ ] **Step 2: 实现 main.py 子命令**

Edit `cli/src/memory_mcp_cli/main.py` — 在文件末尾追加（先加 imports）：

```python
from pathlib import Path as _Path  # at the top, alongside existing Path import

from .sync import run_sync
from .adapters.manual import file_payload, inline_payload
```

Append at end of file（在 `if __name__ == "__main__":` 之前）:

```python
# ---------------------------------------------------------------------------
# thread
# ---------------------------------------------------------------------------
thread_app = typer.Typer(help="thread commands (sync / import / search / get)")
app.add_typer(thread_app, name="thread")


def _config_sync_blocks() -> dict:
    return load_config().get("sync") or {}


@thread_app.command("sync")
def thread_sync(
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider name; default = all sync.<p>.auto = true"),
    root: Optional[Path] = typer.Option(None, "--root", help="Override local root path"),
    since: Optional[int] = typer.Option(None, "--since", help="Epoch seconds; skip files older than this"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; do not POST"),
    resume: bool = typer.Option(False, "--resume", help="Resume previous interrupted run"),
    fmt: str = _format_opt,
) -> None:
    """Push local transcripts to server (incremental).

    Also drains the stop-hook retry queue (~/.local/state/mem/stop_hook_retry.jsonl)
    on every run so that hook pushes that failed offline get a second chance.
    """
    # Drain the stop-hook local retry queue first (best-effort, never fatal).
    if not dry_run:
        try:
            from .thread_stop_helper import drain_retry_queue
            drained = drain_retry_queue()
            if drained.get("drained") or drained.get("kept"):
                typer.echo(
                    f"stop-hook retry queue: drained={drained['drained']} kept={drained['kept']}",
                    err=True,
                )
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"retry queue drain skipped: {exc}", err=True)

    sync_cfg = _config_sync_blocks()
    targets: list[tuple[str, Path]] = []

    if provider:
        if root is None:
            block = sync_cfg.get(provider) or {}
            roots = [Path(r).expanduser() for r in block.get("roots", [])]
            if not roots:
                typer.echo(f"Error: no roots configured for provider {provider}; pass --root", err=True)
                raise SystemExit(1)
            targets = [(provider, r) for r in roots]
        else:
            targets = [(provider, root)]
    else:
        for p, block in sync_cfg.items():
            if not block.get("auto"):
                continue
            for r in block.get("roots", []):
                targets.append((p, Path(r).expanduser()))
        if not targets:
            typer.echo("No providers with sync.<p>.auto = true; pass --provider", err=True)
            raise SystemExit(1)

    client = _client()
    summary = {"providers": []}
    for prov, r in targets:
        result = run_sync(client, provider=prov, root=r, since=since, dry_run=dry_run, resume=resume)
        summary["providers"].append({"provider": prov, "root": str(r), **result})
    _out({"data": summary}, fmt)


@thread_app.command("import-history")
def thread_import_history(
    provider: str = typer.Option(..., "--provider", "-p"),
    root: Optional[Path] = typer.Option(None, "--root"),
    since: Optional[str] = typer.Option(None, "--since", help="ISO date YYYY-MM-DD; only files newer"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    resume: bool = typer.Option(False, "--resume"),
    fmt: str = _format_opt,
) -> None:
    """Backfill all historical transcripts (chunked, idempotent)."""
    import datetime as _dt

    since_epoch: Optional[int] = None
    if since:
        try:
            since_epoch = int(_dt.datetime.fromisoformat(since).timestamp())
        except ValueError:
            typer.echo("Error: --since must be ISO date YYYY-MM-DD", err=True)
            raise SystemExit(1)
    sync_cfg = _config_sync_blocks()
    roots = [root] if root else [Path(r).expanduser() for r in (sync_cfg.get(provider, {}).get("roots") or [])]
    if not roots:
        typer.echo("Error: no roots", err=True)
        raise SystemExit(1)
    client = _client()
    summary = {"runs": []}
    for r in roots:
        out = run_sync(client, provider=provider, root=r, since=since_epoch, dry_run=dry_run, resume=resume)
        summary["runs"].append({"root": str(r), **out})
    _out({"data": summary}, fmt)


@thread_app.command("import")
def thread_import_cmd(
    file: Optional[Path] = typer.Option(None, "--file", help="Local file path"),
    content: Optional[str] = typer.Option(None, "--content", help="Inline content"),
    provider: str = typer.Option("manual", "--provider", "-p"),
    fmt_in: Optional[str] = typer.Option(None, "--format", help="markdown / json / plaintext"),
    thread_id: Optional[str] = typer.Option(None, "--thread-id"),
    title: Optional[str] = typer.Option(None, "--title"),
    fmt: str = _format_opt,
) -> None:
    """Import a single transcript (manual or other provider single file)."""
    if file and content:
        typer.echo("Error: pass either --file or --content, not both", err=True)
        raise SystemExit(1)
    if file:
        payload = file_payload(provider, file, thread_id=thread_id, fmt=fmt_in, title=title)
    elif content:
        payload = inline_payload(provider, content, thread_id=thread_id, fmt=fmt_in or "markdown", title=title)
    else:
        typer.echo("Error: --file or --content required", err=True)
        raise SystemExit(1)
    result = _client().threads_import(payload)
    _out(result, fmt)


@thread_app.command("search")
def thread_search_cmd(
    q: Optional[str] = typer.Option(None, "-q", "--query"),
    provider: Optional[str] = typer.Option(None, "-p", "--provider"),
    page: int = typer.Option(1, "--page"),
    size: int = typer.Option(20, "--size"),
    fmt: str = _format_opt,
) -> None:
    """List/search threads via FTS5."""
    result = _client().threads_list(provider=provider, q=q, page=page, size=size)
    _out(result, fmt)


@thread_app.command("get")
def thread_get_cmd(
    thread_id: str = typer.Argument(...),
    with_messages: bool = typer.Option(False, "--messages"),
    fmt: str = _format_opt,
) -> None:
    """Get a thread metadata (and optionally messages)."""
    result = _client().thread_get(thread_id, with_messages=with_messages)
    _out(result, fmt)
```

- [ ] **Step 3: 跑 PASS**

Run: `cd /Users/kassol/Workspace/memory-mcp/cli && pytest tests/test_thread_commands.py -v`

- [ ] **Step 4: Commit**

```bash
git add cli/src/memory_mcp_cli/main.py cli/tests/test_thread_commands.py
git commit -m "feat(cli): add thread sync/import-history/import/search/get subcommands"
```

---

## Chunk 7: backfill 工具（服务端侧便利脚本）

### Task 14: server backfill module

**Files:**
- Create: `src/memory_mcp/threads/backfill.py`
- Create: `tests/test_threads_backfill.py`

#### 行为约束

- 走 adapter.discover + adapter.parse，逐个 apply_full_thread。
- 每 50 个 thread 之后显式 `commit`/事务边界（apply_full_thread 内部已每次事务，本模块再加进度记录）。
- 支持 `--dry-run`（只打印计划）/ `--resume`（读取 progress 文件，从断点继续）/ `--since`（按 mtime 过滤）。
- 进度文件：`<data_dir>/backfill_progress.json`，结构 `{provider: {root: {processed_refs: [...]}}}`。

- [ ] **Step 1: 写失败测试**

Create `tests/test_threads_backfill.py`:

```python
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "threads" / "claude-code"


@pytest.fixture()
def projects_root(tmp_path):
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    for i in range(3):
        (proj / f"thread-{i}.jsonl").write_text((FIXTURE_DIR / "sample.jsonl").read_text())
    return tmp_path / "projects"


class TestBackfill:
    async def test_dry_run_no_writes(self, test_env, projects_root):
        from memory_mcp.threads.backfill import run_backfill

        plan = await run_backfill(provider="claude-code", root=projects_root, dry_run=True)
        assert plan["planned"] == 3
        assert plan["applied"] == 0

    async def test_apply_all(self, test_env, projects_root):
        from memory_mcp.threads.backfill import run_backfill

        out = await run_backfill(provider="claude-code", root=projects_root)
        assert out["applied"] == 3

    async def test_resume_skips_processed(self, test_env, projects_root, tmp_path):
        from memory_mcp.threads.backfill import run_backfill

        await run_backfill(provider="claude-code", root=projects_root)
        out = await run_backfill(provider="claude-code", root=projects_root, resume=True)
        # second run should re-discover but not produce new messages
        for entry in out["details"]:
            assert entry["new_messages"] == 0

    async def test_since_filter(self, test_env, projects_root):
        from memory_mcp.threads.backfill import run_backfill

        # set since to far-future so no file matches
        out = await run_backfill(provider="claude-code", root=projects_root, since=9_999_999_999)
        assert out["applied"] == 0
```

- [ ] **Step 2: 实现 backfill**

Create `src/memory_mcp/threads/backfill.py`:

```python
"""One-shot backfill: walk a local root and apply_full_thread for each.

Idempotent: relies on sync.apply_full_thread to skip already-synced messages.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ..config import settings
from . import sync as threads_sync
from .registry import get_adapter

logger = logging.getLogger("memory-mcp.threads.backfill")

BATCH = 50


def _progress_path() -> Path:
    return Path(settings.data_dir) / "backfill_progress.json"


def _load_progress() -> dict[str, Any]:
    path = _progress_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_progress(state: dict[str, Any]) -> None:
    path = _progress_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


async def run_backfill(
    *,
    provider: str,
    root: Path,
    since: int | None = None,
    dry_run: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    adapter = get_adapter(provider)
    sources = list(adapter.discover(Path(root)))

    state = _load_progress()
    key = f"{provider}::{root}"
    processed: set[str] = set(state.get(key, {}).get("processed_refs", []))

    if since is not None:
        sources = [s for s in sources if s.mtime is not None and s.mtime >= since]

    details: list[dict] = []
    applied = 0

    for idx, source in enumerate(sources, start=1):
        if resume and source.ref in processed:
            details.append({"ref": source.ref, "skipped": True, "new_messages": 0})
            continue
        if dry_run:
            details.append({"ref": source.ref, "dry_run": True})
            continue

        try:
            parsed = adapter.parse(source)
        except Exception as exc:
            logger.warning("backfill parse failed for %s: %s", source.ref, exc)
            details.append({"ref": source.ref, "error": str(exc)})
            continue

        result = await threads_sync.apply_full_thread(parsed, mtime=source.mtime)
        new_count = len(result.get("new_message_ids", []))
        applied += 1
        processed.add(source.ref)
        details.append({"ref": source.ref, "thread_id": result["thread_id"], "new_messages": new_count})

        if idx % BATCH == 0:
            state[key] = {"processed_refs": sorted(processed), "ts": int(time.time())}
            _save_progress(state)

    state[key] = {"processed_refs": sorted(processed), "ts": int(time.time())}
    if not dry_run:
        _save_progress(state)

    return {
        "provider": provider,
        "root": str(root),
        "planned": len(sources),
        "applied": applied,
        "details": details,
        "dry_run": dry_run,
        "resume": resume,
    }
```

- [ ] **Step 3: 跑 PASS**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_threads_backfill.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/memory_mcp/threads/backfill.py tests/test_threads_backfill.py
git commit -m "feat(threads): add backfill runner with dry-run/resume/since"
```

---

## Chunk 8: stop hook 双步升级

### Task 15: 改写 stop.sh + push helper

**Files:**
- Rewrite: `claude-code-plugin/hooks/stop.sh`
- Create: `claude-code-plugin/hooks/lib/push_thread.sh`

#### 设计

stop hook 读 Claude Code 给的 JSON：

```json
{ "stop_hook_active": false,
  "transcript_path": "/Users/me/.claude/projects/-Users-me-proj/abc.jsonl",
  "session_id": "abc",
  "cwd": "/Users/me/proj" }
```

双步执行：

1. **incremental 推送**：直接调 `mem` CLI 内部接口 — 用 `python3` 走 `subprocess.run([sys.executable, "-m", "memory_mcp_cli.thread_stop_helper", transcript_path, session_id, cwd])`，封装在 `lib/push_thread.sh`。返回 `thread_id` + `new_message_ids` 到 stdout（JSON）。

2. **extract**：拿到 thread_id + new_message_ids 后，组装 messages array（取 transcript 中 `seq ∈ new_message_ids` 的那几条）→ POST `/api/v1/memories/extract` 带 `source_thread_id` + `source_refs`。

为减小 hook 脚本复杂度，封装一个独立的 Python helper：`cli/src/memory_mcp_cli/thread_stop_helper.py`，由 hook 调用。

- [ ] **Step 1: 创建 helper（含本地 retry queue）**

Create `cli/src/memory_mcp_cli/thread_stop_helper.py`:

```python
"""Stop-hook helper. Two steps:

1. Use claude_code adapter to parse the transcript file and POST incremental.
2. Take the new_message_ids, slice the parsed messages, POST extract with
   source_thread_id and source_refs.

Failure handling (spec §13 risk: "stop hook 推送失败"):
- Any HTTP / network failure during step 1 or 2 is appended to a local retry
  queue at ``~/.local/state/mem/stop_hook_retry.jsonl``.
- ``mem thread sync`` (Task 13) drains the queue on its next run by re-POSTing
  each pending payload and removing successful entries.

Usage:
    python -m memory_mcp_cli.thread_stop_helper <transcript_path> [session_id]

Exit 0 always (best-effort, fire-and-forget). Errors go to stderr.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .adapters.claude_code import LocalSource, build_batch
from .client import MemoryClient
from .config import load_config


def _retry_queue_path() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    return base / "mem" / "stop_hook_retry.jsonl"


def _enqueue_retry(kind: str, payload: dict) -> None:
    """Append a failed POST to the local retry queue (JSON Lines)."""
    path = _retry_queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,            # "incremental" | "extract"
        "payload": payload,      # JSON-serializable request body
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: thread_stop_helper <transcript_path> [session_id]", file=sys.stderr)
        return 0

    path = Path(argv[1]).expanduser()
    if not path.exists():
        print(f"transcript missing: {path}", file=sys.stderr)
        return 0

    cfg = load_config()
    client = MemoryClient(cfg["api_url"], cfg["api_key"])

    src = LocalSource(provider="claude-code", ref=path.stem, path=path, mtime=int(path.stat().st_mtime))

    # ask server how far it is
    try:
        status_resp = client.threads_sync_status("claude-code", [src.ref])
        srv = (status_resp.get("data", {}).get("status") or {}).get(src.ref, {})
        since_seq = int(srv.get("last_synced_seq", -1)) if srv.get("last_synced_seq") is not None else -1
    except SystemExit:
        return 0
    except Exception as exc:
        print(f"sync-status failed: {exc}", file=sys.stderr)
        return 0

    batch = build_batch(src, since_seq=since_seq)
    if not batch:
        return 0

    try:
        incr_resp = client.threads_incremental([batch])
    except SystemExit:
        return 0
    except Exception as exc:
        print(f"incremental failed: {exc}", file=sys.stderr)
        _enqueue_retry("incremental", {"batches": [batch]})
        return 0
    results = incr_resp.get("data", {}).get("results", [])
    if not results:
        return 0
    info = results[0]
    thread_id = info["thread_id"]
    new_ids: list[str] = info.get("new_message_ids", [])
    if not new_ids:
        return 0

    # build messages slice for extraction
    seq_in_new = {int(mid.split(":")[-1]) for mid in new_ids}
    extract_msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in batch["messages"]
        if m["seq"] in seq_in_new and m["role"] in ("user", "assistant")
    ]
    if not extract_msgs:
        return 0

    refs = [{"thread_id": thread_id, "message_id": mid} for mid in new_ids]
    extract_payload = {
        "messages": extract_msgs,
        "source_thread_id": thread_id,
        "source_refs": refs,
        "origin_client": "claude-code",
    }
    if len(argv) >= 3:
        extract_payload["origin_session_id"] = argv[2]

    try:
        import httpx

        headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
        with httpx.Client(timeout=120) as c:
            resp = c.post(
                f"{cfg['api_url'].rstrip('/')}/api/v1/memories/extract",
                headers=headers,
                json=extract_payload,
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        print(f"extract failed: {exc}", file=sys.stderr)
        _enqueue_retry("extract", extract_payload)
        return 0

    print(json.dumps({"thread_id": thread_id, "new_messages": len(new_ids), "extracted": True}))
    return 0


def drain_retry_queue() -> dict:
    """Drain the local retry queue. Called by ``mem thread sync``.

    Returns a small report ``{drained, kept}``. Successful entries are removed;
    failures stay in the queue for next pass.
    """
    path = _retry_queue_path()
    if not path.exists():
        return {"drained": 0, "kept": 0}
    cfg = load_config()
    client = MemoryClient(cfg["api_url"], cfg["api_key"])

    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    drained = 0
    kept: list[dict] = []
    for entry in entries:
        kind = entry.get("kind")
        payload = entry.get("payload") or {}
        try:
            if kind == "incremental":
                client.threads_incremental(payload.get("batches") or [])
            elif kind == "extract":
                import httpx

                headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
                with httpx.Client(timeout=120) as c:
                    resp = c.post(
                        f"{cfg['api_url'].rstrip('/')}/api/v1/memories/extract",
                        headers=headers,
                        json=payload,
                    )
                if resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {resp.status_code}")
            else:
                # unknown kind — drop it
                continue
            drained += 1
        except Exception:
            kept.append(entry)

    if kept:
        with path.open("w", encoding="utf-8") as fh:
            for entry in kept:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    else:
        path.unlink(missing_ok=True)

    return {"drained": drained, "kept": len(kept)}


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 2: helper 测试**

Append to `cli/tests/test_thread_commands.py`:

```python
@patch("memory_mcp_cli.thread_stop_helper.MemoryClient")
def test_stop_helper_two_steps(mock_client_cls, tmp_path):
    sample = tmp_path / "abc.jsonl"
    sample.write_text(
        (Path(__file__).resolve().parents[1].parent / "tests" / "fixtures" / "threads" / "claude-code" / "sample.jsonl").read_text()
    )

    client = MagicMock()
    client.threads_sync_status.return_value = {"data": {"status": {}}}
    client.threads_incremental.return_value = {
        "data": {"results": [{"thread_id": "abc", "new_message_ids": ["abc:000001", "abc:000002"]}]}
    }
    mock_client_cls.return_value = client

    with patch("memory_mcp_cli.thread_stop_helper.httpx") as mock_httpx:
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = ctx

        from memory_mcp_cli.thread_stop_helper import main

        rc = main(["prog", str(sample), "session-abc"])
        assert rc == 0
        assert client.threads_incremental.called
        # extract POST should fire (via httpx)
        assert ctx.post.called
```

Add `from pathlib import Path` at top of test file if missing.

- [ ] **Step 3: 跑 PASS**

- [ ] **Step 4: 改写 stop.sh**

Replace `claude-code-plugin/hooks/stop.sh`:

```bash
#!/bin/bash
# Stop hook: two-step thread sync + extraction.
# Runs with async: true (fire-and-forget).
# Step 1: POST /threads/incremental — server returns thread_id + new_message_ids
# Step 2: POST /memories/extract with source_thread_id + source_refs
#
# Errors are non-fatal (best-effort).
python3 -c "
import sys, json, subprocess
d = json.load(sys.stdin)
if d.get('stop_hook_active'):
    sys.exit(0)
tp = d.get('transcript_path', '')
if not tp:
    sys.exit(0)
session_id = d.get('session_id', '')
args = [sys.executable, '-m', 'memory_mcp_cli.thread_stop_helper', tp]
if session_id:
    args.append(session_id)
subprocess.run(args, stderr=subprocess.DEVNULL)
"
```

- [ ] **Step 5: lib/push_thread.sh (optional shared helper for future hooks)**

Create `claude-code-plugin/hooks/lib/push_thread.sh`（可作为 future hooks 共用入口）:

```bash
#!/bin/bash
# Shared helper: invoke memory_mcp_cli.thread_stop_helper.
# Usage: push_thread.sh <transcript_path> [session_id]
set -e
TRANSCRIPT="${1:-}"
SESSION="${2:-}"
if [ -z "$TRANSCRIPT" ]; then
    echo "usage: push_thread.sh <transcript_path> [session_id]" >&2
    exit 1
fi
python3 -m memory_mcp_cli.thread_stop_helper "$TRANSCRIPT" "$SESSION"
```

`chmod +x` 提示放进 task：

- [ ] **Step 6: chmod + commit**

```bash
chmod +x claude-code-plugin/hooks/stop.sh claude-code-plugin/hooks/lib/push_thread.sh
git add claude-code-plugin/hooks/stop.sh claude-code-plugin/hooks/lib/push_thread.sh cli/src/memory_mcp_cli/thread_stop_helper.py cli/tests/test_thread_commands.py
git commit -m "feat(plugin): stop hook two-step (incremental -> extract with source_refs)"
```

---

## Chunk 9: e2e + 收尾

### Task 16: e2e 流程测试

**Files:**
- Create: `tests/test_threads_e2e.py`

- [ ] **Step 1: 写测试**

Create `tests/test_threads_e2e.py`:

```python
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

FIXTURE = ROOT_DIR / "tests" / "fixtures" / "threads" / "claude-code" / "sample.jsonl"


@pytest.fixture()
def app(test_env):
    import memory_mcp.server as server_mod
    importlib.reload(server_mod)
    return server_mod.app


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def headers():
    return {"Authorization": "Bearer test-token"}


class TestStopHookFlow:
    @pytest.mark.asyncio
    async def test_incremental_then_extract_with_refs(self, client, headers, monkeypatch):
        # Step 1: POST /threads/incremental with a payload mirroring stop helper
        from memory_mcp_cli.adapters.claude_code import LocalSource, build_batch

        src = LocalSource(provider="claude-code", ref="abc", path=FIXTURE, mtime=int(FIXTURE.stat().st_mtime))
        batch = build_batch(src, since_seq=-1)
        assert batch is not None
        resp = client.post("/api/v1/threads/incremental", json={"batches": [batch]}, headers=headers)
        result = resp.json()["data"]["results"][0]
        thread_id = result["thread_id"]
        new_ids = result["new_message_ids"]
        assert thread_id == "abc"
        assert new_ids

        # Step 2: POST extract with source_thread_id + source_refs
        from memory_mcp.engine import extraction

        async def fake_call_llm(messages):
            return json.dumps([
                {"entity_key": "preference:editor", "entity_type": "preference", "content": "uses cursor"}
            ])
        monkeypatch.setattr(extraction, "_call_llm", fake_call_llm)

        ext_payload = {
            "messages": [{"role": "user", "content": "use cursor"}],
            "source_thread_id": thread_id,
            "source_refs": [{"thread_id": thread_id, "message_id": mid} for mid in new_ids[:2]],
            "origin_client": "claude-code",
            "origin_session_id": "s-1",
        }
        ext_resp = client.post("/api/v1/memories/extract", json=ext_payload, headers=headers)
        assert ext_resp.status_code == 200, ext_resp.text
        assert ext_resp.json()["data"]["total"] >= 1

        # Step 3: verify thread is searchable
        list_resp = client.get("/api/v1/threads", params={"q": "FTS5"}, headers=headers)
        assert list_resp.status_code == 200
        items = list_resp.json()["data"]["items"]
        assert any(t["thread_id"] == "abc" for t in items)


class TestIdempotencyEnd2End:
    def test_double_apply_via_rest(self, client, headers):
        from memory_mcp_cli.adapters.claude_code import LocalSource, build_batch

        src = LocalSource(provider="claude-code", ref="abc", path=FIXTURE, mtime=int(FIXTURE.stat().st_mtime))
        batch = build_batch(src, since_seq=-1)
        client.post("/api/v1/threads/incremental", json={"batches": [batch]}, headers=headers)
        resp = client.post("/api/v1/threads/incremental", json={"batches": [batch]}, headers=headers)
        assert resp.json()["data"]["results"][0]["new_message_ids"] == []
```

- [ ] **Step 2: 跑 PASS**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_threads_e2e.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/test_threads_e2e.py
git commit -m "test(threads): e2e two-step stop flow with source_refs roundtrip"
```

### Task 17: 全量回归 + AGENTS.md 更新

- [ ] **Step 1: 跑全量 pytest**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest -v`
Expected: 全绿。

Run: `cd /Users/kassol/Workspace/memory-mcp/cli && pytest -v`
Expected: 全绿。

Run: `cd /Users/kassol/Workspace/memory-mcp && ruff check .`
Expected: 无错。

- [ ] **Step 2: 更新 AGENTS.md**

在 `AGENTS.md` 变更日志顶部追加：

```markdown
### 2026-05-21 M3: Threads 模块与 Provider 适配器
- 新增 `threads/` 子包：ThreadAdapter ABC + claude-code 完整实现 + manual / codex stub / chatwise stub
- `threads/sync.py`：upsert + apply_delta + sync-status，单条消息超 64KB 截断 + warning
- `threads/backfill.py`：一次性 backfill，支持 `--dry-run` / `--resume` / `--since`
- 实现 MCP tools：thread_search（FTS5 + jieba）/ thread_get（含 messages 分页）/ thread_import / thread_list_providers
- REST API：POST `/threads/incremental`、GET `/threads/sync-status`、`/threads`/`/{id}`/`/{id}/messages`/`/import`/`/providers`
- Extraction Engine 透传 `source_thread_id` + `source_refs` + `origin_client` + `origin_session_id`，每条 memory 自动回链 thread + message
- CLI `mem thread sync / import-history / import / search / get` 子命令；config 支持 `~/.config/mem/config.toml`
- CLI 端 `thread_stop_helper`：stop hook 双步入口
- Claude Code stop hook 改双步：先 POST `/threads/incremental`，再 POST `/memories/extract` 带 source_refs
- 新增 fixture：`tests/fixtures/threads/claude-code/*.jsonl` + `manual/*`
- 待 Sir 提供 fixture：codex / chatwise adapter 当前为 stub，调用即 NotImplementedError
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: AGENTS.md M3 threads + adapters changelog"
```

### Task 18: smoke test 手动步骤（README/记录）

- [ ] **Step 1: 编辑 `claude-code-plugin/README.md`** — 在 "What it Does" 表后追加：

```markdown
### Stop Hook Two-Step Flow

The Stop hook now performs:

1. POST `/api/v1/threads/incremental` with the new tail of the transcript jsonl
   → server returns `{thread_id, new_message_ids}`.
2. POST `/api/v1/memories/extract` with `source_thread_id` and `source_refs`
   so every extracted memory is linked back to specific messages.

Manual sync (e.g. via launchd or cron):

```bash
mem thread sync                           # auto-sync providers with auto=true
mem thread sync -p claude-code --dry-run  # preview
mem thread import-history -p claude-code  # backfill all
```
```

- [ ] **Step 2: smoke test 手动核对清单（记录在 plan 末尾，不入仓库）**

```text
□ mem thread sync -p claude-code --dry-run  打印 plan, 不发 POST
□ mem thread sync -p claude-code            首次推送, 看到 new_message_ids
□ mem thread sync -p claude-code            二次推送 results 全部 new_message_ids 为 []
□ mem thread search -q "FTS"                能命中 thread
□ mem thread get <thread_id> --messages     看到完整 messages
□ Claude Code 内手动结束 session, 后台 stop hook 触发后:
    - threads 表新增/更新, last_synced_seq 推进
    - memories 表 source_thread_id 与 source_refs 已填充
□ mem thread import --file ./notes.md -p manual --title "..." 单文件导入成功
```

- [ ] **Step 3: Commit**

```bash
git add claude-code-plugin/README.md
git commit -m "docs(plugin): document stop hook two-step flow and manual sync"
```

---

## 自检对照

| Spec §6 子节 | 对应 Task |
|---|---|
| §6.1 适配器架构 | Task 3 (ABC + registry) |
| §6.2 ThreadAdapter 接口 + dataclass + message_id | Task 1, 2, 3 |
| §6.3 分布式 Sync 5 步协议 | Task 6 (服务端 apply_delta + status) + Task 12 (CLI sync.run_sync 1-5 步) |
| §6.4 Provider 关键约定 | Task 4 (claude-code) + Task 3 (codex/chatwise stub) + Task 5 (manual) |
| §6.5 本地 CLI 配置 toml | Task 10 |
| §6.6 CLI 命令 | Task 13 |
| §6.7 调度模板 | 不写代码，README 末尾引用 spec |
| §6.8 stop hook 双步 | Task 15 (helper + stop.sh) + Task 9 (extraction 透传) |
| §4.4 threads / thread_messages DDL | 前提：M1 已建表；M3 sync.py 使用 |
| §11 M3 范围 | 全 plan |

**Hard rules check**:
- 无真实路径 / token：用占位（example.invalid / `MEMORY_MCP_AUTH_TOKEN`）
- codex / chatwise stub：明确 NotImplementedError + TODO(Sir) 注释
- claude-code adapter discover/parse/incremental_payload 完整实现 + 9 个 fixture 行测试覆盖
- backfill `--dry-run` / `--resume` / `--since` + 每 50 thread 进度落盘
- 单条 content >64KB 截断 + warning + metadata.truncated=true
- message_id 格式 `{thread_id}:{seq:06d}` 在 ids.py / sync.py / claude_code adapter / manual adapter / stop helper 一致
- 严格 TDD：每个 task 先 fail test → impl → pass → commit
- git push 不在任何 task

Punt 列表：
- codex / chatwise discover/parse/incremental — 待 Sir 提供 fixture（spec §6.4）
- launchd / cron 调度脚本 — README 引用 spec §6.7，不自动生成
- LLM 自动 summary_gen — M4 worker 范畴

---

## 修复记录

> 2026-05-21 plan 修复（codex 评审）：
>
> - **Task 6（apply_full_thread / apply_delta）**：修复 thread_messages FK violation —— 写入顺序改为「先 upsert threads row（占位字段），再 insert thread_messages，最后 patch threads.message_count / last_synced_seq」。spec §4.4 FK 约束现在满足。
> - **Task 7（REST routes）**：明确「先删除 M2 Task 21 注册的 6 条 `_phase_m3` placeholder route + 对应 handler」再追加真实实现，避免双重注册。
> - **Task 8（thread_messages 返回）**：`_fetch_messages` 增加 `_fetch_extracted_memory_ids`，从 `memories.source_refs` 反向索引出 `{message_id: [memory_id, ...]}`，每条消息携带 `extracted_memory_ids: list[str]` 字段。spec §7.1 / Web UI ThreadMessages 直接消费。
> - **Task 8 新 Step 7（server dispatcher 切换）**：M3 把 `server.py` 的 `thread_*` dispatch 从 M2 `tools.thread_stub` 切到 4 个真实模块，并 `git rm` 掉 stub 文件 + 对应测试。
> - **Task 9 Step 4（remember.py 透传）**：删除 `# ... existing logic to step 4 ...` 伪锚点；M2 Task 10 已实现完整 `_parse_source_refs` + 透传，M3 改为「跑回归断言契约一致」的步骤。
> - **Task 15（stop hook retry queue）**：spec §13 风险缓解「hook 推送失败时本地记 retry queue」落地——`thread_stop_helper` 增加 `_enqueue_retry` 把失败的 incremental/extract POST 写到 `~/.local/state/mem/stop_hook_retry.jsonl`；`mem thread sync` 每次开头自动 `drain_retry_queue`。
> - **Task 13（thread_sync 命令）**：在 `thread_sync` 主体最前 best-effort 调 `drain_retry_queue`，把 retry queue 与日常增量同步合并到一次命令。
