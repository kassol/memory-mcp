#!/bin/sh
# Back up the SQLite database and the vector store, keeping the newest 7 copies.
# Run from cron on the deploy host; backups land in data/backups/, which deploys leave alone.
set -eu
cd "$(dirname "$0")/.."

docker compose exec -T memory-mcp python - <<'EOF'
import datetime
import pathlib
import shutil
import sqlite3
import sys

data = pathlib.Path("/app/data")
root = data / "backups"
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
dst = root / stamp
dst.mkdir(parents=True)

# The backup API copies a consistent snapshot even while the service writes (WAL mode).
src = sqlite3.connect(f"file:{data / 'memory.sqlite3'}?mode=ro", uri=True)
out = sqlite3.connect(dst / "memory.sqlite3")
src.backup(out)
src.close()
check = out.execute("PRAGMA integrity_check").fetchone()[0]
rows = out.execute("SELECT count(*), sum(is_current) FROM memories").fetchone()
out.close()
if check != "ok":
    shutil.rmtree(dst)
    sys.exit(f"backup failed integrity_check: {check}")

shutil.copytree(data / "vectors", dst / "vectors")

# Prune only after a verified backup, so a failing run never removes good copies.
for old in sorted(p for p in root.iterdir() if p.is_dir())[:-7]:
    shutil.rmtree(old)
print(f"backup {stamp}: {rows[0]} rows, {rows[1]} current, integrity ok")
EOF
