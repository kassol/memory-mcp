# Memory MCP Extension Design

**Date**: 2026-03-24
**Status**: Draft
**Author**: Claude (research session) + Kassol (requirements)

---

## 1. Goal

在现有 memory-mcp 项目基础上增量扩展，实现**跨工具、跨会话、跨项目、跨机器的统一持久记忆**。

核心诉求：
- 自动记忆提取（不完全依赖 Agent 主动 remember）
- 检索精度（语义 + 图结构，已有）
- 数据完全可控（自部署，已有）
- 接入方式全面（MCP / REST / CLI / Plugin）

## 2. Current State

### 2.1 Already Built

| Component | Detail |
|-----------|--------|
| MCP Server | Starlette + Streamable HTTP, Bearer Token auth, Cloudflare Tunnel |
| Tools (7) | remember / recall / recall_all / trace / forget / relate / graph_query |
| Data Model | MemoryNode with evolution chain (parent_id + mutation_type), entity_key uniqueness |
| Storage | LanceDB (vector) + NetworkX (graph), dual-backend with InMemory fallback |
| Conflict Detection | entity_key exact match + semantic similarity + LLM judgment |
| Deployment | Docker Compose + Cloudflare Tunnel |

### 2.2 Gaps

| Capability | Status |
|------------|--------|
| CLI client | None, MCP-only access |
| HTTP REST API | Only `/mcp` (JSON-RPC) and `/health` |
| Claude Code plugin | None |
| Auto memory extraction | Fully depends on Agent calling remember |
| Session management | None |
| Working Memory | None (recall_all is close but not structured) |
| Cross-tool behavioral guidance | No system prompt template |

## 3. Architecture

```
+-----------------------------------------------------------+
|                    Access Layer (4 modes)                  |
|                                                           |
|  +----------+ +----------+ +--------+ +-----------+      |
|  | Claude   | |   MCP    | |  CLI   | | HTTP REST |      |
|  | Code     | | Protocol | | (mem)  | |   API     |      |
|  | Plugin   | | (exists) | |        | |           |      |
|  | hooks +  | |          | |        | |           |      |
|  | skills   | |          | |        | |           |      |
|  +----+-----+ +----+-----+ +---+----+ +-----+-----+     |
|       |            |           |             |            |
|       +------------+-----+----+-------------+            |
|                          v                                |
|  +----------------------------------------------------+  |
|  |              memory-mcp server                      |  |
|  |                                                     |  |
|  |  /mcp          -- MCP JSON-RPC (exists)             |  |
|  |  /api/v1/*     -- REST API (new)                    |  |
|  |  /health       -- Health check (exists)             |  |
|  |                                                     |  |
|  |  +------------+ +----------+ +----------------+     |  |
|  |  | Memory     | | Session  | | Working Memory |     |  |
|  |  | Engine     | | Engine   | | Engine         |     |  |
|  |  | (exists)   | | (new)    | | (new)          |     |  |
|  |  +------------+ +----------+ +----------------+     |  |
|  |                      v                              |  |
|  |  +--------------------------------------------------+ |
|  |  |  Storage: LanceDB + NetworkX (exists)            | |
|  |  +--------------------------------------------------+ |
|  +----------------------------------------------------+  |
+-----------------------------------------------------------+
```

**Core design decision**: CLI as the universal glue layer. Hooks call CLI, skills call CLI, other tools call CLI. CLI calls REST API. REST API reuses existing MCP tool functions. One codebase, four access modes.

## 4. Component Design

### 4.1 REST API

Add routes to the existing Starlette app in `server.py`. Each handler extracts parameters from the HTTP request, builds an `arguments` dict, and calls the existing `*_tool()` function.

**Routes**:

