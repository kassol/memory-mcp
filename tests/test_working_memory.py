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


def test_briefing_shows_preferences(tools, wm):
    remember = tools[0]

    async def run():
        await remember.remember_tool(
            {"content": "I use Cursor", "entity_key": "preference:editor", "entity_type": "preference"}
        )
        await remember.remember_tool(
            {"content": "Dark mode always", "entity_key": "preference:theme", "entity_type": "preference"}
        )
        return await wm.generate_briefing()

    result = anyio.run(run)
    assert "## Preferences" in result
    assert "preference:editor" in result
    assert "preference:theme" in result


def test_briefing_truncates_content(tools, wm):
    remember = tools[0]

    async def run():
        long_content = "A" * 200
        await remember.remember_tool(
            {"content": long_content, "entity_key": "preference:verbose", "entity_type": "preference"}
        )
        return await wm.generate_briefing()

    result = anyio.run(run)
    # Content should be truncated, not the full 200 chars
    assert "A" * 80 not in result
    assert "..." in result


def test_briefing_project_filtering(tools, wm):
    remember = tools[0]

    async def run():
        await remember.remember_tool(
            {"content": "memory-mcp is a memory service", "entity_key": "project:memory-mcp", "entity_type": "project"}
        )
        await remember.remember_tool(
            {"content": "unrelated project info", "entity_key": "project:other", "entity_type": "project"}
        )
        return await wm.generate_briefing(cwd="/Users/kassol/Workspace/memory-mcp")

    result = anyio.run(run)
    assert "## Project: memory-mcp" in result
    assert "project:memory-mcp" in result


def test_briefing_without_cwd_no_project_section(tools, wm):
    remember = tools[0]

    async def run():
        await remember.remember_tool(
            {"content": "some project", "entity_key": "project:foo", "entity_type": "project"}
        )
        return await wm.generate_briefing()

    result = anyio.run(run)
    assert "## Project:" not in result


def test_briefing_shows_recent_changes(tools, wm):
    remember = tools[0]

    async def run():
        await remember.remember_tool(
            {"content": "VSCode", "entity_key": "preference:editor", "entity_type": "preference"}
        )
        await remember.remember_tool(
            {"content": "Cursor", "entity_key": "preference:editor", "entity_type": "preference"}
        )
        return await wm.generate_briefing()

    result = anyio.run(run)
    assert "## Recent Changes (7d)" in result
    assert "preference:editor" in result
    assert "->" in result


def test_briefing_shows_conflicts(test_env, tools, wm):
    remember = tools[0]
    _, vector_mod, _ = test_env

    async def run():
        await remember.remember_tool(
            {"content": "I prefer dark mode", "entity_key": "preference:theme", "entity_type": "preference"}
        )
        nodes = await vector_mod.vector_store.list_current(limit=10)
        node = nodes[0]
        node.conflict = True
        await vector_mod.vector_store.update(node)
        return await wm.generate_briefing()

    result = anyio.run(run)
    assert "## Flags" in result
    assert "[conflict]" in result


def test_briefing_total_size_bounded(tools, wm):
    """Even with many memories, briefing should stay small."""
    remember = tools[0]

    async def run():
        for i in range(30):
            await remember.remember_tool(
                {"content": f"Preference number {i} with some detail text", "entity_key": f"preference:pref{i}", "entity_type": "preference"}
            )
        return await wm.generate_briefing()

    result = anyio.run(run)
    # Should show at most _MAX_PREFERENCE (5), not all 30
    assert result.count("preference:pref") <= 5
    # Total should be well under 2KB
    assert len(result) < 2000
