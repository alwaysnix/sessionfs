#!/usr/bin/env python3
"""Spike 1A: Claude Code Session Discovery & Read

Discovers, parses, and exports Claude Code sessions from native storage.
Outputs a clean JSON representation with all messages, tool calls, and metadata.

Usage:
    # Auto-discover and list all sessions
    python src/spikes/spike_1a_cc_read.py

    # Parse a specific session by UUID
    python src/spikes/spike_1a_cc_read.py <session-uuid>

    # Parse a specific JSONL file
    python src/spikes/spike_1a_cc_read.py /path/to/session.jsonl

    # Export parsed session to file
    python src/spikes/spike_1a_cc_read.py <session-uuid> --output session.json

    # Parse all sessions for a project
    python src/spikes/spike_1a_cc_read.py --project /Users/ola/Documents/Repo/foo
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ContentBlock:
    """A single content block within a message."""
    block_type: str  # text, thinking, tool_use, tool_result
    text: str | None = None
    thinking: str | None = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_result_content: str | None = None
    signature: str | None = None


@dataclass
class Message:
    """A parsed conversation message."""
    uuid: str
    parent_uuid: str | None
    role: str  # user, assistant, system, summary
    content_blocks: list[ContentBlock]
    timestamp: str | None = None
    model: str | None = None
    stop_reason: str | None = None
    is_sidechain: bool = False
    is_meta: bool = False
    cwd: str | None = None
    git_branch: str | None = None
    request_id: str | None = None
    usage: dict[str, Any] | None = None


@dataclass
class SubAgent:
    """A sub-agent session."""
    agent_id: str
    messages: list[Message] = field(default_factory=list)
    model: str | None = None


@dataclass
class ParsedSession:
    """A fully parsed Claude Code session."""
    session_id: str
    project_path: str | None = None
    source_path: str | None = None
    claude_code_version: str | None = None
    slug: str | None = None
    git_branch: str | None = None
    first_prompt: str | None = None
    messages: list[Message] = field(default_factory=list)
    sub_agents: list[SubAgent] = field(default_factory=list)
    file_snapshots: list[dict[str, Any]] = field(default_factory=list)
    message_count: int = 0
    parse_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

CLAUDE_HOME = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_HOME / "projects"


def discover_projects() -> list[dict[str, Any]]:
    """Find all Claude Code project directories."""
    if not PROJECTS_DIR.is_dir():
        return []

    projects = []
    for entry in sorted(PROJECTS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        # Decode project path: dashes become slashes
        decoded_path = "/" + entry.name.replace("-", "/")
        sessions = list(entry.glob("*.jsonl"))
        projects.append({
            "encoded_name": entry.name,
            "decoded_path": decoded_path,
            "directory": str(entry),
            "session_count": len(sessions),
        })
    return projects


def discover_sessions(project_dir: Path | None = None) -> list[dict[str, Any]]:
    """Find all session JSONL files, optionally filtered to one project."""
    dirs = [project_dir] if project_dir else [
        d for d in sorted(PROJECTS_DIR.iterdir())
        if d.is_dir() and not d.name.startswith(".")
    ]

    sessions = []
    for d in dirs:
        index_path = d / "sessions-index.json"
        index_entries: dict[str, dict] = {}
        if index_path.exists():
            try:
                idx = json.loads(index_path.read_text())
                for entry in idx.get("entries", []):
                    index_entries[entry["sessionId"]] = entry
            except (json.JSONDecodeError, KeyError):
                pass

        for jsonl in sorted(d.glob("*.jsonl")):
            session_id = jsonl.stem
            idx_entry = index_entries.get(session_id, {})
            size = jsonl.stat().st_size
            sessions.append({
                "session_id": session_id,
                "path": str(jsonl),
                "project_dir": str(d),
                "size_bytes": size,
                "first_prompt": idx_entry.get("firstPrompt", ""),
                "created": idx_entry.get("created", ""),
                "modified": idx_entry.get("modified", ""),
                "git_branch": idx_entry.get("gitBranch", ""),
                "project_path": idx_entry.get("projectPath", ""),
                "message_count": idx_entry.get("messageCount", 0),
            })
    return sessions


def find_session_path(identifier: str) -> Path | None:
    """Resolve a session UUID or file path to a JSONL path."""
    # Direct file path
    p = Path(identifier)
    if p.exists() and p.suffix == ".jsonl":
        return p

    # Search by UUID across all projects
    for jsonl in PROJECTS_DIR.rglob(f"{identifier}.jsonl"):
        # Skip subagent files
        if "subagents" not in str(jsonl):
            return jsonl

    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _copy_to_temp(source: Path) -> Path:
    """Copy a file to a temp location for safe reading (copy-on-read)."""
    tmp = Path(tempfile.mkdtemp(prefix="sfs_spike_"))
    dest = tmp / source.name
    shutil.copy2(source, dest)
    return dest


def _parse_content_blocks(content: Any) -> list[ContentBlock]:
    """Parse message content into ContentBlock list."""
    if isinstance(content, str):
        return [ContentBlock(block_type="text", text=content)]

    if not isinstance(content, list):
        return [ContentBlock(block_type="text", text=str(content))]

    blocks = []
    for item in content:
        if not isinstance(item, dict):
            blocks.append(ContentBlock(block_type="text", text=str(item)))
            continue

        btype = item.get("type", "unknown")

        if btype == "text":
            blocks.append(ContentBlock(block_type="text", text=item.get("text", "")))

        elif btype == "thinking":
            blocks.append(ContentBlock(
                block_type="thinking",
                thinking=item.get("thinking", ""),
                signature=item.get("signature"),
            ))

        elif btype == "tool_use":
            blocks.append(ContentBlock(
                block_type="tool_use",
                tool_use_id=item.get("id"),
                tool_name=item.get("name"),
                tool_input=item.get("input"),
            ))

        elif btype == "tool_result":
            result_content = item.get("content", "")
            if isinstance(result_content, list):
                # Flatten structured tool results to text
                parts = []
                for sub in result_content:
                    if isinstance(sub, dict):
                        parts.append(sub.get("text", str(sub)))
                    else:
                        parts.append(str(sub))
                result_content = "\n".join(parts)

            blocks.append(ContentBlock(
                block_type="tool_result",
                tool_use_id=item.get("tool_use_id"),
                tool_result_content=result_content,
            ))

        else:
            blocks.append(ContentBlock(block_type=btype, text=json.dumps(item)))

    return blocks


def _parse_message(raw: dict[str, Any]) -> Message | None:
    """Parse a raw JSONL line into a Message, or None if not a message type."""
    msg_type = raw.get("type")
    if msg_type not in ("user", "assistant", "summary"):
        return None

    if msg_type == "summary":
        return Message(
            uuid=raw.get("leafUuid", ""),
            parent_uuid=None,
            role="summary",
            content_blocks=[ContentBlock(
                block_type="text",
                text=raw.get("summary", ""),
            )],
            timestamp=raw.get("timestamp"),
        )

    msg = raw.get("message", {})
    role = msg.get("role", msg_type)
    content = msg.get("content", "")
    blocks = _parse_content_blocks(content)

    return Message(
        uuid=raw.get("uuid", ""),
        parent_uuid=raw.get("parentUuid"),
        role=role,
        content_blocks=blocks,
        timestamp=raw.get("timestamp"),
        model=msg.get("model"),
        stop_reason=msg.get("stop_reason"),
        is_sidechain=raw.get("isSidechain", False),
        is_meta=raw.get("isMeta", False),
        cwd=raw.get("cwd"),
        git_branch=raw.get("gitBranch"),
        request_id=raw.get("requestId"),
        usage=msg.get("usage"),
    )


def parse_session(jsonl_path: Path, *, copy_on_read: bool = True) -> ParsedSession:
    """Parse a Claude Code session JSONL file into a structured representation.

    Args:
        jsonl_path: Path to the .jsonl session file.
        copy_on_read: If True, copy file to temp before reading (safe for concurrent access).

    Returns:
        ParsedSession with all messages, metadata, and any parse errors.
    """
    session_id = jsonl_path.stem
    session = ParsedSession(
        session_id=session_id,
        source_path=str(jsonl_path),
    )

    # Copy-on-read for safety
    read_path = jsonl_path
    tmp_dir: Path | None = None
    if copy_on_read:
        read_path = _copy_to_temp(jsonl_path)
        tmp_dir = read_path.parent

    try:
        with open(read_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as e:
                    session.parse_errors.append(f"Line {line_num}: JSON decode error: {e}")
                    continue

                raw_type = raw.get("type")

                # Extract session metadata from first substantive message
                if raw_type in ("user", "assistant") and not session.claude_code_version:
                    session.claude_code_version = raw.get("version")
                    session.slug = raw.get("slug")
                    session.git_branch = raw.get("gitBranch")
                    session.project_path = raw.get("cwd")

                # File history snapshots
                if raw_type == "file-history-snapshot":
                    snap = raw.get("snapshot", {})
                    backups = snap.get("trackedFileBackups", {})
                    if backups:
                        session.file_snapshots.append({
                            "message_id": raw.get("messageId"),
                            "timestamp": snap.get("timestamp"),
                            "files": list(backups.keys()),
                            "is_update": raw.get("isSnapshotUpdate", False),
                        })
                    continue

                # Progress and system events — skip (metadata only)
                if raw_type in ("progress", "system"):
                    continue

                # Parse conversation messages
                message = _parse_message(raw)
                if message:
                    session.messages.append(message)

    finally:
        # Clean up temp copy
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    session.message_count = len(session.messages)

    # Extract first user prompt
    for msg in session.messages:
        if msg.role == "user" and not msg.is_meta:
            for block in msg.content_blocks:
                if block.block_type == "text" and block.text:
                    session.first_prompt = block.text[:200]
                    break
            if session.first_prompt:
                break

    # Parse sub-agents
    session_dir = jsonl_path.parent / session_id
    subagents_dir = session_dir / "subagents"
    if subagents_dir.is_dir():
        for agent_file in sorted(subagents_dir.glob("*.jsonl")):
            agent_id = agent_file.stem
            sub = SubAgent(agent_id=agent_id)

            sub_read = agent_file
            sub_tmp: Path | None = None
            if copy_on_read:
                sub_read = _copy_to_temp(agent_file)
                sub_tmp = sub_read.parent

            try:
                with open(sub_read, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            raw = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        msg = _parse_message(raw)
                        if msg:
                            sub.messages.append(msg)
                            if not sub.model and msg.model:
                                sub.model = msg.model
            finally:
                if sub_tmp and sub_tmp.exists():
                    shutil.rmtree(sub_tmp, ignore_errors=True)

            session.sub_agents.append(sub)

    return session


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def session_to_dict(session: ParsedSession) -> dict[str, Any]:
    """Convert a ParsedSession to a JSON-serializable dict."""
    return asdict(session)


def print_session_summary(session: ParsedSession) -> None:
    """Print a human-readable summary of a parsed session."""
    print(f"\n{'='*70}")
    print(f"Session: {session.session_id}")
    print(f"  Slug:      {session.slug or 'N/A'}")
    print(f"  Project:   {session.project_path or 'N/A'}")
    print(f"  Version:   {session.claude_code_version or 'N/A'}")
    print(f"  Branch:    {session.git_branch or 'N/A'}")
    print(f"  Messages:  {session.message_count}")
    print(f"  Source:    {session.source_path}")

    if session.first_prompt:
        prompt_preview = session.first_prompt[:100]
        if len(session.first_prompt) > 100:
            prompt_preview += "..."
        print(f"  Prompt:    {prompt_preview}")

    # Count content block types
    type_counts: dict[str, int] = {}
    for msg in session.messages:
        for block in msg.content_blocks:
            type_counts[block.block_type] = type_counts.get(block.block_type, 0) + 1

    if type_counts:
        print(f"  Content:   {type_counts}")

    # Role breakdown
    role_counts: dict[str, int] = {}
    for msg in session.messages:
        role_counts[msg.role] = role_counts.get(msg.role, 0) + 1
    print(f"  Roles:     {role_counts}")

    # Sub-agents
    if session.sub_agents:
        print(f"  SubAgents: {len(session.sub_agents)}")
        for sa in session.sub_agents:
            print(f"    - {sa.agent_id}: {len(sa.messages)} msgs, model={sa.model}")

    # File snapshots
    if session.file_snapshots:
        total_files = sum(len(s["files"]) for s in session.file_snapshots)
        print(f"  Snapshots: {len(session.file_snapshots)} ({total_files} files tracked)")

    if session.parse_errors:
        print(f"  Errors:    {len(session.parse_errors)}")
        for err in session.parse_errors[:3]:
            print(f"    - {err}")

    print(f"{'='*70}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    """List discovered sessions."""
    if args.project:
        # Find matching project directory
        encoded = args.project.rstrip("/").replace("/", "-")
        project_dir = PROJECTS_DIR / encoded
        if not project_dir.is_dir():
            print(f"Project directory not found: {project_dir}", file=sys.stderr)
            sys.exit(1)
        sessions = discover_sessions(project_dir)
    else:
        sessions = discover_sessions()

    if not sessions:
        print("No Claude Code sessions found.")
        return

    print(f"\nDiscovered {len(sessions)} session(s):\n")
    for s in sessions:
        size_kb = s["size_bytes"] / 1024
        prompt = s["first_prompt"][:60] + "..." if len(s["first_prompt"]) > 60 else s["first_prompt"]
        print(f"  {s['session_id']}")
        print(f"    Size: {size_kb:.1f} KB | Messages: {s['message_count']} | Branch: {s['git_branch']}")
        if s["project_path"]:
            print(f"    Project: {s['project_path']}")
        if prompt:
            print(f"    Prompt: {prompt}")
        print()


def cmd_parse(args: argparse.Namespace) -> None:
    """Parse one or more sessions."""
    identifiers = args.sessions

    if not identifiers:
        # Parse all sessions
        sessions = discover_sessions()
        identifiers = [s["path"] for s in sessions]

    if not identifiers:
        print("No sessions to parse.", file=sys.stderr)
        sys.exit(1)

    all_parsed = []
    for ident in identifiers:
        path = find_session_path(ident)
        if not path:
            print(f"Session not found: {ident}", file=sys.stderr)
            continue

        parsed = parse_session(path)
        all_parsed.append(parsed)
        print_session_summary(parsed)

    if args.output:
        output_data = [session_to_dict(s) for s in all_parsed]
        if len(output_data) == 1:
            output_data = output_data[0]

        output_path = Path(args.output)
        output_path.write_text(json.dumps(output_data, indent=2, default=str))
        print(f"\nExported to {args.output}")

    print(f"\nParsed {len(all_parsed)} session(s) with "
          f"{sum(s.message_count for s in all_parsed)} total messages")

    total_errors = sum(len(s.parse_errors) for s in all_parsed)
    if total_errors:
        print(f"  ({total_errors} parse errors — see output for details)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Claude Code Session Discovery & Read (Spike 1A)",
    )
    parser.add_argument(
        "sessions",
        nargs="*",
        help="Session UUID(s) or JSONL path(s) to parse. Omit to list all sessions.",
    )
    parser.add_argument(
        "--output", "-o",
        help="Export parsed session(s) to JSON file.",
    )
    parser.add_argument(
        "--project", "-p",
        help="Filter to sessions from a specific project path.",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        dest="list_only",
        help="List sessions without parsing.",
    )

    args = parser.parse_args()

    if args.list_only or (not args.sessions and not args.output):
        cmd_list(args)
    else:
        cmd_parse(args)


if __name__ == "__main__":
    main()
