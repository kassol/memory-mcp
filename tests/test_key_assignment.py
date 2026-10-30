import importlib

import anyio
import httpx
import pytest


def _key_mod(monkeypatch, reply):
    import memory_mcp.engine.key_assignment as key_mod
    importlib.reload(key_mod)
    prompts = []

    async def fake_chat(prompt, timeout=30.0):
        prompts.append(prompt)
        return reply

    monkeypatch.setattr(key_mod, "chat", fake_chat)
    return key_mod, prompts


async def _seed(remember):
    await remember.remember_tool(
        {"content": "Prefers Cursor as main editor", "entity_key": "editor_pref", "entity_type": "preference"}
    )


def test_assign_reuses_neighbor_key(tools, test_env, monkeypatch):
    async def run():
        await _seed(tools[0])
        # LLM echoes the legacy key with a different type; stored type must win.
        key_mod, prompts = _key_mod(monkeypatch, '```json\n{"entity_key": "editor_pref", "entity_type": "tool"}\n```')
        key, etype = await key_mod.assign_entity_key("Now prefers Zed as main editor")
        assert (key, etype) == ("editor_pref", "preference")
        assert "Prefers Cursor as main editor" in prompts[0]
        assert "Now prefers Zed as main editor" in prompts[0]

    anyio.run(run)


def test_assign_creates_new_key(tools, test_env, monkeypatch):
    async def run():
        await _seed(tools[0])
        key_mod, _ = _key_mod(monkeypatch, '{"entity_key": "fact:home_city", "entity_type": "fact"}')
        assert await key_mod.assign_entity_key("Lives in Shanghai") == ("fact:home_city", "fact")

    anyio.run(run)


def test_assign_with_empty_store_lists_no_neighbors(tools, test_env, monkeypatch):
    async def run():
        key_mod, prompts = _key_mod(monkeypatch, '{"entity_key": "fact:home_city", "entity_type": "fact"}')
        assert await key_mod.assign_entity_key("Lives in Shanghai", [0.1, 0.1, 0.1]) == ("fact:home_city", "fact")
        assert "(none)" in prompts[0]

    anyio.run(run)


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        '{"entity_key": "fact:home_city"',
        '{"entity_key": "fact:home_city"}',
        '{"entity_key": "Home City", "entity_type": "fact"}',
        '{"entity_key": "fact:", "entity_type": "fact"}',
    ],
)
def test_assign_rejects_unusable_output(tools, test_env, monkeypatch, reply):
    async def run():
        key_mod, _ = _key_mod(monkeypatch, reply)
        with pytest.raises(key_mod.KeyAssignmentError):
            await key_mod.assign_entity_key("Lives in Shanghai")

    anyio.run(run)


def test_assign_wraps_llm_failure(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.key_assignment as key_mod
        importlib.reload(key_mod)

        async def down(_prompt, timeout=30.0):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(key_mod, "chat", down)
        with pytest.raises(key_mod.KeyAssignmentError):
            await key_mod.assign_entity_key("Lives in Shanghai")

    anyio.run(run)


# ---- conflict check: failures must raise, never mean "no conflict" ----------


def _patch_post(monkeypatch, response=None, exc=None):
    async def fake_post(self, url, **kwargs):
        if exc:
            raise exc
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def _llm_response(status, text):
    request = httpx.Request("POST", "https://example.test/chat/completions")
    return httpx.Response(status, json={"choices": [{"message": {"content": text}}]}, request=request)


@pytest.mark.parametrize(
    "response, exc",
    [
        (None, httpx.ConnectError("down")),
        (_llm_response(503, "YES"), None),
        (_llm_response(200, "I am not sure"), None),
        (httpx.Response(200, text="oops", request=httpx.Request("POST", "https://x")), None),
    ],
)
def test_check_conflict_raises_on_failure(test_env, monkeypatch, response, exc):
    async def run():
        import memory_mcp.engine.conflict as conflict_mod
        _patch_post(monkeypatch, response, exc)
        with pytest.raises(conflict_mod.ConflictCheckError):
            await conflict_mod.ConflictDetector().check_conflict("a", "b")

    anyio.run(run)


@pytest.mark.parametrize("text, expected", [("YES", True), ("**No**.", False), ("yes, they contradict", True)])
def test_check_conflict_parses_verdict(test_env, monkeypatch, text, expected):
    async def run():
        import memory_mcp.engine.conflict as conflict_mod
        _patch_post(monkeypatch, _llm_response(200, text))
        assert await conflict_mod.ConflictDetector().check_conflict("a", "b") is expected

    anyio.run(run)


def test_remember_propagates_conflict_check_error(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.conflict as conflict_mod
        remember = tools[0]
        _, vector, _ = test_env
        await remember.remember_tool({"content": "Lives in Beijing", "entity_key": "fact:home_city", "entity_type": "fact"})

        async def broken(_old, _new):
            raise conflict_mod.ConflictCheckError("Conflict check request failed")

        monkeypatch.setattr(conflict_mod.conflict_detector, "check_conflict", broken)
        # A different key with the same embedding takes the semantic merge path.
        with pytest.raises(conflict_mod.ConflictCheckError):
            await remember.remember_tool({"content": "Lives in Shanghai", "entity_key": "fact:city", "entity_type": "fact"})
        history = await vector.vector_store.get_history("fact:home_city")
        assert [h.content for h in history] == ["Lives in Beijing"]
        assert await vector.vector_store.get_history("fact:city") == []

    anyio.run(run)


def test_llm_requests_disable_reasoning(tools, test_env, monkeypatch):
    """Reasoning made merges 10-28 s and sometimes returned empty content; every LLM call turns it off."""
    import httpx

    import memory_mcp.engine.conflict as conflict_mod
    import memory_mcp.engine.llm as llm

    bodies = []

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): ...
        async def post(self, url, json=None, **_):
            bodies.append(json)
            return httpx.Response(200, json={"choices": [{"message": {"content": "NO"}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    async def run():
        await llm.chat("hi")
        await conflict_mod.ConflictDetector().check_conflict("a", "b")

    anyio.run(run)
    assert [b["reasoning"] for b in bodies] == [{"enabled": False}] * 2


@pytest.mark.parametrize(
    "reply, expected",
    [
        ('{"entity_key": "fact:qwen3.6_35b-a3b", "entity_type": "fact"}', ("fact:qwen3_6_35b_a3b", "fact")),
        ('{"entity_key": "decision:deploy_on_cc-la", "entity_type": "decision"}', ("decision:deploy_on_cc_la", "decision")),
        ('{"entity_key": "fact:trace_retention", "entity_type": "decision"}', ("fact:trace_retention", "fact")),
    ],
)
def test_assign_normalizes_new_keys(tools, test_env, monkeypatch, reply, expected):
    async def run():
        key_mod, _ = _key_mod(monkeypatch, reply)
        assert await key_mod.assign_entity_key("Some new fact") == expected

    anyio.run(run)
