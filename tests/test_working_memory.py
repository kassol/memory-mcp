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


def test_briefing_shows_preferences_full_content(tools, wm):
    remember = tools[0]

    async def run():
        await remember.remember_tool(
            {"content": "Line one\nLine two\nLine three", "entity_key": "preference:multi", "entity_type": "preference"}
        )
        return await wm.generate_briefing()

    result = anyio.run(run)
    assert "## Preferences" in result
    # Full content preserved, no truncation
    assert "Line one\nLine two\nLine three" in result


def test_cwd_adds_project_section_without_reducing_preferences(tools, wm):
    """cwd adds project items on top; global preferences stay at full budget."""
    remember = tools[0]

    async def run():
        for i in range(8):
            await remember.remember_tool(
                {"content": f"Pref {i}", "entity_key": f"preference:p{i}", "entity_type": "preference"}
            )
        await remember.remember_tool(
            {"content": "myproj context", "entity_key": "project:myproj", "entity_type": "project"}
        )
        no_cwd = await wm.generate_briefing()
        with_cwd = await wm.generate_briefing(cwd="/home/user/Workspace/myproj")
        return no_cwd, with_cwd

    no_cwd, with_cwd = anyio.run(run)
    # Both should show 5 preferences (max budget unchanged)
    assert no_cwd.count("preference:p") == 5
    assert with_cwd.count("preference:p") == 5
    # cwd version also has project section
    assert "## Project: myproj" in with_cwd
    assert "## Project:" not in no_cwd


def test_cwd_no_match_same_as_no_cwd(tools, wm):
    """cwd with no matching memories produces same preferences as no cwd."""
    remember = tools[0]

    async def run():
        for i in range(3):
            await remember.remember_tool(
                {"content": f"Pref {i}", "entity_key": f"preference:p{i}", "entity_type": "preference"}
            )
        no_cwd = await wm.generate_briefing()
        with_cwd = await wm.generate_briefing(cwd="/home/user/Workspace/unrelated")
        return no_cwd, with_cwd

    no_cwd, with_cwd = anyio.run(run)
    assert no_cwd == with_cwd


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


def test_selection_caps_at_max(tools, wm):
    """Even with many memories, only _PREF_MAX shown."""
    remember = tools[0]

    async def run():
        for i in range(30):
            await remember.remember_tool(
                {"content": f"Preference {i}", "entity_key": f"preference:pref{i}", "entity_type": "preference"}
            )
        return await wm.generate_briefing()

    result = anyio.run(run)
    assert result.count("preference:pref") == 5
