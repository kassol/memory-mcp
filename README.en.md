# Memory MCP

[中文](README.md)

Personal memory service powered by **MCP Streamable HTTP**. It combines **semantic vector search** and a lightweight **knowledge graph** to persist long-term context, with full traceability of memory evolution (instead of overwriting).

## Features

- **MCP Streamable HTTP** transport (no deprecated SSE)
- **Bearer token auth**: `/mcp` requires `Authorization: Bearer <token>` (`/health` is public)
- **Memory evolution** per `entity_key` with history tracing (`trace`)
- **Conflict detection & labels** (also on exact matches): `conflict / correction / reversal`
- **Semantic recall** via OpenRouter Embedding API (`recall`)
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
- `recall(query, limit?)`: semantic search over current memories; items include `memory_id`, `entity_key`, `content`, `created_at`
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