| Method | Path | Handler | Maps To |
|--------|------|---------|---------|
| POST | `/api/v1/memories` | `api_remember` | `remember_tool` |
| GET | `/api/v1/memories/search` | `api_recall` | `recall_tool` |
| GET | `/api/v1/memories` | `api_recall_all` | `recall_all_tool` |
| GET | `/api/v1/memories/{entity_key:path}/trace` | `api_trace` | `trace_tool` |
| DELETE | `/api/v1/memories/{entity_key:path}` | `api_forget` | `forget_tool` |
| POST | `/api/v1/relations` | `api_relate` | `relate_tool` |
| GET | `/api/v1/graph/{entity_key:path}` | `api_graph_query` | `graph_query_tool` |
| GET | `/api/v1/wm` | `api_working_memory` | `generate_briefing` |
| POST | `/api/v1/sessions` | `api_session_create` | `SessionEngine.create` |
| POST | `/api/v1/sessions/{id}/commit` | `api_session_commit` | `SessionEngine.commit` |

**Auth**: Same Bearer Token middleware (already global via `AuthMiddleware`). The middleware currently returns `{"error": "Unauthorized"}` which doesn't match REST format. **Fix required**: Update `AuthMiddleware` to return `{"ok": false, "error": "Unauthorized"}` for consistency. This is backward-compatible since MCP clients don't parse auth error bodies.

**Response format**: All REST endpoints return JSON with consistent structure:
```json
{
  "ok": true,
  "data": { ... }
}
```
Error:
```json
{
  "ok": false,
  "error": "message"
}
```

**Request body schemas** (POST endpoints):

`POST /api/v1/memories`:
```json
{
  "content": "string (required)",
  "entity_key": "string (required)",
  "entity_type": "string (required) — person|preference|fact|event|goal|project",
  "tags": ["string (optional)"]
}
```

`POST /api/v1/relations`:
```json
{
  "from_entity_key": "string (required)",
  "to_entity_key": "string (required)",
  "relation_type": "string (required)",
  "properties": {"object (optional)"}
}
```

`POST /api/v1/sessions`:
```json
{}
```
Returns: `{"ok": true, "data": {"session_id": "uuid"}}`

`POST /api/v1/sessions/{id}/commit`:
```json
{
  "transcript": "string (required) — full conversation text, or JSON array of {role, content} messages"
}
```
This replaces the multi-step add-message approach (see Section 4.4).

**Query string parameters** (GET endpoints):

`GET /api/v1/memories/search?query=...&entity_type=...&limit=10&include_evolution=false`

`GET /api/v1/memories?entity_type=...&limit=100`

`GET /api/v1/graph/{entity_key}?relation_types=KNOWS,PREFERS&depth=1`
(relation_types: comma-separated list)

**Implementation location**: New file `src/memory_mcp/api/routes.py` for REST handlers, imported into `server.py`.

### 4.2 CLI Client (mem)

Thin CLI that calls the REST API. Single Python package, installable via `pip install memory-mcp-cli` or placed on PATH directly.

**Tech stack**: `httpx` (HTTP client) + `typer` (CLI framework).

**Commands**:

```
# Memory operations
mem remember "content" --type <entity_type> --key <entity_key> [--tags tag1,tag2]
mem recall "query" [--type <entity_type>] [--limit N] [--evolution]
mem recall --all [--type <entity_type>] [--limit N]
mem trace <entity_key>
mem forget <entity_key> [--reason "reason"]

# Relations
mem relate <from_key> <to_key> --type <relation_type>

# Session (for auto extraction)
mem session create                                    # returns session_id
mem session commit <session_id> --transcript <file>   # send full transcript, extract memories

# Working Memory
mem wm

# Status
mem status
mem config
```

**Configuration**: `~/.config/memory-mcp/config.json`
```json
{
  "api_url": "https://memory-mcp.your-domain.com",
  "api_key": "your-token"
}
```

Also supports env vars: `MEMORY_MCP_API_URL`, `MEMORY_MCP_API_KEY`.

**Output**: JSON by default, `--format text` for human-readable.

**Project location**: `cli/` directory within the memory-mcp repo (monorepo approach). Separate `pyproject.toml` for independent install.

```
cli/
  pyproject.toml
  src/
    memory_mcp_cli/
      __init__.py
      main.py        # typer app, all commands
      client.py      # httpx wrapper
      config.py      # config loading
```

