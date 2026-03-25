from datetime import datetime, timezone, timedelta
from pathlib import PurePosixPath

from ..storage.vector import vector_store

_PROJECT_MAX = 5
_PREF_MAX = 5
_RECENT_MAX = 5


def _infer_project_name(cwd: str | None) -> str | None:
    if not cwd:
        return None
    skip = {"home", "Users", "root", "tmp", "var", "opt",
            "Workspace", "workspace", "projects", "src", "code", "dev"}
    for part in reversed(PurePosixPath(cwd).parts):
        if part not in skip and not part.startswith(".") and part != "/":
            return part.lower()
    return None


def _matches_project(entity_key: str, content: str, project_name: str) -> bool:
    return project_name in entity_key.lower() or project_name in content.lower()


async def generate_briefing(cwd: str | None = None) -> str:
    all_nodes = await vector_store.list_current(limit=200)
    if not all_nodes:
        return "No memories yet."

    project_name = _infer_project_name(cwd)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # Classify
    project_nodes = []
    preference_nodes = []
    recent_nodes = []
    conflict_nodes = []

    for node in all_nodes:
        if node.conflict:
            conflict_nodes.append(node)
        if project_name and _matches_project(node.entity_key, node.content, project_name):
            project_nodes.append(node)
        if node.entity_type == "preference":
            preference_nodes.append(node)
        if node.parent_id is not None and node.created_at >= cutoff:
            recent_nodes.append(node)

    preference_nodes.sort(key=lambda n: n.created_at, reverse=True)
    recent_nodes.sort(key=lambda n: n.created_at, reverse=True)

    seen: set[str] = set()
    lines: list[str] = []

    def _add(node) -> bool:
        if node.entity_key in seen:
            return False
        seen.add(node.entity_key)
        lines.append(f"- [{node.entity_type}] {node.entity_key}: {node.content}")
        return True

    # Tier 1: Project (only when cwd matches)
    if project_nodes:
        lines.append(f"## Project: {project_name}")
        count = 0
        for node in project_nodes:
            if count >= _PROJECT_MAX:
                break
            if _add(node):
                count += 1

    # Tier 2: Preferences (always full budget, full content)
    added = 0
    start = len(lines)
    for node in preference_nodes:
        if added >= _PREF_MAX:
            break
        if _add(node):
            added += 1
    if added:
        lines.insert(start, "## Preferences")

    # Tier 3: Recent Changes
    if recent_nodes:
        rc_start = len(lines)
        rc_count = 0
        for node in recent_nodes[:_RECENT_MAX]:
            old = await vector_store.get_by_id(node.parent_id)
            old_summary = old.content if old else "?"
            lines.append(f"- {node.entity_key}: {old_summary} -> {node.content}")
            seen.add(node.entity_key)
            rc_count += 1
        if rc_count:
            lines.insert(rc_start, "## Recent Changes (7d)")

    # Tier 4: Conflicts
    if conflict_nodes:
        lines.append("## Flags")
        for node in conflict_nodes:
            lines.append(f"- [conflict] {node.entity_key}: {node.content}")

    return "\n".join(lines) if lines else "No memories yet."
