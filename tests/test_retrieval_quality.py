"""Fixed corpus + fixed queries: each target must reach the top 3 of recall.

Embeddings are a fixed bag-of-concepts table so the test needs no network. The table
models how a sentence embedding behaves: it captures topic words (GPU, quantization,
deployment) and ignores literal identifiers such as model versions and card numbers.
"""
import anyio
import pytest

CONCEPTS = ["显卡", "量化", "部署", "编辑器", "数据库", "记忆", "城市", "备份"]
CONCEPT_WORDS = {
    "显卡": ["显卡", "gpu", "rtx"],
    "量化": ["量化", "quantization", "awq", "int4"],
    "部署": ["部署", "deploy", "上线", "compose"],
    "编辑器": ["编辑器", "editor"],
    "数据库": ["数据库", "postgres", "sqlite"],
    "记忆": ["记忆", "memory"],
    "城市": ["城市", "住在", "city"],
    "备份": ["备份", "backup"],
}


def _embed(text: str) -> list[float]:
    lowered = text.lower()
    vec = [float(sum(lowered.count(w) for w in CONCEPT_WORDS[c])) for c in CONCEPTS]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


CORPUS = [
    ("fact:gpu_qwen_3090", "边缘部署用单卡 RTX 3090 显卡跑 Qwen3.6-35B-A3B，量化为 int4-mixed-AutoRound"),
    ("fact:gpu_qwen_k100", "海光 K100AI 显卡部署 Qwen3.6-27B，BF16 不做量化"),
    ("fact:gpu_llama_4090", "RTX 4090 显卡跑 Llama-3-70B，量化用 AWQ"),
    ("fact:gpu_glm_5090", "RTX 5090 显卡跑 GLM-4.5，量化用 GPTQ int4"),
    ("fact:gpu_bandwidth", "显卡选型看显存带宽，量化后 decode 速度主要受带宽限制"),
    ("fact:gpu_ascend", "昇腾 310P 显卡部署 W8A8 量化模型不建议上生产"),
    ("preference:editor", "Prefers Cursor as the main editor"),
    ("fact:city", "住在上海"),
    ("fact:memory_backup", "memory-mcp 每天备份 SQLite 与向量库，保留 7 份"),
    ("decision:db", "Project Alpha uses Postgres as its primary database"),
]

LITERAL_QUERY = "3090 上跑 Qwen3.6-35B-A3B 用的什么量化？"
QUERIES = [
    (LITERAL_QUERY, "fact:gpu_qwen_3090"),
    ("Llama-3-70B 用什么显卡", "fact:gpu_llama_4090"),
    ("编辑器偏好", "preference:editor"),
    ("我住在哪个城市", "fact:city"),
    ("memory-mcp 备份保留几份", "fact:memory_backup"),
    ("Project Alpha 用什么数据库", "decision:db"),
]


@pytest.fixture()
def corpus(test_env, monkeypatch):
    import memory_mcp.engine.embedding as embedding
    import memory_mcp.tools.recall as recall
    import memory_mcp.tools.remember as remember

    async def fake_embedding(text: str):
        return _embed(text)

    monkeypatch.setattr(embedding.embedding_service, "get_embedding", fake_embedding)

    async def load():
        for key, content in CORPUS:
            await remember.remember_tool(
                {"content": content, "entity_key": key, "entity_type": key.split(":", 1)[0],
                 "skip_semantic_merge": True}
            )

    anyio.run(load)
    return recall


def _top3(recall, query: str) -> list[str]:
    async def run():
        res = await recall.recall_tool({"query": query, "limit": 3})
        return [r["entity_key"] for r in res["results"]]

    return anyio.run(run)


@pytest.mark.parametrize("query,target", QUERIES)
def test_target_in_top3(corpus, query, target):
    assert target in _top3(corpus, query)


def test_literal_query_needs_hybrid_recall(corpus):
    """Control: vector search alone does not put the literal-query target in the top 3."""
    from memory_mcp.storage.vector import vector_store

    async def vector_top3():
        hits = await vector_store.search(_embed(LITERAL_QUERY), limit=3)
        return [node.entity_key for node, _ in hits]

    assert "fact:gpu_qwen_3090" not in anyio.run(vector_top3)
    assert "fact:gpu_qwen_3090" in _top3(corpus, LITERAL_QUERY)