### 4.3 Working Memory Engine

Server-side module that generates a structured briefing from recent and important memories. No LLM needed — template-based assembly.

**Location**: `src/memory_mcp/engine/working_memory.py`

**Logic**:
1. Fetch all current memories via `vector_store.list_current()`
2. Group by `entity_type`
3. Identify recent changes: filter nodes where `created_at` is within 7 days AND `parent_id is not None` (means evolved). For each such node, call `vector_store.get_by_id(parent_id)` to get the previous content for the "old -> new" display. To avoid N+1 queries on large datasets, limit recent changes to the 20 most recent evolved nodes.
4. Identify conflicts (`conflict == True`)
5. Count evolution depth per entity: count nodes in `get_history(entity_key)` — this is already cached in the list_current result set, no extra query needed for count
6. Assemble markdown briefing

**Output format**:
```markdown
## Active Context
- [preference] editor: Cursor (evolved 3 times)
- [project] memory-mcp: personal memory service
- [goal] build cross-tool persistent memory

## Recent Changes (7d)
- preference:editor -- evolution: VSCode -> Cursor

## Flags
- [conflict] fact:xxx -- conflicting information, needs confirmation
```

**Integration**: Exposed via `GET /api/v1/wm` and `mem wm` CLI command.

### 4.4 Session Engine

Server-side module for conversation-based memory extraction. Stores conversation messages, then uses LLM to extract candidate memories on commit.

**Location**: `src/memory_mcp/engine/session.py`

**Data model**:
```python
class SessionMessage(BaseModel):
    role: str       # "user" | "assistant"
    content: str
    timestamp: datetime

class Session(BaseModel):
    id: str
    messages: list[SessionMessage]
    created_at: datetime
    committed: bool = False
```

**Storage**: In-memory dict + JSON persistence in `data/sessions/` (enabled by default). Sessions are ephemeral — they exist only until committed, then cleaned up after successful commit.

**Simplified API**: Instead of multi-step create/add/commit, the primary flow is a single commit call that accepts the full transcript:

```
POST /api/v1/sessions/{id}/commit
Body: {"transcript": "full conversation text or JSON messages array"}
```

The `create` endpoint returns a session_id. The `commit` endpoint accepts transcript and does extraction in one shot. This avoids the N-requests-per-message problem.

**Commit flow**:
1. LLM analyzes transcript and extracts candidate memories
2. Each candidate is a `{entity_key, entity_type, content}` tuple
3. Each candidate goes through the existing `remember_tool()` pipeline — conflict detection, evolution chain, graph update all reused
4. Return extraction results (what was created/evolved/skipped)

**LLM client**: Session Engine creates its own httpx call to OpenRouter (same pattern as `ConflictDetector` in `conflict.py`). Both share `settings.openrouter_api_key`, `settings.openrouter_base_url`, and `settings.llm_model`. No need for a shared abstraction now — if a third LLM caller appears later, refactor then.

**Extraction prompt** (core):
```
Analyze this conversation and extract information worth remembering long-term.

Categories: preference / fact / event / goal / project / person
For each item output a JSON array:
[
  {"entity_key": "preference:editor", "entity_type": "preference", "content": "Prefers Cursor as primary editor"}
]

Rules:
- Only extract information with long-term value
- Skip temporary discussions, greetings, debugging details
- Use descriptive entity_keys like "preference:editor" or "project:memory-mcp"
- Content should be a concise, self-contained statement
- Output ONLY the JSON array, no other text
```

**LLM output parsing**: Parse response as JSON array. If parsing fails (malformed JSON), attempt to extract JSON from markdown code fences. If still fails, log error and return empty extraction result — never crash.

**LLM**: Uses `settings.llm_model` (default: `anthropic/claude-3-haiku` via OpenRouter).

### 4.5 Claude Code Plugin

Plugin structure for Claude Code, using hooks + skills + CLI.

**Location**: Separate directory `claude-code-plugin/` in the repo.

