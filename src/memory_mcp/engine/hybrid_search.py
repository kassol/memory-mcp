"""Hybrid recall: vector + FTS5 + graph one-hop, fused with Reciprocal Rank Fusion.

Pure vector search misses literal facts such as model names, version numbers and other
numbers. FTS5 over the jieba tokens catches those; RRF merges the ranked lists without
having to calibrate vector distances against bm25 scores.
"""
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..storage.graph import graph_store
from ..storage.repositories.memories import MemoryRepository
from ..storage.vector import vector_store
from .embedding import embedding_service
from .models import MemoryNode
from .tokenizer import tokenize

CANDIDATES_PER_SOURCE = 50
RRF_K = 60
GRAPH_SEEDS = 5
# Time decay on valid_from, per day. Off until an evaluation set shows a gain.
DECAY_LAMBDA = 0.0


@dataclass
class Hit:
    node: MemoryNode
    score: float
    vector_rank: Optional[int] = None
    fts_rank: Optional[int] = None
    graph_rank: Optional[int] = None


def build_fts_query(query: str) -> str:
    """Quote each jieba token as an FTS5 string and OR them; "" when no token has a letter or digit.

    Quoting stops `-`, `:`, `"`, `*` and bare keywords such as OR from being read as FTS5 syntax.
    """
    terms: list[str] = []
    for token in tokenize(query).split():
        if not any(ch.isalnum() for ch in token):
            continue
        term = '"' + token.replace('"', '""') + '"'
        if term not in terms:
            terms.append(term)
    return " OR ".join(terms)


async def _graph_neighbours(seed_keys: list[str]) -> list[MemoryNode]:
    """Current memories one relation away from the seeds, ordered by seed rank."""
    neighbour_keys: list[str] = []
    for seed in seed_keys:
        for edge in await graph_store.get_relations(seed, depth=1):
            other = edge["to_entity_key"] if edge["from_entity_key"] == seed else edge["from_entity_key"]
            if other not in neighbour_keys:
                neighbour_keys.append(other)
    if not neighbour_keys:
        return []
    return await MemoryRepository().get_current_by_entity_keys(neighbour_keys)


def _rrf(hits: dict[str, Hit], ranked: list[MemoryNode], field: str) -> None:
    for rank, node in enumerate(ranked, start=1):
        hit = hits.get(node.id)
        if hit is None:
            hit = hits[node.id] = Hit(node=node, score=0.0)
        if getattr(hit, field) is not None:
            continue
        setattr(hit, field, rank)
        hit.score += 1 / (RRF_K + rank)


def _decay(node: MemoryNode, now: datetime) -> float:
    if DECAY_LAMBDA == 0:
        return 1.0
    age_days = max((now - node.valid_from).total_seconds() / 86400, 0.0)
    return math.exp(-DECAY_LAMBDA * age_days)


async def search(query: str, limit: int, entity_type: Optional[str] = None) -> list[Hit]:
    query_vector = await embedding_service.get_embedding(query)
    # The vector index holds current memories only, so without a type filter nothing is dropped
    # after ANN; the default 4x over-fetch would double the ANN time (200 vs 50 candidates).
    vector_nodes = [
        node
        for node, _ in await vector_store.search(
            query_vector,
            limit=CANDIDATES_PER_SOURCE,
            filter_current=True,
            entity_type=entity_type,
            overfetch=4 if entity_type else 1,
        )
    ]

    fts_query = build_fts_query(query)
    fts_nodes = (
        [
            r["node"]
            for r in await MemoryRepository().fts_search(
                fts_query, limit=CANDIDATES_PER_SOURCE, entity_type=entity_type
            )
        ]
        if fts_query
        else []
    )

    hits: dict[str, Hit] = {}
    _rrf(hits, vector_nodes, "vector_rank")
    _rrf(hits, fts_nodes, "fts_rank")

    seeds: list[str] = []
    for hit in sorted(hits.values(), key=lambda h: h.score, reverse=True):
        if hit.node.entity_key not in seeds:
            seeds.append(hit.node.entity_key)
        if len(seeds) == GRAPH_SEEDS:
            break
    _rrf(hits, await _graph_neighbours(seeds), "graph_rank")

    now = datetime.now(timezone.utc)
    results = [
        hit
        for hit in hits.values()
        if hit.node.is_current and (not entity_type or hit.node.entity_type == entity_type)
    ]
    for hit in results:
        hit.score *= _decay(hit.node, now)
    results.sort(key=lambda h: h.score, reverse=True)
    return results[:limit]
