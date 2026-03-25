from datetime import datetime, timezone, timedelta
from pathlib import PurePosixPath

from ..storage.vector import vector_store

# Limits
_MAX_PROJECT = 5
_MAX_PREFERENCE = 5
_MAX_RECENT = 5
_CONTENT_LIMIT = 80


def _truncate(text: str, limit: int = _CONTENT_LIMIT) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[:limit - 1] + "..."


def _infer_project_name(cwd: str | None) -> str | None:
    """Infer project name from cwd path (last meaningful directory component)."""
    if not cwd:
        return None
    parts = PurePosixPath(cwd).parts
    # Skip common non-project dirs
    skip = {"home", "Users", "root", "tmp", "var", "opt", "Workspace", "workspace", "projects", "src", "code", "dev"}
    for part in reversed(parts):
        if part not in skip and not part.startswith(".") and part != "/":
            return part.lower()
    return None


def _matches_project(entity_key: str, content: str, project_name: str) -> bool:
    """Check if a memory is relevant to the given project."""
    key_lower = entity_key.lower()
    content_lower = content.lower()
    return project_name in key_lower or project_name in content_lower


async def generate_briefing(cwd: str | None = None) -> str:
    all_nodes = await vector_store.list_current(limit=200)

    if not all_nodes:
        return "No memories yet."

    project_name = _infer_project_name(cwd)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # Classify nodes
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

    # Sort by recency
    preference_nodes.sort(key=lambda n: n.created_at, reverse=True)
    recent_nodes.sort(key=lambda n: n.created_at, reverse=True)

    # Deduplicate: track entity_keys already shown
    seen_keys: set[str] = set()
    lines: list[str] = []

    def _add_item(node, prefix: str = "") -> bool:
        if node.entity_key in seen_keys:
            return False
        seen_keys.add(node.entity_key)
        label = prefix or f"[{node.entity_type}]"
        lines.append(f"- {label} {node.entity_key}: {_truncate(node.content)}")
        return True

    # Tier 1: Project-related
    if project_nodes:
        lines.append(f"## Project: {project_name}")
        count = 0
        for node in project_nodes:
            if count >= _MAX_PROJECT:
                break
            if _add_item(node):
                count += 1

    # Tier 2: Preferences
    added = 0
    pref_lines_start = len(lines)
    for node in preference_nodes:
        if added >= _MAX_PREFERENCE:
            break
        if _add_item(node):
            added += 1
    if added > 0:
        lines.insert(pref_lines_start, "## Preferences")

    # Tier 3: Recent Changes (7d)
    if recent_nodes:
        rc_start = len(lines)
        rc_count = 0
        for node in recent_nodes[:_MAX_RECENT]:
            if node.entity_key in seen_keys:
                # Still show the change even if key was shown above
                pass
            old = await vector_store.get_by_id(node.parent_id)
            old_text = _truncate(old.content, 40) if old else "?"
            new_text = _truncate(node.content, 40)
            lines.append(f"- {node.entity_key}: {old_text} -> {new_text}")
            seen_keys.add(node.entity_key)
            rc_count += 1
        if rc_count > 0:
            lines.insert(rc_start, "## Recent Changes (7d)")

    # Tier 4: Conflicts
    if conflict_nodes:
        lines.append("## Flags")
        for node in conflict_nodes:
            lines.append(f"- [conflict] {node.entity_key}: {_truncate(node.content)}")

    return "\n".join(lines) if lines else "No memories yet."
