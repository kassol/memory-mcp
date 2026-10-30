import json
import logging
from contextlib import asynccontextmanager

import jsonschema
from mcp.server import Server, ServerRequestContext
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)
from starlette.applications import Starlette
from pathlib import Path

from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.middleware import Middleware

from .api.routes import routes as api_routes
from .config import settings
from .storage.migrate import current as alembic_current, run_migrations
from .storage.vector import vector_store
from .engine import maintenance
from .tools import remember, recall, trace, forget
from .transport.auth import AuthMiddleware
from .transport.cors import CorsMiddleware
from .transport.streamable_http import StreamableHttpApp

# Setup Logging
logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger("memory-mcp")

async def list_tools(ctx: ServerRequestContext, params: PaginatedRequestParams | None) -> ListToolsResult:
    return ListToolsResult(tools=[
        Tool(
            name="remember",
            description=(
                "Store one long-lived fact: a preference, decision, conclusion, root cause, or project convention. "
                "One fact per call; skip transient task state. The server picks the entity key and merges the fact "
                "into an existing memory on the same subject, so updates replace outdated versions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact, self-contained and specific"},
                    "title": {"type": "string", "description": "Optional short title"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["content"],
                "additionalProperties": False,
            }
        ),
        Tool(
            name="recall",
            description=(
                "Search current memories by meaning and by exact words (names, versions, numbers). Use it when you "
                "start a task and before you make a decision, to reuse known preferences, decisions and past "
                "conclusions. Results are ordered by relevance; a larger relevance means a better match within the "
                "same result list only, so do not compare it across calls."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What you need to know"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
                "additionalProperties": False,
            }
        ),
        Tool(
            name="forget",
            description=(
                "Archive one current memory that is wrong or no longer valid. "
                "Get memory_id from recall. To change a fact, call remember with the new fact instead."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "reason": {"type": "string", "description": "Why the memory is wrong or obsolete"},
                },
                "required": ["memory_id"],
                "additionalProperties": False,
            }
        ),
        Tool(
            name="trace",
            description=(
                "Show the version history of one memory subject (entity_key from recall). "
                "Use it when asked when or why a memory changed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_key": {"type": "string"},
                    "format": {"type": "string", "enum": ["timeline", "summary"], "default": "timeline"},
                },
                "required": ["entity_key"],
                "additionalProperties": False,
            }
        ),
    ])


def _text_result(payload: dict) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))])


async def call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    name = params.name
    arguments = params.arguments or {}
    # mcp 2.0 dropped the lowlevel jsonschema input check; keep the 1.x error shape for clients.
    tool = next((t for t in (await list_tools(ctx, None)).tools if t.name == name), None)
    if tool is not None:
        try:
            jsonschema.validate(instance=arguments, schema=tool.input_schema)
        except jsonschema.ValidationError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Input validation error: {e.message}")],
                is_error=True,
            )
    try:
        result = {}
        if name == "remember":
            result = await remember.remember_tool(arguments)
        elif name == "recall":
            result = await recall.recall_tool(arguments)
        elif name == "trace":
            result = await trace.trace_tool(arguments)
        elif name == "forget":
            result = await forget.forget_tool(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return _text_result(result)
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return _text_result({"error": str(e)})

mcp_server = Server(
    "memory-mcp",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)

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
        try:
            yield
        finally:
            await maintenance.stop()


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/mcp", endpoint=streamable_http_app, methods=["GET", "POST", "DELETE"]),
        Route("/health", endpoint=health, methods=["GET"]),
        *api_routes,
        # Located next to this module so it resolves inside a non-editable install too.
        Mount("/ui", app=StaticFiles(directory=Path(__file__).parent / "ui", html=True), name="ui"),
    ],
    middleware=[
        Middleware(CorsMiddleware),
        Middleware(AuthMiddleware),
    ]
)
