---
name: save-memory
description: Save important information to long-term memory. Use when an important decision is made, a hard problem is solved, or a new preference is discovered.
---

Save to long-term memory using the `mem` CLI:

```bash
mem remember "concise description of what to remember" --type <type> --key <entity_key>
```

Types: `preference`, `fact`, `event`, `goal`, `project`, `person`

Key format: `type:name` (e.g., `preference:editor`, `project:memory-mcp`, `fact:timezone`)

When to save:
- Important decision made (e.g., "chose PostgreSQL over MySQL for X reason")
- Hard problem solved with root cause
- New preference or habit discovered
- Project context that should persist across sessions

When NOT to save:
- Temporary debugging details
- Generic/widely-known information
- Information already stored (check with `mem recall` first)
