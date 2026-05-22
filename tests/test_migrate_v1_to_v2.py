import importlib
import json
import shutil
from pathlib import Path

import anyio


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "v1_data"


def _copy_fixture(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(FIXTURE_DIR, dst)


def test_migrate_v1_data_to_v2(test_env, tmp_path):
    async def run():
        _copy_fixture(tmp_path / "v1_src")

        import memory_mcp.scripts.migrate_v1_to_v2 as migrate_mod
        importlib.reload(migrate_mod)

        report = await migrate_mod.migrate(
            src=tmp_path / "v1_src",
            dst=Path(migrate_mod.settings.data_dir),
            backup=None,
            verify=True,
            dry_run=False,
        )

        # Source counts
        with open(FIXTURE_DIR / "vectors" / "memories.json", encoding="utf-8") as f:
            src_memories = json.load(f)
        with open(FIXTURE_DIR / "graph" / "entities.json", encoding="utf-8") as f:
            src_entities = json.load(f)
        with open(FIXTURE_DIR / "graph" / "relations.json", encoding="utf-8") as f:
            src_relations = json.load(f)

        assert report["memories_count"] == len(src_memories)
        assert report["entities_count"] == len(src_entities)
        assert report["relations_count"] == len(src_relations)
        assert report["fts_rows"] == len(src_memories)
        assert report["vector_rows"] == len(src_memories)
        assert report["fk_violations"] == 0
        assert report["all_have_review_status_legacy"] is True

    anyio.run(run)


def test_dry_run_does_not_write(test_env, tmp_path):
    async def run():
        _copy_fixture(tmp_path / "v1_src")

        import memory_mcp.scripts.migrate_v1_to_v2 as migrate_mod
        importlib.reload(migrate_mod)

        report = await migrate_mod.migrate(
            src=tmp_path / "v1_src",
            dst=Path(migrate_mod.settings.data_dir),
            backup=None,
            verify=False,
            dry_run=True,
        )
        # report still tells you what would have been written
        assert report["memories_count"] > 0
        # but no SQLite memories were inserted
        import memory_mcp.storage.sqlite as sqlite_mod
        importlib.reload(sqlite_mod)
        async with sqlite_mod.get_db() as db:
            row = await db.fetchone("SELECT count(*) AS c FROM memories")
        assert row["c"] == 0

    anyio.run(run)


def test_backup_archive_created(test_env, tmp_path):
    async def run():
        _copy_fixture(tmp_path / "v1_src")
        backup_path = tmp_path / "backup.tgz"
        import memory_mcp.scripts.migrate_v1_to_v2 as migrate_mod
        importlib.reload(migrate_mod)
        await migrate_mod.migrate(
            src=tmp_path / "v1_src",
            dst=Path(migrate_mod.settings.data_dir),
            backup=backup_path,
            verify=False,
            dry_run=False,
        )
        assert backup_path.exists()
        assert backup_path.stat().st_size > 0

    anyio.run(run)
