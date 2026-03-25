---
name: search-memory
description: Search long-term memory for relevant context. Use when the user references previous decisions, preferences, projects, or when you need prior context.
---

Search your long-term memory using the `mem` CLI:

```bash
mem recall "your search query" --format text
```

Use this when:
- The user mentions something from a previous session
- You need context about their preferences or past decisions
- Debugging a problem that seems familiar
- The user asks "do you remember..."

Search tips:
- Use natural language queries
- Add `--type preference` to filter by type (preference/fact/event/goal/project/person)
- Add `--limit 5` to limit results
