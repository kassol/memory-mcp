"""Hybrid recall: vector + FTS5 + graph one-hop, fused with Reciprocal Rank Fusion.

Pure vector search misses literal facts such as model names, version numbers and other
numbers. FTS5 over the jieba tokens catches those; RRF merges the ranked lists without
having to calibrate vector distances against bm25 scores.
"""
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .. import settings_registry
from ..storage.graph import graph_store
from ..storage.repositories.memories import MemoryRepository
from ..storage.vector import vector_store
from .embedding import embedding_service
from .models import MemoryNode
from .tokenizer import tokenize

# Tuning parameters (candidates per source, RRF k, FTS weight, graph seeds, time decay) are
# read from settings_registry on every search; their defaults and the evaluation behind them
# live there. Weighted RRF counts FTS double by default: literal hits are why hybrid recall
# exists, and with equal weights a vector-only neighbour list still outranks them.


@dataclass(frozen=True)
class _Params:
    candidates: int
    rrf_k: int
    fts_weight: float
    graph_seeds: int
    decay_lambda: float


async def _params() -> _Params:
    get = settings_registry.get
    return _Params(
        candidates=await get("candidates_per_source"),
        rrf_k=await get("rrf_k"),
        fts_weight=await get("fts_weight"),
        graph_seeds=await get("graph_seeds"),
        decay_lambda=await get("decay_lambda"),
    )


@dataclass
class Hit:
    node: MemoryNode
    rrf_score: float = 0.0
    score: float = 0.0  # rrf_score after time decay; the ranking key
    vector_rank: Optional[int] = None
    fts_rank: Optional[int] = None
    graph_rank: Optional[int] = None


def build_fts_query(query: str) -> str:
    """Quote each jieba token as an FTS5 string and OR them; "" when no token has a letter or digit.

    Quoting stops `-`, `:`, `"`, `*` and bare keywords such as OR from being read as FTS5 syntax.
    """
    terms = [
        '"' + token.replace('"', '""') + '"'
        for token in tokenize(query).split()
        if any(ch.isalnum() for ch in token)
    ]
    return " OR ".join(dict.fromkeys(terms))


async def _vector_candidates(query: str, entity_type: Optional[str], limit: int) -> list[MemoryNode]:
    query_vector = await embedding_service.get_embedding(query)
    # The vector index holds current memories only, so without a type filter nothing is dropped
    # after ANN; the default 4x over-fetch would double the ANN time (200 vs 50 candidates).
    hits = await vector_store.search(
        query_vector,
        limit=limit,
        filter_current=True,
        entity_type=entity_type,
        overfetch=4 if entity_type else 1,
    )
    return [node for node, _ in hits]


async def _fts_candidates(query: str, entity_type: Optional[str], limit: int) -> list[MemoryNode]:
    fts_query = build_fts_query(query)
    if not fts_query:
        return []
    rows = await MemoryRepository().fts_search(fts_query, limit=limit, entity_type=entity_type)
    return [r["node"] for r in rows]


async def _graph_candidates(seed_keys: list[str], entity_type: Optional[str], limit: int) -> list[MemoryNode]:
    """Current memories one relation away from the seeds, ordered by seed rank.

    Seeds themselves are excluded: an edge between two top hits would only boost them again.
    """
    neighbours: dict[str, None] = {}
    for seed in seed_keys:
        for edge in await graph_store.get_relations(seed, depth=1):
            for key in (edge["from_entity_key"], edge["to_entity_key"]):
                if key not in seed_keys:
                    neighbours[key] = None
    nodes = await MemoryRepository().get_current_by_entity_keys(list(neighbours))
    if entity_type:
        nodes = [n for n in nodes if n.entity_type == entity_type]
    return nodes[:limit]


def _fuse(hits: dict[str, Hit], ranked: list[MemoryNode], rrf_k: int, weight: float = 1.0) -> dict[str, int]:
    """Add this source's weighted RRF term to each hit; return {memory_id: rank} for the source."""
    ranks: dict[str, int] = {}
    for rank, node in enumerate(ranked, start=1):
        ranks[node.id] = rank
        hits.setdefault(node.id, Hit(node=node)).rrf_score += weight / (rrf_k + rank)
    return ranks


def _decay(node: MemoryNode, now: datetime, decay_lambda: float) -> float:
    age_days = max((now - node.valid_from).total_seconds() / 86400, 0.0)
    return math.exp(-decay_lambda * age_days)


async def search(query: str, limit: int, entity_type: Optional[str] = None) -> list[Hit]:
    """Current memories for `query`, best first; every source already returns current memories only."""
    p = await _params()
    hits: dict[str, Hit] = {}
    vector = await _vector_candidates(query, entity_type, p.candidates)
    for memory_id, rank in _fuse(hits, vector, p.rrf_k).items():
        hits[memory_id].vector_rank = rank
    fts = await _fts_candidates(query, entity_type, p.candidates)
    for memory_id, rank in _fuse(hits, fts, p.rrf_k, p.fts_weight).items():
        hits[memory_id].fts_rank = rank

    ranked = sorted(hits.values(), key=lambda h: h.rrf_score, reverse=True)
    seeds = list(dict.fromkeys(h.node.entity_key for h in ranked))[:p.graph_seeds]
    graph = await _graph_candidates(seeds, entity_type, p.candidates)
    for memory_id, rank in _fuse(hits, graph, p.rrf_k).items():
        hits[memory_id].graph_rank = rank

    now = datetime.now(timezone.utc)
    for hit in hits.values():
        hit.score = hit.rrf_score * _decay(hit.node, now, p.decay_lambda)
    return sorted(hits.values(), key=lambda h: h.score, reverse=True)[:limit]
