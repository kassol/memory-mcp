import importlib
import anyio


MESSAGES = [
    {"role": "user", "content": "I prefer Cursor as my main editor and I live in Shanghai."},
    {"role": "assistant", "content": "Got it, I'll remember that."},
]

VALID_LLM_RESPONSE = '[{"content": "Prefers Cursor as main editor"}, {"content": "Lives in Shanghai"}, {"content": ""}, {"entity_key": "x:y"}, "bare string"]'

ASSIGNED_KEYS = {
    "Prefers Cursor as main editor": ("preference:editor", "preference"),
    "Lives in Shanghai": ("fact:location", "fact"),
}


def _patch_assign(monkeypatch, extraction_mod):
    async def fake_assign(content, embedding=None):
        return ASSIGNED_KEYS[content]

    monkeypatch.setattr(extraction_mod, "assign_entity_key", fake_assign)


CODE_FENCE_LLM_RESPONSE = '```json\n[{"content": "Prefers Cursor as main editor"}]\n```'


def test_extract_memories_from_messages(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.extraction as extraction_mod
        importlib.reload(extraction_mod)

        async def fake_call_llm(_messages):
            return VALID_LLM_RESPONSE

        monkeypatch.setattr(extraction_mod, "_call_llm", fake_call_llm)
        _patch_assign(monkeypatch, extraction_mod)

        result = await extraction_mod.extract_memories(MESSAGES)
        assert result["total"] == 2 and result["failed"] == 0
        assert "entity_key" not in extraction_mod._EXTRACTION_PROMPT
        keys = {r["entity_key"] for r in result["results"]}
        assert "preference:editor" in keys
        assert "fact:location" in keys

    anyio.run(run)


def test_extract_handles_malformed_llm_output(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.extraction as extraction_mod
        importlib.reload(extraction_mod)

        async def fake_call_llm(_messages):
            return "this is not json at all !!@#$"

        monkeypatch.setattr(extraction_mod, "_call_llm", fake_call_llm)
        _patch_assign(monkeypatch, extraction_mod)

        result = await extraction_mod.extract_memories(MESSAGES)
        assert result["total"] == 0
        assert result["failed"] == 0
        assert result["results"] == []
        assert result["errors"] == []

    anyio.run(run)


def test_extract_raises_when_llm_call_fails(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.extraction as extraction_mod
        importlib.reload(extraction_mod)

        async def fake_call_llm(_messages):
            raise RuntimeError("llm down")

        monkeypatch.setattr(extraction_mod, "_call_llm", fake_call_llm)
        _patch_assign(monkeypatch, extraction_mod)

        try:
            await extraction_mod.extract_memories(MESSAGES)
        except extraction_mod.ExtractionError as exc:
            assert str(exc) == "LLM extraction failed"
            return
        raise AssertionError("Expected ExtractionError")

    anyio.run(run)


def test_extract_handles_code_fence_json(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.extraction as extraction_mod
        importlib.reload(extraction_mod)

        async def fake_call_llm(_messages):
            return CODE_FENCE_LLM_RESPONSE

        monkeypatch.setattr(extraction_mod, "_call_llm", fake_call_llm)
        _patch_assign(monkeypatch, extraction_mod)

        result = await extraction_mod.extract_memories(MESSAGES)
        assert result["total"] == 1
        assert result["results"][0]["entity_key"] == "preference:editor"

    anyio.run(run)


def test_extract_uses_skip_semantic_merge(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.extraction as extraction_mod
        importlib.reload(extraction_mod)

        async def fake_call_llm(_messages):
            return VALID_LLM_RESPONSE

        monkeypatch.setattr(extraction_mod, "_call_llm", fake_call_llm)
        _patch_assign(monkeypatch, extraction_mod)

        captured_calls = []
        original_remember_tool = extraction_mod.remember_tool

        async def spy_remember_tool(arguments, **kwargs):
            captured_calls.append(dict(arguments))
            return await original_remember_tool(arguments, **kwargs)

        monkeypatch.setattr(extraction_mod, "remember_tool", spy_remember_tool)

        result = await extraction_mod.extract_memories(MESSAGES)
        assert result["total"] == 2
        assert all(call.get("skip_semantic_merge") is True for call in captured_calls)

    anyio.run(run)


def test_extract_reports_candidate_failures(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.extraction as extraction_mod
        importlib.reload(extraction_mod)

        async def fake_call_llm(_messages):
            return VALID_LLM_RESPONSE

        async def fake_remember_tool(arguments, **kwargs):
            if arguments["entity_key"] == "fact:location":
                raise ValueError("write failed")
            return {"status": "created", "entity_key": arguments["entity_key"]}

        monkeypatch.setattr(extraction_mod, "_call_llm", fake_call_llm)
        _patch_assign(monkeypatch, extraction_mod)
        monkeypatch.setattr(extraction_mod, "remember_tool", fake_remember_tool)

        result = await extraction_mod.extract_memories(MESSAGES)
        assert result["total"] == 1
        assert result["failed"] == 1
        assert result["results"][0]["entity_key"] == "preference:editor"
        assert result["errors"][0]["entity_key"] == "fact:location"
        assert result["errors"][0]["error"] == "write failed"

    anyio.run(run)


def test_extract_uses_assigned_key_and_reuses_embedding(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.extraction as extraction_mod
        importlib.reload(extraction_mod)

        async def fake_call_llm(_messages):
            return '[{"content": "Prefers Cursor as main editor"}]'

        embed_calls = []

        async def counting_embedding(text):
            embed_calls.append(text)
            return [0.1, 0.1, 0.1]

        seen_embeddings = []
        original_remember_tool = extraction_mod.remember_tool

        async def spy_remember_tool(arguments, **kwargs):
            seen_embeddings.append(kwargs.get("embedding"))
            return await original_remember_tool(arguments, **kwargs)

        monkeypatch.setattr(extraction_mod, "_call_llm", fake_call_llm)
        monkeypatch.setattr(extraction_mod.embedding_service, "get_embedding", counting_embedding)
        monkeypatch.setattr(extraction_mod, "remember_tool", spy_remember_tool)
        _patch_assign(monkeypatch, extraction_mod)

        result = await extraction_mod.extract_memories(MESSAGES)
        assert result["results"][0]["entity_key"] == "preference:editor"
        assert embed_calls == ["Prefers Cursor as main editor"]
        assert seen_embeddings == [[0.1, 0.1, 0.1]]

    anyio.run(run)


def test_extract_collects_merge_errors(tools, test_env, monkeypatch):
    async def run():
        import memory_mcp.engine.extraction as extraction_mod
        import memory_mcp.engine.merge as merge_mod
        importlib.reload(extraction_mod)
        remember = tools[0]

        await remember.remember_tool(
            {"content": "Prefers Vim as main editor", "entity_key": "preference:editor", "entity_type": "preference"}
        )

        async def broken_merge(_old, _new):
            raise merge_mod.MergeError("LLM merge failed: HTTP 503")

        async def fake_call_llm(_messages):
            return VALID_LLM_RESPONSE

        monkeypatch.setattr(merge_mod, "merge_memories", broken_merge)
        monkeypatch.setattr(extraction_mod, "_call_llm", fake_call_llm)
        _patch_assign(monkeypatch, extraction_mod)

        result = await extraction_mod.extract_memories(MESSAGES)
        assert result["total"] == 1
        assert result["results"][0]["entity_key"] == "fact:location"
        assert result["failed"] == 1
        assert result["errors"][0]["entity_key"] == "preference:editor"
        assert "HTTP 503" in result["errors"][0]["error"]

    anyio.run(run)
