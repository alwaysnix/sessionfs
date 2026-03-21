"""Markdown renderer for .sfs sessions."""

from __future__ import annotations

import json
from typing import Any


def _render_block(block: dict[str, Any]) -> str:
    """Render a single content block as markdown."""
    btype = block.get("type")

    if btype == "text":
        return block.get("text", "")

    elif btype == "thinking":
        text = block.get("text", "")
        if block.get("redacted"):
            text = "[Thinking content redacted]"
        return f"<details>\n<summary>Thinking</summary>\n\n{text}\n\n</details>"

    elif btype == "tool_use":
        name = block.get("name", "unknown")
        tool_input = block.get("input", {})
        input_str = json.dumps(tool_input, indent=2)
        return f"**Tool:** `{name}`\n```json\n{input_str}\n```"

    elif btype == "tool_result":
        content = block.get("content", "")
        is_error = block.get("is_error", False)
        label = "Error" if is_error else "Result"
        # Truncate very long results
        if len(content) > 2000:
            content = content[:2000] + "\n... (truncated)"
        return f"**{label}:**\n```\n{content}\n```"

    elif btype == "summary":
        return f"> **Summary:** {block.get('text', '')}"

    elif btype == "image":
        source = block.get("source", {})
        src_type = source.get("type")
        if src_type == "url":
            return f"![image]({source.get('data', '')})"
        return "[Image]"

    else:
        return f"[{btype} block]"


def render_session_markdown(
    manifest: dict[str, Any],
    messages: list[dict[str, Any]],
) -> str:
    """Render a full .sfs session as markdown.

    Skips sidechain messages.
    """
    parts: list[str] = []

    # Header
    title = manifest.get("title") or "Untitled Session"
    parts.append(f"# {title}")
    parts.append("")

    session_id = manifest.get("session_id", "")
    source = manifest.get("source", {})
    model = manifest.get("model", {})
    stats = manifest.get("stats", {})
    created = manifest.get("created_at", "")

    meta_parts = [f"**Session ID:** `{session_id}`"]
    if source.get("tool"):
        meta_parts.append(f"**Tool:** {source['tool']}")
    if model.get("model_id"):
        meta_parts.append(f"**Model:** {model['model_id']}")
    if created:
        meta_parts.append(f"**Created:** {created}")

    parts.append(" | ".join(meta_parts))

    if stats:
        stat_items = []
        if stats.get("message_count"):
            stat_items.append(f"**Messages:** {stats['message_count']}")
        if stats.get("turn_count"):
            stat_items.append(f"**Turns:** {stats['turn_count']}")
        if stats.get("tool_use_count"):
            stat_items.append(f"**Tool uses:** {stats['tool_use_count']}")
        if stat_items:
            parts.append(" | ".join(stat_items))

    parts.append("")
    parts.append("---")
    parts.append("")

    # Messages
    for msg in messages:
        if msg.get("is_sidechain"):
            continue

        role = msg.get("role", "unknown")
        role_display = role.capitalize()
        if role == "tool":
            role_display = "Tool Result"

        parts.append(f"### {role_display}")

        timestamp = msg.get("timestamp")
        if timestamp:
            parts.append(f"*{timestamp}*")

        parts.append("")

        content_blocks = msg.get("content", [])
        for block in content_blocks:
            rendered = _render_block(block)
            if rendered:
                parts.append(rendered)
                parts.append("")

        parts.append("---")
        parts.append("")

    return "\n".join(parts)
