# Memory MCP

[中文](README.md)

Personal memory service powered by **MCP Streamable HTTP**. It combines **semantic vector search** and a lightweight **knowledge graph** to persist long-term context, with full traceability of memory evolution (instead of overwriting).

## Features

- **MCP Streamable HTTP** transport (no deprecated SSE)
- **Bearer token auth**: `/mcp` requires `Authorization: Bearer <token>` (`/health` is public)
- **Memory evolution** per `entity_key` with history tracing (`trace`)
- **Conflict detection & labels** (also on exact matches): `conflict / correction / reversal`
- **Hybrid recall** (`recall`): vector (OpenRouter Embedding), FTS5 keywords (jieba tokens) and graph one-hop, fused by weighted RRF, so model names and version strings also match
- **Knowledge graph relations** with BFS depth query (REST / CLI: `relate` / `graph_query`)
- **Test-friendly storage**: LanceDB by default, `MEMORY_MCP_VECTOR_BACKEND=memory` backend for tests

## Endpoints

- **MCP**: `/mcp` (Streamable HTTP)
- **Health**: `/health`

## Quick Start (Local)

1. Install: `pip install .`
2. Create `.env`: `cp .env.example .env` and set at least:
   - `MEMORY_MCP_AUTH_TOKEN`
   - `MEMORY_MCP_OPENROUTER_API_KEY`
3. Run: `python -m memory_mcp`
4. Check: `curl http://127.0.0.1:8765/health`

## Docker (Recommended)

1. Configure: `cp .env.example .env`
2. Build & run: `docker compose up -d --build`

Notes:
- `docker-compose.yml` binds the service to the host loopback address `127.0.0.1:18765` only.
- In production, a reverse proxy on the host terminates HTTPS and forwards to `http://127.0.0.1:18765`.

## Environment Variables

See `.env.example`.

- **Required**
  - `MEMORY_MCP_AUTH_TOKEN`
  - `MEMORY_MCP_OPENROUTER_API_KEY`
- **Common**
  - `MEMORY_MCP_HOST` (default `0.0.0.0`)
  - `MEMORY_MCP_PORT` (default `8765`)
  - `MEMORY_MCP_DATA_DIR` (default `./data`)
  - `MEMORY_MCP_DEBUG` (default `false`)
- **Vector backend (optional)**
  - `MEMORY_MCP_VECTOR_BACKEND`: `lancedb` (default) / `memory` / `auto`
  - Production should use `lancedb`; LanceDB startup failure stops the service so existing memories stay visible as a deployment issue
  - `memory` is useful for tests; `auto` switches to `memory` after LanceDB initialization failure

## MCP Client Config (Example)

Replace the domain and token:

```json
{
  "mcpServers": {
    "memory-mcp": {
      "url": "https://memory-mcp.your-domain.com/mcp",
      "transport": { "type": "http" },
      "headers": {
        "Authorization": "Bearer your-secure-token-here"
      }
    }
  }
}
```

## Tools

MCP exposes 4 tools and no resources (returning every memory at once would overflow client context):

- `remember(content, title?, tags?)`: store one long-lived fact; the server assigns `entity_key` against similar stored memories, then merges and labels conflicts on the same subject
- `recall(query, limit?)`: hybrid search over current memories; items include `memory_id`, `entity_key`, `content`, `created_at`; `relevance` is the fused score, comparable only within one result list
- `forget(memory_id, reason?)`: archive one current memory by id
- `trace(entity_key, format?)`: evolution chain (timeline/summary)

`recall_all`, `relate`, `unrelate`, `graph_query` and archive-by-`entity_key` are available only through the REST API / CLI.

## Development & Testing

- Dev deps: `pip install .[dev]`
- Tests: `pytest`
- Lint: `ruff check .`

More details: `docs/testing.md`

## License

MIT License. See `LICENSE`.

## Backup

On the deploy host, run `ops/backup-db.sh` daily from cron. It keeps the newest 7 snapshots of SQLite and the vector store under `data/backups/`. To restore, stop the service, copy `memory.sqlite3` and `vectors/` from a backup directory over the same files in `data/`, then start it again.

## Console

The service serves a management console at `/ui/` (a React single-page app; source in `web/`): open findings, records with version history, and settings. Sign in with the access token (`MEMORY_MCP_AUTH_TOKEN`); it is kept in the current tab only.

- The Dockerfile builds the console in a Node stage and copies the output into the Python package's `ui/` directory. The output is not committed, and the runtime image has no Node.
- Local development: `cd web && pnpm install && pnpm dev` (the Vite dev server proxies `/api` to `127.0.0.1:8765`). `pnpm build` writes the output to `src/memory_mcp/ui/`.
- Frontend checks: `pnpm typecheck`, `pnpm lint`, `pnpm test`.

## Settings

Behaviour settings (semantic merge threshold, maintenance LLM budget) and tuning parameters (hybrid recall and maintenance check values such as `fts_weight`, `rrf_k`, `cross_key_min_cosine`) can be changed on the console's settings page; a save applies on the next call. The effective value is the console value, else the configuration file or environment (`MEMORY_MCP_<KEY>`, for example `MEMORY_MCP_FTS_WEIGHT`), else the default. The console shows the source of each value and can revert to the file value. A configuration-file value outside its range stops the service at start with the reason. REST: `GET /api/v1/settings`, `PUT /api/v1/settings/{key}` (`{value}`), `DELETE /api/v1/settings/{key}` (revert).

## Maintenance

Maintenance checks find memories that a person should review. The results are called findings (terms in `GLOSSARY.md`): cross-key duplicates, internal contradictions, and keys with more than one current version. Checks only create findings; they never archive or merge.

- The service never starts maintenance by itself. On the deploy host, run `ops/run-maintenance.sh` daily from cron (after the backup). It calls `POST /api/v1/maintenance/run`, which runs one round in the background; it returns 409 while a round is in progress.
- The setting `maintenance_max_llm_calls` limits LLM calls per round (default 100; console or `MEMORY_MCP_MAINTENANCE_MAX_LLM_CALLS`); work left over goes to the next round.
- Read findings with `GET /api/v1/findings?status=open&kind=`. Per-round counts and errors are in the `jobs` table (`job_type = 'maintenance'`).

Example cron (`/etc/cron.d/memory-mcp-maintenance`, 20:17 UTC):

```
17 20 * * * root /opt/memory-mcp/ops/run-maintenance.sh >> /var/log/memory-mcp-maintenance.log 2>&1
```
