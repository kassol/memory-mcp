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


def test_no_truncation_first_line_preserved(tools, wm):
    """Multi-line content: first line shown in full, not char-truncated."""
    remember = tools[0]

    async def run():
        content = "First line is the summary\nSecond line has details\nThird line too"
        await remember.remember_tool(
            {"content": content, "entity_key": "preference:verbose", "entity_type": "preference"}
        )
        return await wm.generate_briefing()

    result = anyio.run(run)
    assert "First line is the summary" in result
    assert "Second line" not in result
    assert "..." not in result  # no truncation marker


def test_cwd_reduces_preference_count(tools, wm):
    """With cwd (project mode), fewer global preferences shown."""
    remember = tools[0]

    async def run():
        for i in range(10):
            await remember.remember_tool(
                {"content": f"Pref {i}", "entity_key": f"preference:p{i}", "entity_type": "preference"}
            )
        no_cwd = await wm.generate_briefing()
        with_cwd = await wm.generate_briefing(cwd="/Users/x/Workspace/someproject")
        return no_cwd, with_cwd

    no_cwd, with_cwd = anyio.run(run)
    # Without cwd: 5 prefs max
    assert no_cwd.count("preference:p") == 5
    # With cwd (project mode): 3 prefs max
    assert with_cwd.count("preference:p") == 3


def test_cwd_project_match(tools, wm):
    remember = tools[0]

    async def run():
        await remember.remember_tool(
            {"content": "memory-mcp is a memory service", "entity_key": "project:memory-mcp", "entity_type": "project"}
        )
        await remember.remember_tool(
            {"content": "unrelated stuff", "entity_key": "project:other", "entity_type": "project"}
        )
        return await wm.generate_briefing(cwd="/Users/kassol/Workspace/memory-mcp")

    result = anyio.run(run)
    assert "## Project: memory-mcp" in result
    assert "project:memory-mcp" in result


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


def test_briefing_size_bounded(tools, wm):
    remember = tools[0]

    async def run():
        for i in range(30):
            await remember.remember_tool(
                {"content": f"Preference {i}", "entity_key": f"preference:pref{i}", "entity_type": "preference"}
            )
        return await wm.generate_briefing()

    result = anyio.run(run)
    assert result.count("preference:pref") <= 5
    assert len(result) < 2000
