import importlib
import json

import anyio


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

        tools = await server.list_tools()
        assert any(tool.name == "unrelate" for tool in tools)

        relate_result = await server.call_tool(
            "relate",
            {
                "from_entity_key": "person:alice",
                "to_entity_key": "project:x",
                "relation_type": "WORKS_ON",
            },
        )
        relation_id = json.loads(relate_result[0].text)["relation_id"]

        unrelate_result = await server.call_tool("unrelate", {"relation_id": relation_id})
        payload = json.loads(unrelate_result[0].text)
        assert payload == {"status": "deleted", "relation_id": relation_id}

    anyio.run(run)