```
claude-code-plugin/
  hooks/
    session-start.sh       # mem wm -> inject as systemMessage
    stop.sh                # async: extract transcript -> session commit
  skills/
    search-memory/SKILL.md
    save-memory/SKILL.md
  commands/
    save.md                # /save
    search.md              # /search <query>
    status.md              # /status
  README.md
```

**Hooks behavior**:

| Hook | Action | Blocking |
|------|--------|----------|
| SessionStart | `mem wm` -> return as system message | Sync, 8s timeout |
| Stop | Collect transcript -> `mem session commit` | Async, 120s timeout |

**Stop hook transcript handling**: Claude Code provides conversation context via `$CLAUDE_CONVERSATION` env var (JSON). The `stop.sh` script:
1. Reads `$CLAUDE_CONVERSATION` (or falls back to reading the transcript file)
2. Calls `mem session create` to get a session_id
3. Calls `mem session commit <session_id> --transcript <file_or_stdin>` — sends the full transcript in one request
4. Server extracts memories from the transcript in one LLM call

**Phase 3 initial behavior**: In Phase 3 (before Session Engine exists), `stop.sh` is a no-op placeholder. It only becomes functional in Phase 4 when Session Engine is ready.

**Key design**: Hooks only call `mem` CLI, never Python bridge. This means:
- Claude Code doesn't need Python runtime
- Decoupled from MCP transport
- Same CLI reusable by any tool

**Skills**:

- `search-memory`: Prompts Claude to use `mem recall` for relevant context lookup
- `save-memory`: Prompts Claude to use `mem remember` for saving important decisions/preferences

**Commands**:

- `/save [content]`: Quick save via `mem remember`
- `/search <query>`: Quick search via `mem recall`
- `/status`: Show `mem status` + `mem wm` summary

### 4.6 Cross-Tool Integration

| Tool | Integration Method |
|------|-------------------|
| Claude Code | Plugin (hooks + skills + CLI) |
| Cursor | MCP (existing `/mcp` endpoint) |
| Gemini CLI | System prompt + CLI (`mem` commands) |
| Claude Desktop | MCP (existing) |
| Others | System prompt template + MCP or CLI |

**Behavioral guidance template** (`behavioral-guidance.md`): A markdown template to embed in any tool's system prompt.

```markdown
## Memory Available
- Search memories: `mem recall "query"`
- Save important info: `mem remember "content" --type <type> --key <key>`
- View current context: `mem wm`

## When to Search
- User references previous decisions/preferences/projects
- Debugging a familiar-looking issue
- Need prior context

## When to Save
- Important decision made
- Hard problem solved (with root cause)
- New preference/habit discovered
- Do NOT save temporary, generic, or widely-known information
```

## 5. Implementation Phases

### Phase 1: REST API + CLI (priority: highest)

**Server side**:
- New file: `src/memory_mcp/api/__init__.py`
- New file: `src/memory_mcp/api/routes.py` — REST handlers wrapping existing tool functions
- Edit: `server.py` — import and mount REST routes

**CLI side**:
- New directory: `cli/`
- `cli/pyproject.toml` — package definition
- `cli/src/memory_mcp_cli/main.py` — typer CLI app
- `cli/src/memory_mcp_cli/client.py` — httpx REST client
- `cli/src/memory_mcp_cli/config.py` — config loading

**Validation**: `mem recall "test"` and `mem remember "test" --type fact --key fact:test` work against deployed server.

### Phase 2: Working Memory

- New file: `src/memory_mcp/engine/working_memory.py`
- Edit: `src/memory_mcp/api/routes.py` — add `GET /api/v1/wm`
- Edit: `cli/src/memory_mcp_cli/main.py` — add `mem wm` command

**Validation**: `mem wm` returns structured briefing.

### Phase 3: Claude Code Plugin

- New directory: `claude-code-plugin/`
- Hook scripts: `session-start.sh`, `stop.sh`
- Skills: `search-memory/SKILL.md`, `save-memory/SKILL.md`
- Commands: `save.md`, `search.md`, `status.md`

**Validation**: In Claude Code, SessionStart hook injects working memory, /search and /save commands work.

