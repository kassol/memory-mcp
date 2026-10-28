import importlib
import json

import anyio
from typer.testing import CliRunner


def _rec(mid, created_at, content, **extra):
    return {"id": mid, "title": f"t-{mid}", "content": content, "created_at": created_at, **extra}


RECORDS = [
    _rec("n3", "2026-07-01T00:00:00+00:00", "Lives in Shanghai"),
    _rec("n1", "2026-05-01T00:00:00+00:00", "Lives in Beijing"),
    _rec("n2", "2026-06-01T00:00:00+00:00", "Prefers Cursor as main editor"),
]

KEYS = {
    "Lives in Beijing": ("fact:home_city", "fact"),
    "Lives in Shanghai": ("fact:home_city", "fact"),
    "Prefers Cursor as main editor": ("preference:main_editor", "preference"),
}


def _setup(monkeypatch, fail_on=()):
    import memory_mcp.engine.key_assignment as key_mod
    import memory_mcp.scripts.import_nowledge as imp

    importlib.reload(imp)
    calls = []

    async def fake_assign(content, embedding=None):
        calls.append(content)
        if content in fail_on:
            raise key_mod.KeyAssignmentError("bad output")
        return KEYS[content]

    monkeypatch.setattr(key_mod, "assign_entity_key", fake_assign)
    monkeypatch.setattr(imp, "fetch_labels", lambda mid: [f"label-{mid}"])
    return imp, calls


def test_load_records_accepts_list_output_and_jsonl(tmp_path):
    import memory_mcp.scripts.import_nowledge as imp

    as_json = tmp_path / "a.json"
    as_json.write_text(json.dumps({"memories": RECORDS, "total": 3}))
    as_jsonl = tmp_path / "a.jsonl"
    as_jsonl.write_text("\n".join(json.dumps(r) for r in RECORDS) + "\n")
    assert imp.load_records(as_json) == RECORDS
    assert imp.load_records(as_jsonl) == RECORDS


def test_select_current_sorts_ascending():
    import memory_mcp.scripts.import_nowledge as imp

    assert [r["id"] for r in imp.select_current(RECORDS, [])] == ["n1", "n2", "n3"]


def test_select_current_drops_replaced_by_listed_memory():
    import memory_mcp.scripts.import_nowledge as imp

    records = RECORDS + [_rec("n0", "2026-04-01T00:00:00.5+00:00", "Old fact"), _rec("n4", "2026-04-02T00:00:00+00:00", "")]
    edges = [
        {"older_id": "n1", "newer_id": "n3", "content_relation": "replaces"},
        {"older_id": "n2", "newer_id": "n3", "content_relation": "enriches"},
        # replacement is not listed (archived/forgotten), so n0 stays current
        {"older_id": "n0", "newer_id": "gone", "content_relation": "replaces"},
    ]
    assert [r["id"] for r in imp.select_current(records, edges)] == ["n0", "n2", "n3"]


def test_import_writes_in_order_and_resumes(tools, test_env, monkeypatch, tmp_path):
    async def run():
        imp, calls = _setup(monkeypatch)
        _, vector, _ = test_env
        state_path = tmp_path / "state.json"
        records = imp.select_current(RECORDS, [])

        first = await imp.run_import(records, state_path, limit=2)
        assert first["processed"] == 2 and first["created"] == 2 and first["failed"] == 0
        assert calls == ["Lives in Beijing", "Prefers Cursor as main editor"]

        second = await imp.run_import(records, state_path)
        assert calls[2:] == ["Lives in Shanghai"]
        assert second["processed"] == 1 and second["evolved"] == 1 and second["skipped_already_done"] == 2

        state = json.loads(state_path.read_text())
        assert state["done"] == ["n1", "n2", "n3"] and state["failed"] == []

        history = await vector.vector_store.get_history("fact:home_city")
        current = next(h for h in history if h.is_current)
        assert current.content == "Lives in Shanghai"
        assert current.origin_client == "nowledge" and current.origin_session_id == "n3"
        first_node = next(h for h in history if not h.is_current)
        assert first_node.tags == ["label-n1"]

    anyio.run(run)


def test_import_single_failure_continues_and_retries(tools, test_env, monkeypatch, tmp_path):
    async def run():
        imp, _ = _setup(monkeypatch, fail_on={"Prefers Cursor as main editor"})
        state_path = tmp_path / "state.json"
        records = imp.select_current(RECORDS, [])

        report = await imp.run_import(records, state_path)
        assert report["failed"] == 1 and report["created"] == 1 and report["evolved"] == 1
        state = json.loads(state_path.read_text())
        assert state["done"] == ["n1", "n3"]
        assert state["failed"][0]["id"] == "n2" and "bad output" in state["failed"][0]["error"]

        imp, calls = _setup(monkeypatch)
        retry = await imp.run_import(records, state_path)
        assert calls == ["Prefers Cursor as main editor"]
        assert retry["created"] == 1 and retry["failed_total_in_state"] == 0
        assert json.loads(state_path.read_text())["failed"] == []

    anyio.run(run)


def test_dry_run_does_not_call_llm_or_write(tools, test_env, monkeypatch, tmp_path):
    imp, calls = _setup(monkeypatch)

    async def must_not_run(*_args, **_kwargs):
        raise AssertionError("dry-run must not import")

    edges_by_id = {"n1": [{"older_id": "n1", "newer_id": "n3", "content_relation": "replaces"}]}
    monkeypatch.setattr(imp, "run_import", must_not_run)
    monkeypatch.setattr(imp, "fetch_evolves", lambda mid: edges_by_id.get(mid, []))
    input_path = tmp_path / "export.json"
    input_path.write_text(json.dumps({"memories": RECORDS}))
    state_path = tmp_path / "state.json"

    result = CliRunner().invoke(
        imp.app, ["--input", str(input_path), "--state", str(state_path), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    out = result.output
    summary = json.loads(out[out.index("{") : out.index("}") + 1])
    assert summary["total"] == 3 and summary["excluded"] == 1 and summary["current"] == 2
    assert summary["earliest_created_at"] == "2026-06-01T00:00:00+00:00"
    assert summary["latest_created_at"] == "2026-07-01T00:00:00+00:00"
    assert calls == [] and not state_path.exists()
    assert json.loads((tmp_path / "export.json.evolves.json").read_text()) == edges_by_id["n1"]
