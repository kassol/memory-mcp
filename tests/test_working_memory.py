import importlib

import anyio
import pytest


@pytest.fixture()
def wm(test_env):
    import memory_mcp.engine.working_memory as wm_mod
    importlib.reload(wm_mod)
    return wm_mod


def test_briefing_empty(wm):
    result = anyio.run(wm.generate_briefing)
    assert result == "No memories yet."


def test_briefing_groups_by_type(tools, wm):
    remember = tools[0]

    async def run():
        await remember.remember_tool(
            {"content": "I use Cursor", "entity_key": "preference:editor", "entity_type": "preference"}
        )
        await remember.remember_tool(
            {"content": "memory-mcp personal memory service", "entity_key": "project:memory-mcp", "entity_type": "project"}
        )
        return await wm.generate_briefing()

    result = anyio.run(run)
    assert "preference" in result
    assert "project" in result


def test_briefing_shows_recent_changes(tools, wm):
    remember = tools[0]

    async def run():
        # Initial memory
        await remember.remember_tool(
            {"content": "VSCode", "entity_key": "preference:editor", "entity_type": "preference"}
        )
        # Evolve it
        await remember.remember_tool(
            {"content": "Cursor", "entity_key": "preference:editor", "entity_type": "preference"}
        )
        return await wm.generate_briefing()

    result = anyio.run(run)
    assert "Recent Changes" in result
    assert "preference:editor" in result


def test_briefing_shows_conflicts(test_env, tools, wm):
    remember = tools[0]
    # test_env returns (config, vector, graph); use the already-reloaded vector module
    _, vector_mod, _ = test_env

    async def run():
        await remember.remember_tool(
            {"content": "I prefer dark mode", "entity_key": "preference:theme", "entity_type": "preference"}
        )
        # Manually mark the current node as a conflict
        nodes = await vector_mod.vector_store.list_current(limit=10)
        assert nodes, "expected at least one node"
        node = nodes[0]
        node.conflict = True
        await vector_mod.vector_store.update(node)

        return await wm.generate_briefing()

    result = anyio.run(run)
    assert "Flags" in result
    assert "conflict" in result
