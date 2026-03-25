# Memory MCP Extension Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add REST API, CLI client, Working Memory, Auto Extraction, and Claude Code Plugin to the existing memory-mcp server.

**Architecture:** REST routes are thin wrappers around existing `*_tool()` functions, mounted on the same Starlette app. CLI (`mem`) calls REST API via httpx. Working Memory assembles briefings from current memories without LLM. Extraction Engine uses LLM to extract candidate memories from conversation transcripts. Claude Code Plugin uses hooks + skills that call `mem` CLI.

**Tech Stack:** Python 3.11+, Starlette (existing), httpx, typer, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-24-memory-mcp-extension-design.md`

---

## File Structure

### Server Side (additions/modifications)

| File | Action | Responsibility |
|------|--------|----------------|
| `src/memory_mcp/transport/auth.py` | Modify | Update error response format to `{"ok": false, "error": ...}` |
| `src/memory_mcp/api/__init__.py` | Create | Empty package init |
| `src/memory_mcp/api/routes.py` | Create | All REST route handlers |
| `src/memory_mcp/server.py` | Modify | Mount REST routes |
| `src/memory_mcp/engine/working_memory.py` | Create | Briefing generator |
| `src/memory_mcp/engine/extraction.py` | Create | LLM-based memory extraction |
| `src/memory_mcp/tools/remember.py` | Modify | Add `skip_semantic_merge` param |
| `AGENTS.md` | Modify | Already done — protocol positioning updated |

### Tests

| File | Action | Tests |
|------|--------|-------|
| `tests/test_api.py` | Create | REST API routes via Starlette TestClient |
| `tests/test_working_memory.py` | Create | Briefing assembly logic |
| `tests/test_extraction.py` | Create | LLM extraction + remember pipeline |

### CLI

| File | Action | Responsibility |
|------|--------|----------------|
| `cli/pyproject.toml` | Create | Package definition |
| `cli/src/memory_mcp_cli/__init__.py` | Create | Empty package init |
| `cli/src/memory_mcp_cli/config.py` | Create | Config loading (file + env vars) |
| `cli/src/memory_mcp_cli/client.py` | Create | httpx REST client wrapper |
| `cli/src/memory_mcp_cli/main.py` | Create | Typer app with all commands |
| `cli/tests/__init__.py` | Create | Empty |
| `cli/tests/test_cli.py` | Create | CLI command tests with mocked HTTP |

### Claude Code Plugin

| File | Action | Responsibility |
|------|--------|----------------|
| `claude-code-plugin/hooks/session-start.sh` | Create | Inject working memory via stdout |
| `claude-code-plugin/hooks/stop.sh` | Create | Extract memories from transcript |
| `claude-code-plugin/skills/search-memory/SKILL.md` | Create | Prompt for memory search |
| `claude-code-plugin/skills/save-memory/SKILL.md` | Create | Prompt for memory save |
| `claude-code-plugin/commands/save.md` | Create | /save slash command |
| `claude-code-plugin/commands/search.md` | Create | /search slash command |
| `claude-code-plugin/commands/status.md` | Create | /status slash command |
| `claude-code-plugin/README.md` | Create | Installation & usage guide |

---

## Chunk 1: REST API Server Side

### Task 1: Fix AuthMiddleware Error Format

**Files:**
- Modify: `src/memory_mcp/transport/auth.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing tests for auth error format**

Create `tests/test_api.py`:

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
def auth_headers():
    return {"Authorization": "Bearer test-token"}


