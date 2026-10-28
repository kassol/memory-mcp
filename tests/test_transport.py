import importlib
import json

import anyio
from mcp import Client


def test_starlette_lifespan_accepts_app_arg(test_env):
    async def run():
        import memory_mcp.server as server

        importlib.reload(server)

        async with server.app.router.lifespan_context(server.app):
            pass

    anyio.run(run)


def test_mcp_exposes_and_calls_unrelate(test_env):
    async def run():
        import memory_mcp.server as server

        importlib.reload(server)

        async with Client(server.mcp_server) as client:
            tools = (await client.list_tools()).tools
            assert any(tool.name == "unrelate" for tool in tools)

            relate_result = await client.call_tool(
                "relate",
                {
                    "from_entity_key": "person:alice",
                    "to_entity_key": "project:x",
                    "relation_type": "WORKS_ON",
                },
            )
            relation_id = json.loads(relate_result.content[0].text)["relation_id"]

            unrelate_result = await client.call_tool("unrelate", {"relation_id": relation_id})
            payload = json.loads(unrelate_result.content[0].text)
            assert payload == {"status": "deleted", "relation_id": relation_id}

    anyio.run(run)


def test_mcp_contract_tools_validation_and_resources(test_env):
    async def run():
        import memory_mcp.server as server

        importlib.reload(server)

        # legacy = initialize handshake, the path 1.x clients use
        async with Client(server.mcp_server, mode="legacy") as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert names == {
                "remember", "recall", "recall_all", "forget",
                "relate", "unrelate", "graph_query", "trace",
            }

            bad = await client.call_tool("unrelate", {})
            assert bad.is_error
            assert bad.content[0].text == "Input validation error: 'relation_id' is a required property"

            unknown = await client.call_tool("nope", {})
            assert not unknown.is_error
            assert json.loads(unknown.content[0].text) == {"error": "Unknown tool: nope"}

            uris = {r.uri for r in (await client.list_resources()).resources}
            assert uris == {"memory:///current", "memory:///entities"}
            templates = (await client.list_resource_templates()).resource_templates
            assert [t.uri_template for t in templates] == ["memory:///entity/{entity_key}"]

            read = await client.read_resource("memory:///current")
            assert read.contents[0].mime_type == "application/json"
            assert json.loads(read.contents[0].text) == []

    anyio.run(run)
