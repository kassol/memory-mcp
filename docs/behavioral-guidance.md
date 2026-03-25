# Memory Behavioral Guidance

Embed this in your AI tool's system prompt to enable memory-aware behavior.

---

## Memory Available
- Search memories: `mem recall "query"`
- Save important info: `mem remember "content" --type <type> --key <key>`
- View current context: `mem wm`

## When to Search
- User references previous decisions, preferences, or projects
- Debugging a familiar-looking issue
- Need context from previous sessions

## When to Save
- Important decision made (with rationale)
- Hard problem solved (with root cause)
- New preference or habit discovered
- Do NOT save temporary, generic, or widely-known information

## Entity Types
- `preference` — user preferences and choices
- `fact` — factual information about the user
- `event` — notable events
- `goal` — goals and objectives
- `project` — project context
- `person` — people and relationships
