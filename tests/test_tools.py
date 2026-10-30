import anyio
import importlib

import pytest


def test_remember_create_and_evolve(tools, test_env):
    async def run():
        remember, _, _, _, _, _, _ = tools
        _, vector, graph = test_env

        res1 = await remember.remember_tool(
            {
                "content": "Prefer Cursor as main editor",
                "entity_type": "preference",
                "entity_key": "preference:editor",
            }
        )
        res2 = await remember.remember_tool(
            {
                "content": "Prefer VSCode as main editor",
                "entity_type": "preference",
                "entity_key": "preference:editor",
            }
        )

        history = await vector.vector_store.get_history("preference:editor")
        assert res1["status"] == "created"
        assert res2["status"] == "evolved"
        assert len(history) == 2
        assert sum(1 for h in history if h.is_current) == 1

        entities = await graph.graph_store.list_entities()
        assert any(e.get("entity_key") == "preference:editor" for e in entities)

    anyio.run(run)

def test_remember_exact_match_conflict_marks_correction(tools, test_env, monkeypatch):
    async def run():
        remember, _, _, _, _, _, _ = tools

        import memory_mcp.engine.merge as merge_mod

        async def always_conflict(_old: str, new: str):
            return new, True

        monkeypatch.setattr(merge_mod, "merge_memories", always_conflict)

        await remember.remember_tool(
            {
                "content": "I live in Beijing",
                "entity_type": "fact",
                "entity_key": "fact:location",
            }
        )
        res = await remember.remember_tool(
            {
                "content": "I live in Shanghai",
                "entity_type": "fact",
                "entity_key": "fact:location",
            }
        )
        assert res["conflict"] is True
        assert res["mutation_type"] == "correction"
        assert set(res["labels"]) == {"conflict", "correction"}

    anyio.run(run)

def test_remember_exact_match_conflict_marks_reversal(tools, test_env, monkeypatch):
    async def run():
        remember, _, _, _, _, _, _ = tools

        import memory_mcp.engine.merge as merge_mod

        async def always_conflict(_old: str, new: str):
            return new, True

        monkeypatch.setattr(merge_mod, "merge_memories", always_conflict)

        await remember.remember_tool(
            {
                "content": "I like apples",
                "entity_type": "preference",
                "entity_key": "preference:apples",
            }
        )
        res = await remember.remember_tool(
            {
                "content": "I do not like apples",
                "entity_type": "preference",
                "entity_key": "preference:apples",
            }
        )
        assert res["conflict"] is True
        assert res["mutation_type"] == "reversal"
        assert set(res["labels"]) == {"conflict", "reversal"}

    anyio.run(run)

def test_recall_includes_relevance_and_evolution(tools, test_env):
    async def run():
        remember, recall, _, _, _, _, _ = tools

        await remember.remember_tool(
            {
                "content": "Prefer Cursor as main editor",
                "entity_type": "preference",
                "entity_key": "preference:editor",
            }
        )
        res = await recall.recall_tool({"query": "Cursor", "include_evolution": True})
        assert res["results"]
        assert "relevance" in res["results"][0]
        assert "evolution_count" in res["results"][0]

    anyio.run(run)

def test_recall_all(tools, test_env):
    async def run():
        remember, _, recall_all, _, _, _, _ = tools

        await remember.remember_tool(
            {
                "content": "Prefer Cursor as main editor",
                "entity_type": "preference",
                "entity_key": "preference:editor",
            }
        )
        res = await recall_all.recall_all_tool({})
        assert res["total"] == 1
        assert res["results"][0]["entity_key"] == "preference:editor"

    anyio.run(run)

def test_trace_summary_format(tools, test_env):
    async def run():
        remember, _, _, trace, _, _, _ = tools

        await remember.remember_tool(
            {
                "content": "Prefer Cursor as main editor",
                "entity_type": "preference",
                "entity_key": "preference:editor",
            }
        )
        res = await trace.trace_tool({"entity_key": "preference:editor", "format": "summary"})
        assert "summary" in res
        assert res["total_versions"] == 1

    anyio.run(run)

def test_remember_skip_semantic_merge_creates_new(tools, test_env, monkeypatch):
    """When skip_semantic_merge=True, a different entity_key always creates new memory."""
    async def run():
        remember, _, _, _, _, _, _ = tools
        await remember.remember_tool({
            "content": "Use Cursor editor",
            "entity_type": "preference",
            "entity_key": "preference:editor",
        })
        res = await remember.remember_tool({
            "content": "Use Cursor editor",
            "entity_type": "preference",
            "entity_key": "preference:editor-v2",
            "skip_semantic_merge": True,
        })
        assert res["status"] == "created"
        assert res["entity_key"] == "preference:editor-v2"
    anyio.run(run)


def test_graph_query_depth(tools, test_env):
    async def run():
        _, _, _, _, _, relate, graph_query = tools

        await relate.relate_tool(
            {
                "from_entity_key": "person:alice",
                "to_entity_key": "project:x",
                "relation_type": "WORKS_ON",
            }
        )
        await relate.relate_tool(
            {
                "from_entity_key": "project:x",
                "to_entity_key": "tech:python",
                "relation_type": "USES",
            }
        )
        res = await graph_query.graph_query_tool({"entity_key": "person:alice", "depth": 2})
        assert res["count"] >= 2

    anyio.run(run)


