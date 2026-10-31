import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import anyio
import pytest

_T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
_seq = iter(range(10_000))
_axis = iter(range(10_000))


def _unique_vector() -> list[float]:
    """Orthogonal to the other default vectors of a test, so it is nobody's cross-key neighbour."""
    vec = [0.0] * 512
    vec[next(_axis) % 512] = 1.0
    return vec


async def _add(key: str, content: str = "x", embedding=None, *, conflict: bool = False, current: bool = True) -> str:
    from memory_mcp.engine.models import MemoryNode, MutationType
    from memory_mcp.engine.tokenizer import tokenize
    from memory_mcp.storage.vector import vector_store

    at = _T0 + timedelta(minutes=next(_seq))
    node = MemoryNode(
        id=str(uuid4()),
        entity_key=key,
        entity_type=key.split(":", 1)[0],
        content=content,
        content_tokens=tokenize(content),
        embedding=embedding or _unique_vector(),
        mutation_type=MutationType.CORRECTION if conflict else MutationType.INITIAL,
        created_at=at,
        valid_from=at,
        is_current=current,
        conflict=conflict,
    )
    await vector_store.insert(node)
    return node.id


async def _archive(memory_id: str) -> None:
    from memory_mcp.storage.vector import vector_store

    node = await vector_store.get_by_id(memory_id)
    node.is_current = False
    await vector_store.update(node)


async def _findings(**filters):
    from memory_mcp.engine import maintenance

    return await maintenance.list_findings(**filters)


async def _jobs():
    from memory_mcp.storage.sqlite import get_db

    async with get_db() as db:
        rows = await db.fetchall("SELECT status, payload, error FROM jobs WHERE job_type = 'maintenance'")
    return [dict(r) for r in rows]


class FakeLLM:
    """Answers by content: a memory with CLASH, or a pair where both sides carry DUP."""

    def __init__(self, monkeypatch):
        import memory_mcp.engine.maintenance as maintenance

        self.prompts: list[str] = []
        self.override: str | None = None
        monkeypatch.setattr(maintenance, "chat", self)

    async def __call__(self, prompt: str, timeout: float = 30.0) -> str:
        self.prompts.append(prompt)
        if self.override is not None:
            return self.override
        if "Memory A" not in prompt:  # internal-contradiction prompt
            verdict = "internal_contradiction" if "CLASH" in prompt else "consistent"
        elif prompt.count("DUP") == 2:
            verdict = "duplicate"
        else:
            verdict = "compatible"
        detail = "" if verdict in {"consistent", "compatible"} else "A and B cannot both hold"
        return json.dumps({"verdict": verdict, "detail": detail})


