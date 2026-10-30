import importlib
import json

import anyio
import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError


def test_starlette_lifespan_accepts_app_arg(test_env):
    async def run():
        import memory_mcp.server as server

        importlib.reload(server)

        async with server.app.router.lifespan_context(server.app):
            pass

    anyio.run(run)


def _payload(result) -> dict:
    return json.loads(result.content[0].text)


def test_mcp_contract_four_tools_no_resources(test_env):
    async def run():
        import memory_mcp.server as server

        importlib.reload(server)

        # legacy = initialize handshake, the path 1.x clients use
        async with Client(server.mcp_server, mode="legacy") as client:
            tools = {tool.name: tool.input_schema for tool in (await client.list_tools()).tools}
            assert set(tools) == {"remember", "recall", "forget", "trace"}
            expected = {
                "remember": ({"content", "title", "tags"}, ["content"]),
                "recall": ({"query", "limit"}, ["query"]),
                "forget": ({"memory_id", "reason"}, ["memory_id"]),
                "trace": ({"entity_key", "format"}, ["entity_key"]),
            }
            for name, (props, required) in expected.items():
                assert set(tools[name]["properties"]) == props
                assert tools[name]["required"] == required
                assert tools[name]["additionalProperties"] is False

            bad = await client.call_tool("forget", {})
            assert bad.is_error
            assert bad.content[0].text == "Input validation error: 'memory_id' is a required property"

            extra = await client.call_tool("remember", {"content": "x", "entity_key": "fact:x"})
            assert extra.is_error

            unknown = await client.call_tool("nope", {})
            assert not unknown.is_error
            assert _payload(unknown) == {"error": "Unknown tool: nope"}

            assert client.server_capabilities.resources is None
            with pytest.raises(MCPError):
                await client.list_resources()

    anyio.run(run)


def test_mcp_remember_recall_forget_flow(test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.key_assignment as key_mod
        import memory_mcp.server as server

        importlib.reload(server)
        assigned = []

        async def fake_assign(content, embedding=None):
            assigned.append(content)
            return "preference:main_editor", "preference"

        monkeypatch.setattr(key_mod, "assign_entity_key", fake_assign)

        async with Client(server.mcp_server) as client:
            created = _payload(await client.call_tool("remember", {"content": "Prefers Cursor"}))
            assert created["status"] == "created"
            assert created["entity_key"] == "preference:main_editor"
            assert assigned == ["Prefers Cursor"]

            hits = _payload(await client.call_tool("recall", {"query": "editor"}))["results"]
            assert [h["memory_id"] for h in hits] == [created["memory_id"]]
            assert {"memory_id", "entity_key", "content", "created_at"} <= set(hits[0])

            forgotten = _payload(
                await client.call_tool("forget", {"memory_id": created["memory_id"], "reason": "wrong"})
            )
            assert forgotten["status"] == "archived"
            assert _payload(await client.call_tool("recall", {"query": "editor"}))["results"] == []

            missing = _payload(await client.call_tool("forget", {"memory_id": "no-such-id"}))
            assert missing == {"error": "Memory not found: no-such-id"}

            history = _payload(await client.call_tool("trace", {"entity_key": "preference:main_editor"}))
            assert history["total_versions"] == 1

    anyio.run(run)
