import importlib
import json
from datetime import datetime, timezone

import anyio
import httpx
import pytest


def _real_merge(monkeypatch, replies):
    """Reload merge (dropping conftest's stub) and feed `chat` canned replies or exceptions."""
    import memory_mcp.engine.merge as merge_mod

    importlib.reload(merge_mod)
    prompts = []

    async def fake_chat(prompt, timeout=30.0):
        prompts.append(prompt)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(merge_mod, "chat", fake_chat)
    return merge_mod, prompts


def _reply(content, conflict):
    return json.dumps({"content": content, "conflict": conflict}, ensure_ascii=False)


def _fact(content, key="fact:home", etype="fact"):
    return {"content": content, "entity_key": key, "entity_type": etype}


@pytest.mark.parametrize(
    "reply",
    [
        httpx.ConnectError("down"),
        "not json",
        '{"content": "x"}',
        '{"conflict": false}',
        '{"content": "  ", "conflict": false}',
        '{"content": "x", "conflict": "yes"}',
        "[1, 2]",
    ],
)
def test_merge_rejects_unusable_output(test_env, monkeypatch, reply):
    async def run():
        merge_mod, _ = _real_merge(monkeypatch, [reply])
        with pytest.raises(merge_mod.MergeError):
            await merge_mod.merge_memories("a", "b")

    anyio.run(run)


def test_merge_parses_fenced_json(test_env, monkeypatch):
    async def run():
        merge_mod, prompts = _real_merge(monkeypatch, ['```json\n{"content": " [2026-05] A; B ", "conflict": true}\n```'])
        assert await merge_mod.merge_memories("[2026-05] A", "B") == ("[2026-05] A; B", True)
        assert "[2026-05] A" in prompts[0] and "\nB\n" in prompts[0]

    anyio.run(run)


def test_same_key_evolution_stores_merged_content(tools, test_env, monkeypatch):
    async def run():
        remember = tools[0]
        _, vector, _ = test_env
        await remember.remember_tool(_fact("Lives in Beijing"))
        _real_merge(monkeypatch, [_reply("Lives in Beijing; works in Haidian", False)])

        res = await remember.remember_tool(_fact("Works in Haidian"))
        assert res["status"] == "evolved" and res["conflict"] is False and res["labels"] == []

        history = await vector.vector_store.get_history("fact:home")
        current = next(h for h in history if h.is_current)
        old = next(h for h in history if not h.is_current)
        assert current.content == "Lives in Beijing; works in Haidian"
        assert old.content == "Lives in Beijing" and current.parent_id == old.id

    anyio.run(run)


def test_same_key_conflict_flag_comes_from_merge(tools, test_env, monkeypatch):
    async def run():
        remember = tools[0]
        await remember.remember_tool(_fact("Lives in Beijing"))
        _, prompts = _real_merge(monkeypatch, [_reply("Lives in Shanghai", True)])

        res = await remember.remember_tool(_fact("Lives in Shanghai"))
        assert res["conflict"] is True and res["mutation_type"] == "correction"
        assert len(prompts) == 1  # the merge call replaces the conflict check

    anyio.run(run)


def test_merge_failure_raises_and_writes_nothing(tools, test_env, monkeypatch):
    async def run():
        remember = tools[0]
        _, vector, _ = test_env
        await remember.remember_tool(_fact("Lives in Beijing"))
        merge_mod, _ = _real_merge(monkeypatch, ["oops"])

        with pytest.raises(merge_mod.MergeError):
            await remember.remember_tool(_fact("Lives in Shanghai"))
        history = await vector.vector_store.get_history("fact:home")
        assert [(h.content, h.is_current) for h in history] == [("Lives in Beijing", True)]

    anyio.run(run)


def test_merge_equal_to_old_is_no_change(tools, test_env, monkeypatch):
    async def run():
        remember = tools[0]
        _, vector, _ = test_env
        created = await remember.remember_tool(_fact("Lives in Beijing"))
        _real_merge(monkeypatch, [_reply("Lives in Beijing", False)])

        res = await remember.remember_tool(_fact("Lives in Beijing."))
        assert res == {"status": "no_change", "memory_id": created["memory_id"]}
        assert len(await vector.vector_store.get_history("fact:home")) == 1

    anyio.run(run)


def test_semantic_merge_path_stores_merged_content(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.conflict as conflict_mod

        remember = tools[0]
        _, vector, _ = test_env
        await remember.remember_tool(_fact("Lives in Beijing"))

        async def always_conflict(_old, _new):
            return True

        monkeypatch.setattr(conflict_mod.conflict_detector, "check_conflict", always_conflict)
        _real_merge(monkeypatch, [_reply("Lives in Shanghai since 2026", False)])

        # Different key, same (stubbed) embedding: matched by similarity, evolves the old key.
        res = await remember.remember_tool(_fact("Lives in Shanghai", key="fact:city"))
        assert res["status"] == "evolved" and res["matched_entity_key"] == "fact:home" and res["conflict"] is True
        current = next(h for h in await vector.vector_store.get_history("fact:home") if h.is_current)
        assert current.content == "Lives in Shanghai since 2026"

    anyio.run(run)


def test_merged_content_gets_its_own_embedding(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.embedding as embedding_mod

        remember = tools[0]
        await remember.remember_tool(_fact("Lives in Beijing"))
        embedded = []

        async def spy(text):
            embedded.append(text)
            return [0.2, 0.2, 0.2]

        monkeypatch.setattr(embedding_mod.embedding_service, "get_embedding", spy)
        _real_merge(monkeypatch, [_reply("Lives in Beijing; works in Haidian", False)])
        await remember.remember_tool(_fact("Works in Haidian"), embedding=[0.1, 0.1, 0.1])
        assert embedded == ["Lives in Beijing; works in Haidian"]

    anyio.run(run)


def test_created_at_is_used_for_create_and_evolve(tools, test_env):
    async def run():
        remember = tools[0]
        _, vector, _ = test_env
        t1 = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        t2 = datetime(2025, 6, 1, tzinfo=timezone.utc)
        await remember.remember_tool(_fact("Lives in Beijing"), created_at=t1)
        await remember.remember_tool(_fact("Lives in Shanghai"), created_at=t2)

        history = await vector.vector_store.get_history("fact:home")
        old = next(h for h in history if not h.is_current)
        new = next(h for h in history if h.is_current)
        assert old.created_at == old.valid_from == t1 and old.valid_until == t2
        assert new.created_at == new.valid_from == t2 and new.valid_until is None

    anyio.run(run)


def test_created_at_defaults_to_now(tools, test_env):
    async def run():
        remember = tools[0]
        _, vector, _ = test_env
        before = datetime.now(timezone.utc)
        await remember.remember_tool(_fact("Lives in Beijing"))
        await remember.remember_tool(_fact("Lives in Shanghai"))
        after = datetime.now(timezone.utc)

        history = await vector.vector_store.get_history("fact:home")
        old = next(h for h in history if not h.is_current)
        new = next(h for h in history if h.is_current)
        assert before <= old.created_at <= new.created_at <= after
        assert old.valid_until == new.valid_from == new.created_at

    anyio.run(run)


def test_same_key_evolution_merges_tags(tools, test_env):
    async def run():
        remember = tools[0]
        _, vector, _ = test_env
        await remember.remember_tool({**_fact("Lives in Beijing"), "tags": ["home", "city"]})
        await remember.remember_tool({**_fact("Works in Haidian"), "tags": ["city", "work"]})

        history = await vector.vector_store.get_history("fact:home")
        current = next(h for h in history if h.is_current)
        assert current.tags == ["home", "city", "work"]

    anyio.run(run)