def test_multiple_current_found_once_and_resolved_when_fixed(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance

        FakeLLM(monkeypatch)
        first = await _add("fact:deploy", "v1")
        second = await _add("fact:deploy", "v2")
        await _add("fact:other")

        await maintenance.run_once()
        await maintenance.run_once()

        found = await _findings(status="open")
        assert [(f["kind"], f["entity_key"], f["memory_id"], f["other_memory_id"]) for f in found] == [
            ("multiple_current", "fact:deploy", first, second)
        ]

        await _archive(first)
        await maintenance.run_once()
        assert await _findings(status="open") == []
        resolved = await _findings(status="resolved")
        assert [f["kind"] for f in resolved] == ["multiple_current"]
        assert resolved[0]["resolved_at"] is not None

        jobs = await _jobs()
        assert [j["status"] for j in jobs] == ["done", "done", "done"]

    anyio.run(run)


def test_internal_contradiction_only_checks_conflict_memories_once(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance

        llm = FakeLLM(monkeypatch)
        clash = await _add("tool:x", "uses A. CLASH switched A to B", conflict=True)
        await _add("tool:y", "consistent after a conflicting merge", conflict=True)
        await _add("tool:z", "CLASH but never merged with a conflict", conflict=False)

        await maintenance.run_once()
        assert len(llm.prompts) == 2
        found = await _findings(status="open")
        assert [(f["kind"], f["memory_id"], f["entity_key"], f["detail"]) for f in found] == [
            ("internal_contradiction", clash, "tool:x", "A and B cannot both hold")
        ]

        await maintenance.run_once()
        assert len(llm.prompts) == 2  # every memory already has a check
        assert len(await _findings()) == 1

    anyio.run(run)


def test_cross_key_pairs_judged_once_and_only_problems_become_findings(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance

        llm = FakeLLM(monkeypatch)
        near = [1.0, 0.0, 0.0]
        await _add("fact:a", "deploy with rsync", near)
        await _add("fact:b", "deploy with scp", [0.99, 0.1, 0.0])
        await _add("fact:a", "same key as a, never a cross-key pair", near, current=False)
        c = await _add("fact:c", "DUP note", [0.0, 1.0, 0.0])
        d = await _add("fact:d", "DUP note again", [0.05, 1.0, 0.0])
        await _add("fact:e", "related but fine", [0.0, 0.95, 0.31])
        await _add("fact:far", "unrelated", [0.0, 0.0, 1.0])

        await maintenance.run_once()
        found = {(f["kind"], frozenset((f["memory_id"], f["other_memory_id"]))) for f in await _findings()}
        assert found == {("duplicate", frozenset((c, d)))}
        pair_prompts = [p for p in llm.prompts if "Memory A" in p]
        # a-b, c-d, c-e and d-e are above the cosine threshold; each unordered pair once.
        assert len(pair_prompts) == 4

        await maintenance.run_once()
        assert len([p for p in llm.prompts if "Memory A" in p]) == 4

    anyio.run(run)


def test_budget_split_and_continuation_across_runs(test_env, monkeypatch):
    """Each LLM check gets half the budget; unused budget goes to the other; the rest waits for the next run."""
    async def run():
        from memory_mcp.engine import maintenance
        from memory_mcp import settings_registry

        monkeypatch.setattr(settings_registry.settings, "maintenance_max_llm_calls", 4)
        llm = FakeLLM(monkeypatch)
        for i in range(5):
            await _add(f"tool:t{i}", f"merged {i}", conflict=True)
        for i in range(3):
            await _add(f"fact:p{i}", f"pair {i}", [1.0, 0.0, i / 100])

        def counts():
            internal = sum(1 for p in llm.prompts if "Memory A" not in p)
            return internal, len(llm.prompts) - internal

        await maintenance.run_once()
        assert counts() == (2, 2)
        await maintenance.run_once()
        assert counts() == (5, 3)  # pairs ran out after 1 call; internal used the rest
        await maintenance.run_once()
        assert counts() == (5, 3)  # nothing left to judge
        jobs = await _jobs()
        assert [json.loads(j["payload"])["llm_calls"] for j in jobs] == [4, 4, 0]

    anyio.run(run)


@pytest.mark.parametrize("bad", ["YES", '{"verdict": "maybe", "detail": ""}', '{"verdict": "consistent"}'])
def test_unusable_llm_output_fails_the_run_and_writes_no_check(test_env, monkeypatch, bad):
    async def run():
        from memory_mcp.engine import maintenance
        from memory_mcp.storage.sqlite import get_db

        llm = FakeLLM(monkeypatch)
        await _add("tool:x", "merged", conflict=True)

        llm.override = bad
        await maintenance.run_once()
        jobs = await _jobs()
        assert jobs[0]["status"] == "failed"
        assert jobs[0]["error"].startswith("1 judgment(s) failed")
        assert len(llm.prompts) == 1  # not retried within the run
        async with get_db() as db:
            internal = await db.fetchone("SELECT count(*) AS n FROM memory_checks WHERE check_type = 'internal'")
        assert internal["n"] == 0

        llm.override = None
        await maintenance.run_once()
        assert (await _jobs())[1]["status"] == "done"
        async with get_db() as db:
            row = await db.fetchone("SELECT outcome FROM memory_checks WHERE check_type = 'internal'")
        assert row["outcome"] == "consistent"

    anyio.run(run)


def test_llm_request_failure_is_recorded(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance

        async def down(_prompt, timeout=30.0):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(maintenance, "chat", down)
        await _add("tool:x", "merged", conflict=True)
        await maintenance.run_once()
        job = (await _jobs())[0]
        assert job["status"] == "failed"
        assert "connection refused" in job["error"]

    anyio.run(run)


def _rest_app():
    import importlib

    from starlette.applications import Starlette
    from starlette.middleware import Middleware

    import memory_mcp.api.routes as routes_mod
    import memory_mcp.transport.auth as auth_mod

    importlib.reload(routes_mod)
    return Starlette(routes=routes_mod.routes, middleware=[Middleware(auth_mod.AuthMiddleware)])


_AUTH = {"Authorization": "Bearer test-token"}


def test_rest_run_returns_202_then_409_while_running_and_lists_findings_only(test_env, monkeypatch):
    async def run():
        import httpx

        from memory_mcp.engine import maintenance

        gate = anyio.Event()

        async def slow(prompt: str, timeout: float = 30.0) -> str:
            await gate.wait()
            verdict = "internal_contradiction" if "CLASH" in prompt else "consistent"
            return json.dumps({"verdict": verdict, "detail": "two states"})

        monkeypatch.setattr(maintenance, "chat", slow)
        clash = await _add("tool:x", "CLASH", conflict=True)
        await _add("tool:y", "fine", conflict=True)

        transport = httpx.ASGITransport(app=_rest_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post("/api/v1/maintenance/run", headers=_AUTH)
            assert first.status_code == 202
            job_id = first.json()["data"]["job_id"]
            second = await client.post("/api/v1/maintenance/run", headers=_AUTH)
            assert second.status_code == 409
            assert (await client.post("/api/v1/maintenance/run")).status_code == 401

            gate.set()
            await maintenance._task
            assert (await _jobs())[0]["status"] == "done"

            listed = (await client.get("/api/v1/findings?status=open", headers=_AUTH)).json()["data"]
            assert [(f["kind"], f["memory_id"]) for f in listed["items"]] == [("internal_contradiction", clash)]
            assert listed["total"] == 1
            none = (await client.get("/api/v1/findings?kind=duplicate", headers=_AUTH)).json()["data"]
            assert none == {"items": [], "total": 0}

            again = await client.post("/api/v1/maintenance/run", headers=_AUTH)
            assert again.status_code == 202
            assert again.json()["data"]["job_id"] != job_id
            await maintenance._task

    anyio.run(run)


def test_recall_is_not_blocked_while_a_run_waits_on_the_llm(test_env, monkeypatch):
    async def run():
        import time

        from memory_mcp.engine import maintenance
        from memory_mcp.tools import recall

        gate = anyio.Event()

        async def slow(prompt: str, timeout: float = 30.0) -> str:
            await gate.wait()
            return json.dumps({"verdict": "consistent", "detail": ""})

        monkeypatch.setattr(maintenance, "chat", slow)
        await _add("tool:x", "merged deploy note", conflict=True)
        await maintenance.start()

        started = time.perf_counter()
        res = await recall.recall_tool({"query": "deploy"})
        assert time.perf_counter() - started < 1.0
        assert res["total"] == 1

        gate.set()
        await maintenance._task

    anyio.run(run)


def test_service_shutdown_cancels_a_run_and_marks_it_failed(test_env, monkeypatch):
    async def run():
        import importlib

        import memory_mcp.server as server
        from memory_mcp.engine import maintenance

        importlib.reload(server)

        async def never(prompt: str, timeout: float = 30.0) -> str:
            await anyio.sleep_forever()

        monkeypatch.setattr(maintenance, "chat", never)
        await _add("tool:x", "merged", conflict=True)
        async with server.app.router.lifespan_context(server.app):
            await maintenance.start()
            await anyio.sleep(0.05)
        job = (await _jobs())[0]
        assert job["status"] == "failed"
        assert "CancelledError" in job["error"]
        assert not maintenance._running

    anyio.run(run)


def test_pair_finding_resolves_when_either_memory_evolves_and_new_version_is_checked(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance

        llm = FakeLLM(monkeypatch)
        a = await _add("fact:a", "DUP one", [1.0, 0.0, 0.0])
        b = await _add("fact:b", "DUP two", [0.99, 0.1, 0.0])
        await maintenance.run_once()
        assert len(await _findings(status="open")) == 1

        await _archive(b)
        b2 = await _add("fact:b", "DUP two, revised", [0.98, 0.15, 0.0])
        await maintenance.run_once()
        assert [f["memory_id"] for f in await _findings(status="resolved")] in ([a], [b])
        open_now = await _findings(status="open")
        assert [frozenset((f["memory_id"], f["other_memory_id"])) for f in open_now] == [frozenset((a, b2))]
        assert len([p for p in llm.prompts if "Memory A" in p]) == 2

    anyio.run(run)


def test_one_unjudgeable_memory_does_not_block_the_rest(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance
        from memory_mcp.storage.sqlite import get_db

        llm = FakeLLM(monkeypatch)
        real = llm.__call__

        async def flaky(prompt: str, timeout: float = 30.0) -> str:
            if "POISON" in prompt:
                llm.prompts.append(prompt)
                return "not json"
            return await real(prompt)

        monkeypatch.setattr(maintenance, "chat", flaky)
        await _add("tool:p", "POISON", conflict=True)
        await _add("tool:x", "CLASH", conflict=True)
        await _add("fact:a", "DUP one", [1.0, 0.0, 0.0])
        await _add("fact:b", "DUP two", [0.99, 0.1, 0.0])

        await maintenance.run_once()
        job = (await _jobs())[0]
        assert job["status"] == "failed" and job["error"].startswith("1 judgment(s) failed")
        assert {f["kind"] for f in await _findings()} == {"internal_contradiction", "duplicate"}
        async with get_db() as db:
            internal = await db.fetchall("SELECT outcome FROM memory_checks WHERE check_type = 'internal'")
        assert [r["outcome"] for r in internal] == ["internal_contradiction"]

    anyio.run(run)


def test_dismissed_multiple_current_is_not_reported_again(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance
        from memory_mcp.storage.sqlite import get_db

        FakeLLM(monkeypatch)
        await _add("fact:deploy", "v1")
        await _add("fact:deploy", "v2")
        await maintenance.run_once()
        async with get_db() as db:
            await db.execute("UPDATE memory_findings SET status = 'dismissed'")
        await maintenance.run_once()
        assert [f["status"] for f in await _findings()] == ["dismissed"]

    anyio.run(run)


def test_problem_verdict_without_detail_is_unusable(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance

        llm = FakeLLM(monkeypatch)
        llm.override = '{"verdict": "internal_contradiction", "detail": " "}'
        await _add("tool:x", "CLASH", conflict=True)
        await maintenance.run_once()
        assert (await _jobs())[0]["status"] == "failed"
        assert await _findings() == []

    anyio.run(run)


def test_service_start_runs_nothing_without_a_call(test_env, monkeypatch):
    async def run():
        import importlib

        import memory_mcp.server as server

        llm = FakeLLM(monkeypatch)
        importlib.reload(server)
        await _add("tool:x", "CLASH", conflict=True)
        async with server.app.router.lifespan_context(server.app):
            await anyio.sleep(0.05)
        assert await _jobs() == []
        assert llm.prompts == []

    anyio.run(run)


def test_unused_internal_budget_goes_to_pairs(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance
        from memory_mcp import settings_registry

        monkeypatch.setattr(settings_registry.settings, "maintenance_max_llm_calls", 4)
        llm = FakeLLM(monkeypatch)
        await _add("tool:t", "merged", conflict=True)
        for i in range(4):
            await _add(f"fact:p{i}", f"pair {i}", [1.0, 0.0, i / 100])

        await maintenance.run_once()
        internal = sum(1 for p in llm.prompts if "Memory A" not in p)
        assert (internal, len(llm.prompts) - internal) == (1, 3)

    anyio.run(run)


def test_cancel_before_the_run_starts_still_closes_the_job(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance

        FakeLLM(monkeypatch)
        await maintenance.start()
        await maintenance.stop()  # cancels before the task got a chance to run
        job = (await _jobs())[0]
        assert job["status"] == "failed"
        assert not maintenance._running
        await maintenance.run_once()

    anyio.run(run)


def test_failed_pair_is_retried_next_run(test_env, monkeypatch):
    async def run():
        from memory_mcp.engine import maintenance

        llm = FakeLLM(monkeypatch)
        a = await _add("fact:a", "DUP one", [1.0, 0.0, 0.0])
        b = await _add("fact:b", "DUP two", [0.99, 0.1, 0.0])
        llm.override = "garbage"
        await maintenance.run_once()
        assert (await _jobs())[0]["status"] == "failed"
        assert await _findings() == []

        llm.override = None
        await maintenance.run_once()
        assert [frozenset((f["memory_id"], f["other_memory_id"])) for f in await _findings()] == [
            frozenset((a, b))
        ]

    anyio.run(run)


def test_pairs_are_never_judged_contradictions(test_env, monkeypatch):
    """Cross-key contradiction was dropped (0 of 13 correct in production); that verdict is unusable."""
    async def run():
        from memory_mcp.engine import maintenance

        llm = FakeLLM(monkeypatch)
        await _add("fact:a", "one", [1.0, 0.0, 0.0])
        await _add("fact:b", "two", [0.99, 0.1, 0.0])
        llm.override = json.dumps({"verdict": "contradiction", "detail": "x vs y"})
        await maintenance.run_once()
        assert (await _jobs())[0]["status"] == "failed"
        assert await _findings() == []

    anyio.run(run)
