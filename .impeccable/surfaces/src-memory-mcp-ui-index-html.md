---
version: 1
slug: "src-memory-mcp-ui-index-html"
primary_target: "src/memory_mcp/ui/index.html"
related_targets: ["web/src/shell.tsx","web/src/index.css","web/src/pages/docket.tsx","web/src/pages/records.tsx","web/src/pages/settings.tsx"]
---

Scope: the whole web console at /ui/ (single page app, Operate mode). Audience: the single owner of the memory service, desktop first, phone usable. Job: clear the open findings queue; correct or archive wrong memories; browse stale memories.

## Direction contract

The console uses shadcn/ui with its default look (radix-nova, neutral, Geist); see DESIGN.md. The earlier records-registry direction is retired (2026-10-31, owner's decision).
