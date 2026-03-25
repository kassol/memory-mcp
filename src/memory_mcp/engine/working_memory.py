from datetime import datetime, timezone, timedelta

from ..storage.vector import vector_store


async def generate_briefing() -> str:
    nodes = await vector_store.list_current(limit=200)

    if not nodes:
        return "No memories yet."

    # Group by entity_type
    by_type: dict[str, list] = {}
    for node in nodes:
        by_type.setdefault(node.entity_type, []).append(node)

    lines: list[str] = []

    # --- Active Context ---
    lines.append("## Active Context")
    for entity_type, type_nodes in sorted(by_type.items()):
        for node in type_nodes:
            lines.append(f"- [{entity_type}] {node.entity_key}: {node.content}")

    # --- Recent Changes (7d) ---
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent = [
        n for n in nodes
        if n.parent_id is not None and n.created_at >= cutoff
    ]
    recent = recent[:20]

    if recent:
        lines.append("")
        lines.append("## Recent Changes (7d)")
        for node in recent:
            old_node = await vector_store.get_by_id(node.parent_id)
            old_content = old_node.content if old_node else "?"
            lines.append(f"- {node.entity_key} -- {old_content} -> {node.content}")

    # --- Flags ---
    conflicts = [n for n in nodes if n.conflict]
    if conflicts:
        lines.append("")
        lines.append("## Flags")
        for node in conflicts:
            lines.append(f"- [conflict] {node.entity_key} -- conflicting info")

    return "\n".join(lines)