### Phase 4: Session + Auto Extraction

- New file: `src/memory_mcp/engine/session.py`
- Edit: `src/memory_mcp/api/routes.py` — add session endpoints
- Edit: `cli/src/memory_mcp_cli/main.py` — add `mem session` commands
- Edit: `claude-code-plugin/hooks/stop.sh` — switch to session mode

**Validation**: `mem session create` -> `mem session commit <id> --transcript <file>` extracts and stores memories.

### Phase 5: Behavioral Guidance + Other Tools

- New file: `docs/behavioral-guidance.md`
- Verify Cursor MCP integration
- Write Gemini CLI system prompt template

**Validation**: Cursor and Gemini CLI can access memories.

## 6. Data Flow Examples

### 6.1 Claude Code Session Lifecycle

```
SessionStart hook fires
  -> mem wm
  -> CLI calls GET /api/v1/wm
  -> Server assembles briefing from vector_store.list_current()
  -> Returns markdown briefing
  -> Hook injects as system message
  -> Claude sees: "## Active Context ..."

User works with Claude...

Stop hook fires (async)
  -> Read $CLAUDE_CONVERSATION transcript
  -> mem session create -> POST /api/v1/sessions -> returns session_id
  -> mem session commit <id> --transcript <file>
     -> POST /api/v1/sessions/{id}/commit with full transcript
     -> Server: LLM extracts candidates from transcript
     -> Each candidate: remember_tool(arguments)
       -> Conflict detection
       -> Evolution chain
       -> Graph update
     -> Returns: {extracted: 3, evolved: 1, created: 2, skipped: 0}
```

### 6.2 CLI Direct Usage

```
$ mem remember "Prefer dark mode in all editors" --type preference --key preference:dark-mode
{"ok": true, "data": {"status": "created", "memory_id": "abc-123", ...}}

$ mem recall "editor theme"
{"ok": true, "data": {"results": [{"entity_key": "preference:dark-mode", "content": "Prefer dark mode in all editors", "relevance": 0.92}], "total": 1}}
```

## 7. Error Handling

- REST API returns HTTP status codes: 200 (success), 400 (bad request), 401 (unauthorized), 500 (server error)
- CLI exits with code 0 on success, 1 on error, prints error to stderr
- Session commit: if LLM extraction fails, returns partial results + error details for failed candidates
- Working Memory: if vector_store is empty, returns a minimal briefing ("No memories yet")
- Hooks: timeout gracefully — SessionStart falls back to no injection, Stop logs failure but doesn't block

## 8. Testing Strategy

| Component | Test Type | Approach |
|-----------|-----------|----------|
| REST API routes | Unit + Integration | pytest-asyncio, mock tool functions, test HTTP layer with Starlette TestClient |
| CLI | Unit | Mock httpx responses, verify command parsing and output formatting |
| Working Memory | Unit | Feed known MemoryNode list, verify briefing output |
| Session Engine | Unit + Integration | Mock LLM responses, verify extraction -> remember pipeline |
| Plugin hooks | Manual | Run in Claude Code, verify injection and extraction |

Existing tests for remember/recall/conflict/evolution remain unchanged.

## 9. Dependencies

### Server (additions to existing pyproject.toml)

No new dependencies needed — Starlette already available, all tool functions already exist.

### CLI (new pyproject.toml)

```
httpx>=0.27.0
typer>=0.12.0
```

### Plugin

No dependencies — shell scripts calling `mem` CLI binary.

## 10. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Session commit LLM hallucination | Bad memories extracted | remember_tool's conflict detection catches contradictions; extraction prompt enforces conservative extraction |
| CLI install friction | Adoption barrier | Single `pip install` or standalone binary via PyInstaller |
| Hook timeout in Claude Code | Missing injection/extraction | Graceful fallback (no injection / async retry) |
| REST API adds attack surface | Security | Same auth middleware, rate limiting can be added later |
| Large transcripts exceed LLM context | Extraction failure | Truncate to last N messages or chunk-and-merge |
