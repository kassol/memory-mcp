---
version: 1
slug: "src-memory-mcp-ui-index-html"
primary_target: "src/memory_mcp/ui/index.html"
related_targets: ["web/src/shell.tsx","web/src/index.css","web/src/pages/docket.tsx","web/src/pages/records.tsx","web/src/pages/settings.tsx","web/src/pages/overview.tsx"]
---

Scope: the whole web console at /ui/ (single page app, Operate mode). One owner, desktop first, phone usable. Job: clear the open findings queue; correct or archive wrong memories; browse stale memories and tune the service.

The console is porcelain and graphite with one deep-pine accent: modern, restrained, editorial, not the shadcn default. Status is dots and words. Light is a working paper surface; dark is the same system at night. Generated shadcn components stay as generated; theme tokens in `web/src/index.css` and page layouts carry the look.

## Direction contract

THESIS: A quiet review desk, not a dashboard. The docket is the front page; every other screen supports it. The category-default grid of equal cards is refused.

OWN-WORLD: Porcelain #F6F6F3 ground, white panels, graphite #17181A ink, hairline borders, 11px radii, one deep-pine #245C4F accent, amber/slate data colors, Geist plus a CJK sans; dots for status, no gradients, glass, stamps or ornamental rules.

STORY: The owner opens the console, sees how many findings wait and of what kind, filters the queue, reads two records side by side, corrects or archives one, and moves to the next. The same grammar carries records, charts and settings.

FIRST VIEWPORT: A full-width finding band: large count at 46px, a short hint, and a two-column kind breakdown with counts on the right, then two secondary panels (memory totals, last maintenance) and one 30-day chart panel. The primary action is 去处理, top right.

FORM: The grounded "porcelain desk" direction, chosen by the owner from the third decision round. Seed key 70309f1f.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