class TestAuthMiddleware:
    def test_missing_auth_returns_401_with_ok_false(self, client):
        resp = client.get("/api/v1/memories")
        assert resp.status_code == 401
        body = resp.json()
        assert body["ok"] is False
        assert "error" in body

    def test_wrong_token_returns_403_with_ok_false(self, client):
        resp = client.get(
            "/api/v1/memories",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body["ok"] is False
        assert "error" in body

    def test_valid_token_passes(self, client, auth_headers):
        resp = client.get("/api/v1/memories", headers=auth_headers)
        assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api.py::TestAuthMiddleware -v`
Expected: FAIL (routes don't exist yet, but auth tests should fail on format)

- [ ] **Step 3: Fix AuthMiddleware**

Edit `src/memory_mcp/transport/auth.py` — change both error responses:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request

from ..config import settings


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health" or request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

        token = auth_header.split(" ", 1)[1]
        if token != settings.auth_token:
            return JSONResponse({"ok": False, "error": "Forbidden"}, status_code=403)

        return await call_next(request)
```

- [ ] **Step 4: Commit auth fix (tests still pending REST routes)**

```bash
git add src/memory_mcp/transport/auth.py
git commit -m "fix: update AuthMiddleware error format to {ok: false, error}"
```

### Task 2: Create REST API Routes

**Files:**
- Create: `src/memory_mcp/api/__init__.py`
- Create: `src/memory_mcp/api/routes.py`
- Modify: `src/memory_mcp/server.py`

- [ ] **Step 1: Create empty package init**

Create `src/memory_mcp/api/__init__.py` — empty file.

- [ ] **Step 2: Create REST route handlers**

Create `src/memory_mcp/api/routes.py`:

```python
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..tools import remember, recall, recall_all, trace, forget, relate, graph_query

logger = logging.getLogger("memory-mcp.api")


def _ok(data: dict) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data})


def _err(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


async def api_remember(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        result = await remember.remember_tool(body)
        return _ok(result)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error("api_remember error: %s", e)
        return _err(str(e), 500)


async def api_recall(request: Request) -> JSONResponse:
    try:
        args = {
            "query": request.query_params.get("query", ""),
            "entity_type": request.query_params.get("entity_type"),
            "limit": int(request.query_params.get("limit", "10")),
            "include_evolution": request.query_params.get("include_evolution", "false").lower() == "true",
        }
        if not args["query"]:
            return _err("Missing required parameter: query")
        result = await recall.recall_tool(args)
        return _ok(result)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error("api_recall error: %s", e)
        return _err(str(e), 500)


async def api_recall_all(request: Request) -> JSONResponse:
    try:
        args = {
            "entity_type": request.query_params.get("entity_type"),
            "limit": int(request.query_params.get("limit", "100")),
        }
        result = await recall_all.recall_all_tool(args)
        return _ok(result)
    except Exception as e:
        logger.error("api_recall_all error: %s", e)
        return _err(str(e), 500)


async def api_trace(request: Request) -> JSONResponse:
    try:
        entity_key = request.path_params["entity_key"]
        args = {
            "entity_key": entity_key,
            "format": request.query_params.get("format", "timeline"),
        }
        result = await trace.trace_tool(args)
        return _ok(result)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error("api_trace error: %s", e)
        return _err(str(e), 500)


async def api_forget(request: Request) -> JSONResponse:
    try:
        entity_key = request.path_params["entity_key"]
        body = {}
        if request.headers.get("content-type", "").startswith("application/json"):
            body = await request.json()
        args = {"entity_key": entity_key, "reason": body.get("reason", "User requested archive")}
        result = await forget.forget_tool(args)
        return _ok(result)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error("api_forget error: %s", e)
        return _err(str(e), 500)


async def api_relate(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        result = await relate.relate_tool(body)
        return _ok(result)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error("api_relate error: %s", e)
        return _err(str(e), 500)


async def api_graph_query(request: Request) -> JSONResponse:
    try:
        entity_key = request.path_params["entity_key"]
        relation_types_raw = request.query_params.get("relation_types", "")
        args = {
            "entity_key": entity_key,
            "relation_types": [t.strip() for t in relation_types_raw.split(",") if t.strip()] or None,
            "depth": int(request.query_params.get("depth", "1")),
        }
        result = await graph_query.graph_query_tool(args)
        return _ok(result)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error("api_graph_query error: %s", e)
        return _err(str(e), 500)


api_routes = [
    Route("/api/v1/memories/search", endpoint=api_recall, methods=["GET"]),
    Route("/api/v1/memories/{entity_key:path}/trace", endpoint=api_trace, methods=["GET"]),
    Route("/api/v1/memories/{entity_key:path}", endpoint=api_forget, methods=["DELETE"]),
    Route("/api/v1/memories", endpoint=api_remember, methods=["POST"]),
    Route("/api/v1/memories", endpoint=api_recall_all, methods=["GET"]),
    Route("/api/v1/relations", endpoint=api_relate, methods=["POST"]),
    Route("/api/v1/graph/{entity_key:path}", endpoint=api_graph_query, methods=["GET"]),
]
```

Note: `/api/v1/memories/search` must be before `/api/v1/memories` for Starlette routing to work. `/api/v1/wm` and `/api/v1/memories/extract` are added in later tasks.

- [ ] **Step 3: Mount REST routes in server.py**

Edit `src/memory_mcp/server.py` — add import and merge routes:

Add import after existing imports (line 27):
```python
from .api.routes import api_routes
```

Replace the `routes` list in `Starlette(...)` (line 250-253):
```python
app = Starlette(
    lifespan=streamable_http_app.lifespan,
    routes=[
        Route("/mcp", endpoint=streamable_http_app, methods=["GET", "POST", "DELETE"]),
        Route("/health", endpoint=health, methods=["GET"]),
    ] + api_routes,
    middleware=[
        Middleware(CorsMiddleware),
        Middleware(AuthMiddleware),
    ]
)
```

- [ ] **Step 4: Run auth tests to verify they pass now**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api.py::TestAuthMiddleware -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/api/ src/memory_mcp/server.py tests/test_api.py
git commit -m "feat: add REST API routes wrapping existing tool functions"
```

### Task 3: Test REST API Endpoints

**Files:**
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add REST endpoint tests**

Append to `tests/test_api.py`:

```python
class TestRestMemories:
    def test_remember_creates_memory(self, client, auth_headers):
        resp = client.post(
            "/api/v1/memories",
            json={
                "content": "Prefer dark mode",
                "entity_key": "preference:theme",
                "entity_type": "preference",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "created"

    def test_remember_missing_fields(self, client, auth_headers):
        resp = client.post(
            "/api/v1/memories",
            json={"content": "incomplete"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["ok"] is False

    def test_recall_all(self, client, auth_headers):
        # Create a memory first
        client.post(
            "/api/v1/memories",
            json={
                "content": "Test memory",
                "entity_key": "fact:test",
                "entity_type": "fact",
            },
            headers=auth_headers,
        )
        resp = client.get("/api/v1/memories", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["total"] >= 1

    def test_recall_search(self, client, auth_headers):
        client.post(
            "/api/v1/memories",
            json={
                "content": "Python is my favorite language",
                "entity_key": "preference:language",
                "entity_type": "preference",
            },
            headers=auth_headers,
        )
        resp = client.get(
            "/api/v1/memories/search?query=Python",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_recall_search_missing_query(self, client, auth_headers):
        resp = client.get("/api/v1/memories/search", headers=auth_headers)
        assert resp.status_code == 400

    def test_trace(self, client, auth_headers):
        client.post(
            "/api/v1/memories",
            json={
                "content": "v1",
                "entity_key": "fact:version",
                "entity_type": "fact",
            },
            headers=auth_headers,
        )
        resp = client.get(
            "/api/v1/memories/fact:version/trace",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["total_versions"] == 1

    def test_forget(self, client, auth_headers):
        client.post(
            "/api/v1/memories",
            json={
                "content": "temp memory",
                "entity_key": "fact:temp",
                "entity_type": "fact",
            },
            headers=auth_headers,
        )
        resp = client.request(
            "DELETE",
            "/api/v1/memories/fact:temp",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "archived"

    def test_relate_and_graph_query(self, client, auth_headers):
        resp = client.post(
            "/api/v1/relations",
            json={
                "from_entity_key": "person:alice",
                "to_entity_key": "project:x",
                "relation_type": "WORKS_ON",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "created"

        resp = client.get(
            "/api/v1/graph/person:alice?depth=1",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["count"] >= 1
```

- [ ] **Step 2: Run all REST tests**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_api.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite to ensure no regressions**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest -v`
Expected: All existing tests still PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_api.py
git commit -m "test: add REST API endpoint tests"
```

---

## Chunk 2: CLI Client

### Task 4: CLI Package Setup

**Files:**
- Create: `cli/pyproject.toml`
- Create: `cli/src/memory_mcp_cli/__init__.py`
- Create: `cli/src/memory_mcp_cli/config.py`

- [ ] **Step 1: Create CLI pyproject.toml**

```toml
[project]
name = "memory-mcp-cli"
version = "0.1.0"
description = "CLI client for memory-mcp server"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27.0",
    "typer>=0.12.0",
]

[project.scripts]
mem = "memory_mcp_cli.main:app"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/memory_mcp_cli"]
```

- [ ] **Step 2: Create empty init**

Create `cli/src/memory_mcp_cli/__init__.py` — empty file.

- [ ] **Step 3: Create config module**

Create `cli/src/memory_mcp_cli/config.py`:

```python
import json
import os
from pathlib import Path


def _config_path() -> Path:
    return Path(os.environ.get("MEM_CONFIG_PATH", Path.home() / ".config" / "memory-mcp" / "config.json"))


def load_config() -> dict:
    """Load config from file, env vars override file values."""
    cfg = {"api_url": "http://localhost:8765", "api_key": ""}
    path = _config_path()
    if path.exists():
        with open(path) as f:
            cfg.update(json.load(f))
    cfg["api_url"] = os.environ.get("MEMORY_MCP_API_URL", cfg["api_url"])
    cfg["api_key"] = os.environ.get("MEMORY_MCP_API_KEY", cfg["api_key"])
    return cfg
```

- [ ] **Step 4: Commit**

```bash
git add cli/
git commit -m "feat(cli): scaffold CLI package with config module"
```

### Task 5: CLI HTTP Client

**Files:**
- Create: `cli/src/memory_mcp_cli/client.py`

- [ ] **Step 1: Create HTTP client wrapper**

Create `cli/src/memory_mcp_cli/client.py`:

```python
from __future__ import annotations

import sys
from typing import Any

import httpx

from .config import load_config


class MemClient:
    def __init__(self, cfg: dict | None = None):
        self._cfg = cfg or load_config()
        self._base = self._cfg["api_url"].rstrip("/")
        self._headers = {"Authorization": f"Bearer {self._cfg['api_key']}"}

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def _handle(self, resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = {"ok": False, "error": resp.text}
            print(f"Error: {body.get('error', resp.text)}", file=sys.stderr)
            raise SystemExit(1)
        return resp.json()

    def remember(self, content: str, entity_key: str, entity_type: str, tags: list[str] | None = None) -> dict:
        body: dict[str, Any] = {"content": content, "entity_key": entity_key, "entity_type": entity_type}
        if tags:
            body["tags"] = tags
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.post(self._url("/api/v1/memories"), json=body))

    def recall(self, query: str, entity_type: str | None = None, limit: int = 10, include_evolution: bool = False) -> dict:
        params: dict[str, Any] = {"query": query, "limit": limit, "include_evolution": str(include_evolution).lower()}
        if entity_type:
            params["entity_type"] = entity_type
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(self._url("/api/v1/memories/search"), params=params))

    def recall_all(self, entity_type: str | None = None, limit: int = 100) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if entity_type:
            params["entity_type"] = entity_type
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(self._url("/api/v1/memories"), params=params))

    def trace(self, entity_key: str, fmt: str = "timeline") -> dict:
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(self._url(f"/api/v1/memories/{entity_key}/trace"), params={"format": fmt}))

    def forget(self, entity_key: str, reason: str | None = None) -> dict:
        body = {"reason": reason} if reason else {}
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.request("DELETE", self._url(f"/api/v1/memories/{entity_key}"), json=body))

    def relate(self, from_key: str, to_key: str, relation_type: str) -> dict:
        body = {"from_entity_key": from_key, "to_entity_key": to_key, "relation_type": relation_type}
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.post(self._url("/api/v1/relations"), json=body))

    def graph_query(self, entity_key: str, relation_types: list[str] | None = None, depth: int = 1) -> dict:
        params: dict[str, Any] = {"depth": depth}
        if relation_types:
            params["relation_types"] = ",".join(relation_types)
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(self._url(f"/api/v1/graph/{entity_key}"), params=params))

    def wm(self) -> dict:
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(self._url("/api/v1/wm")))

    def extract(self, messages: list[dict]) -> dict:
        with httpx.Client(headers=self._headers, timeout=120) as c:
            return self._handle(c.post(self._url("/api/v1/memories/extract"), json={"messages": messages}))
```

- [ ] **Step 2: Commit**

```bash
git add cli/src/memory_mcp_cli/client.py
git commit -m "feat(cli): add HTTP client wrapper for REST API"
```

### Task 6: CLI Commands (Typer App)

**Files:**
- Create: `cli/src/memory_mcp_cli/main.py`

- [ ] **Step 1: Create typer app with all commands**

Create `cli/src/memory_mcp_cli/main.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from .client import MemClient

app = typer.Typer(name="mem", help="CLI client for memory-mcp server", no_args_is_help=True)


def _out(data: dict, fmt: str) -> None:
    if fmt == "text":
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        # Single-value dict with string value: print directly (e.g., briefing)
        if isinstance(data, dict) and len(data) == 1:
            val = next(iter(data.values()))
            if isinstance(val, str):
                print(val)
                return
        if isinstance(data, str):
            print(data)
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False))


_format_opt = typer.Option("json", "--format", "-f", help="Output format: json or text")


@app.command()
def remember(
    content: str,
    type: str = typer.Option(..., "--type", "-t", help="Entity type"),
    key: str = typer.Option(..., "--key", "-k", help="Entity key"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
    format: str = _format_opt,
) -> None:
    """Store a new memory."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    _out(MemClient().remember(content, key, type, tag_list), format)


@app.command()
def recall(
    query: Optional[str] = typer.Argument(None),
    all: bool = typer.Option(False, "--all", help="Fetch all memories"),
    type: Optional[str] = typer.Option(None, "--type", "-t"),
    limit: int = typer.Option(10, "--limit", "-l"),
    evolution: bool = typer.Option(False, "--evolution"),
    format: str = _format_opt,
) -> None:
    """Search for memories."""
    c = MemClient()
    if all:
        _out(c.recall_all(type, limit), format)
    else:
        if not query:
            print("Error: query is required (or use --all)", file=sys.stderr)
            raise typer.Exit(1)
        _out(c.recall(query, type, limit, evolution), format)


@app.command()
def trace(
    entity_key: str,
    trace_format: str = typer.Option("timeline", "--trace-format", help="Trace format: timeline or summary"),
    format: str = _format_opt,
) -> None:
    """Trace evolution history of an entity."""
    _out(MemClient().trace(entity_key, trace_format), format)


@app.command()
def forget(
    entity_key: str,
    reason: Optional[str] = typer.Option(None, "--reason"),
    format: str = _format_opt,
) -> None:
    """Archive a memory."""
    _out(MemClient().forget(entity_key, reason), format)


@app.command()
def relate(
    from_key: str,
    to_key: str,
    type: str = typer.Option(..., "--type", "-t"),
    format: str = _format_opt,
) -> None:
    """Create a relationship between entities."""
    _out(MemClient().relate(from_key, to_key, type), format)


@app.command()
def wm(format: str = _format_opt) -> None:
    """Get working memory briefing."""
    _out(MemClient().wm(), format)


@app.command()
def extract(
    transcript: Optional[Path] = typer.Option(None, "--transcript", help="Path to transcript file (JSONL/JSON). Reads stdin if omitted."),
    format: str = _format_opt,
) -> None:
    """Extract memories from a conversation transcript."""
    messages = _parse_transcript(transcript)
    if not messages:
        print("Error: no user/assistant messages found in transcript", file=sys.stderr)
        raise typer.Exit(1)
    _out(MemClient().extract(messages), format)


def _parse_transcript(path: Path | None) -> list[dict]:
    """Read transcript from file or stdin, return [{role, content}]."""
    if path:
        text = path.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    # Try JSON array first
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return _filter_messages(data)
    except json.JSONDecodeError:
        pass

    # Try JSONL (one JSON object per line)
    messages = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            messages.append(obj)
        except json.JSONDecodeError:
            continue

    return _filter_messages(messages)


def _filter_messages(items: list[dict]) -> list[dict]:
    """Filter to user/assistant messages with content."""
    result = []
    for item in items:
        role = item.get("role", "")
        content = item.get("content", "")
        if role in ("user", "assistant") and content:
            result.append({"role": role, "content": content})
    return result


@app.command()
def status(format: str = _format_opt) -> None:
    """Check server connectivity."""
    from .config import load_config
    cfg = load_config()
    import httpx
    try:
        resp = httpx.get(f"{cfg['api_url'].rstrip('/')}/health", timeout=5)
        _out({"status": "connected", "server": resp.json()}, format)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(1)


@app.command()
def config() -> None:
    """Show current configuration."""
    from .config import load_config
    cfg = load_config()
    cfg["api_key"] = cfg["api_key"][:4] + "****" if len(cfg["api_key"]) > 4 else "****"
    print(json.dumps(cfg, indent=2))
```

- [ ] **Step 2: Commit**

```bash
git add cli/src/memory_mcp_cli/main.py
git commit -m "feat(cli): add typer commands for all memory operations"
```

### Task 7: CLI Tests

**Files:**
- Create: `cli/tests/__init__.py`
- Create: `cli/tests/test_cli.py`

- [ ] **Step 1: Create CLI tests with mocked HTTP**

Create `cli/tests/__init__.py` — empty file.

Create `cli/tests/test_cli.py`:

```python
import json
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from memory_mcp_cli.main import app, _parse_transcript, _filter_messages

runner = CliRunner()


@pytest.fixture(autouse=True)
def mock_config(monkeypatch):
    monkeypatch.setenv("MEMORY_MCP_API_URL", "http://test:8765")
    monkeypatch.setenv("MEMORY_MCP_API_KEY", "test-key")


def _mock_response(data: dict, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"ok": True, "data": data}
    return resp


class TestTranscriptParsing:
    def test_parse_json_array(self, tmp_path):
        f = tmp_path / "t.json"
        f.write_text(json.dumps([
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "system", "content": "skip"},
        ]))
        msgs = _parse_transcript(f)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"

    def test_parse_jsonl(self, tmp_path):
        f = tmp_path / "t.jsonl"
        lines = [
            json.dumps({"role": "user", "content": "hello"}),
            json.dumps({"role": "assistant", "content": "hi"}),
        ]
        f.write_text("\n".join(lines))
        msgs = _parse_transcript(f)
        assert len(msgs) == 2

    def test_filter_messages(self):
        items = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "tool", "content": "c"},
            {"role": "user", "content": ""},
        ]
        assert len(_filter_messages(items)) == 2


class TestCliCommands:
    @patch("memory_mcp_cli.client.httpx.Client")
    def test_remember(self, mock_client_cls):
        mock_ctx = MagicMock()
        mock_ctx.post.return_value = _mock_response({"status": "created", "memory_id": "123"})
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_ctx

        result = runner.invoke(app, ["remember", "test content", "--type", "fact", "--key", "fact:test"])
        assert result.exit_code == 0
        assert "created" in result.stdout

    @patch("memory_mcp_cli.client.httpx.Client")
    def test_recall_all(self, mock_client_cls):
        mock_ctx = MagicMock()
        mock_ctx.get.return_value = _mock_response({"results": [], "total": 0})
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_ctx

        result = runner.invoke(app, ["recall", "--all"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Install CLI dev deps and run tests**

Run: `cd /Users/kassol/Workspace/memory-mcp/cli && pip install -e ".[dev]" && pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add cli/tests/
git commit -m "test(cli): add CLI command and transcript parsing tests"
```

---

## Chunk 3: Working Memory + Extraction Engine

### Task 8: Working Memory Engine

**Files:**
- Create: `src/memory_mcp/engine/working_memory.py`
- Create: `tests/test_working_memory.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_working_memory.py`:

```python
import importlib

import anyio
from datetime import datetime, timezone, timedelta


def _get_briefing():
    """Reload working_memory to pick up reloaded vector_store from test_env fixture."""
    import memory_mcp.engine.working_memory as wm_mod
    importlib.reload(wm_mod)
    return wm_mod.generate_briefing


def test_briefing_empty(test_env):
    async def run():
        generate_briefing = _get_briefing()
        result = await generate_briefing()
        assert "No memories yet" in result
    anyio.run(run)


def test_briefing_groups_by_type(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({"content": "Use Cursor", "entity_key": "preference:editor", "entity_type": "preference"})
        await remember.remember_tool({"content": "Build memory-mcp", "entity_key": "project:memory-mcp", "entity_type": "project"})

        generate_briefing = _get_briefing()
        result = await generate_briefing()
        assert "[preference]" in result
        assert "[project]" in result
    anyio.run(run)


def test_briefing_shows_recent_changes(tools, test_env):
    async def run():
        remember, *_ = tools
        await remember.remember_tool({"content": "Use VSCode", "entity_key": "preference:editor", "entity_type": "preference"})
        await remember.remember_tool({"content": "Use Cursor", "entity_key": "preference:editor", "entity_type": "preference"})

        generate_briefing = _get_briefing()
        result = await generate_briefing()
        assert "Recent Changes" in result
        assert "preference:editor" in result
    anyio.run(run)


def test_briefing_shows_conflicts(tools, test_env):
    async def run():
        remember, *_ = tools

        # Create a memory and manually set conflict flag
        await remember.remember_tool({"content": "I live in Beijing", "entity_key": "fact:location", "entity_type": "fact"})

        import memory_mcp.storage.vector as vector_mod
        importlib.reload(vector_mod)
        history = await vector_mod.vector_store.get_history("fact:location")
        node = history[0]
        node.conflict = True
        await vector_mod.vector_store.update(node)

        generate_briefing = _get_briefing()
        result = await generate_briefing()
        assert "Flags" in result
        assert "conflict" in result.lower()
    anyio.run(run)
```

- [ ] **Step 2: Run to verify tests fail**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_working_memory.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement Working Memory Engine**

Create `src/memory_mcp/engine/working_memory.py`:

```python
from datetime import datetime, timezone, timedelta

from ..storage.vector import vector_store


async def generate_briefing() -> str:
    all_current = await vector_store.list_current(limit=200)

    if not all_current:
        return "No memories yet."

    # Group by entity_type
    by_type: dict[str, list] = {}
    for node in all_current:
        by_type.setdefault(node.entity_type, []).append(node)

    # Active Context
    lines = ["## Active Context"]
    for etype, nodes in sorted(by_type.items()):
        for node in nodes:
            label = node.entity_key.split(":", 1)[-1] if ":" in node.entity_key else node.entity_key
            lines.append(f"- [{etype}] {label}: {node.content}")

    # Recent Changes (7d) — evolved nodes only
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent_evolved = [
        n for n in all_current
        if n.parent_id is not None and n.created_at >= cutoff
    ]
    recent_evolved.sort(key=lambda n: n.created_at, reverse=True)
    recent_evolved = recent_evolved[:20]

    if recent_evolved:
        lines.append("")
        lines.append("## Recent Changes (7d)")
        for node in recent_evolved:
            parent = await vector_store.get_by_id(node.parent_id)
            if parent:
                lines.append(f"- {node.entity_key} -- {parent.content} -> {node.content}")
            else:
                lines.append(f"- {node.entity_key} -- (updated) {node.content}")

    # Flags — conflicts
    conflicts = [n for n in all_current if n.conflict]
    if conflicts:
        lines.append("")
        lines.append("## Flags")
        for node in conflicts:
            lines.append(f"- [conflict] {node.entity_key} -- {node.content}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_working_memory.py -v`
Expected: All PASS

- [ ] **Step 5: Add WM route and CLI command**

Append to `src/memory_mcp/api/routes.py` — add import at top:
```python
from ..engine.working_memory import generate_briefing
```

Add handler function:
```python
async def api_working_memory(request: Request) -> JSONResponse:
    try:
        briefing = await generate_briefing()
        return _ok({"briefing": briefing})
    except Exception as e:
        logger.error("api_working_memory error: %s", e)
        return _err(str(e), 500)
```

Add to `api_routes` list:
```python
    Route("/api/v1/wm", endpoint=api_working_memory, methods=["GET"]),
```

- [ ] **Step 6: Add WM test to test_api.py**

Append to `tests/test_api.py`:

```python
class TestWorkingMemory:
    def test_wm_empty(self, client, auth_headers):
        resp = client.get("/api/v1/wm", headers=auth_headers)
        assert resp.status_code == 200
        assert "No memories yet" in resp.json()["data"]["briefing"]

    def test_wm_with_memories(self, client, auth_headers):
        client.post(
            "/api/v1/memories",
            json={"content": "Use Cursor", "entity_key": "preference:editor", "entity_type": "preference"},
            headers=auth_headers,
        )
        resp = client.get("/api/v1/wm", headers=auth_headers)
        assert resp.status_code == 200
        assert "preference" in resp.json()["data"]["briefing"]
```

- [ ] **Step 7: Run all tests**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/memory_mcp/engine/working_memory.py src/memory_mcp/api/routes.py tests/test_working_memory.py tests/test_api.py
git commit -m "feat: add Working Memory engine with REST endpoint and tests"
```

### Task 9: Add skip_semantic_merge to remember_tool

**Files:**
- Modify: `src/memory_mcp/tools/remember.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write test for skip_semantic_merge**

Append to `tests/test_tools.py`:

```python
def test_remember_skip_semantic_merge_creates_new(tools, test_env, monkeypatch):
    """When skip_semantic_merge=True, a new entity_key always creates a new memory
    even if semantically similar content exists."""
    async def run():
        remember, _, _, _, _, _, _ = tools

        # Create first memory
        await remember.remember_tool({
            "content": "Use Cursor editor",
            "entity_type": "preference",
            "entity_key": "preference:editor",
        })

        # With skip_semantic_merge, a different key should always create new, not merge
        res = await remember.remember_tool({
            "content": "Use Cursor editor",  # same content
            "entity_type": "preference",
            "entity_key": "preference:editor-v2",  # different key
            "skip_semantic_merge": True,
        })
        assert res["status"] == "created"
        assert res["entity_key"] == "preference:editor-v2"

    anyio.run(run)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_tools.py::test_remember_skip_semantic_merge_creates_new -v`
Expected: FAIL (parameter not recognized)

- [ ] **Step 3: Add parameter to remember_tool**

Edit `src/memory_mcp/tools/remember.py` — modify `remember_tool` function:

At line 31, add:
```python
    skip_semantic_merge = arguments.get("skip_semantic_merge", False)
```

At line 80, wrap the semantic similarity block with the guard:
```python
    # 3. Semantic similarity check (skip when called from extraction engine)
    if not skip_semantic_merge:
```

Indent lines 81-117 by one level (the entire semantic similarity block).

- [ ] **Step 4: Run test**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_tools.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/tools/remember.py tests/test_tools.py
git commit -m "feat: add skip_semantic_merge parameter to remember_tool"
```

### Task 10: Extraction Engine

**Files:**
- Create: `src/memory_mcp/engine/extraction.py`
- Create: `tests/test_extraction.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_extraction.py`:

```python
import anyio
import json


def test_extract_memories_from_messages(tools, test_env, monkeypatch):
    """Extraction should parse LLM output and call remember_tool for each candidate."""
    async def run():
        remember, *_ = tools

        # Mock LLM to return structured extraction
        llm_response = json.dumps([
            {"entity_key": "preference:editor", "entity_type": "preference", "content": "Prefers Cursor"},
            {"entity_key": "project:memory-mcp", "entity_type": "project", "content": "Building a memory service"},
        ])

        import memory_mcp.engine.extraction as extraction_mod
        import importlib
        importlib.reload(extraction_mod)

        async def mock_llm_extract(_messages):
            return llm_response

        monkeypatch.setattr(extraction_mod, "_call_llm", mock_llm_extract)

        messages = [
            {"role": "user", "content": "I prefer Cursor for editing code."},
            {"role": "assistant", "content": "Got it, I'll remember that."},
        ]
        result = await extraction_mod.extract_memories(messages)
        assert result["total"] >= 1
        # Verify memories were actually stored
        from memory_mcp.storage.vector import vector_store
        current = await vector_store.list_current()
        keys = [n.entity_key for n in current]
        assert "preference:editor" in keys

    anyio.run(run)


def test_extract_handles_malformed_llm_output(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.extraction as extraction_mod
        import importlib
        importlib.reload(extraction_mod)

        async def mock_llm_bad(_messages):
            return "not valid json at all"

        monkeypatch.setattr(extraction_mod, "_call_llm", mock_llm_bad)

        result = await extraction_mod.extract_memories([{"role": "user", "content": "test"}])
        assert result["total"] == 0
        assert result["results"] == []

    anyio.run(run)


def test_extract_handles_code_fence_json(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.extraction as extraction_mod
        import importlib
        importlib.reload(extraction_mod)

        async def mock_llm_fenced(_messages):
            return '```json\n[{"entity_key": "fact:test", "entity_type": "fact", "content": "Test fact"}]\n```'

        monkeypatch.setattr(extraction_mod, "_call_llm", mock_llm_fenced)

        result = await extraction_mod.extract_memories([{"role": "user", "content": "test"}])
        assert result["total"] == 1

    anyio.run(run)


def test_extract_uses_skip_semantic_merge(tools, test_env, monkeypatch):
    """Extraction should call remember_tool with skip_semantic_merge=True."""
    async def run():
        remember_mod, *_ = tools
        import memory_mcp.engine.extraction as extraction_mod
        import importlib
        importlib.reload(extraction_mod)

        calls = []
        original = remember_mod.remember_tool

        async def spy(arguments):
            calls.append(arguments)
            return await original(arguments)

        monkeypatch.setattr(remember_mod, "remember_tool", spy)
        # Re-import extraction so it picks up the patched remember
        importlib.reload(extraction_mod)

        async def mock_llm(_messages):
            return json.dumps([{"entity_key": "fact:x", "entity_type": "fact", "content": "X"}])

        monkeypatch.setattr(extraction_mod, "_call_llm", mock_llm)

        await extraction_mod.extract_memories([{"role": "user", "content": "test"}])
        assert any(c.get("skip_semantic_merge") is True for c in calls)

    anyio.run(run)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_extraction.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement Extraction Engine**

Create `src/memory_mcp/engine/extraction.py`:

```python
import json
import logging
import re

import httpx

from ..config import settings
from ..tools.remember import remember_tool

logger = logging.getLogger("memory-mcp.extraction")

_EXTRACTION_PROMPT = """Analyze this conversation and extract information worth remembering long-term.

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
- Output ONLY the JSON array, no other text"""


async def _call_llm(messages: list[dict]) -> str:
    """Call OpenRouter LLM to extract memories from conversation."""
    conversation_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in messages)
    prompt = f"{_EXTRACTION_PROMPT}\n\nConversation:\n{conversation_text}"

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://memory-mcp.app",
        "X-Title": "Memory MCP",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers=headers,
            json={
                "model": settings.llm_model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()


def _parse_llm_output(text: str) -> list[dict]:
    """Parse LLM output as JSON array, with fallback for code fences."""
    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try extracting from code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    logger.warning("Failed to parse LLM extraction output: %s", text[:200])
    return []


async def extract_memories(messages: list[dict]) -> dict:
    """Extract memories from conversation messages and store them."""
    results = []
    try:
        raw = await _call_llm(messages)
        candidates = _parse_llm_output(raw)
    except Exception as e:
        logger.error("LLM extraction failed: %s", e)
        return {"results": [], "total": 0, "error": str(e)}

    for candidate in candidates:
        entity_key = candidate.get("entity_key", "")
        entity_type = candidate.get("entity_type", "")
        content = candidate.get("content", "")
        if not (entity_key and entity_type and content):
            continue
        try:
            result = await remember_tool({
                "content": content,
                "entity_key": entity_key,
                "entity_type": entity_type,
                "skip_semantic_merge": True,
            })
            results.append(result)
        except Exception as e:
            logger.warning("Failed to store extracted memory %s: %s", entity_key, e)
            results.append({"entity_key": entity_key, "status": "error", "error": str(e)})

    return {"results": results, "total": len(results)}
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_extraction.py -v`
Expected: All PASS

- [ ] **Step 5: Add extract route**

Add to `src/memory_mcp/api/routes.py` — import at top:
```python
from ..engine.extraction import extract_memories
```

Add handler:
```python
async def api_extract(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        messages = body.get("messages")
        if not messages or not isinstance(messages, list):
            return _err("Missing required field: messages (array)")
        result = await extract_memories(messages)
        return _ok(result)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error("api_extract error: %s", e)
        return _err(str(e), 500)
```

Add to `api_routes` (before the `/api/v1/memories` catch-all routes):
```python
    Route("/api/v1/memories/extract", endpoint=api_extract, methods=["POST"]),
```

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/memory_mcp/engine/extraction.py src/memory_mcp/api/routes.py tests/test_extraction.py
git commit -m "feat: add Extraction Engine with LLM-based memory extraction"
```

---

## Chunk 4: Claude Code Plugin

### Task 11: Hook Scripts

**Files:**
- Create: `claude-code-plugin/hooks/session-start.sh`
- Create: `claude-code-plugin/hooks/stop.sh`

- [ ] **Step 1: Create SessionStart hook**

Create `claude-code-plugin/hooks/session-start.sh`:

```bash
#!/bin/bash
# SessionStart hook: inject working memory briefing as context for Claude.
# stdout is captured and shown to Claude as additional context.
# Only fires on fresh startup (not resume/compact).
python3 -c "
import sys, json, subprocess
d = json.load(sys.stdin)
source = d.get('source', '')
if source and source != 'startup':
    sys.exit(0)
r = subprocess.run(['mem', 'wm', '--format', 'text'], capture_output=True, text=True)
if r.returncode == 0:
    print(r.stdout, end='')
else:
    print('Memory service unavailable')
"
```

- [ ] **Step 2: Create Stop hook**

Create `claude-code-plugin/hooks/stop.sh`:

```bash
#!/bin/bash
# Stop hook: extract memories from conversation transcript.
# Runs with async: true (fire-and-forget).
# Uses python3 to avoid jq dependency and shell injection risks.
python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('stop_hook_active'):
    sys.exit(0)
tp = d.get('transcript_path', '')
if not tp:
    sys.exit(0)
import subprocess
subprocess.run(['mem', 'extract', '--transcript', tp], stderr=subprocess.DEVNULL)
"
```

- [ ] **Step 3: Make executable**

```bash
chmod +x claude-code-plugin/hooks/session-start.sh claude-code-plugin/hooks/stop.sh
```

- [ ] **Step 4: Commit**

```bash
git add claude-code-plugin/hooks/
git commit -m "feat(plugin): add Claude Code hook scripts for session start and stop"
```

### Task 12: Skills and Commands

**Files:**
- Create: `claude-code-plugin/skills/search-memory/SKILL.md`
- Create: `claude-code-plugin/skills/save-memory/SKILL.md`
- Create: `claude-code-plugin/commands/save.md`
- Create: `claude-code-plugin/commands/search.md`
- Create: `claude-code-plugin/commands/status.md`

- [ ] **Step 1: Create search-memory skill**

Create `claude-code-plugin/skills/search-memory/SKILL.md`:

```markdown
---
name: search-memory
description: Search long-term memory for relevant context. Use when the user references previous decisions, preferences, projects, or when you need prior context.
---

Search your long-term memory using the `mem` CLI:

```bash
mem recall "your search query" --format text
```

Use this when:
- The user mentions something from a previous session
- You need context about their preferences or past decisions
- Debugging a problem that seems familiar
- The user asks "do you remember..."

Search tips:
- Use natural language queries
- Add `--type preference` to filter by type (preference/fact/event/goal/project/person)
- Add `--limit 5` to limit results
```

- [ ] **Step 2: Create save-memory skill**

Create `claude-code-plugin/skills/save-memory/SKILL.md`:

```markdown
---
name: save-memory
description: Save important information to long-term memory. Use when an important decision is made, a hard problem is solved, or a new preference is discovered.
---

Save to long-term memory using the `mem` CLI:

```bash
mem remember "concise description of what to remember" --type <type> --key <entity_key>
```

Types: `preference`, `fact`, `event`, `goal`, `project`, `person`

Key format: `type:name` (e.g., `preference:editor`, `project:memory-mcp`, `fact:timezone`)

When to save:
- Important decision made (e.g., "chose PostgreSQL over MySQL for X reason")
- Hard problem solved with root cause
- New preference or habit discovered
- Project context that should persist across sessions

When NOT to save:
- Temporary debugging details
- Generic/widely-known information
- Information already stored (check with `mem recall` first)
```

- [ ] **Step 3: Create slash commands**

Create `claude-code-plugin/commands/save.md`:

```markdown
---
name: save
description: Quick save to long-term memory
arguments: content to save
---

Save the provided content to long-term memory. Analyze the content to determine the appropriate entity_type and entity_key, then run:

```bash
mem remember "<content>" --type <inferred_type> --key <inferred_key>
```

If the content is ambiguous, ask the user for the type and key.
```

Create `claude-code-plugin/commands/search.md`:

```markdown
---
name: search
description: Search long-term memory
arguments: search query
---

Search long-term memory for the given query:

```bash
mem recall "<query>" --format text
```

Present the results in a readable format. If no results found, say so.
```

Create `claude-code-plugin/commands/status.md`:

```markdown
---
name: status
description: Show memory service status and working memory briefing
---

Check memory service status and display current context:

```bash
mem status
mem wm --format text
```

Present both outputs to the user.
```

- [ ] **Step 4: Commit**

```bash
git add claude-code-plugin/skills/ claude-code-plugin/commands/
git commit -m "feat(plugin): add skills and slash commands for memory operations"
```

### Task 13: Plugin README

**Files:**
- Create: `claude-code-plugin/README.md`

- [ ] **Step 1: Create README**

Create `claude-code-plugin/README.md`:

```markdown
# Memory MCP Claude Code Plugin

Integrates long-term memory into Claude Code via hooks, skills, and slash commands.

## Prerequisites

- `mem` CLI installed: `pipx install memory-mcp-cli` or `uv tool install memory-mcp-cli`
- `mem` configured: `~/.config/memory-mcp/config.json` with `api_url` and `api_key`
- `python3` available in PATH

## Installation

Add hooks to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "/path/to/claude-code-plugin/hooks/session-start.sh",
        "timeout": 10
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "/path/to/claude-code-plugin/hooks/stop.sh",
        "async": true,
        "timeout": 120
      }
    ]
  }
}
```

Copy skills to your Claude Code skills directory, or reference them from this repo.

## What it Does

| Component | Behavior |
|-----------|----------|
| **SessionStart hook** | Injects working memory briefing as context |
| **Stop hook** | Extracts memories from conversation transcript (async) |
| **search-memory skill** | Guides Claude to search long-term memory |
| **save-memory skill** | Guides Claude to save important information |
| **/save** | Quick save to memory |
| **/search** | Quick search in memory |
| **/status** | Show service status and current context |
```

- [ ] **Step 2: Commit**

```bash
git add claude-code-plugin/README.md
git commit -m "docs(plugin): add installation and usage guide"
```

---

## Chunk 5: Behavioral Guidance + Final Validation

### Task 14: Behavioral Guidance Template

**Files:**
- Create: `docs/behavioral-guidance.md`

- [ ] **Step 1: Create template**

Create `docs/behavioral-guidance.md`:

```markdown
# Memory Behavioral Guidance

Embed this in your AI tool's system prompt to enable memory-aware behavior.

---

## Memory Available
- Search memories: `mem recall "query"`
- Save important info: `mem remember "content" --type <type> --key <key>`
- View current context: `mem wm`

## When to Search
- User references previous decisions, preferences, or projects
- Debugging a familiar-looking issue
- Need context from previous sessions

## When to Save
- Important decision made (with rationale)
- Hard problem solved (with root cause)
- New preference or habit discovered
- Do NOT save temporary, generic, or widely-known information

## Entity Types
- `preference` — user preferences and choices
- `fact` — factual information about the user
- `event` — notable events
- `goal` — goals and objectives
- `project` — project context
- `person` — people and relationships
```

- [ ] **Step 2: Commit**

```bash
git add docs/behavioral-guidance.md
git commit -m "docs: add behavioral guidance template for cross-tool memory integration"
```

### Task 15: Full Test Suite + AGENTS.md Update

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/kassol/Workspace/memory-mcp && pytest -v`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Run CLI tests**

Run: `cd /Users/kassol/Workspace/memory-mcp/cli && pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Update AGENTS.md changelog**

Append to the changelog section of `AGENTS.md`:

```markdown
### 2026-03-25 Extension: REST API + CLI + Working Memory + Extraction + Plugin
- Added REST API (`/api/v1/*`) as secondary transport, reusing existing tool functions
- Added `mem` CLI client (httpx + typer) in `cli/` directory
- Added Working Memory engine — template-based briefing from current memories
- Added Extraction Engine — LLM-based memory extraction from conversation transcripts
- Added `skip_semantic_merge` parameter to `remember_tool` for extraction safety
- Added Claude Code plugin with hooks (session-start, stop), skills, and slash commands
- Updated AuthMiddleware error format to `{"ok": false, "error": ...}`
- Updated protocol constraint: MCP primary + REST secondary
```

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS.md changelog for extension release"
```
