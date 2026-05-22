# Memory MCP M5 — Web UI 治理台实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `web/` 子目录从零搭建 React 19 + TS 6 + Vite 8 + Tailwind v4 + shadcn 的 SPA 治理台，配合后端 cookie session 中间件与 FastAPI 静态文件挂载，并通过多阶段 Dockerfile 把构建产物 serve 给同一个 ASGI 应用。

**Architecture:** Web SPA 与后端 API 同源部署，浏览器走 cookie session（`mem_session` HttpOnly/Secure/SameSite=Strict），MCP/CLI 走 Bearer Token。`AuthMiddleware` 同时接受两种凭据。`/mcp` / `/api/v1/*` / `/health` 优先匹配，未命中路径 fallback 到 `WEB_DIST_DIR` 下的 SPA `index.html`，由 React Router 接管前端路由。

**Tech Stack:** React 19.2 / TypeScript 6.0 / Vite 8.0 / Tailwind v4.3（CSS-based `@theme`）/ shadcn CLI 4.7 / react-router-dom 7.15（declarative mode）/ @tanstack/react-query 5.100 / @tanstack/react-table 8.21 / zustand 5.0 / @xyflow/react 12.10 / lucide-react 1.16 / dagre / itsdangerous（后端）/ pnpm + corepack

**Spec:** `docs/superpowers/specs/2026-05-21-memory-mcp-agent-kernel-design.md` §7（Web UI 治理台）+ §5.2（REST API）+ §5.4（recall 响应结构）

**前置:** M1-M4 已完成，所有后端 CRUD / Hybrid Search / Threads / Worker / REST API 就绪。

---

## File Structure

### 后端新增/修改

| File | Action | Responsibility |
|------|--------|----------------|
| `src/memory_mcp/config.py` | Modify | 新增 `session_secret` 字段（从 `MEMORY_MCP_SESSION_SECRET` 读） |
| `src/memory_mcp/api/auth.py` | Create | cookie session 三端点（login / logout / me）+ 签名工具 |
| `src/memory_mcp/transport/auth.py` | Modify | `AuthMiddleware` 同时接受 Bearer Header 与 `mem_session` cookie |
| `src/memory_mcp/api/routes.py` | Modify | 注册 auth 路由 |
| `src/memory_mcp/server.py` | Modify | 路由注册顺序调整 + SPA fallback 挂载（`WEB_DIST_DIR`） |
| `pyproject.toml` | Modify | 添加 `itsdangerous` 依赖 |
| `requirements.lock` | Modify | `pip-compile` 重新生成 |
| `.env.example` | Modify | 新增 `MEMORY_MCP_SESSION_SECRET` 占位 |

### 后端测试

| File | Action | Tests |
|------|--------|-------|
| `tests/test_auth_api.py` | Create | login/logout/me 三端点 + cookie 签名校验 + middleware 双凭据 |
| `tests/test_spa_fallback.py` | Create | SPA fallback 行为 + 优先级 |

### Web 前端（全部新建）

| File | Action | Responsibility |
|------|--------|----------------|
| `web/.gitignore` | Create | node_modules / dist / .env.local |
| `web/.npmrc` | Create | 强制 pnpm |
| `web/package.json` | Create | 依赖清单 + scripts |
| `web/pnpm-workspace.yaml` | Create | 单包 workspace |
| `web/tsconfig.json` | Create | TS 6 strict |
| `web/tsconfig.node.json` | Create | vite config 编译 |
| `web/vite.config.ts` | Create | dev proxy / build / path alias |
| `web/index.html` | Create | SPA 入口 |
| `web/components.json` | Create | shadcn 配置 |
| `web/postcss.config.js` | Create | Tailwind v4 PostCSS |
| `web/src/main.tsx` | Create | React 19 root + Router |
| `web/src/App.tsx` | Create | 路由表 + Layout |
| `web/src/styles/globals.css` | Create | Tailwind v4 `@theme` |
| `web/src/lib/utils.ts` | Create | shadcn `cn` |
| `web/src/lib/api-client.ts` | Create | fetch wrapper + cookie session 401 重定向 |
| `web/src/lib/format.ts` | Create | 日期 / 分数格式化 |
| `web/src/lib/storage.ts` | Create | 本地 zustand persist 工具 |
| `web/src/stores/ui-store.ts` | Create | UI 状态（侧边栏 / toast） |
| `web/src/stores/auth-store.ts` | Create | session 状态 |
| `web/src/api/auth.ts` | Create | `useAuth` / `useLogin` / `useLogout` |
| `web/src/api/memories.ts` | Create | `useMemories` / `useMemory` / mutations |
| `web/src/api/threads.ts` | Create | `useThreads` / `useThread` / `useThreadMessages` |
| `web/src/api/graph.ts` | Create | `useGraph` |
| `web/src/api/jobs.ts` | Create | `useJobs` / retry / cancel |
| `web/src/api/sync.ts` | Create | `useSyncStatus` |
| `web/src/components/ui/button.tsx` | Create | shadcn |
| `web/src/components/ui/input.tsx` | Create | shadcn |
| `web/src/components/ui/dialog.tsx` | Create | shadcn |
| `web/src/components/ui/table.tsx` | Create | shadcn |
| `web/src/components/ui/tabs.tsx` | Create | shadcn |
| `web/src/components/ui/toast.tsx` | Create | shadcn + sonner |
| `web/src/components/ui/tooltip.tsx` | Create | shadcn |
| `web/src/components/ui/dropdown-menu.tsx` | Create | shadcn |
| `web/src/components/ui/form.tsx` | Create | shadcn |
| `web/src/components/ui/badge.tsx` | Create | shadcn |
| `web/src/components/ui/textarea.tsx` | Create | shadcn |
| `web/src/components/ui/select.tsx` | Create | shadcn |
| `web/src/components/ui/checkbox.tsx` | Create | shadcn |
| `web/src/components/ui/card.tsx` | Create | shadcn |
| `web/src/components/ui/skeleton.tsx` | Create | shadcn |
| `web/src/components/AppLayout.tsx` | Create | 主框架 + 侧边栏 |
| `web/src/components/RequireAuth.tsx` | Create | 路由守卫 |
| `web/src/components/MemoryList.tsx` | Create | 虚拟列表 + 多选 + 批量 toolbar |
| `web/src/components/MemoryDetail.tsx` | Create | 编辑表单 + tabs |
| `web/src/components/MemoryMergeDialog.tsx` | Create | source → target 合并预览 |
| `web/src/components/EvolutionTimeline.tsx` | Create | 演化链时间线 |
| `web/src/components/SourceRefsPanel.tsx` | Create | 跳转 thread 高亮 message |
| `web/src/components/ThreadMessages.tsx` | Create | 虚拟化消息流 |
| `web/src/components/GraphView.tsx` | Create | @xyflow/react + dagre |
| `web/src/components/RelevanceBreakdown.tsx` | Create | 排名贡献条 |
| `web/src/components/SyncStatusCard.tsx` | Create | provider 同步状态 |
| `web/src/components/JobsTable.tsx` | Create | Worker 任务表 |
| `web/src/pages/LoginPage.tsx` | Create | `/login` |
| `web/src/pages/MemoriesPage.tsx` | Create | `/memories` |
| `web/src/pages/MemoryDetailPage.tsx` | Create | `/memories/:id` |
| `web/src/pages/MemoryNewPage.tsx` | Create | `/memories/new` |
| `web/src/pages/ThreadsPage.tsx` | Create | `/threads` |
| `web/src/pages/ThreadDetailPage.tsx` | Create | `/threads/:id` |
| `web/src/pages/GraphPage.tsx` | Create | `/graph` |
| `web/src/pages/JobsPage.tsx` | Create | `/jobs` |
| `web/src/pages/SourcesPage.tsx` | Create | `/sources`（占位） |
| `web/src/pages/SettingsPage.tsx` | Create | `/settings` |
| `web/src/types/index.ts` | Create | API DTO 类型 |
| `web/vitest.config.ts` | Create | vitest + jsdom |
| `web/src/test/setup.ts` | Create | testing-library 初始化 |
| `web/src/components/__tests__/MemoryList.test.tsx` | Create | 列表渲染 / 多选 |
| `web/src/components/__tests__/MemoryMergeDialog.test.tsx` | Create | 选择交互 |
| `web/src/components/__tests__/GraphView.test.tsx` | Create | 节点点击跳转 |
| `web/src/api/__tests__/api-client.test.ts` | Create | 401 重定向 |

### 部署

| File | Action | Responsibility |
|------|--------|----------------|
| `Dockerfile` | Modify | 多阶段：node:22-alpine build → python:3.12-slim runtime + `WEB_DIST_DIR` |
| `docker-compose.yml` | Modify | 注入 `MEMORY_MCP_SESSION_SECRET` |
| `.dockerignore` | Modify | 排除 `web/node_modules` / `web/dist` 源码 |

### 文档

| File | Action | Responsibility |
|------|--------|----------------|
| `AGENTS.md` | Modify | 变更日志 + 目录索引补 `web/` |
| `web/AGENTS.md` | Create | 子目录职责 / 结构约定 / 命令 |

---

## Chunk 1: 后端 Cookie Session 与 SPA 静态文件挂载

### Task 1: 配置与依赖

**Files:**
- Modify: `src/memory_mcp/config.py`
- Modify: `pyproject.toml`
- Modify: `requirements.lock`
- Modify: `.env.example`

- [ ] **Step 1: 添加 `session_secret` 配置字段**

Edit `src/memory_mcp/config.py` — 在 `auth_token` 之后添加：

```python
    # Session (Web UI cookie auth)
    session_secret: str = Field(
        validation_alias=AliasChoices("MEMORY_MCP_SESSION_SECRET", "SESSION_SECRET")
    )
    session_cookie_name: str = "mem_session"
    session_max_age: int = 60 * 60 * 24 * 7  # 7 days
    web_dist_dir: str = Field(
        default="./web/dist",
        validation_alias=AliasChoices("WEB_DIST_DIR", "MEMORY_MCP_WEB_DIST_DIR"),
    )
```

注意 `session_secret` 无默认值——服务启动时强制 env 注入，防止生产用 fallback 密钥。

- [ ] **Step 2: 添加 `itsdangerous` 依赖**

Edit `pyproject.toml` — 在 `dependencies` 列表末尾追加：

```toml
    "itsdangerous>=2.2.0"
```

- [ ] **Step 3: 重新生成锁文件**

```bash
cd /Users/kassol/Workspace/memory-mcp
pip install --upgrade pip-tools
pip-compile --output-file requirements.lock pyproject.toml
```

如果项目未使用 pip-tools，手动在 `requirements.lock` 末尾追加 `itsdangerous==2.2.0`（具体版本号以 `pip show itsdangerous` 为准）。

- [ ] **Step 4: 更新 `.env.example`**

Edit `.env.example` — 追加：

```
# Web UI cookie session signing secret (REQUIRED, generate via: python -c "import secrets; print(secrets.token_urlsafe(64))")
MEMORY_MCP_SESSION_SECRET=

# Optional: override default web dist directory
# WEB_DIST_DIR=./web/dist
```

如果项目根目录没有 `.env.example`，新建它，只写上面这两条。

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/config.py pyproject.toml requirements.lock .env.example
git commit -m "feat(config): add session_secret and web_dist_dir for Web UI"
```

### Task 2: Cookie Session 中间件升级

**Files:**
- Create: `tests/test_auth_api.py`
- Modify: `src/memory_mcp/transport/auth.py`

- [ ] **Step 1: 写失败的 cookie session 测试**

Create `tests/test_auth_api.py`:

```python
import importlib
import os
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture()
def app(test_env, monkeypatch):
    monkeypatch.setenv("MEMORY_MCP_SESSION_SECRET", "unit-test-secret-please-do-not-use-in-prod")
    import memory_mcp.config as config_mod
    importlib.reload(config_mod)
    import memory_mcp.server as server_mod
    importlib.reload(server_mod)
    return server_mod.app


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def bearer_headers():
    return {"Authorization": "Bearer test-token"}