def test_unrelate_deletes_relation(tools, test_env):
    async def run():
        _, _, _, _, _, relate, graph_query = tools
        import memory_mcp.tools.unrelate as unrelate

        importlib.reload(unrelate)

        created = await relate.relate_tool(
            {
                "from_entity_key": "person:alice",
                "to_entity_key": "project:x",
                "relation_type": "WORKS_ON",
            }
        )
        relation_id = created["relation_id"]

        before = await graph_query.graph_query_tool({"entity_key": "person:alice"})
        assert before["count"] == 1

        deleted = await unrelate.unrelate_tool({"relation_id": relation_id})
        assert deleted == {"status": "deleted", "relation_id": relation_id}

        after = await graph_query.graph_query_tool({"entity_key": "person:alice"})
        assert after["count"] == 0

        missing = await unrelate.unrelate_tool({"relation_id": relation_id})
        assert missing == {"status": "not_found", "relation_id": relation_id}

    anyio.run(run)


def test_unrelate_requires_relation_id(tools, test_env):
    async def run():
        import memory_mcp.tools.unrelate as unrelate

        importlib.reload(unrelate)

        try:
            await unrelate.unrelate_tool({})
        except ValueError as exc:
            assert str(exc) == "Missing required argument: relation_id"
        else:
            raise AssertionError("Expected ValueError")

    anyio.run(run)


def _count_embeddings(monkeypatch):
    import memory_mcp.engine.embedding as embedding_mod

    calls = []

    async def fake_embedding(text: str):
        calls.append(text)
        return [0.1, 0.1, 0.1]

    monkeypatch.setattr(embedding_mod.embedding_service, "get_embedding", fake_embedding)
    return calls


def test_remember_without_key_assigns_key_with_one_embedding(tools, test_env, monkeypatch):
    async def run():
        remember = tools[0]
        _, vector, _ = test_env
        import memory_mcp.engine.key_assignment as key_mod

        embed_calls = _count_embeddings(monkeypatch)
        assign_calls = []

        async def fake_assign(content, embedding=None):
            assign_calls.append((content, embedding))
            return "preference:main_editor", "preference"

        monkeypatch.setattr(key_mod, "assign_entity_key", fake_assign)

        res = await remember.remember_tool({"content": "Prefers Cursor"})
        assert res["status"] == "created"
        assert res["entity_key"] == "preference:main_editor"
        assert assign_calls == [("Prefers Cursor", [0.1, 0.1, 0.1])]
        assert embed_calls == ["Prefers Cursor"]

        async def no_semantic_search(**_kwargs):
            raise AssertionError("semantic merge must be skipped when the server assigns the key")

        # A new subject must not fall into the semantic-merge search either.
        async def new_subject(content, embedding=None):
            return "preference:indent", "preference"

        monkeypatch.setattr(key_mod, "assign_entity_key", new_subject)
        monkeypatch.setattr(vector.vector_store, "search", no_semantic_search)
        res2 = await remember.remember_tool({"content": "Uses tabs"})
        assert res2["status"] == "created"
        assert res2["entity_key"] == "preference:indent"

    anyio.run(run)


def test_remember_with_explicit_key_skips_assignment(tools, test_env, monkeypatch):
    async def run():
        remember = tools[0]
        import memory_mcp.engine.key_assignment as key_mod

        async def must_not_assign(*_args, **_kwargs):
            raise AssertionError("assign_entity_key must not run when a key is given")

        monkeypatch.setattr(key_mod, "assign_entity_key", must_not_assign)
        res = await remember.remember_tool(
            {"content": "Prefers Cursor", "entity_key": "preference:editor", "entity_type": "preference"}
        )
        assert res["status"] == "created"
        assert res["entity_key"] == "preference:editor"

    anyio.run(run)


def test_remember_rejects_key_without_type(tools, test_env):
    async def run():
        remember = tools[0]
        with pytest.raises(ValueError, match="together"):
            await remember.remember_tool({"content": "x", "entity_key": "fact:x"})

    anyio.run(run)


def test_forget_by_memory_id(tools, test_env):
    async def run():
        remember, recall, _, _, forget, _, _ = tools
        _, vector, _ = test_env

        res = await remember.remember_tool(
            {"content": "Uses tabs", "entity_key": "preference:indent", "entity_type": "preference"}
        )
        found = await recall.recall_tool({"query": "indent"})
        assert found["results"][0]["memory_id"] == res["memory_id"]

        out = await forget.forget_tool({"memory_id": res["memory_id"], "reason": "wrong"})
        assert out["status"] == "archived"
        assert out["memory_id"] == res["memory_id"]
        node = await vector.vector_store.get_by_id(res["memory_id"])
        assert node.is_current is False
        assert node.archived_reason == "wrong"
        assert node.archived_at is not None
        assert (await recall.recall_tool({"query": "indent"}))["results"] == []

        with pytest.raises(ValueError, match="not current"):
            await forget.forget_tool({"memory_id": res["memory_id"]})
        with pytest.raises(ValueError, match="not found"):
            await forget.forget_tool({"memory_id": "nope"})
        with pytest.raises(ValueError, match="memory_id or entity_key"):
            await forget.forget_tool({})

    anyio.run(run)
