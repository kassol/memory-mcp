# Memory MCP Claude Code Plugin

Integrates long-term memory into Claude Code via hooks, skills, and slash commands.

## Prerequisites

- `mem` CLI installed: `pipx install memory-mcp-cli` or `uv tool install memory-mcp-cli`
- `mem` configured: `~/.config/memory-mcp/config.json` with `api_url` and `api_key`
- `python3` available in PATH

## Installation

Add hooks to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "/path/to/claude-code-plugin/hooks/session-start.sh",
        "timeout": 10
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "/path/to/claude-code-plugin/hooks/stop.sh",
        "async": true,
        "timeout": 120
      }
    ]
  }
}
```

Copy skills to your Claude Code skills directory, or reference them from this repo.

## What it Does

| Component | Behavior |
|-----------|----------|
| **SessionStart hook** | Injects working memory briefing as context |
| **Stop hook** | Extracts memories from conversation transcript (async) |
| **search-memory skill** | Guides Claude to search long-term memory |
| **save-memory skill** | Guides Claude to save important information |
| **/save** | Quick save to memory |
| **/search** | Quick search in memory |
| **/status** | Show service status and current context |
