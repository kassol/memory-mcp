---
version: 1
slug: "src-memory-mcp-ui-index-html"
primary_target: "src/memory_mcp/ui/index.html"
related_targets: ["src/memory_mcp/ui/app.js","src/memory_mcp/ui/style.css"]
---

Scope: the whole web console at /ui/ (single page app, Operate mode). Audience: the single owner of the memory service, desktop first, phone usable. Job: clear the open findings queue; correct or archive wrong memories; browse stale memories.

## Direction contract

THESIS: the console is a records registry, not a dashboard. Every memory is a filed record with an identifier; the findings queue is the docket of cases awaiting a ruling. Refuses the category default of metric cards and a sidebar of charts.

OWN-WORLD: neutral grey ledger ground, system sans for text, tabular monospace only for identifiers, dates and counts. Thin ruled rows on one baseline. One accent (ink blue in light, lighter blue in dark) only for the current row, focus and the primary action. Status shows as small outlined stamps: current, archived, correction, conflict.

STORY: open the console, see how many cases are on the docket, take the first case, read both records side by side in full, rule on it (correct, archive, or dismiss), move to the next.

FIRST VIEWPORT: top bar with the registry name, two tabs (docket with its count, records; search lives at the top of the records list, since a search result is a filtered records list). Left column a list of cases; right the case file with both records in two equal columns, full text, and the ruling actions under them. On phones the list and the case file are separate views.

FORM: archival registry and docket, candidate 7 of 7; seed key c7b7baee.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
