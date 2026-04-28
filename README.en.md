# Memory MCP

[中文](README.md)

Personal memory service powered by **MCP Streamable HTTP**. It combines **semantic vector search** and a lightweight **knowledge graph** to persist long-term context, with full traceability of memory evolution (instead of overwriting).

## Features

- **MCP Streamable HTTP** transport (no deprecated SSE)
- **Bearer token auth**: `/mcp` requires `Authorization: Bearer <token>` (`/health` is public)
- **Memory evolution** per `entity_key` with history tracing (`trace`)
- **Conflict detection & labels** (also on exact matches): `conflict / correction / reversal`
- **Semantic recall** via OpenRouter Embedding API (`recall`)
- **Knowledge graph relations** with BFS depth query (`relate` / `graph_query`)
- **MCP resources**: `memory:///...` (current/entities/entity)
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
- `docker-compose.yml` **does not expose port 8765** by default.
- For local debugging, add:
  ```yaml
  ports:
    - "8765:8765"
  ```
- In production, expose HTTPS via **Cloudflare Tunnel / reverse proxy**.

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
- **Cloudflare Tunnel (optional)**
  - `CLOUDFLARE_TUNNEL_TOKEN`

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

- `remember`: write/evolve memory (+ conflict labels)
- `recall`: semantic search (optionally include evolution metadata)
- `recall_all`: load all current memories
- `trace`: evolution chain (timeline/summary)
- `forget`: archive current memory for an entity
- `relate`: create relations between entities
- `graph_query`: query relations with BFS depth (in + out edges)

## Resources

- `memory:///current`
- `memory:///entities`
- `memory:///entity/{entity_key}`

## Development & Testing

- Dev deps: `pip install .[dev]`
- Tests: `pytest`
- Lint: `ruff check .`

More details: `docs/testing.md`

## License

MIT License. See `LICENSE`.
