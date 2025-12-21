# Testing Guide

## Scope
- Tools: remember, recall, recall_all, trace, forget, relate, graph_query
- Engine: evolution inference and conflict handling
- Storage: vector/graph persistence

## Local Setup
1. Install dev deps: `pip install .[dev]`
2. Copy env template: `cp .env.example .env`
3. Fill required settings (auth token, OpenRouter key)
4. Run tests: `pytest`

Note: LanceDB may require a working pandas install in the runtime environment.
If you want to run without LanceDB, set `MEMORY_MCP_VECTOR_BACKEND=memory`.

## Unit Tests
- `tests/test_tools.py::test_remember_create_and_evolve`
- `tests/test_tools.py::test_recall_includes_relevance_and_evolution`
- `tests/test_tools.py::test_recall_all`
- `tests/test_tools.py::test_trace_summary_format`
- `tests/test_tools.py::test_graph_query_depth`

## Integration Test (Manual)
## Test Steps
1. Start server: `python -m memory_mcp`
2. Health check: `curl http://localhost:8765/health`
3. Initialize MCP session via POST `/mcp`
4. Call tools in order: remember -> recall -> trace -> forget -> relate -> graph_query
5. Expect valid JSON responses and archived memories excluded from recall
