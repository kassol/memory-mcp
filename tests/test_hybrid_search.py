from datetime import datetime, timezone
from uuid import uuid4

import anyio


async def _add(key: str, content: str, embedding: list[float], *, current: bool = True) -> str:
    from memory_mcp.engine.models import MemoryNode, MutationType
    from memory_mcp.engine.tokenizer import tokenize
    from memory_mcp.storage.vector import vector_store

    now = datetime.now(timezone.utc)
    node = MemoryNode(
        id=str(uuid4()),
        entity_key=key,
        entity_type=key.split(":", 1)[0],
        content=content,
        content_tokens=tokenize(content),
        embedding=embedding,
        mutation_type=MutationType.INITIAL,
        created_at=now,
        valid_from=now,
        is_current=current,
    )
    await vector_store.insert(node)
    return node.id


def _embed_query_as(monkeypatch, vector: list[float]) -> None:
    import memory_mcp.engine.embedding as embedding

    async def fake(_text: str):
        return vector

    monkeypatch.setattr(embedding.embedding_service, "get_embedding", fake)


def test_literal_match_outranks_vector_neighbours(test_env, monkeypatch):
    """A version-number query finds its memory through FTS even when the vector ranks it last."""
    async def run():
        from memory_mcp.engine import hybrid_search

        for i in range(5):
            await _add(f"fact:near_{i}", f"unrelated note {i}", [1.0, 0.0, 0.0])
        await _add("fact:gpu", "RTX 3090 runs Qwen3.6-35B-A3B with AutoRound int4", [0.0, 0.0, 1.0])
        _embed_query_as(monkeypatch, [1.0, 0.0, 0.0])

        hits = await hybrid_search.search("Qwen3.6-35B-A3B", limit=3)
        assert hits[0].node.entity_key == "fact:gpu"
        assert hits[0].fts_rank == 1

    anyio.run(run)


def test_query_syntax_characters_do_not_break_fts(test_env, monkeypatch):
    """Hyphens, dots, colons, quotes, FTS keywords and punctuation-only input never raise."""
    async def run():
        from memory_mcp.engine import hybrid_search

        await _add("fact:model", 'gpt-4.1 "mini" a:b NOT OR', [0.0, 1.0, 0.0])
        _embed_query_as(monkeypatch, [1.0, 0.0, 0.0])

        for query in ['gpt-4.1', 'a:b', '"mini"', 'NOT OR', 'col:*', '！？。', '...', '"']:
            await hybrid_search.search(query, limit=5)

        hits = await hybrid_search.search('gpt-4.1 "mini"', limit=5)
        assert hits[0].node.entity_key == "fact:model"
        assert hits[0].fts_rank == 1

    anyio.run(run)


def test_punctuation_only_query_skips_fts():
    from memory_mcp.engine import hybrid_search

    assert hybrid_search.build_fts_query("！？。...") == ""
    assert hybrid_search.build_fts_query("   ") == ""


def test_old_versions_do_not_crowd_out_current_fts_hits(test_env, monkeypatch):
    """The FTS index holds every version. Old versions that match better must not fill the
    FTS candidates and push out a current memory that only FTS can find."""
    async def run():
        from memory_mcp.engine import hybrid_search

        for i in range(60):
            await _add(f"fact:near_{i}", f"unrelated note {i}", [1.0, 0.0, 0.0])
        for i in range(60):
            await _add("fact:awq", f"AWQ AWQ {i}", [1.0, 0.0, 0.0], current=False)
        current_id = await _add(
            "fact:awq", "AWQ quantization with a long tail of other words", [0.0, 0.0, 1.0]
        )
        _embed_query_as(monkeypatch, [1.0, 0.0, 0.0])

        hits = await hybrid_search.search("AWQ", limit=100)
        awq = [h for h in hits if h.node.entity_key == "fact:awq"]
        assert [h.node.id for h in awq] == [current_id]
        assert awq[0].fts_rank == 1
        assert all(h.node.is_current for h in hits)

    anyio.run(run)


def test_graph_neighbour_of_a_top_hit_is_recalled(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import hybrid_search
        from memory_mcp.engine.models import Relation
        from memory_mcp.storage.graph import graph_store

        await _add("project:alpha", "Project Alpha uses Postgres", [1.0, 0.0, 0.0])
        await _add("person:bob", "Bob prefers tabs", [0.0, 1.0, 0.0], current=False)
        bob_id = await _add("person:bob", "Bob prefers spaces", [0.0, 1.0, 0.0])
        await graph_store.add_relation(Relation(
            id=str(uuid4()),
            from_entity_key="person:bob",
            to_entity_key="project:alpha",
            relation_type="WORKS_ON",
            created_at=datetime.now(timezone.utc),
        ))
        _embed_query_as(monkeypatch, [1.0, 0.0, 0.0])

        hits = await hybrid_search.search("Postgres", limit=5)
        bob = [h for h in hits if h.node.entity_key == "person:bob"]
        assert [h.node.id for h in bob] == [bob_id]
        assert bob[0].graph_rank == 1

    anyio.run(run)


def test_no_relations_means_no_graph_hits(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import hybrid_search

        await _add("fact:a", "alpha", [1.0, 0.0, 0.0])
        _embed_query_as(monkeypatch, [1.0, 0.0, 0.0])

        hits = await hybrid_search.search("alpha", limit=5)
        assert [h.node.entity_key for h in hits] == ["fact:a"]
        assert hits[0].graph_rank is None

    anyio.run(run)


def test_rrf_sums_ranks_across_sources(test_env, monkeypatch):
    """A memory ranked by both vector and FTS beats one ranked first by vector alone."""
    async def run():
        from memory_mcp.engine import hybrid_search

        await _add("fact:vec_only", "nothing literal here", [1.0, 0.0, 0.0])
        await _add("fact:both", "the K100AI deployment", [0.9, 0.1, 0.0])
        _embed_query_as(monkeypatch, [1.0, 0.0, 0.0])

        hits = await hybrid_search.search("K100AI", limit=5)
        assert [h.node.entity_key for h in hits] == ["fact:both", "fact:vec_only"]
        both = hits[0]
        assert (both.vector_rank, both.fts_rank) == (2, 1)
        assert both.score == 1 / (60 + 2) + 1 / (60 + 1)

    anyio.run(run)


def test_entity_type_filter(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import hybrid_search

        await _add("fact:x", "shared word zebra", [1.0, 0.0, 0.0])
        await _add("preference:y", "shared word zebra", [1.0, 0.0, 0.0])
        _embed_query_as(monkeypatch, [1.0, 0.0, 0.0])

        hits = await hybrid_search.search("zebra", limit=5, entity_type="preference")
        assert [h.node.entity_key for h in hits] == ["preference:y"]

    anyio.run(run)
