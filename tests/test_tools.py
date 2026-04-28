import anyio
import importlib


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

        import memory_mcp.engine.conflict as conflict_mod

        async def always_conflict(_old: str, _new: str):
            return True

        monkeypatch.setattr(conflict_mod.conflict_detector, "check_conflict", always_conflict)

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

        import memory_mcp.engine.conflict as conflict_mod

        async def always_conflict(_old: str, _new: str):
            return True

        monkeypatch.setattr(conflict_mod.conflict_detector, "check_conflict", always_conflict)

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