class TestCookieSession:
    def test_login_with_valid_token_sets_cookie(self, client):
        resp = client.post("/api/v1/auth/login", json={"token": "test-token"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["authenticated"] is True
        cookie = resp.cookies.get("mem_session")
        assert cookie, "mem_session cookie should be set"
        # Cookie raw header should include security flags
        set_cookie = resp.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie
        assert "SameSite=strict" in set_cookie.lower()

    def test_login_with_wrong_token_returns_403(self, client):
        resp = client.post("/api/v1/auth/login", json={"token": "wrong"})
        assert resp.status_code == 403
        assert resp.json()["ok"] is False

    def test_login_with_missing_token_returns_400(self, client):
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 400

    def test_me_without_cookie_returns_401(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_with_valid_cookie_returns_authenticated(self, client):
        client.post("/api/v1/auth/login", json={"token": "test-token"})
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["authenticated"] is True

    def test_logout_clears_cookie(self, client):
        client.post("/api/v1/auth/login", json={"token": "test-token"})
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        # Cookie cleared
        me = client.get("/api/v1/auth/me")
        assert me.status_code == 401

    def test_tampered_cookie_rejected(self, client):
        client.post("/api/v1/auth/login", json={"token": "test-token"})
        client.cookies.set("mem_session", "tampered.invalid.value")
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


class TestAuthMiddlewareDualCredentials:
    def test_bearer_header_still_works(self, client, bearer_headers):
        resp = client.get("/api/v1/memories", headers=bearer_headers)
        assert resp.status_code == 200

    def test_cookie_session_authenticates_api(self, client):
        client.post("/api/v1/auth/login", json={"token": "test-token"})
        resp = client.get("/api/v1/memories")
        assert resp.status_code == 200

    def test_no_credentials_returns_401(self, client):
        resp = client.get("/api/v1/memories")
        assert resp.status_code == 401
        assert resp.json()["ok"] is False

    def test_health_remains_public(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
```

- [ ] **Step 2: 运行测试确认全部失败**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_auth_api.py -v
```
Expected: 全部 FAIL（路由与签名工具尚未实现）。

- [ ] **Step 3: 实现 cookie 签名工具与登录路由**

Create `src/memory_mcp/api/auth.py`:

```python
"""Cookie session auth endpoints for Web UI.

MCP / REST / CLI clients keep using Bearer tokens. Browsers use a signed cookie
(`mem_session`) so we don't ship long-lived tokens to localStorage. The
`AuthMiddleware` accepts either credential.
"""

from __future__ import annotations

import logging
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import settings

logger = logging.getLogger("memory-mcp.auth")

_SERIALIZER_SALT = "memory-mcp.session.v1"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt=_SERIALIZER_SALT)


def issue_session_token() -> str:
    """Mint a fresh signed session token.

    Payload is intentionally minimal: a single string identifier ("web"). The
    signature + timestamp do all the heavy lifting. If we ever multiplex
    multiple identities we can swap this for a dict.
    """
    return _serializer().dumps("web")


def verify_session_token(token: str) -> bool:
    if not token:
        return False
    try:
        _serializer().loads(token, max_age=settings.session_max_age)
        return True
    except SignatureExpired:
        logger.debug("session token expired")
        return False
    except BadSignature:
        logger.debug("session token bad signature")
        return False


def extract_session_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(settings.session_cookie_name)


def _ok(data: dict) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data})


def _err(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


def _set_session_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )


def _clear_session_cookie(response: JSONResponse) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        samesite="strict",
        secure=True,
        httponly=True,
    )


# POST /api/v1/auth/login
async def handle_login(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON body")
    token = body.get("token")
    if not isinstance(token, str) or not token:
        return _err("Missing required field: token")
    if token != settings.auth_token:
        return _err("Forbidden", status=403)
    session_token = issue_session_token()
    response = _ok({"authenticated": True})
    _set_session_cookie(response, session_token)
    return response


# POST /api/v1/auth/logout
async def handle_logout(request: Request) -> JSONResponse:
    response = _ok({"authenticated": False})
    _clear_session_cookie(response)
    return response


# GET /api/v1/auth/me
async def handle_me(request: Request) -> JSONResponse:
    cookie = extract_session_cookie(request)
    if cookie and verify_session_token(cookie):
        return _ok({"authenticated": True})
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        if token == settings.auth_token:
            return _ok({"authenticated": True})
    return _err("Unauthorized", status=401)
```

- [ ] **Step 4: 升级 `AuthMiddleware` 同时接受 Bearer + cookie**

Replace `src/memory_mcp/transport/auth.py` with:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..api.auth import extract_session_cookie, verify_session_token
from ..config import settings


# Paths that bypass auth entirely. SPA fallback files (HTML/CSS/JS bundles)
# are served by StaticFiles which is mounted AFTER the auth middleware so we
# allow-list common static prefixes here. The MCP/REST paths under /mcp and
# /api/v1 still require credentials.
_PUBLIC_PATHS = {"/health"}
_PUBLIC_PREFIXES = (
    "/assets/",
    "/api/v1/auth/login",
    "/favicon",
)


def _is_public(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        return True
    # SPA bootstrap: anything that does not start with /mcp or /api/v1 is
    # treated as a static frontend asset and let through. The static handler
    # downstream returns 404 if the file doesn't exist.
    if not path.startswith("/mcp") and not path.startswith("/api/v1"):
        return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        if _is_public(request.url.path):
            return await call_next(request)

        # 1) Bearer header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            if token == settings.auth_token:
                return await call_next(request)
            return JSONResponse({"ok": False, "error": "Forbidden"}, status_code=403)

        # 2) Cookie session (Web UI)
        cookie = extract_session_cookie(request)
        if cookie and verify_session_token(cookie):
            return await call_next(request)

        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)
```

- [ ] **Step 5: 注册 auth 路由**

Edit `src/memory_mcp/api/routes.py` — 在文件顶部其它 import 之后追加：

```python
from .auth import handle_login, handle_logout, handle_me
```

在 `routes = [...]` 列表开头插入：

```python
    Route("/api/v1/auth/login", endpoint=handle_login, methods=["POST"]),
    Route("/api/v1/auth/logout", endpoint=handle_logout, methods=["POST"]),
    Route("/api/v1/auth/me", endpoint=handle_me, methods=["GET"]),
```

- [ ] **Step 6: 跑测试**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_auth_api.py -v
```
Expected: 全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add src/memory_mcp/api/auth.py src/memory_mcp/transport/auth.py src/memory_mcp/api/routes.py tests/test_auth_api.py
git commit -m "feat(auth): add cookie session for Web UI alongside Bearer auth"
```

### Task 2.5: 收紧 CORS（cookie session 安全前提）

**Files:**
- Modify: `src/memory_mcp/transport/cors.py`
- Modify: `tests/test_auth_api.py`

> 当前 `CorsMiddleware` 写死 `Access-Control-Allow-Origin: *`，与 cookie session 不兼容（浏览器规范禁止 `*` + `credentials: include` 组合）。本 task 改为：(1) 同源/允许列表内的 Origin 才回写，且回写实际 Origin 而非 `*`；(2) 输出 `Access-Control-Allow-Credentials: true`，让浏览器接受 cookie。允许列表通过 `MEMORY_MCP_ALLOWED_ORIGINS` 环境变量配置（逗号分隔），默认空（即只允许同源）。

- [ ] **Step 1: 写测试**

Append to `tests/test_auth_api.py`:

```python
class TestCorsCookieFriendly:
    def test_allowed_origin_gets_echoed_with_credentials(self, client, monkeypatch):
        monkeypatch.setenv("MEMORY_MCP_ALLOWED_ORIGINS", "https://memory-mcp.example")
        resp = client.options(
            "/api/v1/memories",
            headers={
                "Origin": "https://memory-mcp.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "https://memory-mcp.example"
        assert resp.headers.get("access-control-allow-credentials") == "true"
        # No wildcard when echoing origin — that's the whole point.
        assert resp.headers.get("access-control-allow-origin") != "*"

    def test_unknown_origin_omits_acao(self, client, monkeypatch):
        monkeypatch.setenv("MEMORY_MCP_ALLOWED_ORIGINS", "https://only.example")
        resp = client.options(
            "/api/v1/memories",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        # We still 200 the preflight (some proxies require it) but without ACAO.
        assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()}

    def test_no_origin_header_omits_acao(self, client):
        resp = client.get("/health")
        assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()}
```

- [ ] **Step 2: 重写 CorsMiddleware**

Replace `src/memory_mcp/transport/cors.py` with:

```python
import os

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send


def _allowed_origins() -> set[str]:
    raw = os.environ.get("MEMORY_MCP_ALLOWED_ORIGINS", "")
    return {o.strip() for o in raw.split(",") if o.strip()}


_BASE_HEADERS = {
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Mcp-Session-Id",
    "Access-Control-Expose-Headers": "Mcp-Session-Id",
    "Access-Control-Allow-Credentials": "true",
    "Vary": "Origin",
}


class CorsMiddleware:
    """Cookie-session friendly CORS.

    - Echoes a single Origin (never `*`) when it's in the allow list
    - Always sends `Access-Control-Allow-Credentials: true` (required by the
      browser for `fetch(..., credentials: 'include')`)
    - Returns 200 for OPTIONS preflight regardless, but omits ACAO when the
      Origin is unknown so the browser refuses cross-origin XHR.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        origin = request.headers.get("origin")
        allowed = _allowed_origins()
        echo_origin = origin if (origin and origin in allowed) else None
        headers = dict(_BASE_HEADERS)
        if echo_origin:
            headers["Access-Control-Allow-Origin"] = echo_origin

        if request.method == "OPTIONS":
            response = Response(status_code=200, headers=headers if echo_origin else dict(_BASE_HEADERS))
            if not echo_origin:
                # Drop ACAC too — without ACAO it has no effect, and emitting
                # it on bare requests is confusing.
                response.headers.pop("access-control-allow-credentials", None)
            await response(scope, receive, send)
            return

        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                existing = {k.lower(): k for k, _ in raw_headers}
                appended = []
                for key, value in headers.items():
                    if echo_origin is None and key == "Access-Control-Allow-Origin":
                        continue
                    if echo_origin is None and key == "Access-Control-Allow-Credentials":
                        continue
                    if key.lower() in existing:
                        # Replace existing header
                        raw_headers = [
                            (k, value.encode()) if k.decode().lower() == key.lower() else (k, v)
                            for k, v in raw_headers
                        ]
                    else:
                        appended.append((key.encode(), value.encode()))
                message["headers"] = raw_headers + appended
            await send(message)

        await self.app(scope, receive, send_with_cors)
```

> Important：`.env.example` 同时记一行 `MEMORY_MCP_ALLOWED_ORIGINS=https://memory-mcp.<your-domain>`；生产 Sir 部署时填实际域名。本地 dev 同源（SPA 与 API 都在 `localhost:8765`）不依赖 CORS，留空即可。

- [ ] **Step 3: 跑测试**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_auth_api.py -k "Cors or cors" -v
```
Expected: 3 条新 PASS；原 auth 测试不受影响（不携带 Origin header）。

- [ ] **Step 4: Commit**

```bash
git add src/memory_mcp/transport/cors.py tests/test_auth_api.py .env.example
git commit -m "feat(cors): tighten allow list and emit credentials header for cookie session"
```

### Task 3: SPA 静态文件 fallback

**Files:**
- Create: `tests/test_spa_fallback.py`
- Modify: `src/memory_mcp/server.py`

- [ ] **Step 1: 写失败的 SPA fallback 测试**

Create `tests/test_spa_fallback.py`:

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
def dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "web-dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><body>SPA</body></html>")
    (dist / "assets" / "app.css").write_text("body{color:red}")
    return dist


@pytest.fixture()
def app(test_env, monkeypatch, dist_dir):
    monkeypatch.setenv("MEMORY_MCP_SESSION_SECRET", "spa-test-secret")
    monkeypatch.setenv("WEB_DIST_DIR", str(dist_dir))
    import memory_mcp.config as config_mod
    importlib.reload(config_mod)
    import memory_mcp.server as server_mod
    importlib.reload(server_mod)
    return server_mod.app


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestSpaFallback:
    def test_root_returns_index_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "SPA" in resp.text

    def test_deep_route_returns_index_html(self, client):
        # React Router URL — server must return index.html so client routes
        resp = client.get("/memories/abc-123")
        assert resp.status_code == 200
        assert "SPA" in resp.text

    def test_static_asset_served(self, client):
        resp = client.get("/assets/app.css")
        assert resp.status_code == 200
        assert "color:red" in resp.text

    def test_api_route_not_swallowed(self, client):
        # /api/v1/* must NOT hit SPA fallback even without auth
        resp = client.get("/api/v1/memories")
        assert resp.status_code == 401
        assert resp.json()["ok"] is False

    def test_health_still_returns_json(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_unknown_api_route_returns_404_json(self, client, auth_headers):
        resp = client.get("/api/v1/no-such-endpoint", headers=auth_headers)
        assert resp.status_code in (404, 405)
        # Must not be HTML
        assert "html" not in resp.text.lower()


@pytest.fixture()
def auth_headers():
    return {"Authorization": "Bearer test-token"}
```

- [ ] **Step 2: 跑测试看初始失败**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_spa_fallback.py -v
```
Expected: FAIL（fallback 尚未挂载）。

- [ ] **Step 3: 实现 SPA fallback 挂载**

Edit `src/memory_mcp/server.py` — 在文件顶部 import 块追加：

```python
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles
```

在文件底部（`app = Starlette(...)` 之前）追加：

```python
def _build_spa_routes() -> list:
    dist_dir = Path(settings.web_dist_dir).resolve()
    if not dist_dir.exists():
        logger.warning("WEB_DIST_DIR %s does not exist; SPA disabled", dist_dir)
        return []
    index_file = dist_dir / "index.html"
    if not index_file.exists():
        logger.warning("WEB_DIST_DIR has no index.html; SPA disabled")
        return []

    static_app = StaticFiles(directory=str(dist_dir), html=False)

    async def spa_fallback(request: Request):
        path = request.url.path
        # API paths must never reach here — they should 404 with JSON
        if path.startswith("/mcp") or path.startswith("/api/") or path == "/health":
            return JSONResponse({"ok": False, "error": "Not found"}, status_code=404)

        candidate = dist_dir / path.lstrip("/")
        if candidate.is_file():
            return FileResponse(candidate)

        # SPA route → serve index.html
        return FileResponse(index_file)

    from starlette.routing import Mount, Route as StarletteRoute
    return [
        Mount("/assets", app=StaticFiles(directory=str(dist_dir / "assets"), html=False)),
        StarletteRoute("/{full_path:path}", endpoint=spa_fallback, methods=["GET"]),
    ]
```

Replace the `app = Starlette(...)` block with:

```python
app = Starlette(
    lifespan=streamable_http_app.lifespan,
    routes=[
        Route("/mcp", endpoint=streamable_http_app, methods=["GET", "POST", "DELETE"]),
        Route("/health", endpoint=health, methods=["GET"]),
        *api_routes,
        *_build_spa_routes(),
    ],
    middleware=[
        Middleware(CorsMiddleware),
        Middleware(AuthMiddleware),
    ],
)
```

- [ ] **Step 4: 跑 fallback + 全量回归**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest tests/test_spa_fallback.py tests/test_auth_api.py -v
cd /Users/kassol/Workspace/memory-mcp && pytest -v
```
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/memory_mcp/server.py tests/test_spa_fallback.py
git commit -m "feat(server): mount SPA fallback with /assets static serving"
```

---

## Chunk 2: Web 项目脚手架

### Task 4: pnpm workspace 与 package.json

**Files:**
- Create: `web/.gitignore`
- Create: `web/.npmrc`
- Create: `web/pnpm-workspace.yaml`
- Create: `web/package.json`

- [ ] **Step 1: 建目录与 ignore 文件**

```bash
mkdir -p /Users/kassol/Workspace/memory-mcp/web/src
```

Create `web/.gitignore`:

```
node_modules
dist
dist-ssr
*.local
.env.local
.env.*.local
.vite
coverage
.DS_Store
```

Create `web/.npmrc`:

```
engine-strict=true
auto-install-peers=true
shamefully-hoist=false
```

Create `web/pnpm-workspace.yaml`:

```yaml
packages:
  - .
```

- [ ] **Step 2: 写 package.json**

Create `web/package.json`:

```json
{
  "name": "memory-mcp-web",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "packageManager": "pnpm@9.12.0",
  "engines": {
    "node": ">=22.0.0",
    "pnpm": ">=9.0.0"
  },
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@radix-ui/react-checkbox": "^1.1.3",
    "@radix-ui/react-dialog": "^1.1.4",
    "@radix-ui/react-dropdown-menu": "^2.1.4",
    "@radix-ui/react-label": "^2.1.1",
    "@radix-ui/react-select": "^2.1.4",
    "@radix-ui/react-slot": "^1.1.1",
    "@radix-ui/react-tabs": "^1.1.2",
    "@radix-ui/react-tooltip": "^1.1.5",
    "@tanstack/react-query": "^5.100.0",
    "@tanstack/react-table": "^8.21.0",
    "@tanstack/react-virtual": "^3.11.0",
    "@xyflow/react": "^12.10.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "dagre": "^0.8.5",
    "date-fns": "^4.1.0",
    "lucide-react": "^1.16.0",
    "react": "^19.2.0",
    "react-dom": "^19.2.0",
    "react-hook-form": "^7.54.2",
    "react-router-dom": "^7.15.0",
    "sonner": "^1.7.1",
    "tailwind-merge": "^3.0.0",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4.3.0",
    "@tailwindcss/vite": "^4.3.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/dagre": "^0.7.52",
    "@types/node": "^22.10.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react-swc": "^4.0.0",
    "jsdom": "^26.0.0",
    "postcss": "^8.5.0",
    "tailwindcss": "^4.3.0",
    "typescript": "~6.0.0",
    "vite": "^8.0.0",
    "vitest": "^3.0.0"
  }
}
```

如果某个具体 patch 版本不存在，pnpm 会自动取该 minor 下最新可用版本。这里只锁 major.minor。

- [ ] **Step 3: 安装依赖**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && corepack enable && pnpm install
```
Expected: lockfile (`pnpm-lock.yaml`) 生成，无 error。如果某个版本不存在 (`ERR_PNPM_NO_MATCHING_VERSION`)，把该包的版本前缀降到 `^x.0.0` 再试。

- [ ] **Step 4: Commit**

```bash
git add web/.gitignore web/.npmrc web/pnpm-workspace.yaml web/package.json web/pnpm-lock.yaml
git commit -m "chore(web): scaffold pnpm workspace with React 19 stack"
```

### Task 5: TypeScript 与 Vite 配置

**Files:**
- Create: `web/tsconfig.json`
- Create: `web/tsconfig.node.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/postcss.config.js`

- [ ] **Step 1: tsconfig**

Create `web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    },
    "types": ["vite/client", "vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vite.config.ts", "vitest.config.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `web/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2023",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true
  },
  "include": ["vite.config.ts", "vitest.config.ts"]
}
```

- [ ] **Step 2: vite config**

Create `web/vite.config.ts`:

```ts
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import tailwindcss from "@tailwindcss/vite";

const API_TARGET = process.env.VITE_API_TARGET ?? "http://localhost:8765";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
      "/mcp": { target: API_TARGET, changeOrigin: true, ws: true },
      "/health": { target: API_TARGET, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    target: "es2022",
    chunkSizeWarningLimit: 1024,
  },
});
```

- [ ] **Step 3: index.html**

Create `web/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Memory MCP 治理台</title>
  </head>
  <body class="min-h-screen bg-background text-foreground antialiased">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: postcss config**

Create `web/postcss.config.js`:

```js
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
```

- [ ] **Step 5: 验证 type-check 通过**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm lint
```
Expected: 无 error（src 还没建文件时只会报"找不到 entry"，可暂时忽略）。

- [ ] **Step 6: Commit**

```bash
git add web/tsconfig.json web/tsconfig.node.json web/vite.config.ts web/index.html web/postcss.config.js
git commit -m "chore(web): add TS 6 / Vite 8 / PostCSS configs"
```

### Task 6: Tailwind v4 全局样式与 shadcn 配置

**Files:**
- Create: `web/src/styles/globals.css`
- Create: `web/components.json`
- Create: `web/src/lib/utils.ts`

- [ ] **Step 1: Tailwind v4 globals**

Create `web/src/styles/globals.css`:

```css
@import "tailwindcss";
@plugin "tailwindcss-animate";

@custom-variant dark (&:is(.dark *));

@theme {
  --color-background: oklch(1 0 0);
  --color-foreground: oklch(0.145 0 0);

  --color-card: oklch(1 0 0);
  --color-card-foreground: oklch(0.145 0 0);

  --color-popover: oklch(1 0 0);
  --color-popover-foreground: oklch(0.145 0 0);

  --color-primary: oklch(0.205 0 0);
  --color-primary-foreground: oklch(0.985 0 0);

  --color-secondary: oklch(0.97 0 0);
  --color-secondary-foreground: oklch(0.205 0 0);

  --color-muted: oklch(0.97 0 0);
  --color-muted-foreground: oklch(0.556 0 0);

  --color-accent: oklch(0.97 0 0);
  --color-accent-foreground: oklch(0.205 0 0);

  --color-destructive: oklch(0.577 0.245 27.325);
  --color-destructive-foreground: oklch(0.985 0 0);

  --color-border: oklch(0.922 0 0);
  --color-input: oklch(0.922 0 0);
  --color-ring: oklch(0.708 0 0);

  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;

  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "Menlo", monospace;
}

.dark {
  --color-background: oklch(0.145 0 0);
  --color-foreground: oklch(0.985 0 0);
  --color-card: oklch(0.205 0 0);
  --color-card-foreground: oklch(0.985 0 0);
  --color-popover: oklch(0.205 0 0);
  --color-popover-foreground: oklch(0.985 0 0);
  --color-primary: oklch(0.985 0 0);
  --color-primary-foreground: oklch(0.205 0 0);
  --color-secondary: oklch(0.269 0 0);
  --color-secondary-foreground: oklch(0.985 0 0);
  --color-muted: oklch(0.269 0 0);
  --color-muted-foreground: oklch(0.708 0 0);
  --color-accent: oklch(0.269 0 0);
  --color-accent-foreground: oklch(0.985 0 0);
  --color-destructive: oklch(0.704 0.191 22.216);
  --color-destructive-foreground: oklch(0.985 0 0);
  --color-border: oklch(0.269 0 0);
  --color-input: oklch(0.269 0 0);
  --color-ring: oklch(0.556 0 0);
}

html,
body,
#root {
  min-height: 100vh;
}

body {
  font-family: var(--font-sans);
  background-color: var(--color-background);
  color: var(--color-foreground);
}
```

- [ ] **Step 2: shadcn `components.json`**

Create `web/components.json`:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/styles/globals.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

- [ ] **Step 3: `cn` 工具**

Create `web/src/lib/utils.ts`:

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 4: Commit**

```bash
git add web/src/styles/globals.css web/components.json web/src/lib/utils.ts
git commit -m "chore(web): add Tailwind v4 theme tokens and shadcn config"
```

### Task 7: 安装 shadcn 组件

**Files:**
- Create: `web/src/components/ui/*.tsx`

- [ ] **Step 1: 用 shadcn CLI 拉组件**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm dlx shadcn@latest add button input dialog table tabs tooltip dropdown-menu form badge textarea select checkbox card skeleton -y
```

如果 CLI 询问覆盖路径，全部接受默认。CLI 会写入 `web/src/components/ui/`。

- [ ] **Step 1b: 离线 fallback（CLI 不可用时）**

如果 CI / 离线环境跑 `pnpm dlx shadcn@latest` 失败，执行以下脚本一次性下载 14 个组件的 tagged release 源码：

```bash
cd /Users/kassol/Workspace/memory-mcp/web
mkdir -p src/components/ui

# Pin to shadcn-ui 4.7.x reference revision (matches version pin in package.json).
# Source: https://github.com/shadcn-ui/ui/tree/<commit>/apps/v4/registry/new-york-v4/ui
SHADCN_REF="v4.7.0"
COMPONENTS=(button input dialog table tabs tooltip dropdown-menu form badge textarea select checkbox card skeleton sonner)
BASE="https://raw.githubusercontent.com/shadcn-ui/ui/${SHADCN_REF}/apps/v4/registry/new-york-v4/ui"

for c in "${COMPONENTS[@]}"; do
  dest="src/components/ui/${c}.tsx"
  if [ -f "$dest" ]; then
    echo "skip existing $dest"
    continue
  fi
  echo "fetching $c..."
  curl -fsSL "${BASE}/${c}.tsx" -o "$dest"
done

# shadcn components depend on tailwindcss-animate, radix, sonner, react-hook-form, etc.
# All are listed in package.json from Task 4; if any peer is missing, pnpm install will warn.
pnpm install
pnpm dlx tsc --noEmit
```

`tsc --noEmit` 确认 14 个文件的类型都过；不过 fallback 路径推荐留作最后兜底，平时使用 CLI 走默认路径。

> 如果 `SHADCN_REF` 不可用（仓库 tag 变动），优先选择 shadcn-ui 仓库 [release 列表](https://github.com/shadcn-ui/ui/releases)中最近一个 4.7.x tag；不要直接拉 `main`（无 SemVer 保证）。

- [ ] **Step 2: 额外加 sonner toast**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm dlx shadcn@latest add sonner -y
```

会生成 `web/src/components/ui/sonner.tsx`。

- [ ] **Step 3: 验证 ts 编译**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm lint
```
Expected: 无 type error（shadcn 组件自带类型）。

- [ ] **Step 4: Commit**

```bash
git add web/src/components/ui/
git commit -m "chore(web): install shadcn UI primitives"
```

---

## Chunk 3: API 客户端、Store 与类型

### Task 8: 类型定义与 API client

**Files:**
- Create: `web/src/types/index.ts`
- Create: `web/src/lib/api-client.ts`
- Create: `web/src/lib/format.ts`
- Create: `web/src/api/__tests__/api-client.test.ts`
- Create: `web/vitest.config.ts`
- Create: `web/src/test/setup.ts`

- [ ] **Step 1: vitest 配置**

Create `web/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: {
      reporter: ["text", "html"],
      exclude: ["src/components/ui/**", "src/test/**"],
    },
  },
});
```

Create `web/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
```

- [ ] **Step 2: 通用类型**

Create `web/src/types/index.ts`:

```ts
export type ReviewStatus =
  | "auto"
  | "reviewed"
  | "confirmed"
  | "challenged"
  | "legacy"
  | "archived";

// Mirrors `src/memory_mcp/engine/models.py::MutationType` (M1 authoritative).
// The backend writes these strings via `MutationType.<x>.value`.
export type MutationType =
  | "initial"
  | "update"
  | "refinement"
  | "correction"
  | "reversal"
  | "evolution";

export type SourceRef = {
  thread_id: string;
  message_id: string;
};

export interface MemoryNode {
  id: string;
  entity_key: string;
  entity_type: string;
  content: string;
  title: string | null;
  parent_id: string | null;
  mutation_type: MutationType;
  mutation_reason: string | null;
  created_at: string;
  valid_from: string;
  valid_until: string | null;
  is_current: boolean;
  confidence: number;
  review_status: ReviewStatus;
  conflict: boolean;
  conflict_with_id: string | null;
  tags: string[];
  source: string;
  origin_client: string | null;
  origin_session_id: string | null;
  source_thread_id: string | null;
  source_refs: SourceRef[];
  access_count: number;
  last_accessed_at: string | null;
  reinforce_count: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface RecallResult {
  memory_id: string;
  entity_key: string;
  content: string;
  title: string | null;
  final_score: number;
  relevance_breakdown: {
    rrf_score: number;
    vector_rank: number | null;
    fts_rank: number | null;
    graph_rank: number | null;
    confidence: number;
    reinforce_factor: number;
    decay_factor: number;
  };
  review_status: ReviewStatus;
  origin_client: string | null;
  source_thread_id: string | null;
  evolution_count: number;
}

export interface RecallResponse {
  results: RecallResult[];
  total: number;
  search_mode: string;
  search_metadata: {
    vector_candidates: number;
    fts_candidates: number;
    graph_candidates: number;
    filtered_out: number;
    elapsed_ms: number;
  };
}

export interface ThreadSummary {
  thread_id: string;
  source_provider: string;
  source_ref: string;
  title: string | null;
  started_at: string | null;
  ended_at: string | null;
  message_count: number;
  summary: string | null;
}

export interface ThreadMessage {
  message_id: string;
  thread_id: string;
  seq: number;
  role: string;
  content: string;
  ts: string | null;
  metadata: Record<string, unknown>;
  extracted_memory_ids?: string[];
}

export interface GraphNode {
  id: string;
  entity_key: string;
  entity_type: string;
  label: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation_type: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface JobRecord {
  id: string;
  job_type: string;
  status: "pending" | "running" | "done" | "failed";
  attempts: number;
  max_attempts: number;
  scheduled_at: string;
  started_at: string | null;
  finished_at: string | null;
  next_retry_at: string | null;
  error: string | null;
  payload: Record<string, unknown>;
}

export interface SyncStatusItem {
  provider: string;
  source_ref: string;
  last_synced_mtime: number | null;
  last_synced_seq: number | null;
  last_synced_at: string | null;
}

export interface ApiEnvelope<T> {
  ok: boolean;
  data?: T;
  error?: string;
}
```

- [ ] **Step 3: 通用 fetch wrapper**

Create `web/src/lib/api-client.ts`:

```ts
import type { ApiEnvelope } from "@/types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

const DEFAULT_HEADERS: HeadersInit = {
  "Content-Type": "application/json",
};

export type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
};

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(path, window.location.origin);
  if (query) {
    Object.entries(query).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      url.searchParams.set(key, String(value));
    });
  }
  return url.toString();
}

async function parseEnvelope<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  let payload: ApiEnvelope<T> | null = null;
  try {
    payload = (await response.json()) as ApiEnvelope<T>;
  } catch {
    throw new ApiError(response.status, response.statusText);
  }
  if (!response.ok || !payload || payload.ok === false) {
    const message = payload?.error ?? response.statusText;
    throw new ApiError(response.status, message);
  }
  return (payload.data ?? (payload as unknown as T)) as T;
}

export async function apiFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { body, query, headers, ...rest } = opts;
  const init: RequestInit = {
    ...rest,
    credentials: "include",
    headers: { ...DEFAULT_HEADERS, ...(headers ?? {}) },
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }

  const response = await fetch(buildUrl(path, query), init);

  if (response.status === 401 && !path.startsWith("/api/v1/auth/")) {
    // Session expired or never authenticated → bounce to login
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.replace(`/login?next=${next}`);
    throw new ApiError(401, "Unauthorized");
  }

  return parseEnvelope<T>(response);
}

export const api = {
  get: <T>(path: string, query?: RequestOptions["query"]) =>
    apiFetch<T>(path, { method: "GET", query }),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "PUT", body }),
  delete: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "DELETE", body }),
};
```

- [ ] **Step 4: 格式化工具**

Create `web/src/lib/format.ts`:

```ts
import { formatDistanceToNow, format, parseISO } from "date-fns";

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), "yyyy-MM-dd HH:mm");
  } catch {
    return iso;
  }
}

export function formatScore(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}
```

- [ ] **Step 5: 写 api-client 测试**

Create `web/src/api/__tests__/api-client.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api, ApiError } from "@/lib/api-client";

describe("api-client", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    vi.spyOn(global, "fetch");
    Object.defineProperty(window, "location", {
      writable: true,
      value: {
        ...originalLocation,
        pathname: "/memories",
        search: "",
        replace: vi.fn(),
        origin: "http://localhost",
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window, "location", { writable: true, value: originalLocation });
  });

  it("returns data on 200 envelope", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true, data: { items: [], total: 0 } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await api.get<{ items: unknown[] }>("/api/v1/memories");
    expect(result).toEqual({ items: [], total: 0 });
  });

  it("throws ApiError on non-ok envelope", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: false, error: "boom" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(api.get("/api/v1/memories")).rejects.toBeInstanceOf(ApiError);
  });

  it("redirects to /login on 401 for non-auth path", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: false, error: "Unauthorized" }), { status: 401 }),
    );
    await expect(api.get("/api/v1/memories")).rejects.toBeInstanceOf(ApiError);
    expect(window.location.replace).toHaveBeenCalledWith(
      "/login?next=%2Fmemories",
    );
  });

  it("does not redirect on 401 from /auth/login itself", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: false, error: "Forbidden" }), { status: 403 }),
    );
    await expect(api.post("/api/v1/auth/login", { token: "x" })).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(window.location.replace).not.toHaveBeenCalled();
  });

  it("builds query string", async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true, data: {} }), { status: 200 }),
    );
    await api.get("/api/v1/memories", { page: 2, size: 50, entity_type: "preference" });
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("page=2");
    expect(url).toContain("size=50");
    expect(url).toContain("entity_type=preference");
  });
});
```

- [ ] **Step 6: 跑测试**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm test
```
Expected: api-client 测试全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add web/src/types/ web/src/lib/api-client.ts web/src/lib/format.ts \
        web/src/api/__tests__/api-client.test.ts \
        web/vitest.config.ts web/src/test/setup.ts
git commit -m "feat(web): add typed api-client with 401 redirect and tests"
```

### Task 9: Zustand stores 与本地存储

**Files:**
- Create: `web/src/lib/storage.ts`
- Create: `web/src/stores/ui-store.ts`
- Create: `web/src/stores/auth-store.ts`

- [ ] **Step 1: storage 工具**

Create `web/src/lib/storage.ts`:

```ts
const NAMESPACE = "memory-mcp";

export function nsKey(key: string): string {
  return `${NAMESPACE}:${key}`;
}

export function safeGetItem<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(nsKey(key));
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function safeSetItem(key: string, value: unknown): void {
  try {
    localStorage.setItem(nsKey(key), JSON.stringify(value));
  } catch {
    // localStorage may be disabled — silent fail
  }
}
```

- [ ] **Step 2: UI store**

Create `web/src/stores/ui-store.ts`:

```ts
import { create } from "zustand";

interface UiState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebar: (collapsed: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebar: (collapsed) => set({ sidebarCollapsed: collapsed }),
}));
```

- [ ] **Step 3: Auth store**

Create `web/src/stores/auth-store.ts`:

```ts
import { create } from "zustand";

interface AuthState {
  authenticated: boolean | null; // null = not yet checked
  setAuthenticated: (value: boolean) => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  authenticated: null,
  setAuthenticated: (value) => set({ authenticated: value }),
  reset: () => set({ authenticated: false }),
}));
```

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/storage.ts web/src/stores/
git commit -m "feat(web): add zustand stores for UI and auth state"
```

### Task 10: TanStack Query hooks

**Files:**
- Create: `web/src/api/auth.ts`
- Create: `web/src/api/memories.ts`
- Create: `web/src/api/threads.ts`
- Create: `web/src/api/graph.ts`
- Create: `web/src/api/jobs.ts`
- Create: `web/src/api/sync.ts`

- [ ] **Step 1: Auth hooks**

Create `web/src/api/auth.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";

const ME_KEY = ["auth", "me"] as const;

export function useAuthMe(enabled = true) {
  const setAuthenticated = useAuthStore((s) => s.setAuthenticated);
  return useQuery({
    queryKey: ME_KEY,
    enabled,
    retry: false,
    queryFn: async () => {
      try {
        const data = await api.get<{ authenticated: boolean }>("/api/v1/auth/me");
        setAuthenticated(data.authenticated);
        return data;
      } catch {
        setAuthenticated(false);
        throw new Error("Unauthorized");
      }
    },
  });
}

export function useLogin() {
  const qc = useQueryClient();
  const setAuthenticated = useAuthStore((s) => s.setAuthenticated);
  return useMutation({
    mutationFn: (token: string) =>
      api.post<{ authenticated: boolean }>("/api/v1/auth/login", { token }),
    onSuccess: () => {
      setAuthenticated(true);
      qc.invalidateQueries({ queryKey: ME_KEY });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  const reset = useAuthStore((s) => s.reset);
  return useMutation({
    mutationFn: () => api.post<{ authenticated: boolean }>("/api/v1/auth/logout"),
    onSuccess: () => {
      reset();
      qc.clear();
    },
  });
}
```

- [ ] **Step 2: Memories hooks**

Create `web/src/api/memories.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  MemoryNode,
  PaginatedResponse,
  RecallResponse,
  ReviewStatus,
} from "@/types";

export interface MemoryListParams {
  page?: number;
  size?: number;
  entity_type?: string;
  review_status?: ReviewStatus;
  origin_client?: string;
  q?: string;
}

export function useMemories(params: MemoryListParams) {
  return useQuery({
    queryKey: ["memories", "list", params],
    queryFn: () => api.get<PaginatedResponse<MemoryNode>>("/api/v1/memories", params),
    placeholderData: (prev) => prev,
  });
}

export function useMemory(id: string | undefined) {
  return useQuery({
    queryKey: ["memories", "detail", id],
    enabled: Boolean(id),
    queryFn: () => api.get<MemoryNode>(`/api/v1/memories/${id}`),
  });
}

export function useMemoryEvolution(id: string | undefined) {
  return useQuery({
    queryKey: ["memories", "evolution", id],
    enabled: Boolean(id),
    queryFn: () => api.get<MemoryNode[]>(`/api/v1/memories/${id}/evolution`),
  });
}

export interface MemoryCreatePayload {
  content: string;
  entity_key: string;
  entity_type: string;
  title?: string | null;
  tags?: string[];
}

export interface MemoryUpdatePayload {
  content?: string;
  title?: string | null;
  tags?: string[];
  review_status?: ReviewStatus;
}

export function useCreateMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: MemoryCreatePayload) =>
      api.post<MemoryNode>("/api/v1/memories", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories"] }),
  });
}

export function useUpdateMemory(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: MemoryUpdatePayload) =>
      api.patch<MemoryNode>(`/api/v1/memories/${id}`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories", "detail", id] });
      qc.invalidateQueries({ queryKey: ["memories", "list"] });
    },
  });
}

export function useDeleteMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, hard }: { id: string; hard?: boolean }) =>
      api.delete<{ status: string }>(`/api/v1/memories/${id}${hard ? "?hard=true" : ""}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories"] }),
  });
}

export function useBulkDelete() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) =>
      api.post<{ deleted: number }>("/api/v1/memories/bulk-delete", { ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories"] }),
  });
}

export function useMergeMemories() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      sourceIds,
      targetId,
    }: {
      sourceIds: string[];
      targetId: string;
    }) =>
      api.post<{ merged: number; target_id: string }>("/api/v1/memories/bulk-merge", {
        source_ids: sourceIds,
        target_id: targetId,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories"] }),
  });
}

export function useRecall(query: string, enabled = true) {
  return useQuery({
    queryKey: ["recall", query],
    enabled: enabled && Boolean(query),
    queryFn: () =>
      api.post<RecallResponse>("/api/v1/search", { query, mode: "hybrid" }),
  });
}
```

- [ ] **Step 3: Threads hooks**

Create `web/src/api/threads.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  PaginatedResponse,
  ThreadMessage,
  ThreadSummary,
} from "@/types";

export interface ThreadListParams {
  page?: number;
  size?: number;
  provider?: string;
  q?: string;
}

export function useThreads(params: ThreadListParams) {
  return useQuery({
    queryKey: ["threads", "list", params],
    queryFn: () => api.get<PaginatedResponse<ThreadSummary>>("/api/v1/threads", params),
    placeholderData: (prev) => prev,
  });
}

export function useThread(id: string | undefined) {
  return useQuery({
    queryKey: ["threads", "detail", id],
    enabled: Boolean(id),
    queryFn: () => api.get<ThreadSummary>(`/api/v1/threads/${id}`),
  });
}

export function useThreadMessages(id: string | undefined, page = 1, size = 200) {
  return useQuery({
    queryKey: ["threads", "messages", id, page, size],
    enabled: Boolean(id),
    queryFn: () =>
      api.get<PaginatedResponse<ThreadMessage>>(`/api/v1/threads/${id}/messages`, {
        page,
        size,
      }),
    placeholderData: (prev) => prev,
  });
}
```

- [ ] **Step 4: Graph / Jobs / Sync hooks**

Create `web/src/api/graph.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { GraphResponse } from "@/types";

export interface GraphParams {
  entity_key?: string;
  depth?: number;
}

export function useGraph(params: GraphParams = {}) {
  return useQuery({
    queryKey: ["graph", params],
    queryFn: () => api.get<GraphResponse>("/api/v1/graph/subgraph", params),
  });
}
```

Create `web/src/api/jobs.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { JobRecord, PaginatedResponse } from "@/types";

export interface JobListParams {
  status?: string;
  job_type?: string;
  page?: number;
  size?: number;
}

export function useJobs(params: JobListParams) {
  return useQuery({
    queryKey: ["jobs", "list", params],
    queryFn: () => api.get<PaginatedResponse<JobRecord>>("/api/v1/jobs", params),
    refetchInterval: 5000,
  });
}

export function useRetryJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<JobRecord>(`/api/v1/jobs/${id}/retry`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<JobRecord>(`/api/v1/jobs/${id}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}
```

Create `web/src/api/sync.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { SyncStatusItem } from "@/types";

export function useSyncStatus(provider?: string) {
  return useQuery({
    queryKey: ["sync-status", provider],
    queryFn: () =>
      api.get<{ items: SyncStatusItem[] }>("/api/v1/threads/sync-status", {
        provider,
      }),
  });
}
```

- [ ] **Step 5: Commit**

```bash
git add web/src/api/auth.ts web/src/api/memories.ts web/src/api/threads.ts \
        web/src/api/graph.ts web/src/api/jobs.ts web/src/api/sync.ts
git commit -m "feat(web): add TanStack Query hooks for all REST endpoints"
```

---

## Chunk 4: 主框架与路由

### Task 11: 主入口、Layout 与路由守卫

**Files:**
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/components/AppLayout.tsx`
- Create: `web/src/components/RequireAuth.tsx`

- [ ] **Step 1: main.tsx**

Create `web/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/sonner";
import App from "./App";
import "./styles/globals.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <Toaster richColors closeButton position="top-right" />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 2: 路由表 App.tsx**

Create `web/src/App.tsx`:

```tsx
import { Navigate, Route, Routes } from "react-router-dom";
import { lazy, Suspense } from "react";
import { AppLayout } from "@/components/AppLayout";
import { RequireAuth } from "@/components/RequireAuth";
import { Skeleton } from "@/components/ui/skeleton";

const LoginPage = lazy(() => import("@/pages/LoginPage"));
const MemoriesPage = lazy(() => import("@/pages/MemoriesPage"));
const MemoryDetailPage = lazy(() => import("@/pages/MemoryDetailPage"));
const MemoryNewPage = lazy(() => import("@/pages/MemoryNewPage"));
const ThreadsPage = lazy(() => import("@/pages/ThreadsPage"));
const ThreadDetailPage = lazy(() => import("@/pages/ThreadDetailPage"));
const GraphPage = lazy(() => import("@/pages/GraphPage"));
const JobsPage = lazy(() => import("@/pages/JobsPage"));
const SourcesPage = lazy(() => import("@/pages/SourcesPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));

function LazyFallback() {
  return (
    <div className="p-8 space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<LazyFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/memories" replace />} />
          <Route path="/memories" element={<MemoriesPage />} />
          <Route path="/memories/new" element={<MemoryNewPage />} />
          <Route path="/memories/:id" element={<MemoryDetailPage />} />
          <Route path="/threads" element={<ThreadsPage />} />
          <Route path="/threads/:id" element={<ThreadDetailPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/sources" element={<SourcesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/memories" replace />} />
      </Routes>
    </Suspense>
  );
}
```

- [ ] **Step 3: RequireAuth**

Create `web/src/components/RequireAuth.tsx`:

```tsx
import { Navigate, useLocation } from "react-router-dom";
import { useAuthMe } from "@/api/auth";
import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  children: React.ReactNode;
}

export function RequireAuth({ children }: Props) {
  const location = useLocation();
  const { data, isLoading, isError } = useAuthMe();

  if (isLoading) {
    return (
      <div className="min-h-screen p-8 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError || !data?.authenticated) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return <>{children}</>;
}
```

- [ ] **Step 4: AppLayout**

Create `web/src/components/AppLayout.tsx`:

```tsx
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Brain,
  GitBranch,
  ListChecks,
  LogOut,
  MessagesSquare,
  Network,
  Settings,
  BookOpen,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { useUiStore } from "@/stores/ui-store";
import { useLogout } from "@/api/auth";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { to: "/memories", label: "Memories", icon: Brain },
  { to: "/threads", label: "Threads", icon: MessagesSquare },
  { to: "/graph", label: "Graph", icon: Network },
  { to: "/jobs", label: "Jobs", icon: ListChecks },
  { to: "/sources", label: "Sources", icon: BookOpen },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppLayout() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggle = useUiStore((s) => s.toggleSidebar);
  const navigate = useNavigate();
  const logout = useLogout();

  const handleLogout = async () => {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-screen w-full">
      <aside
        className={cn(
          "border-r border-border bg-card transition-all duration-200 flex flex-col",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <div className="flex items-center justify-between p-4 border-b border-border">
          {!collapsed && (
            <div className="flex items-center gap-2 text-sm font-semibold">
              <GitBranch className="size-4" />
              <span>Memory MCP</span>
            </div>
          )}
          <Button variant="ghost" size="icon" onClick={toggle}>
            {collapsed ? (
              <PanelLeftOpen className="size-4" />
            ) : (
              <PanelLeftClose className="size-4" />
            )}
          </Button>
        </div>

        <nav className="flex-1 p-2 space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted",
                )
              }
            >
              <item.icon className="size-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="p-2 border-t border-border">
          <Button
            variant="ghost"
            className="w-full justify-start text-muted-foreground"
            onClick={handleLogout}
          >
            <LogOut className="size-4" />
            {!collapsed && <span className="ml-3">Logout</span>}
          </Button>
        </div>
      </aside>

      <main className="flex-1 min-w-0 overflow-auto bg-background">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add web/src/main.tsx web/src/App.tsx web/src/components/AppLayout.tsx web/src/components/RequireAuth.tsx
git commit -m "feat(web): add main entry, router, layout, and auth guard"
```

### Task 12: Login 页面

**Files:**
- Create: `web/src/pages/LoginPage.tsx`

- [ ] **Step 1: 实现登录页**

Create `web/src/pages/LoginPage.tsx`:

```tsx
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useLogin } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  const [token, setToken] = useState("");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const login = useLogin();

  const next = params.get("next") ?? "/memories";

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      toast.error("请输入 token");
      return;
    }
    try {
      await login.mutateAsync(token);
      toast.success("登录成功");
      navigate(next, { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : "登录失败";
      toast.error(message);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Memory MCP</CardTitle>
          <CardDescription>使用部署时配置的 Bearer Token 登录治理台</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <Input
              type="password"
              autoComplete="current-password"
              placeholder="Bearer Token"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              disabled={login.isPending}
            />
            <Button type="submit" className="w-full" disabled={login.isPending}>
              {login.isPending ? "验证中..." : "登录"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: 跑 type check**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm lint
```
Expected: 无 error（其它 page 还没建会报 `Cannot find module @/pages/...`，这个 task 后才会被解决，可忽略到 Task 18 完成后再校验）。

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/LoginPage.tsx
git commit -m "feat(web): add login page with Bearer token form"
```

---

## Chunk 5: Memory 相关组件

### Task 13: RelevanceBreakdown 与 EvolutionTimeline

**Files:**
- Create: `web/src/components/RelevanceBreakdown.tsx`
- Create: `web/src/components/EvolutionTimeline.tsx`

- [ ] **Step 1: RelevanceBreakdown**

Create `web/src/components/RelevanceBreakdown.tsx`:

```tsx
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { formatPercent, formatScore } from "@/lib/format";
import type { RecallResult } from "@/types";

interface Props {
  breakdown: RecallResult["relevance_breakdown"];
  finalScore: number;
}

export function RelevanceBreakdown({ breakdown, finalScore }: Props) {
  const items: Array<{ label: string; value: string }> = [
    { label: "RRF", value: formatScore(breakdown.rrf_score) },
    { label: "Vector", value: breakdown.vector_rank?.toString() ?? "—" },
    { label: "FTS", value: breakdown.fts_rank?.toString() ?? "—" },
    { label: "Graph", value: breakdown.graph_rank?.toString() ?? "—" },
    { label: "Confidence", value: formatPercent(breakdown.confidence) },
    { label: "Reinforce", value: `×${formatScore(breakdown.reinforce_factor)}` },
    { label: "Decay", value: `×${formatScore(breakdown.decay_factor)}` },
  ];

  return (
    <TooltipProvider>
      <div className="flex flex-wrap gap-1.5">
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="default" className="font-mono">
              {formatScore(finalScore)}
            </Badge>
          </TooltipTrigger>
          <TooltipContent>final_score</TooltipContent>
        </Tooltip>
        {items.map((item) => (
          <Tooltip key={item.label}>
            <TooltipTrigger asChild>
              <Badge variant="outline" className="font-mono">
                {item.label}:{item.value}
              </Badge>
            </TooltipTrigger>
            <TooltipContent>{item.label}</TooltipContent>
          </Tooltip>
        ))}
      </div>
    </TooltipProvider>
  );
}
```

- [ ] **Step 2: EvolutionTimeline**

Create `web/src/components/EvolutionTimeline.tsx`:

```tsx
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { MemoryNode } from "@/types";

interface Props {
  history: MemoryNode[];
  currentId: string;
}

// Keys mirror M1 `MutationType` enum values.
const MUTATION_LABEL: Record<string, string> = {
  initial: "创建",
  update: "更新",
  refinement: "细化",
  correction: "修正",
  reversal: "反转",
  evolution: "演化",
};

export function EvolutionTimeline({ history, currentId }: Props) {
  if (history.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无历史。</p>;
  }
  const sorted = [...history].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <ol className="space-y-4">
      {sorted.map((node) => {
        const isCurrent = node.id === currentId;
        return (
          <li
            key={node.id}
            className={cn(
              "relative pl-6 border-l-2 border-border",
              isCurrent && "border-primary",
            )}
          >
            <span
              className={cn(
                "absolute -left-[7px] top-1 size-3 rounded-full bg-muted-foreground",
                isCurrent && "bg-primary",
              )}
            />
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant={isCurrent ? "default" : "outline"}>
                {MUTATION_LABEL[node.mutation_type] ?? node.mutation_type}
              </Badge>
              <span>{formatDateTime(node.created_at)}</span>
              {isCurrent && <Badge variant="secondary">current</Badge>}
            </div>
            <p className="mt-1 text-sm">{node.content}</p>
            {node.mutation_reason && (
              <p className="mt-1 text-xs italic text-muted-foreground">
                原因：{node.mutation_reason}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web/src/components/RelevanceBreakdown.tsx web/src/components/EvolutionTimeline.tsx
git commit -m "feat(web): add RelevanceBreakdown and EvolutionTimeline components"
```

### Task 14: SourceRefsPanel

**Files:**
- Create: `web/src/components/SourceRefsPanel.tsx`

- [ ] **Step 1: 实现源回链面板**

Create `web/src/components/SourceRefsPanel.tsx`:

```tsx
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { MemoryNode } from "@/types";

interface Props {
  memory: Pick<MemoryNode, "source_thread_id" | "source_refs" | "origin_client" | "origin_session_id">;
}

export function SourceRefsPanel({ memory }: Props) {
  const hasRefs = (memory.source_refs?.length ?? 0) > 0;
  const hasThread = Boolean(memory.source_thread_id);

  if (!hasRefs && !hasThread && !memory.origin_client) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">来源</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          手动创建或从 v1 迁移而来，无源回链。
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">来源</CardTitle>
        {memory.origin_client && <Badge variant="outline">{memory.origin_client}</Badge>}
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {hasThread && (
          <div>
            <span className="text-muted-foreground">线程：</span>
            <Link
              to={`/threads/${memory.source_thread_id}`}
              className="font-mono underline-offset-2 hover:underline"
            >
              {memory.source_thread_id}
            </Link>
          </div>
        )}
        {hasRefs && (
          <div>
            <span className="text-muted-foreground">消息回链：</span>
            <ul className="mt-1 space-y-1">
              {memory.source_refs.map((ref) => (
                <li key={ref.message_id}>
                  <Link
                    to={`/threads/${ref.thread_id}?focus=${encodeURIComponent(ref.message_id)}`}
                    className="font-mono text-xs underline-offset-2 hover:underline"
                  >
                    {ref.message_id}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
        {memory.origin_session_id && (
          <div>
            <span className="text-muted-foreground">会话 ID：</span>
            <span className="font-mono text-xs">{memory.origin_session_id}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/SourceRefsPanel.tsx
git commit -m "feat(web): add SourceRefsPanel for memory source backlinks"
```

### Task 15: MemoryList 组件 + 测试

**Files:**
- Create: `web/src/components/MemoryList.tsx`
- Create: `web/src/components/__tests__/MemoryList.test.tsx`

- [ ] **Step 1: 写组件测试**

Create `web/src/components/__tests__/MemoryList.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MemoryList } from "@/components/MemoryList";
import type { MemoryNode } from "@/types";

const SAMPLE: MemoryNode[] = [
  {
    id: "m-1",
    entity_key: "preference:editor",
    entity_type: "preference",
    content: "Use Cursor",
    title: "编辑器偏好",
    parent_id: null,
    mutation_type: "initial",
    mutation_reason: null,
    created_at: "2026-05-20T10:00:00Z",
    valid_from: "2026-05-20T10:00:00Z",
    valid_until: null,
    is_current: true,
    confidence: 1,
    review_status: "auto",
    conflict: false,
    conflict_with_id: null,
    tags: ["editor"],
    source: "conversation",
    origin_client: "claude-code",
    origin_session_id: null,
    source_thread_id: null,
    source_refs: [],
    access_count: 3,
    last_accessed_at: null,
    reinforce_count: 1,
  },
  {
    id: "m-2",
    entity_key: "project:memory-mcp",
    entity_type: "project",
    content: "Building memory service",
    title: null,
    parent_id: null,
    mutation_type: "initial",
    mutation_reason: null,
    created_at: "2026-05-19T08:00:00Z",
    valid_from: "2026-05-19T08:00:00Z",
    valid_until: null,
    is_current: true,
    confidence: 1,
    review_status: "confirmed",
    conflict: false,
    conflict_with_id: null,
    tags: [],
    source: "conversation",
    origin_client: null,
    origin_session_id: null,
    source_thread_id: null,
    source_refs: [],
    access_count: 0,
    last_accessed_at: null,
    reinforce_count: 0,
  },
];

function renderList(props?: Partial<React.ComponentProps<typeof MemoryList>>) {
  const onSelectionChange = vi.fn();
  const onBulkDelete = vi.fn();
  const onMergeRequest = vi.fn();
  render(
    <MemoryRouter>
      <MemoryList
        items={SAMPLE}
        loading={false}
        selectedIds={new Set()}
        onSelectionChange={onSelectionChange}
        onBulkDelete={onBulkDelete}
        onMergeRequest={onMergeRequest}
        {...props}
      />
    </MemoryRouter>,
  );
  return { onSelectionChange, onBulkDelete, onMergeRequest };
}

describe("MemoryList", () => {
  it("renders rows for each item", () => {
    renderList();
    expect(screen.getByText("Use Cursor")).toBeInTheDocument();
    expect(screen.getByText("Building memory service")).toBeInTheDocument();
  });

  it("toggles selection via checkbox", () => {
    const { onSelectionChange } = renderList();
    const rowCheckbox = screen.getAllByRole("checkbox").find(
      (el) => el.getAttribute("data-row-id") === "m-1",
    );
    expect(rowCheckbox).toBeDefined();
    fireEvent.click(rowCheckbox!);
    expect(onSelectionChange).toHaveBeenCalled();
    const next = onSelectionChange.mock.calls[0][0] as Set<string>;
    expect(next.has("m-1")).toBe(true);
  });

  it("shows bulk toolbar only when items selected", () => {
    const { rerender } = render(
      <MemoryRouter>
        <MemoryList
          items={SAMPLE}
          loading={false}
          selectedIds={new Set()}
          onSelectionChange={vi.fn()}
          onBulkDelete={vi.fn()}
          onMergeRequest={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/已选/)).not.toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <MemoryList
          items={SAMPLE}
          loading={false}
          selectedIds={new Set(["m-1", "m-2"])}
          onSelectionChange={vi.fn()}
          onBulkDelete={vi.fn()}
          onMergeRequest={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/已选 2/)).toBeInTheDocument();
  });

  it("invokes onMergeRequest when merge action clicked", () => {
    const { onMergeRequest } = renderList({ selectedIds: new Set(["m-1", "m-2"]) });
    fireEvent.click(screen.getByRole("button", { name: /合并/ }));
    expect(onMergeRequest).toHaveBeenCalledWith(["m-1", "m-2"]);
  });
});
```

- [ ] **Step 2: 跑测试看初始失败**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm test -- MemoryList
```
Expected: FAIL（组件未创建）。

- [ ] **Step 3: 实现组件**

Create `web/src/components/MemoryList.tsx`:

```tsx
import { Link } from "react-router-dom";
import { Trash2, GitMerge } from "lucide-react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { formatRelative } from "@/lib/format";
import type { MemoryNode, ReviewStatus } from "@/types";

interface Props {
  items: MemoryNode[];
  loading: boolean;
  selectedIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
  onBulkDelete: (ids: string[]) => void;
  onMergeRequest: (ids: string[]) => void;
}

const REVIEW_BADGE: Record<ReviewStatus, { label: string; variant: "default" | "outline" | "secondary" | "destructive" }> = {
  auto: { label: "auto", variant: "outline" },
  reviewed: { label: "reviewed", variant: "secondary" },
  confirmed: { label: "confirmed", variant: "default" },
  challenged: { label: "challenged", variant: "destructive" },
  legacy: { label: "legacy", variant: "outline" },
  archived: { label: "archived", variant: "outline" },
};

export function MemoryList({
  items,
  loading,
  selectedIds,
  onSelectionChange,
  onBulkDelete,
  onMergeRequest,
}: Props) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 96,
    overscan: 8,
  });

  const toggle = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    onSelectionChange(next);
  };

  const toggleAll = () => {
    if (selectedIds.size === items.length) {
      onSelectionChange(new Set());
    } else {
      onSelectionChange(new Set(items.map((i) => i.id)));
    }
  };

  const selectedList = Array.from(selectedIds);

  return (
    <div className="space-y-3">
      {selectedIds.size > 0 && (
        <div className="flex items-center justify-between rounded-md border border-border bg-card p-3">
          <span className="text-sm">已选 {selectedIds.size} 项</span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={selectedIds.size < 2}
              onClick={() => onMergeRequest(selectedList)}
            >
              <GitMerge className="size-4 mr-1" /> 合并
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => onBulkDelete(selectedList)}
            >
              <Trash2 className="size-4 mr-1" /> 批量删除
            </Button>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3 px-3 py-2 border-b border-border text-xs text-muted-foreground">
        <Checkbox
          checked={items.length > 0 && selectedIds.size === items.length}
          onCheckedChange={toggleAll}
          aria-label="select all"
        />
        <span>选择</span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, idx) => (
            <Skeleton key={idx} className="h-20 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground p-8 text-center">暂无记忆。</p>
      ) : (
        <div ref={parentRef} className="h-[70vh] overflow-auto">
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              position: "relative",
              width: "100%",
            }}
          >
            {virtualizer.getVirtualItems().map((row) => {
              const memory = items[row.index];
              const review = REVIEW_BADGE[memory.review_status];
              return (
                <div
                  key={memory.id}
                  data-row-id={memory.id}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${row.start}px)`,
                  }}
                  className={cn(
                    "flex gap-3 border-b border-border px-3 py-3 hover:bg-muted/40 transition-colors",
                    selectedIds.has(memory.id) && "bg-muted/60",
                  )}
                >
                  <Checkbox
                    data-row-id={memory.id}
                    checked={selectedIds.has(memory.id)}
                    onCheckedChange={() => toggle(memory.id)}
                    aria-label={`select ${memory.entity_key}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <Link
                        to={`/memories/${memory.id}`}
                        className="font-mono text-foreground hover:underline truncate max-w-[280px]"
                      >
                        {memory.entity_key}
                      </Link>
                      <Badge variant="outline">{memory.entity_type}</Badge>
                      <Badge variant={review.variant}>{review.label}</Badge>
                      {memory.conflict && <Badge variant="destructive">conflict</Badge>}
                      {memory.origin_client && (
                        <Badge variant="outline">{memory.origin_client}</Badge>
                      )}
                      <span>{formatRelative(memory.created_at)}</span>
                    </div>
                    <p className="mt-1 text-sm line-clamp-2">{memory.content}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: 跑测试**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm test -- MemoryList
```
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add web/src/components/MemoryList.tsx web/src/components/__tests__/MemoryList.test.tsx
git commit -m "feat(web): add MemoryList with virtualization, multi-select, and tests"
```

### Task 16: MemoryMergeDialog 组件 + 测试

**Files:**
- Create: `web/src/components/MemoryMergeDialog.tsx`
- Create: `web/src/components/__tests__/MemoryMergeDialog.test.tsx`

- [ ] **Step 1: 写组件测试**

Create `web/src/components/__tests__/MemoryMergeDialog.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryMergeDialog } from "@/components/MemoryMergeDialog";
import type { MemoryNode } from "@/types";

const NODES: MemoryNode[] = [
  {
    id: "m-1",
    entity_key: "preference:editor",
    entity_type: "preference",
    content: "Use Cursor",
    title: null,
    parent_id: null,
    mutation_type: "initial",
    mutation_reason: null,
    created_at: "2026-05-20T10:00:00Z",
    valid_from: "2026-05-20T10:00:00Z",
    valid_until: null,
    is_current: true,
    confidence: 1,
    review_status: "auto",
    conflict: false,
    conflict_with_id: null,
    tags: [],
    source: "conversation",
    origin_client: null,
    origin_session_id: null,
    source_thread_id: null,
    source_refs: [],
    access_count: 0,
    last_accessed_at: null,
    reinforce_count: 0,
  },
  {
    id: "m-2",
    entity_key: "preference:editor",
    entity_type: "preference",
    content: "Cursor IDE",
    title: null,
    parent_id: null,
    mutation_type: "initial",
    mutation_reason: null,
    created_at: "2026-05-21T10:00:00Z",
    valid_from: "2026-05-21T10:00:00Z",
    valid_until: null,
    is_current: true,
    confidence: 1,
    review_status: "auto",
    conflict: false,
    conflict_with_id: null,
    tags: [],
    source: "conversation",
    origin_client: null,
    origin_session_id: null,
    source_thread_id: null,
    source_refs: [],
    access_count: 0,
    last_accessed_at: null,
    reinforce_count: 0,
  },
];

describe("MemoryMergeDialog", () => {
  it("renders all candidate memories", () => {
    render(
      <MemoryMergeDialog
        open
        onOpenChange={vi.fn()}
        candidates={NODES}
        onConfirm={vi.fn()}
        submitting={false}
      />,
    );
    expect(screen.getByText("Use Cursor")).toBeInTheDocument();
    expect(screen.getByText("Cursor IDE")).toBeInTheDocument();
  });

  it("requires picking a target before confirm", () => {
    const onConfirm = vi.fn();
    render(
      <MemoryMergeDialog
        open
        onOpenChange={vi.fn()}
        candidates={NODES}
        onConfirm={onConfirm}
        submitting={false}
      />,
    );
    const confirmBtn = screen.getByRole("button", { name: /确认合并/ });
    expect(confirmBtn).toBeDisabled();
  });

  it("invokes onConfirm with source/target ids", () => {
    const onConfirm = vi.fn();
    render(
      <MemoryMergeDialog
        open
        onOpenChange={vi.fn()}
        candidates={NODES}
        onConfirm={onConfirm}
        submitting={false}
      />,
    );
    // pick m-2 as target
    fireEvent.click(screen.getByRole("radio", { name: /m-2/ }));
    fireEvent.click(screen.getByRole("button", { name: /确认合并/ }));
    expect(onConfirm).toHaveBeenCalledWith({
      targetId: "m-2",
      sourceIds: ["m-1"],
    });
  });
});
```

- [ ] **Step 2: 跑测试看初始失败**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm test -- MemoryMergeDialog
```
Expected: FAIL。

- [ ] **Step 3: 实现 dialog**

Create `web/src/components/MemoryMergeDialog.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/format";
import type { MemoryNode } from "@/types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  candidates: MemoryNode[];
  submitting: boolean;
  onConfirm: (payload: { targetId: string; sourceIds: string[] }) => void;
}

export function MemoryMergeDialog({ open, onOpenChange, candidates, submitting, onConfirm }: Props) {
  const [targetId, setTargetId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) setTargetId(null);
  }, [open]);

  const sourceIds = candidates.filter((c) => c.id !== targetId).map((c) => c.id);

  const handleConfirm = () => {
    if (!targetId) return;
    onConfirm({ targetId, sourceIds });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>合并记忆</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            选择保留的目标记忆，其余将归档并把演化链指向目标。
          </p>
          <ul className="space-y-2 max-h-80 overflow-auto pr-2">
            {candidates.map((c) => {
              const checked = targetId === c.id;
              return (
                <li
                  key={c.id}
                  className={cn(
                    "rounded-md border border-border p-3 cursor-pointer hover:bg-muted/40",
                    checked && "border-primary bg-muted/60",
                  )}
                  onClick={() => setTargetId(c.id)}
                >
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="radio"
                      name="merge-target"
                      checked={checked}
                      onChange={() => setTargetId(c.id)}
                      aria-label={`target ${c.id}`}
                      className="mt-1"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span className="font-mono">{c.id}</span>
                        <Badge variant="outline">{c.entity_type}</Badge>
                        <Badge variant="outline">{c.review_status}</Badge>
                        <span>{formatDateTime(c.created_at)}</span>
                      </div>
                      <p className="mt-1 text-sm">{c.content}</p>
                    </div>
                  </label>
                </li>
              );
            })}
          </ul>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleConfirm} disabled={!targetId || submitting}>
            {submitting ? "合并中..." : "确认合并"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: 跑测试**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm test -- MemoryMergeDialog
```
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add web/src/components/MemoryMergeDialog.tsx web/src/components/__tests__/MemoryMergeDialog.test.tsx
git commit -m "feat(web): add MemoryMergeDialog with target-pick UI and tests"
```

### Task 17: MemoryDetail 组件

**Files:**
- Create: `web/src/components/MemoryDetail.tsx`

- [ ] **Step 1: 实现详情表单**

Create `web/src/components/MemoryDetail.tsx`:

```tsx
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EvolutionTimeline } from "@/components/EvolutionTimeline";
import { SourceRefsPanel } from "@/components/SourceRefsPanel";
import { formatDateTime } from "@/lib/format";
import type { MemoryNode, ReviewStatus } from "@/types";
import { useMemoryEvolution, useUpdateMemory, useDeleteMemory } from "@/api/memories";

interface Props {
  memory: MemoryNode;
}

const REVIEW_OPTIONS: ReviewStatus[] = [
  "auto",
  "reviewed",
  "confirmed",
  "challenged",
  "legacy",
];

export function MemoryDetail({ memory }: Props) {
  const [title, setTitle] = useState(memory.title ?? "");
  const [content, setContent] = useState(memory.content);
  const [tagsInput, setTagsInput] = useState(memory.tags.join(", "));
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus>(memory.review_status);

  const evolution = useMemoryEvolution(memory.id);
  const updateMutation = useUpdateMemory(memory.id);
  const deleteMutation = useDeleteMemory();

  useEffect(() => {
    setTitle(memory.title ?? "");
    setContent(memory.content);
    setTagsInput(memory.tags.join(", "));
    setReviewStatus(memory.review_status);
  }, [memory.id]);

  const handleSave = async () => {
    try {
      await updateMutation.mutateAsync({
        title: title.trim() || null,
        content,
        tags: tagsInput
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        review_status: reviewStatus,
      });
      toast.success("已保存");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    }
  };

  const handleArchive = async () => {
    try {
      await deleteMutation.mutateAsync({ id: memory.id });
      toast.success("已归档");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "归档失败");
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="font-mono text-xs">{memory.entity_key}</span>
            <Badge variant="outline">{memory.entity_type}</Badge>
            {memory.conflict && <Badge variant="destructive">conflict</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="edit">
            <TabsList>
              <TabsTrigger value="edit">编辑</TabsTrigger>
              <TabsTrigger value="evolution">演化链</TabsTrigger>
              <TabsTrigger value="raw">Raw</TabsTrigger>
            </TabsList>

            <TabsContent value="edit" className="space-y-4 mt-4">
              <div>
                <label className="text-xs text-muted-foreground">Title</label>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Content</label>
                <Textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  rows={6}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground">Tags (逗号分隔)</label>
                  <Input value={tagsInput} onChange={(e) => setTagsInput(e.target.value)} />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Review Status</label>
                  <Select
                    value={reviewStatus}
                    onValueChange={(v) => setReviewStatus(v as ReviewStatus)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {REVIEW_OPTIONS.map((opt) => (
                        <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex justify-between pt-2">
                <Button variant="destructive" onClick={handleArchive} disabled={deleteMutation.isPending}>
                  归档
                </Button>
                <Button onClick={handleSave} disabled={updateMutation.isPending}>
                  {updateMutation.isPending ? "保存中..." : "保存"}
                </Button>
              </div>
            </TabsContent>

            <TabsContent value="evolution" className="mt-4">
              {evolution.isLoading ? (
                <p className="text-sm text-muted-foreground">加载中...</p>
              ) : (
                <EvolutionTimeline
                  history={evolution.data ?? []}
                  currentId={memory.id}
                />
              )}
            </TabsContent>

            <TabsContent value="raw" className="mt-4">
              <pre className="text-xs bg-muted rounded-md p-3 overflow-auto max-h-96">
                {JSON.stringify(memory, null, 2)}
              </pre>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">元信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">创建</span>
              <span>{formatDateTime(memory.created_at)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">最近访问</span>
              <span>{formatDateTime(memory.last_accessed_at)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">访问次数</span>
              <span>{memory.access_count}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">强化次数</span>
              <span>{memory.reinforce_count}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">置信度</span>
              <span>{memory.confidence.toFixed(2)}</span>
            </div>
          </CardContent>
        </Card>

        <SourceRefsPanel memory={memory} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/MemoryDetail.tsx
git commit -m "feat(web): add MemoryDetail with edit form, evolution, and source panel"
```

---

## Chunk 6: Thread / Graph / Jobs / Sync 组件

### Task 18: ThreadMessages 组件

**Files:**
- Create: `web/src/components/ThreadMessages.tsx`

- [ ] **Step 1: 实现虚拟化消息流**

Create `web/src/components/ThreadMessages.tsx`:

```tsx
import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/format";
import type { ThreadMessage } from "@/types";

interface Props {
  messages: ThreadMessage[];
}

const ROLE_COLOR: Record<string, string> = {
  user: "border-blue-500/40",
  assistant: "border-emerald-500/40",
  tool: "border-amber-500/40",
  system: "border-zinc-500/40",
};

export function ThreadMessages({ messages }: Props) {
  const [params] = useSearchParams();
  const focusId = params.get("focus");
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 160,
    overscan: 6,
  });

  useEffect(() => {
    if (!focusId) return;
    const idx = messages.findIndex((m) => m.message_id === focusId);
    if (idx >= 0) {
      virtualizer.scrollToIndex(idx, { align: "center" });
    }
  }, [focusId, messages, virtualizer]);

  if (messages.length === 0) {
    return <p className="text-sm text-muted-foreground p-8 text-center">线程为空。</p>;
  }

  return (
    <div ref={parentRef} className="h-[75vh] overflow-auto">
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          position: "relative",
          width: "100%",
        }}
      >
        {virtualizer.getVirtualItems().map((row) => {
          const message = messages[row.index];
          const extracted = message.extracted_memory_ids ?? [];
          const isFocus = message.message_id === focusId;
          return (
            <div
              key={message.message_id}
              data-message-id={message.message_id}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${row.start}px)`,
                padding: "0 4px",
              }}
            >
              <div
                className={cn(
                  "rounded-md border-l-4 bg-card p-3 mb-2 transition-all",
                  ROLE_COLOR[message.role] ?? "border-zinc-500/40",
                  extracted.length > 0 && "ring-1 ring-primary/30",
                  isFocus && "ring-2 ring-primary",
                )}
              >
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline">{message.role}</Badge>
                  <span className="font-mono">{message.message_id}</span>
                  <span>{formatDateTime(message.ts)}</span>
                  {extracted.length > 0 && (
                    <Badge variant="secondary">已抽取 {extracted.length} 条</Badge>
                  )}
                </div>
                <pre className="mt-2 whitespace-pre-wrap text-sm leading-relaxed font-sans">
                  {message.content}
                </pre>
                {extracted.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {extracted.map((id) => (
                      <Link
                        key={id}
                        to={`/memories/${id}`}
                        className="text-xs underline-offset-2 hover:underline font-mono"
                      >
                        →{id}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/ThreadMessages.tsx
git commit -m "feat(web): add ThreadMessages with virtualization and extraction highlight"
```

### Task 19: GraphView 组件 + 测试

**Files:**
- Create: `web/src/components/GraphView.tsx`
- Create: `web/src/components/__tests__/GraphView.test.tsx`

- [ ] **Step 1: 写组件测试**

Create `web/src/components/__tests__/GraphView.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { GraphView } from "@/components/GraphView";

// Mock @xyflow/react to a simple DOM so tests do not require canvas
vi.mock("@xyflow/react", () => {
  const React = require("react");
  return {
    ReactFlow: ({ nodes, onNodeClick, children }: any) => (
      React.createElement(
        "div",
        { "data-testid": "rf" },
        ...nodes.map((n: any) =>
          React.createElement(
            "button",
            {
              key: n.id,
              "data-node-id": n.id,
              "data-label": n.data?.label,
              onClick: (e: any) => onNodeClick?.(e, n),
            },
            n.data?.label,
          ),
        ),
        children,
      )
    ),
    Background: () => React.createElement("div", { "data-testid": "bg" }),
    Controls: () => React.createElement("div", { "data-testid": "controls" }),
    MarkerType: { ArrowClosed: "arrowclosed" },
  };
});

describe("GraphView", () => {
  it("renders provided nodes", () => {
    render(
      <MemoryRouter>
        <GraphView
          nodes={[
            { id: "n-1", entity_key: "person:alice", entity_type: "person", label: "Alice" },
            { id: "n-2", entity_key: "project:x", entity_type: "project", label: "Project X" },
          ]}
          edges={[{ id: "e-1", source: "n-1", target: "n-2", relation_type: "WORKS_ON" }]}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Project X")).toBeInTheDocument();
  });

  it("navigates to memory on node click", () => {
    const onSelect = vi.fn();
    render(
      <MemoryRouter>
        <GraphView
          nodes={[
            { id: "m-99", entity_key: "fact:x", entity_type: "fact", label: "X" },
          ]}
          edges={[]}
          onSelect={onSelect}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("X"));
    expect(onSelect).toHaveBeenCalledWith({
      id: "m-99",
      entity_key: "fact:x",
      entity_type: "fact",
      label: "X",
    });
  });
});
```

- [ ] **Step 2: 跑测试看初始失败**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm test -- GraphView
```
Expected: FAIL。

- [ ] **Step 3: 实现 GraphView**

Create `web/src/components/GraphView.tsx`:

```tsx
import { useMemo } from "react";
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge as RfEdge,
  type Node as RfNode,
} from "@xyflow/react";
import dagre from "dagre";
import "@xyflow/react/dist/style.css";
import type { GraphEdge, GraphNode } from "@/types";

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onSelect?: (node: GraphNode) => void;
}

const NODE_WIDTH = 180;
const NODE_HEIGHT = 60;

function layout(nodes: GraphNode[], edges: GraphEdge[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 80 });

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  const rfNodes: RfNode[] = nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      data: { label: n.label, entity_key: n.entity_key, entity_type: n.entity_type },
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      style: {
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        borderRadius: 8,
        padding: 8,
        fontSize: 12,
      },
    };
  });

  const rfEdges: RfEdge[] = edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.relation_type,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));

  return { rfNodes, rfEdges };
}

export function GraphView({ nodes, edges, onSelect }: Props) {
  const { rfNodes, rfEdges } = useMemo(() => layout(nodes, edges), [nodes, edges]);

  const handleNodeClick = (_: unknown, node: RfNode) => {
    const original = nodes.find((n) => n.id === node.id);
    if (original) {
      onSelect?.(original);
    }
  };

  return (
    <div className="h-[80vh] w-full rounded-md border border-border bg-card">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        onNodeClick={handleNodeClick}
        fitView
        nodesDraggable
        defaultEdgeOptions={{ animated: false }}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
```

- [ ] **Step 4: 跑测试**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm test -- GraphView
```
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add web/src/components/GraphView.tsx web/src/components/__tests__/GraphView.test.tsx
git commit -m "feat(web): add GraphView with @xyflow/react + dagre layout and tests"
```

### Task 20: JobsTable 与 SyncStatusCard

**Files:**
- Create: `web/src/components/JobsTable.tsx`
- Create: `web/src/components/SyncStatusCard.tsx`

- [ ] **Step 1: JobsTable**

Create `web/src/components/JobsTable.tsx`:

```tsx
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useCancelJob, useRetryJob } from "@/api/jobs";
import { formatRelative } from "@/lib/format";
import type { JobRecord } from "@/types";

interface Props {
  jobs: JobRecord[];
  loading: boolean;
}

const STATUS_VARIANT: Record<
  JobRecord["status"],
  "default" | "outline" | "secondary" | "destructive"
> = {
  pending: "outline",
  running: "secondary",
  done: "default",
  failed: "destructive",
};

export function JobsTable({ jobs, loading }: Props) {
  const retry = useRetryJob();
  const cancel = useCancelJob();

  const handleRetry = async (id: string) => {
    try {
      await retry.mutateAsync(id);
      toast.success("已加入重试");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "重试失败");
    }
  };

  const handleCancel = async (id: string) => {
    try {
      await cancel.mutateAsync(id);
      toast.success("已取消");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "取消失败");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">后台任务</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-muted-foreground">加载中...</p>
        ) : jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground">无任务。</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>类型</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>尝试</TableHead>
                <TableHead>调度</TableHead>
                <TableHead>错误</TableHead>
                <TableHead className="w-[140px] text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => (
                <TableRow key={job.id}>
                  <TableCell className="font-mono text-xs">{job.job_type}</TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANT[job.status]}>{job.status}</Badge>
                  </TableCell>
                  <TableCell>{job.attempts}/{job.max_attempts}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatRelative(job.scheduled_at)}
                  </TableCell>
                  <TableCell className="max-w-[280px] truncate text-xs text-destructive">
                    {job.error ?? "—"}
                  </TableCell>
                  <TableCell className="text-right space-x-2">
                    {job.status === "failed" && (
                      <Button size="sm" variant="outline" onClick={() => handleRetry(job.id)}>
                        重试
                      </Button>
                    )}
                    {(job.status === "pending" || job.status === "running") && (
                      <Button size="sm" variant="ghost" onClick={() => handleCancel(job.id)}>
                        取消
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: SyncStatusCard**

Create `web/src/components/SyncStatusCard.tsx`:

```tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatRelative } from "@/lib/format";
import type { SyncStatusItem } from "@/types";

interface Props {
  items: SyncStatusItem[];
}

export function SyncStatusCard({ items }: Props) {
  const byProvider = items.reduce<Record<string, SyncStatusItem[]>>((acc, item) => {
    acc[item.provider] = acc[item.provider] ?? [];
    acc[item.provider].push(item);
    return acc;
  }, {});

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {Object.entries(byProvider).map(([provider, providerItems]) => {
        const latest = providerItems.reduce<SyncStatusItem | null>((acc, item) => {
          if (!item.last_synced_at) return acc;
          if (!acc?.last_synced_at) return item;
          return new Date(item.last_synced_at) > new Date(acc.last_synced_at) ? item : acc;
        }, null);
        return (
          <Card key={provider}>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">{provider}</CardTitle>
              <Badge variant="outline">{providerItems.length} threads</Badge>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">最近同步</span>
                <span>{formatRelative(latest?.last_synced_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">最大 seq</span>
                <span className="font-mono text-xs">
                  {latest?.last_synced_seq ?? "—"}
                </span>
              </div>
            </CardContent>
          </Card>
        );
      })}
      {items.length === 0 && (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            尚无同步记录，先在本地运行 `mem thread sync`。
          </CardContent>
        </Card>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web/src/components/JobsTable.tsx web/src/components/SyncStatusCard.tsx
git commit -m "feat(web): add JobsTable and SyncStatusCard components"
```

---

## Chunk 7: 页面整合

### Task 21: MemoriesPage 与 MemoryDetailPage / MemoryNewPage

**Files:**
- Create: `web/src/pages/MemoriesPage.tsx`
- Create: `web/src/pages/MemoryDetailPage.tsx`
- Create: `web/src/pages/MemoryNewPage.tsx`

- [ ] **Step 1: MemoriesPage**

Create `web/src/pages/MemoriesPage.tsx`:

```tsx
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MemoryList } from "@/components/MemoryList";
import { MemoryMergeDialog } from "@/components/MemoryMergeDialog";
import { useMemories, useBulkDelete, useMergeMemories } from "@/api/memories";
import type { MemoryNode, ReviewStatus } from "@/types";

const REVIEW_OPTIONS: Array<ReviewStatus | "all"> = [
  "all",
  "auto",
  "reviewed",
  "confirmed",
  "challenged",
  "legacy",
  "archived",
];

export default function MemoriesPage() {
  const [query, setQuery] = useState("");
  const [entityType, setEntityType] = useState<string>("all");
  const [reviewStatus, setReviewStatus] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeCandidates, setMergeCandidates] = useState<MemoryNode[]>([]);

  const params = useMemo(
    () => ({
      page,
      size: 50,
      q: query || undefined,
      entity_type: entityType !== "all" ? entityType : undefined,
      review_status: reviewStatus !== "all" ? (reviewStatus as ReviewStatus) : undefined,
    }),
    [page, query, entityType, reviewStatus],
  );

  const memoriesQuery = useMemories(params);
  const bulkDelete = useBulkDelete();
  const merge = useMergeMemories();

  const items = memoriesQuery.data?.items ?? [];

  const handleBulkDelete = async (ids: string[]) => {
    if (!confirm(`确认删除 ${ids.length} 项？`)) return;
    try {
      await bulkDelete.mutateAsync(ids);
      toast.success(`已删除 ${ids.length} 项`);
      setSelectedIds(new Set());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    }
  };

  const handleMergeRequest = (ids: string[]) => {
    setMergeCandidates(items.filter((it) => ids.includes(it.id)));
    setMergeOpen(true);
  };

  const handleMergeConfirm = async (payload: { targetId: string; sourceIds: string[] }) => {
    try {
      await merge.mutateAsync({
        sourceIds: payload.sourceIds,
        targetId: payload.targetId,
      });
      toast.success("合并成功");
      setMergeOpen(false);
      setSelectedIds(new Set());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "合并失败");
    }
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Memories</h1>
        <Button asChild>
          <Link to="/memories/new">
            <Plus className="size-4 mr-1" /> 新建
          </Link>
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_180px_180px] gap-3">
        <Input
          placeholder="搜索内容或 entity_key"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
        />
        <Select value={entityType} onValueChange={(v) => { setEntityType(v); setPage(1); }}>
          <SelectTrigger><SelectValue placeholder="entity_type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部类型</SelectItem>
            {["person", "preference", "fact", "event", "goal", "project"].map((t) => (
              <SelectItem key={t} value={t}>{t}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={reviewStatus} onValueChange={(v) => { setReviewStatus(v); setPage(1); }}>
          <SelectTrigger><SelectValue placeholder="review_status" /></SelectTrigger>
          <SelectContent>
            {REVIEW_OPTIONS.map((opt) => (
              <SelectItem key={opt} value={opt}>{opt === "all" ? "全部状态" : opt}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <MemoryList
        items={items}
        loading={memoriesQuery.isLoading}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
        onBulkDelete={handleBulkDelete}
        onMergeRequest={handleMergeRequest}
      />

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          共 {memoriesQuery.data?.total ?? 0} 条
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            上一页
          </Button>
          <span>第 {page} 页</span>
          <Button
            variant="outline"
            size="sm"
            disabled={items.length < 50}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页
          </Button>
        </div>
      </div>

      <MemoryMergeDialog
        open={mergeOpen}
        onOpenChange={setMergeOpen}
        candidates={mergeCandidates}
        submitting={merge.isPending}
        onConfirm={handleMergeConfirm}
      />
    </div>
  );
}
```

- [ ] **Step 2: MemoryDetailPage**

Create `web/src/pages/MemoryDetailPage.tsx`:

```tsx
import { useNavigate, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMemory } from "@/api/memories";
import { MemoryDetail } from "@/components/MemoryDetail";

export default function MemoryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useMemory(id);

  return (
    <div className="p-6 space-y-4">
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
        <ChevronLeft className="size-4 mr-1" /> 返回
      </Button>
      {isLoading && <Skeleton className="h-96 w-full" />}
      {isError && (
        <p className="text-sm text-destructive">
          加载失败：{error instanceof Error ? error.message : "未知错误"}
        </p>
      )}
      {data && <MemoryDetail memory={data} />}
    </div>
  );
}
```

- [ ] **Step 3: MemoryNewPage**

Create `web/src/pages/MemoryNewPage.tsx`:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateMemory } from "@/api/memories";

const ENTITY_TYPES = ["person", "preference", "fact", "event", "goal", "project"];

export default function MemoryNewPage() {
  const navigate = useNavigate();
  const create = useCreateMemory();

  const [entityKey, setEntityKey] = useState("");
  const [entityType, setEntityType] = useState("fact");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tagsInput, setTagsInput] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!entityKey || !content) {
      toast.error("entity_key 与 content 必填");
      return;
    }
    try {
      const created = await create.mutateAsync({
        entity_key: entityKey,
        entity_type: entityType,
        content,
        title: title.trim() || null,
        tags: tagsInput
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
      toast.success("已创建");
      navigate(`/memories/${created.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "创建失败");
    }
  };

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <Card>
        <CardHeader>
          <CardTitle>新建记忆</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="grid grid-cols-[1fr_180px] gap-3">
              <div>
                <label className="text-xs text-muted-foreground">entity_key</label>
                <Input
                  placeholder="preference:editor"
                  value={entityKey}
                  onChange={(e) => setEntityKey(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">entity_type</label>
                <Select value={entityType} onValueChange={setEntityType}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ENTITY_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>{t}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">title (可选)</label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">content</label>
              <Textarea rows={6} value={content} onChange={(e) => setContent(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">tags (逗号分隔)</label>
              <Input value={tagsInput} onChange={(e) => setTagsInput(e.target.value)} />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => navigate(-1)}>取消</Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "创建中..." : "创建"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/MemoriesPage.tsx web/src/pages/MemoryDetailPage.tsx web/src/pages/MemoryNewPage.tsx
git commit -m "feat(web): add Memories list / detail / new pages"
```

### Task 22: ThreadsPage 与 ThreadDetailPage

**Files:**
- Create: `web/src/pages/ThreadsPage.tsx`
- Create: `web/src/pages/ThreadDetailPage.tsx`

- [ ] **Step 1: ThreadsPage**

Create `web/src/pages/ThreadsPage.tsx`:

```tsx
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useThreads } from "@/api/threads";
import { formatDateTime, formatRelative } from "@/lib/format";

const PROVIDERS = ["all", "claude-code", "codex", "chatwise", "manual"];

export default function ThreadsPage() {
  const [provider, setProvider] = useState("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const params = useMemo(
    () => ({
      page,
      size: 30,
      provider: provider === "all" ? undefined : provider,
      q: query || undefined,
    }),
    [page, provider, query],
  );

  const threadsQuery = useThreads(params);
  const items = threadsQuery.data?.items ?? [];

  return (
    <div className="p-6 space-y-5">
      <h1 className="text-xl font-semibold">Threads</h1>
      <div className="grid grid-cols-[1fr_200px] gap-3">
        <Input
          placeholder="按内容 / 标题搜索 (FTS5)"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
        />
        <Select value={provider} onValueChange={(v) => { setProvider(v); setPage(1); }}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            {PROVIDERS.map((p) => (
              <SelectItem key={p} value={p}>{p === "all" ? "全部 provider" : p}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {threadsQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, idx) => (
            <Skeleton key={idx} className="h-20 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card><CardContent className="p-8 text-sm text-muted-foreground text-center">暂无线程。</CardContent></Card>
      ) : (
        <ul className="space-y-2">
          {items.map((thread) => (
            <li key={thread.thread_id}>
              <Link
                to={`/threads/${thread.thread_id}`}
                className="block rounded-md border border-border bg-card p-4 hover:bg-muted/40 transition-colors"
              >
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline">{thread.source_provider}</Badge>
                  <span className="font-mono">{thread.thread_id}</span>
                  <span>{formatDateTime(thread.started_at)}</span>
                  <span>· {thread.message_count} 条消息</span>
                </div>
                <p className="mt-1 text-sm font-medium">{thread.title ?? "(未命名)"}</p>
                {thread.summary && (
                  <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{thread.summary}</p>
                )}
                <p className="mt-1 text-[10px] text-muted-foreground">
                  结束 {formatRelative(thread.ended_at)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <div className="flex justify-between items-center text-sm text-muted-foreground">
        <span>共 {threadsQuery.data?.total ?? 0} 条</span>
        <div className="flex gap-2 items-center">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
            上一页
          </Button>
          <span>第 {page} 页</span>
          <Button variant="outline" size="sm" disabled={items.length < 30} onClick={() => setPage(p => p + 1)}>
            下一页
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: ThreadDetailPage**

Create `web/src/pages/ThreadDetailPage.tsx`:

```tsx
import { useNavigate, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useThread, useThreadMessages } from "@/api/threads";
import { ThreadMessages } from "@/components/ThreadMessages";
import { formatDateTime } from "@/lib/format";

export default function ThreadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const thread = useThread(id);
  const messages = useThreadMessages(id);

  return (
    <div className="p-6 space-y-4">
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
        <ChevronLeft className="size-4 mr-1" /> 返回
      </Button>

      {thread.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : thread.data ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <span>{thread.data.title ?? "(未命名线程)"}</span>
              <Badge variant="outline">{thread.data.source_provider}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-1">
            <div>线程 ID：<span className="font-mono">{thread.data.thread_id}</span></div>
            <div>开始：{formatDateTime(thread.data.started_at)}</div>
            <div>结束：{formatDateTime(thread.data.ended_at)}</div>
            <div>消息数：{thread.data.message_count}</div>
            {thread.data.summary && <div>摘要：{thread.data.summary}</div>}
          </CardContent>
        </Card>
      ) : null}

      {messages.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <ThreadMessages messages={messages.data?.items ?? []} />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/ThreadsPage.tsx web/src/pages/ThreadDetailPage.tsx
git commit -m "feat(web): add Threads list and detail pages"
```

### Task 23: GraphPage / JobsPage / SourcesPage / SettingsPage

**Files:**
- Create: `web/src/pages/GraphPage.tsx`
- Create: `web/src/pages/JobsPage.tsx`
- Create: `web/src/pages/SourcesPage.tsx`
- Create: `web/src/pages/SettingsPage.tsx`

- [ ] **Step 1: GraphPage**

Create `web/src/pages/GraphPage.tsx`:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { GraphView } from "@/components/GraphView";
import { useGraph } from "@/api/graph";
import type { GraphNode } from "@/types";

export default function GraphPage() {
  const [entityKey, setEntityKey] = useState("");
  const [depth] = useState(2);
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useGraph({
    entity_key: entityKey || undefined,
    depth,
  });

  const handleSelect = (node: GraphNode) => {
    // Try to find a memory id from node — fall back to entity-keyed page
    if (node.id.startsWith("m-") || /^[0-9a-fA-F-]{8,}$/.test(node.id)) {
      navigate(`/memories/${node.id}`);
      return;
    }
    navigate(`/memories?entity_type=${encodeURIComponent(node.entity_type)}`);
  };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-semibold">Knowledge Graph</h1>
      <Input
        placeholder="按 entity_key 聚焦子图（留空查看全图）"
        value={entityKey}
        onChange={(e) => setEntityKey(e.target.value)}
      />
      {isLoading ? (
        <Skeleton className="h-[80vh] w-full" />
      ) : isError ? (
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            加载失败：{error instanceof Error ? error.message : "未知错误"}
          </CardContent>
        </Card>
      ) : (
        <GraphView
          nodes={data?.nodes ?? []}
          edges={data?.edges ?? []}
          onSelect={handleSelect}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: JobsPage**

Create `web/src/pages/JobsPage.tsx`:

```tsx
import { useState } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { JobsTable } from "@/components/JobsTable";
import { useJobs } from "@/api/jobs";

const STATUSES = ["all", "pending", "running", "done", "failed"];

export default function JobsPage() {
  const [status, setStatus] = useState("all");
  const { data, isLoading } = useJobs({
    status: status === "all" ? undefined : status,
    page: 1,
    size: 100,
  });

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-xl font-semibold">Background Jobs</h1>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-[160px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>{s === "all" ? "全部状态" : s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <JobsTable jobs={data?.items ?? []} loading={isLoading} />
    </div>
  );
}
```

- [ ] **Step 3: SourcesPage（占位）**

Create `web/src/pages/SourcesPage.tsx`:

```tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SourcesPage() {
  return (
    <div className="p-6">
      <Card>
        <CardHeader>
          <CardTitle>Library / Sources</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p>文档导入（MD / PDF / Web chunk）在 Phase 2 开放。</p>
          <p>Coming in Phase 2.</p>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: SettingsPage**

Create `web/src/pages/SettingsPage.tsx`:

```tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthMe, useLogout } from "@/api/auth";
import { useSyncStatus } from "@/api/sync";
import { SyncStatusCard } from "@/components/SyncStatusCard";

export default function SettingsPage() {
  const me = useAuthMe();
  const logout = useLogout();
  const sync = useSyncStatus();

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">会话</CardTitle>
          {me.isLoading ? (
            <Skeleton className="h-5 w-24" />
          ) : (
            <Badge variant={me.data?.authenticated ? "default" : "outline"}>
              {me.data?.authenticated ? "已登录" : "未登录"}
            </Badge>
          )}
        </CardHeader>
        <CardContent>
          <Button
            variant="destructive"
            onClick={() => logout.mutateAsync()}
            disabled={logout.isPending}
          >
            {logout.isPending ? "登出中..." : "登出"}
          </Button>
        </CardContent>
      </Card>

      <section className="space-y-3">
        <h2 className="text-base font-semibold">同步状态</h2>
        {sync.isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <SyncStatusCard items={sync.data?.items ?? []} />
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 5: 现在所有页面就位，验证 type-check 与 vitest**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm lint && pnpm test
```
Expected: 都 PASS。

- [ ] **Step 6: Commit**

```bash
git add web/src/pages/GraphPage.tsx web/src/pages/JobsPage.tsx \
        web/src/pages/SourcesPage.tsx web/src/pages/SettingsPage.tsx
git commit -m "feat(web): add Graph / Jobs / Sources / Settings pages"
```

---

## Chunk 8: 构建、部署与文档

### Task 24: 多阶段 Dockerfile 与 compose

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.dockerignore`

- [ ] **Step 1: 重写 Dockerfile 为多阶段**

Replace `Dockerfile` content with:

```dockerfile
# syntax=docker/dockerfile:1.7

# ---------- Stage 1: build Web UI ----------
FROM node:22-alpine AS web-builder
WORKDIR /web

# Enable corepack pinned pnpm version
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

# Install deps first for layer caching
COPY web/package.json web/pnpm-lock.yaml web/.npmrc ./
RUN pnpm install --frozen-lockfile

# Build
COPY web/ ./
RUN pnpm build

# ---------- Stage 2: Python runtime ----------
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_DIST_DIR=/app/web/dist

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install locked Python deps
COPY requirements.lock pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src/ src/
RUN pip install --no-cache-dir --no-deps .

# Copy web dist from builder
COPY --from=web-builder /web/dist /app/web/dist

# Data dirs
RUN mkdir -p /app/data/vectors /app/data/graph

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -fsS http://localhost:8765/health || exit 1

CMD ["python", "-m", "memory_mcp"]
```

- [ ] **Step 2: 更新 docker-compose.yml 注入 session secret**

Edit `docker-compose.yml` — 在 `memory-mcp.environment` 列表追加：

```yaml
      - MEMORY_MCP_SESSION_SECRET=${MEMORY_MCP_SESSION_SECRET}
      - WEB_DIST_DIR=/app/web/dist
```

如果 `.env` 文件不被注入到容器，需要在 service 顶部加：

```yaml
    env_file:
      - .env
```

确保不要把 `.env` 内容写入仓库；只在本地 / 部署机存在。

- [ ] **Step 3: 调整 `.dockerignore`**

Edit `.dockerignore`（如不存在则新建）— 确保包含：

```
.git
__pycache__
*.pyc
.pytest_cache
.venv
data/
.env
.env.*
!.env.example
web/node_modules
web/dist
web/.vite
web/coverage
```

注意：`web/dist` 被忽略，因为多阶段 build 内部产出，不需要从宿主复制。

- [ ] **Step 4: 本地构建验证**

```bash
cd /Users/kassol/Workspace/memory-mcp && docker build -t memory-mcp:m5-local .
```
Expected: 构建无 error，最终镜像内 `/app/web/dist/index.html` 存在。

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "build: multi-stage Dockerfile bundling Web UI dist into runtime"
```

### Task 25: web/AGENTS.md 与根 AGENTS.md 更新

**Files:**
- Create: `web/AGENTS.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: 创建子目录 AGENTS.md**

Create `web/AGENTS.md`:

```markdown
# Web UI (memory-mcp-web)

## 职责
治理台 SPA。提供记忆 CRUD、合并、线程浏览、知识图谱、后台任务监控、设置中心。
与后端 FastAPI 同源部署，通过 cookie session 鉴权。

## 目录结构
- `src/main.tsx` 应用入口（QueryClient + Router）
- `src/App.tsx` 路由表
- `src/pages/` 路由 entry，按页面拆分
- `src/components/` 业务组件（含 `ui/` 下 shadcn 原子）
- `src/api/` TanStack Query hooks
- `src/lib/` 通用工具（api-client / format / utils）
- `src/stores/` zustand store
- `src/types/` API DTO 类型
- `src/styles/globals.css` Tailwind v4 主题
- `src/test/setup.ts` vitest 初始化
- `dist/` 构建产物（不入仓）

## 模块规范
- 包管理器：pnpm，禁用 npm / yarn
- 严格 TS 6（`strict` + `noUnusedLocals` + `noUnusedParameters`）
- shadcn 组件复制到 `src/components/ui/`，按需新增用 `pnpm dlx shadcn@latest add <name>`
- Tailwind v4 用 CSS-based `@theme`，不存在 `tailwind.config.js`
- 状态管理：服务器状态 → TanStack Query；UI 状态 → zustand；不混用
- 鉴权：浏览器走 cookie session（fetch 自动带 cookie），api-client 在 401 时跳 `/login`
- 测试：核心组件 + api-client 有 vitest 单测

## 依赖关系
- 调用后端 `/api/v1/*`
- 不直接读写 `localStorage`，统一走 `src/lib/storage.ts`

## 常用命令
- `pnpm dev` 启动 dev server，proxy `/api` `/mcp` `/health` 到 `http://localhost:8765`
- `pnpm build` 产出 `dist/`
- `pnpm test` 运行 vitest
- `pnpm lint` 仅类型检查

## 变更日志
### 2026-05-21 M5 初始化
- 从零搭建 React 19 + TS 6 + Vite 8 + Tailwind v4 + shadcn 治理台
- 完成 Memories / Threads / Graph / Jobs / Sources / Settings 全部页面
- cookie session 登录闭环；api-client 401 自动跳登录
```

- [ ] **Step 2: 更新根 AGENTS.md**

Edit `AGENTS.md` — 在「目录索引」追加：

```markdown
- `web/` - Web UI 治理台（React 19 SPA，pnpm 包）
```

在「变更日志」顶部追加：

```markdown
### 2026-05-21 M5 Web UI 治理台
- 新增 `web/` 子目录：React 19 / TS 6 / Vite 8 / Tailwind v4 / shadcn / @xyflow/react SPA
- 新增 cookie session 鉴权（`mem_session` HttpOnly/Secure/SameSite=Strict），`AuthMiddleware` 同时接受 Bearer 与 cookie
- 服务端 SPA fallback：未命中 `/mcp` `/api/v1` `/health` 的请求由 `WEB_DIST_DIR` 下的 `index.html` 接管
- 治理台覆盖：Memories CRUD/批量合并/批量删除、Threads 浏览、Graph、Jobs、Sources 占位、Settings 同步状态
- 多阶段 Dockerfile：`node:22-alpine` 构建 Web → `python:3.12-slim` 注入 `WEB_DIST_DIR`
```

- [ ] **Step 3: Commit**

```bash
git add web/AGENTS.md AGENTS.md
git commit -m "docs: add web AGENTS.md and update root changelog for M5"
```

### Task 26: 全量回归与人工 smoke

- [ ] **Step 1: 后端全量测试**

```bash
cd /Users/kassol/Workspace/memory-mcp && pytest -v
```
Expected: 全部 PASS。

- [ ] **Step 2: 前端类型 + 单测**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm lint && pnpm test
```
Expected: PASS。

- [ ] **Step 3: 前端 build 验证**

```bash
cd /Users/kassol/Workspace/memory-mcp/web && pnpm build
```
Expected: 生成 `web/dist/index.html` 与 `web/dist/assets/*`。

- [ ] **Step 4: 本地联调**

终端 A：
```bash
cd /Users/kassol/Workspace/memory-mcp
export MEMORY_MCP_AUTH_TOKEN=test-token
export MEMORY_MCP_SESSION_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
python -m memory_mcp
```

终端 B：
```bash
cd /Users/kassol/Workspace/memory-mcp/web
VITE_API_TARGET=http://localhost:8765 pnpm dev
```

浏览器打开 `http://localhost:5173/login`：

- [ ] 输入 `test-token` 登录 → 跳 `/memories`
- [ ] 列表能渲染（即便为空也无报错）
- [ ] 点 "新建" → 创建一条 memory → 列表出现
- [ ] 点击进入详情 → 编辑 → 保存 → toast 成功
- [ ] 多选两条 → 合并对话框 → 选目标 → 确认
- [ ] 删除单条 / 批量删除
- [ ] `/threads` 列表能加载（如果后端有数据）
- [ ] `/graph` 渲染节点（若无数据展示空状态即可）
- [ ] `/jobs` 渲染并每 5 秒刷新
- [ ] `/settings` 显示 sync 状态卡片
- [ ] 点 "登出" → 回 `/login`
- [ ] 浏览器直接访问 `/memories/abc` 非法 ID → 显示 "加载失败"

- [ ] **Step 5: 容器化 smoke**

```bash
cd /Users/kassol/Workspace/memory-mcp
docker build -t memory-mcp:m5-local .
docker run --rm \
  -e MEMORY_MCP_AUTH_TOKEN=test-token \
  -e MEMORY_MCP_SESSION_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))") \
  -e MEMORY_MCP_OPENROUTER_API_KEY=dummy \
  -p 8765:8765 \
  memory-mcp:m5-local
```

另一个终端：
```bash
curl -fsS http://localhost:8765/health | jq
curl -fsS http://localhost:8765/ | head -5    # 应返回 index.html
```

浏览器打开 `http://localhost:8765/login` 走一次登录 → memories 流程，确认 SPA + API 同源 cookie 工作。

- [ ] **Step 6: Commit smoke 记录**

```bash
git status
# 如果有 dist 之类的产物被改，确认 .gitignore 覆盖
git log --oneline -20
```

不需要额外 commit；smoke 通过即代表 M5 完成。

---

## 附录：常见问题排查

### shadcn CLI 失败
- 检查 `web/components.json` 是否合法
- 手动到 https://ui.shadcn.com/docs/components/<name> 复制源码到 `web/src/components/ui/<name>.tsx`

### Tailwind v4 样式不生效
- 确认 `globals.css` 顶部有 `@import "tailwindcss";`
- `vite.config.ts` 的 `plugins` 包含 `tailwindcss()`（来自 `@tailwindcss/vite`）
- 不需要 `tailwind.config.js`，主题写在 `@theme {}` 内

### `pnpm dev` cookie 不带上 API
- Vite proxy 默认 `changeOrigin: true`，Set-Cookie 的 Domain 会用后端域名；本地 `http://localhost` 应自动同源
- 浏览器 DevTools Network 中确认请求带了 `mem_session`
- 后端响应的 `Set-Cookie` 不含 Secure 时，浏览器不会保存到 HTTPS-only context；如果在 HTTP localhost 调试，可把 `_set_session_cookie` 临时改 `secure=False`（**生产必须 True**）

### `/api/v1/memories` 返回 HTML 不是 JSON
- SPA fallback 路由顺序错了。检查 `server.py` 中 `*_build_spa_routes()` 必须在 `*api_routes` **之后**
- `_is_public` 必须把 `/api/v1/` 与 `/mcp` 留给鉴权，不允许放进静态白名单

### `@xyflow/react` peer dependency 报错
- 确认 React 是 19.x；若版本不一致用 `pnpm why react`
- xyflow 12.10 要求 `@types/react@>=18`；TS 6 + React 19 类型可能需要 `--strict-peer-dependencies=false`，可在 `.npmrc` 加 `strict-peer-dependencies=false`

### 测试中 `dagre is not defined`
- 测试默认 mock 了 `@xyflow/react`，dagre 不会被加载；如果新增其它图组件用了 dagre，需要在测试里 stub

---

## 修复记录

> 2026-05-21 plan 修复（codex 评审 + Sir 新约束）：
>
> - **MutationType 枚举对齐**：`web/src/types/index.ts` MutationType 改为 M1 权威值 `initial/update/refinement/correction/reversal/evolution`（之前 M5 自创 `created/evolved/...` 与后端不一致，会让 EvolutionTimeline label 全部 fall back 为 raw 字符串）；`MUTATION_LABEL` 中文映射同步更新；4 处测试 fixture 的 `mutation_type: "created"` → `"initial"`。
> - **新 Task 2.5（CORS 收紧）**：写死 `Allow-Origin: *` + cookie session 在浏览器里是非法组合。新 middleware 走 allow-list（`MEMORY_MCP_ALLOWED_ORIGINS` env），同源回写 + `Allow-Credentials: true`；未知 Origin 不回 ACAO，由浏览器拒绝。
> - **Task 7 Step 1b（shadcn 离线 fallback）**：补完整 fallback 脚本（`curl` 拉 pinned `v4.7.0` tag 的 14 个组件 + 跑 `tsc --noEmit` 校验），替代「网络不可用时手动复制」的模糊指引。
> - **Sir 新约束（Playwright → agent-browser）**：M5 plan 本身不含 Playwright（已确认），自动化 e2e 由 spec §10/§12 改为 agent-browser；本 plan 无需改动，但 §10/§12 已在 spec 修复（见 spec 修复记录）。
> - **契约一致性确认**：M5 已使用 `items` 分页 DTO、`/api/v1/memories/${id}` 直接 by-id 路径、`extracted_memory_ids` 字段——与 M2/M3 修复后的契约对齐，无需改动。
