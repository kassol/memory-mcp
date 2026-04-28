import json
import logging
from urllib.parse import urlparse, unquote

from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import (
    Resource,
    ResourceTemplate,
    TextContent,
    ImageContent,
    EmbeddedResource,
    Tool,
)
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.middleware import Middleware

from .api.routes import routes as api_routes
from .config import settings
from .storage.graph import graph_store
from .storage.vector import vector_store
from .tools import remember, recall, trace, forget, relate, graph_query, recall_all
from .transport.auth import AuthMiddleware
from .transport.cors import CorsMiddleware
from .transport.streamable_http import StreamableHttpApp

# Setup Logging
logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger("memory-mcp")

# Initialize MCP Server
mcp_server = Server("memory-mcp")

# Register Tools
@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="remember",
            description="Store a new memory. The system automatically handles evolution and conflict detection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The content to remember"},
                    "entity_key": {"type": "string", "description": "Unique key for the entity (e.g., preference:editor)"},
                    "entity_type": {
                        "type": "string",
                        "enum": ["person", "preference", "fact", "event", "goal", "project"],
                        "description": "Entity type",
                    },
                    "tags": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["content", "entity_key", "entity_type"]
            }
        ),
        Tool(
            name="recall",
            description="Search for memories by semantic similarity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "entity_type": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                    "include_evolution": {"type": "boolean", "default": False}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="recall_all",
            description="Fetch all current memories for context loading.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_type": {"type": "string"},
                    "limit": {"type": "integer", "default": 100}
                }
            }
        ),
        Tool(
            name="trace",
            description="Trace the evolution history of a specific entity's memory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_key": {"type": "string"},
                    "format": {"type": "string", "enum": ["timeline", "summary"], "default": "timeline"}
                },
                "required": ["entity_key"]
            }
        ),
        Tool(
            name="forget",
            description="Archive a memory so it's no longer current.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_key": {"type": "string"},
                    "reason": {"type": "string"}
                },
                "required": ["entity_key"]
            }
        ),
        Tool(
            name="relate",
            description="Create a relationship between two entities.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_entity_key": {"type": "string"},
                    "to_entity_key": {"type": "string"},
                    "relation_type": {"type": "string"},
                    "properties": {"type": "object"}
                },
                "required": ["from_entity_key", "to_entity_key", "relation_type"]
            }
        ),
        Tool(
            name="graph_query",
            description="Query relations for an entity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_key": {"type": "string"},
                    "relation_types": {"type": "array", "items": {"type": "string"}},
                    "depth": {"type": "integer", "default": 1}
                },
                "required": ["entity_key"]
            }
        )
    ]

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent | EmbeddedResource]:
    try:
        result = {}
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
        elif name == "graph_query":
            result = await graph_query.graph_query_tool(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]

@mcp_server.list_resources()
async def list_resources() -> list[Resource]:
    return [
        Resource(
            name="current-memories",
            title="Current Memories",
            uri="memory:///current",
            description="All current active memories",
            mimeType="application/json",
        ),
        Resource(
            name="entities",
            title="Entities",
            uri="memory:///entities",
            description="Entity metadata list",
            mimeType="application/json",
        ),
    ]

@mcp_server.list_resource_templates()
async def list_resource_templates() -> list[ResourceTemplate]:
    return [
        ResourceTemplate(
            name="entity-memory",
            title="Entity Memory",
            uriTemplate="memory:///entity/{entity_key}",
            description="Evolution chain and current memory for an entity",
            mimeType="application/json",
        )
    ]

def _parse_memory_uri(uri: str) -> str:
    parsed = urlparse(str(uri))
    path = parsed.path or ""
    if parsed.netloc:
        path = f"/{parsed.netloc}{path}"
    return unquote(path)

@mcp_server.read_resource()
async def read_resource(uri: str) -> list[ReadResourceContents]:
    path = _parse_memory_uri(uri)
    if path == "/current":
        memories = await vector_store.list_current(limit=100)
        payload = [
            {
                "entity_key": node.entity_key,
                "entity_type": node.entity_type,
                "content": node.content,
                "created_at": node.created_at.isoformat(),
                "last_mutation": node.mutation_type.value,
            }
            for node in memories
        ]
        return [ReadResourceContents(content=json.dumps(payload, ensure_ascii=False), mime_type="application/json")]
    if path == "/entities":
        entities = await graph_store.list_entities()
        return [ReadResourceContents(content=json.dumps(entities, ensure_ascii=False), mime_type="application/json")]
    if path.startswith("/entity/"):
        entity_key = path.removeprefix("/entity/")
        history = await vector_store.get_history(entity_key)
        payload = [
            {
                "id": node.id,
                "entity_key": node.entity_key,
                "entity_type": node.entity_type,
                "content": node.content,
                "mutation_type": node.mutation_type.value,
                "mutation_reason": node.mutation_reason,
                "created_at": node.created_at.isoformat(),
                "is_current": node.is_current,
            }
            for node in history
        ]
        return [ReadResourceContents(content=json.dumps(payload, ensure_ascii=False), mime_type="application/json")]
    return [
        ReadResourceContents(
            content=json.dumps({"error": "Resource not found"}, ensure_ascii=False),
            mime_type="application/json",
        )
    ]

async def health(request: Request):
    return JSONResponse({"status": "healthy", "vector_backend": vector_store.backend_name})

streamable_http_app = StreamableHttpApp(mcp_server, json_response=False)

app = Starlette(
    lifespan=streamable_http_app.lifespan,
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
