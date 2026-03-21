#!/usr/bin/env python3
"""Spike 1B: Codex CLI Session Discovery & Read

Discovers, parses, and exports Codex CLI sessions from native storage.
Outputs a clean JSON representation with all messages, tool calls, and metadata.

Usage:
    # Auto-discover and list all sessions
    python src/spikes/spike_1b_codex_read.py

    # Parse a specific session by UUID
    python src/spikes/spike_1b_codex_read.py <session-uuid>

    # Parse a specific JSONL rollout file
    python src/spikes/spike_1b_codex_read.py /path/to/rollout.jsonl

    # Export parsed session to file
    python src/spikes/spike_1b_codex_read.py <session-uuid> --output session.json

    # Override CODEX_HOME
    CODEX_HOME=/tmp/codex_test_home python src/spikes/spike_1b_codex_read.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
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
    block_type: str  # input_text, output_text, input_image
    text: str | None = None
    image_url: str | None = None


@dataclass
class ToolCall:
    """A tool call (shell command or function call)."""
    call_type: str  # local_shell_call, function_call, custom_tool_call, web_search_call
    call_id: str | None = None
    tool_id: str | None = None
    name: str | None = None
    command: list[str] | None = None
    arguments: str | None = None
    working_directory: str | None = None
    status: str | None = None


@dataclass
class ToolResult:
    """A tool call result."""
    call_id: str
    output: str | None = None
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    duration_ms: float | None = None


@dataclass
class Message:
    """A parsed conversation message."""
    role: str  # user, assistant, developer
    content_blocks: list[ContentBlock]
    message_id: str | None = None
    phase: str | None = None  # commentary, final_answer
    end_turn: bool | None = None
    timestamp: str | None = None


@dataclass
class Reasoning:
    """A reasoning/thinking block."""
    reasoning_id: str
    summary: list[str] = field(default_factory=list)
    content: list[str] = field(default_factory=list)
    has_encrypted_content: bool = False
    timestamp: str | None = None


@dataclass
class TurnContext:
    """Per-turn context snapshot."""
    turn_id: str
    cwd: str | None = None
    model: str | None = None
    approval_policy: str | None = None
    sandbox_policy: str | None = None
    current_date: str | None = None
    timezone: str | None = None
    personality: str | None = None
    reasoning_effort: str | None = None
    timestamp: str | None = None


@dataclass
class TokenUsage:
    """Token usage information."""
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class Turn:
    """A complete turn (user prompt + agent response + tool calls)."""
    turn_id: str
    context: TurnContext | None = None
    messages: list[Message] = field(default_factory=list)
    reasoning: list[Reasoning] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    token_usage: TokenUsage | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class GitInfo:
    """Git information at session start."""
    commit_hash: str | None = None
    branch: str | None = None
    repository_url: str | None = None


@dataclass
class ParsedSession:
    """A fully parsed Codex CLI session."""
    session_id: str
    source_path: str | None = None
    cwd: str | None = None
    originator: str | None = None
    cli_version: str | None = None
    source: str | None = None  # cli, vscode, exec, mcp
    model_provider: str | None = None
    model: str | None = None
    git: GitInfo | None = None
    forked_from_id: str | None = None
    has_system_prompt: bool = False
    system_prompt_length: int | None = None
    turns: list[Turn] = field(default_factory=list)
    message_count: int = 0
    tool_call_count: int = 0
    first_user_message: str | None = None
    total_token_usage: TokenUsage | None = None
    parse_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def get_codex_home() -> Path:
    """Get the Codex home directory."""
    env = os.environ.get("CODEX_HOME")
    if env:
        return Path(env)
    return Path.home() / ".codex"


CODEX_HOME = get_codex_home()
SESSIONS_DIR = CODEX_HOME / "sessions"
ARCHIVED_DIR = CODEX_HOME / "archived_sessions"
STATE_DB = CODEX_HOME / "state_5.sqlite"

# Filename pattern: rollout-YYYY-MM-DDThh-mm-ss-{uuid}.jsonl
ROLLOUT_PATTERN = re.compile(
    r"^rollout-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})-"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)


def parse_rollout_filename(name: str) -> tuple[str, str] | None:
    """Extract (timestamp, uuid) from a rollout filename."""
    m = ROLLOUT_PATTERN.match(name)
    if m:
        ts = m.group(1).replace("-", ":", 2)  # Restore time separators
        return ts, m.group(2)
    return None


def discover_sessions_from_db() -> list[dict[str, Any]]:
    """Discover sessions from the SQLite metadata database."""
    if not STATE_DB.exists():
        return []

    sessions = []
    try:
        conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, rollout_path, created_at, updated_at, source, "
            "model_provider, cwd, title, first_user_message, cli_version, "
            "git_sha, git_branch, git_origin_url, model, reasoning_effort, "
            "tokens_used, archived, agent_nickname, agent_role "
            "FROM threads ORDER BY created_at DESC"
        )
        for row in cursor:
            sessions.append({
                "session_id": row["id"],
                "rollout_path": row["rollout_path"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "source": row["source"],
                "model_provider": row["model_provider"],
                "cwd": row["cwd"],
                "title": row["title"],
                "first_user_message": row["first_user_message"],
                "cli_version": row["cli_version"],
                "git_sha": row["git_sha"],
                "git_branch": row["git_branch"],
                "git_origin_url": row["git_origin_url"],
                "model": row["model"],
                "tokens_used": row["tokens_used"],
                "archived": bool(row["archived"]),
            })
        conn.close()
    except (sqlite3.Error, Exception) as e:
        print(f"Warning: Could not read SQLite database: {e}", file=sys.stderr)
    return sessions


def discover_sessions_from_filesystem() -> list[dict[str, Any]]:
    """Discover sessions by scanning the sessions directory."""
    sessions = []

    for search_dir in [SESSIONS_DIR, ARCHIVED_DIR]:
        if not search_dir.is_dir():
            continue
        for jsonl in sorted(search_dir.rglob("rollout-*.jsonl"), reverse=True):
            parsed = parse_rollout_filename(jsonl.name)
            if not parsed:
                continue
            ts_str, uuid_str = parsed
            size = jsonl.stat().st_size
            sessions.append({
                "session_id": uuid_str,
                "rollout_path": str(jsonl),
                "size_bytes": size,
                "filename_timestamp": ts_str,
                "archived": "archived" in str(jsonl),
            })

    return sessions


def discover_sessions() -> list[dict[str, Any]]:
    """Discover sessions using DB first, filesystem fallback."""
    db_sessions = discover_sessions_from_db()
    if db_sessions:
        # Enrich with file sizes
        for s in db_sessions:
            p = Path(s["rollout_path"])
            if p.exists():
                s["size_bytes"] = p.stat().st_size
                s["file_exists"] = True
            else:
                s["size_bytes"] = 0
                s["file_exists"] = False
        return db_sessions

    return discover_sessions_from_filesystem()


def find_session_path(identifier: str) -> Path | None:
    """Resolve a session UUID or file path to a rollout JSONL path."""
    # Direct file path
    p = Path(identifier)
    if p.exists() and p.suffix == ".jsonl":
        return p

    # Try SQLite lookup
    if STATE_DB.exists():
        try:
            conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
            cursor = conn.execute(
                "SELECT rollout_path FROM threads WHERE id = ?", (identifier,)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                rp = Path(row[0])
                if rp.exists():
                    return rp
        except sqlite3.Error:
            pass

    # Filesystem search by UUID
    for search_dir in [SESSIONS_DIR, ARCHIVED_DIR]:
        if not search_dir.is_dir():
            continue
        for jsonl in search_dir.rglob(f"rollout-*-{identifier}.jsonl"):
            return jsonl

    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _copy_to_temp(source: Path) -> Path:
    """Copy a file to a temp location for safe reading (copy-on-read)."""
    tmp = Path(tempfile.mkdtemp(prefix="sfs_spike_codex_"))
    dest = tmp / source.name
    shutil.copy2(source, dest)
    return dest


def _parse_content_blocks(content: Any) -> list[ContentBlock]:
    """Parse message content into ContentBlock list."""
    if isinstance(content, str):
        return [ContentBlock(block_type="output_text", text=content)]

    if not isinstance(content, list):
        return [ContentBlock(block_type="output_text", text=str(content))]

    blocks = []
    for item in content:
        if not isinstance(item, dict):
            blocks.append(ContentBlock(block_type="output_text", text=str(item)))
            continue

        btype = item.get("type", "unknown")

        if btype == "output_text":
            blocks.append(ContentBlock(block_type="output_text", text=item.get("text", "")))
        elif btype == "input_text":
            blocks.append(ContentBlock(block_type="input_text", text=item.get("text", "")))
        elif btype == "input_image":
            blocks.append(ContentBlock(block_type="input_image", image_url=item.get("image_url")))
        else:
            blocks.append(ContentBlock(block_type=btype, text=json.dumps(item)))

    return blocks


def _parse_response_item(payload: dict[str, Any], timestamp: str) -> dict[str, Any]:
    """Parse a response_item payload into typed objects.

    Returns a dict with optional keys: 'message', 'reasoning', 'tool_call', 'tool_result'.
    """
    result: dict[str, Any] = {}
    item_type = payload.get("type", "")

    if item_type == "message":
        content = payload.get("content", [])
        blocks = _parse_content_blocks(content)
        msg = Message(
            role=payload.get("role", "unknown"),
            content_blocks=blocks,
            message_id=payload.get("id"),
            phase=payload.get("phase"),
            end_turn=payload.get("end_turn"),
            timestamp=timestamp,
        )
        result["message"] = msg

    elif item_type == "reasoning":
        summaries = []
        for s in payload.get("summary", []):
            if isinstance(s, dict):
                summaries.append(s.get("text", str(s)))
            else:
                summaries.append(str(s))

        contents = []
        for c in payload.get("content", []) or []:
            if isinstance(c, dict):
                contents.append(c.get("text", str(c)))
            else:
                contents.append(str(c))

        reasoning = Reasoning(
            reasoning_id=payload.get("id", ""),
            summary=summaries,
            content=contents,
            has_encrypted_content=bool(payload.get("encrypted_content")),
            timestamp=timestamp,
        )
        result["reasoning"] = reasoning

    elif item_type == "local_shell_call":
        action = payload.get("action", {})
        tc = ToolCall(
            call_type="local_shell_call",
            call_id=payload.get("call_id"),
            tool_id=payload.get("id"),
            command=action.get("command"),
            working_directory=action.get("working_directory"),
            status=payload.get("status"),
        )
        result["tool_call"] = tc

    elif item_type == "function_call":
        tc = ToolCall(
            call_type="function_call",
            call_id=payload.get("call_id"),
            tool_id=payload.get("id"),
            name=payload.get("name"),
            arguments=payload.get("arguments"),
            status=None,
        )
        result["tool_call"] = tc

    elif item_type == "function_call_output":
        output_payload = payload.get("output", {})
        output_text = ""
        if isinstance(output_payload, dict):
            output_text = output_payload.get("text", "")
        elif isinstance(output_payload, str):
            output_text = output_payload

        tr = ToolResult(
            call_id=payload.get("call_id", ""),
            output=output_text,
        )
        result["tool_result"] = tr

    elif item_type == "custom_tool_call":
        tc = ToolCall(
            call_type="custom_tool_call",
            call_id=payload.get("call_id"),
            tool_id=payload.get("id"),
            name=payload.get("name"),
            arguments=payload.get("input"),
            status=payload.get("status"),
        )
        result["tool_call"] = tc

    elif item_type == "custom_tool_call_output":
        output_payload = payload.get("output", {})
        output_text = ""
        if isinstance(output_payload, dict):
            output_text = output_payload.get("text", "")
        elif isinstance(output_payload, str):
            output_text = output_payload

        tr = ToolResult(
            call_id=payload.get("call_id", ""),
            output=output_text,
        )
        result["tool_result"] = tr

    elif item_type == "web_search_call":
        tc = ToolCall(
            call_type="web_search_call",
            tool_id=payload.get("id"),
            status=payload.get("status"),
        )
        result["tool_call"] = tc

    return result


def parse_session(jsonl_path: Path, *, copy_on_read: bool = True) -> ParsedSession:
    """Parse a Codex CLI session JSONL file into a structured representation.

    Args:
        jsonl_path: Path to the rollout .jsonl session file.
        copy_on_read: If True, copy file to temp before reading (safe for concurrent access).

    Returns:
        ParsedSession with all messages, metadata, and any parse errors.
    """
    # Extract session ID from filename
    parsed_name = parse_rollout_filename(jsonl_path.name)
    session_id = parsed_name[1] if parsed_name else jsonl_path.stem

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

    current_turn: Turn | None = None
    all_messages: list[Message] = []
    all_tool_calls: list[ToolCall] = []

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

                timestamp = raw.get("timestamp", "")
                item_type = raw.get("type", "")
                payload = raw.get("payload", {})

                # --- session_meta (first line) ---
                if item_type == "session_meta":
                    session.session_id = payload.get("id", session_id)
                    session.cwd = payload.get("cwd")
                    session.originator = payload.get("originator")
                    session.cli_version = payload.get("cli_version")
                    session.source = payload.get("source")
                    session.model_provider = payload.get("model_provider")
                    session.forked_from_id = payload.get("forked_from_id")

                    # System prompt
                    base_instructions = payload.get("base_instructions")
                    if base_instructions and isinstance(base_instructions, dict):
                        prompt_text = base_instructions.get("text", "")
                        if prompt_text:
                            session.has_system_prompt = True
                            session.system_prompt_length = len(prompt_text)

                    # Git info
                    git_data = payload.get("git")
                    if git_data and isinstance(git_data, dict):
                        session.git = GitInfo(
                            commit_hash=git_data.get("commit_hash"),
                            branch=git_data.get("branch"),
                            repository_url=git_data.get("repository_url"),
                        )
                    continue

                # --- turn_context ---
                if item_type == "turn_context":
                    sandbox = payload.get("sandbox_policy")
                    sandbox_str = None
                    if isinstance(sandbox, dict):
                        sandbox_str = sandbox.get("type")
                    elif isinstance(sandbox, str):
                        sandbox_str = sandbox

                    tc = TurnContext(
                        turn_id=payload.get("turn_id", ""),
                        cwd=payload.get("cwd"),
                        model=payload.get("model"),
                        approval_policy=payload.get("approval_policy"),
                        sandbox_policy=sandbox_str,
                        current_date=payload.get("current_date"),
                        timezone=payload.get("timezone"),
                        personality=payload.get("personality"),
                        timestamp=timestamp,
                    )

                    # Set session model from first turn context
                    if not session.model and tc.model:
                        session.model = tc.model

                    # Associate with current turn
                    if current_turn and current_turn.turn_id == tc.turn_id:
                        current_turn.context = tc
                    continue

                # --- event_msg ---
                if item_type == "event_msg":
                    event_type = payload.get("type", "")

                    if event_type == "task_started":
                        # Start a new turn
                        turn_id = payload.get("turn_id", "")
                        current_turn = Turn(
                            turn_id=turn_id,
                            started_at=timestamp,
                        )
                        session.turns.append(current_turn)

                    elif event_type == "task_complete":
                        if current_turn:
                            current_turn.completed_at = timestamp

                    elif event_type == "user_message":
                        msg_text = payload.get("message", "")
                        msg = Message(
                            role="user",
                            content_blocks=[ContentBlock(block_type="input_text", text=msg_text)],
                            timestamp=timestamp,
                        )
                        all_messages.append(msg)
                        if current_turn:
                            current_turn.messages.append(msg)

                        # Track first user message
                        if not session.first_user_message and msg_text:
                            session.first_user_message = msg_text[:200]

                    elif event_type == "agent_message":
                        msg_text = payload.get("message", "")
                        msg = Message(
                            role="assistant",
                            content_blocks=[ContentBlock(block_type="output_text", text=msg_text)],
                            phase=payload.get("phase"),
                            timestamp=timestamp,
                        )
                        all_messages.append(msg)
                        if current_turn:
                            current_turn.messages.append(msg)

                    elif event_type == "agent_reasoning":
                        # Reasoning summaries in event form
                        pass

                    elif event_type == "token_count":
                        info = payload.get("info", {})
                        total = info.get("total_token_usage", {})
                        if total and current_turn:
                            current_turn.token_usage = TokenUsage(
                                input_tokens=total.get("input_tokens", 0),
                                cached_input_tokens=total.get("cached_input_tokens", 0),
                                output_tokens=total.get("output_tokens", 0),
                                reasoning_output_tokens=total.get("reasoning_output_tokens", 0),
                                total_tokens=total.get("total_tokens", 0),
                            )

                    elif event_type == "exec_command_end":
                        # Shell command completion with results
                        tr = ToolResult(
                            call_id=payload.get("call_id", ""),
                            output=payload.get("aggregated_output"),
                            stdout=payload.get("stdout"),
                            stderr=payload.get("stderr"),
                            exit_code=payload.get("exit_code"),
                            duration_ms=payload.get("duration", {}).get("secs", 0) * 1000
                            if isinstance(payload.get("duration"), dict) else None,
                        )
                        if current_turn:
                            current_turn.tool_results.append(tr)

                    continue

                # --- response_item ---
                if item_type == "response_item":
                    parsed = _parse_response_item(payload, timestamp)

                    if "message" in parsed:
                        msg = parsed["message"]
                        # Only count assistant messages from response_items.
                        # User messages are captured via event_msg (user_message)
                        # to avoid double-counting. Developer messages are
                        # system-injected context (permissions, skills, env).
                        if msg.role == "assistant":
                            all_messages.append(msg)
                        if current_turn:
                            current_turn.messages.append(msg)

                    if "reasoning" in parsed:
                        if current_turn:
                            current_turn.reasoning.append(parsed["reasoning"])

                    if "tool_call" in parsed:
                        tc = parsed["tool_call"]
                        all_tool_calls.append(tc)
                        if current_turn:
                            current_turn.tool_calls.append(tc)

                    if "tool_result" in parsed:
                        if current_turn:
                            current_turn.tool_results.append(parsed["tool_result"])
                    continue

                # --- compacted ---
                if item_type == "compacted":
                    # Context compaction — note it but don't try to parse encrypted content
                    continue

    finally:
        # Clean up temp copy
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    session.message_count = len(all_messages)
    session.tool_call_count = len(all_tool_calls)

    # Aggregate token usage from last turn
    for turn in reversed(session.turns):
        if turn.token_usage:
            session.total_token_usage = turn.token_usage
            break

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
    print(f"  Source:    {session.source or 'N/A'} ({session.originator or 'N/A'})")
    print(f"  CWD:       {session.cwd or 'N/A'}")
    print(f"  Version:   {session.cli_version or 'N/A'}")
    print(f"  Model:     {session.model or 'N/A'} (provider: {session.model_provider or 'N/A'})")
    print(f"  Messages:  {session.message_count}")
    print(f"  Tools:     {session.tool_call_count}")
    print(f"  Turns:     {len(session.turns)}")
    print(f"  File:      {session.source_path}")

    if session.git:
        git_parts = []
        if session.git.branch:
            git_parts.append(f"branch={session.git.branch}")
        if session.git.commit_hash:
            git_parts.append(f"sha={session.git.commit_hash[:8]}")
        if git_parts:
            print(f"  Git:       {', '.join(git_parts)}")

    if session.has_system_prompt:
        print(f"  SysPrompt: {session.system_prompt_length} chars")

    if session.first_user_message:
        preview = session.first_user_message[:80]
        if len(session.first_user_message) > 80:
            preview += "..."
        print(f"  Prompt:    {preview}")

    if session.forked_from_id:
        print(f"  Forked:    {session.forked_from_id}")

    # Turn details
    for i, turn in enumerate(session.turns):
        status = "completed" if turn.completed_at else "incomplete"
        model = turn.context.model if turn.context else "?"
        msgs = len(turn.messages)
        tools = len(turn.tool_calls)
        reasoning = len(turn.reasoning)
        parts = [f"{msgs} msgs"]
        if tools:
            parts.append(f"{tools} tools")
        if reasoning:
            parts.append(f"{reasoning} reasoning")
        if turn.token_usage:
            parts.append(f"{turn.token_usage.total_tokens} tokens")
        print(f"  Turn {i+1}:    [{status}] model={model} | {', '.join(parts)}")

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
    sessions = discover_sessions()

    if not sessions:
        print("No Codex CLI sessions found.")
        print(f"  (Searched: {CODEX_HOME})")
        return

    print(f"\nDiscovered {len(sessions)} session(s) in {CODEX_HOME}:\n")
    for s in sessions:
        session_id = s["session_id"]
        size = s.get("size_bytes", 0)
        size_kb = size / 1024 if size else 0

        # DB-sourced fields
        title = s.get("title") or s.get("first_user_message") or ""
        model = s.get("model") or ""
        source = s.get("source", "")
        cwd = s.get("cwd", "")

        prompt = title[:60] + "..." if len(title) > 60 else title

        print(f"  {session_id}")
        print(f"    Size: {size_kb:.1f} KB | Source: {source} | Model: {model}")
        if cwd:
            print(f"    CWD: {cwd}")
        if prompt:
            print(f"    Prompt: {prompt}")

        file_exists = s.get("file_exists")
        if file_exists is False:
            print(f"    WARNING: Rollout file missing!")
        print()


def cmd_parse(args: argparse.Namespace) -> None:
    """Parse one or more sessions."""
    identifiers = args.sessions

    if not identifiers:
        # Parse all sessions
        sessions = discover_sessions()
        identifiers = [
            s.get("rollout_path", s["session_id"])
            for s in sessions
            if s.get("file_exists", True)
        ]

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
          f"{sum(s.message_count for s in all_parsed)} total messages, "
          f"{sum(s.tool_call_count for s in all_parsed)} tool calls")

    total_errors = sum(len(s.parse_errors) for s in all_parsed)
    if total_errors:
        print(f"  ({total_errors} parse errors — see output for details)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Codex CLI Session Discovery & Read (Spike 1B)",
    )
    parser.add_argument(
        "sessions",
        nargs="*",
        help="Session UUID(s) or rollout JSONL path(s) to parse. Omit to list all sessions.",
    )
    parser.add_argument(
        "--output", "-o",
        help="Export parsed session(s) to JSON file.",
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
