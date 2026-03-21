#!/usr/bin/env python3
"""Spike 2A: Claude Code Session Write-Back Test

Tests whether we can inject or extend sessions in Claude Code's local storage
and have Claude Code recognize them.

Usage:
    # Test 1: Inject a copy of an existing session under a new UUID
    python src/spikes/spike_2a_cc_writeback.py inject --source <session-uuid> --project <project-path>

    # Test 2: Extend an existing session with a synthetic user message
    python src/spikes/spike_2a_cc_writeback.py extend --source <session-uuid> --message "Hello from SessionFS"

    # Test 3: Cross-project injection
    python src/spikes/spike_2a_cc_writeback.py cross-inject --source <session-uuid> --target-project <project-path>

    # Test 4: Create a fully synthetic session from scratch
    python src/spikes/spike_2a_cc_writeback.py synthetic --project <project-path> --message "This is a synthetic session"

    # Cleanup: Remove all injected test sessions
    python src/spikes/spike_2a_cc_writeback.py cleanup

    # Dry run (any command): show what would be written without writing
    python src/spikes/spike_2a_cc_writeback.py inject --source <uuid> --project <path> --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_HOME = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_HOME / "projects"
# Track all files we create for cleanup
MANIFEST_PATH = Path(__file__).parent / ".spike_2a_manifest.json"


def _load_manifest() -> list[str]:
    """Load list of files created by this spike."""
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return []


def _save_manifest(paths: list[str]) -> None:
    """Save list of created file paths."""
    MANIFEST_PATH.write_text(json.dumps(paths, indent=2))


def _record_created(path: str) -> None:
    """Record a file path that was created by this spike."""
    manifest = _load_manifest()
    if path not in manifest:
        manifest.append(path)
        _save_manifest(manifest)


# ---------------------------------------------------------------------------
# Path encoding
# ---------------------------------------------------------------------------

def encode_project_path(project_path: str) -> str:
    """Encode an absolute project path to Claude Code's directory name format.

    Claude Code replaces '/' with '-' in the project path.
    e.g., /Users/ola/Documents/Repo/foo -> -Users-ola-Documents-Repo-foo
    """
    return project_path.replace("/", "-")


def get_project_dir(project_path: str) -> Path:
    """Get the Claude Code project directory for a given project path."""
    encoded = encode_project_path(project_path)
    return PROJECTS_DIR / encoded


# ---------------------------------------------------------------------------
# Session Index Management
# ---------------------------------------------------------------------------

def read_sessions_index(project_dir: Path) -> dict[str, Any]:
    """Read the sessions-index.json for a project directory."""
    index_path = project_dir / "sessions-index.json"
    if index_path.exists():
        return json.loads(index_path.read_text())
    return {"version": 1, "entries": []}


def write_sessions_index(project_dir: Path, index: dict[str, Any]) -> None:
    """Write sessions-index.json for a project directory."""
    index_path = project_dir / "sessions-index.json"
    index_path.write_text(json.dumps(index, indent=2))


def add_index_entry(
    project_dir: Path,
    session_id: str,
    project_path: str,
    first_prompt: str,
    message_count: int,
    git_branch: str = "",
) -> None:
    """Add a session entry to the project's sessions-index.json."""
    index = read_sessions_index(project_dir)
    now = datetime.now(timezone.utc)
    jsonl_path = project_dir / f"{session_id}.jsonl"

    entry = {
        "sessionId": session_id,
        "fullPath": str(jsonl_path),
        "fileMtime": int(now.timestamp() * 1000),
        "firstPrompt": first_prompt[:200],
        "messageCount": message_count,
        "created": now.isoformat().replace("+00:00", "Z"),
        "modified": now.isoformat().replace("+00:00", "Z"),
        "gitBranch": git_branch,
        "projectPath": project_path,
        "isSidechain": False,
    }

    # Remove any existing entry for this session
    index["entries"] = [
        e for e in index["entries"] if e.get("sessionId") != session_id
    ]
    index["entries"].append(entry)
    write_sessions_index(project_dir, index)


# ---------------------------------------------------------------------------
# Message Builders
# ---------------------------------------------------------------------------

def new_uuid() -> str:
    """Generate a new UUID v4."""
    return str(uuid.uuid4())


def build_user_message(
    text: str,
    *,
    session_id: str,
    parent_uuid: str | None = None,
    cwd: str = "/tmp",
    git_branch: str = "",
    version: str = "2.1.59",
    slug: str = "",
    is_meta: bool = False,
) -> dict[str, Any]:
    """Build a user message in Claude Code's native JSONL format.

    Args:
        text: The user message text.
        session_id: Session UUID.
        parent_uuid: UUID of the parent message (for tree structure).
        cwd: Working directory.
        git_branch: Active git branch.
        version: Claude Code version string.
        slug: Session slug.
        is_meta: Whether this is a meta/system message.

    Returns:
        Dict ready to be serialized as one JSONL line.
    """
    msg_uuid = new_uuid()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    entry: dict[str, Any] = {
        "parentUuid": parent_uuid,
        "isSidechain": False,
        "userType": "external",
        "cwd": cwd,
        "sessionId": session_id,
        "version": version,
        "gitBranch": git_branch,
        "type": "user",
        "message": {
            "role": "user",
            "content": text,
        },
        "uuid": msg_uuid,
        "timestamp": now,
    }

    if slug:
        entry["slug"] = slug
    if is_meta:
        entry["isMeta"] = True

    return entry


def build_assistant_message(
    text: str,
    *,
    session_id: str,
    parent_uuid: str,
    cwd: str = "/tmp",
    git_branch: str = "",
    version: str = "2.1.59",
    slug: str = "",
    model: str = "claude-opus-4-6",
) -> dict[str, Any]:
    """Build an assistant message in Claude Code's native JSONL format."""
    msg_uuid = new_uuid()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "parentUuid": parent_uuid,
        "isSidechain": False,
        "userType": "external",
        "cwd": cwd,
        "sessionId": session_id,
        "version": version,
        "gitBranch": git_branch,
        "slug": slug,
        "message": {
            "model": model,
            "id": f"msg_{new_uuid().replace('-', '')[:24]}",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": text},
            ],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
        "requestId": f"req_{new_uuid().replace('-', '')[:24]}",
        "type": "assistant",
        "uuid": msg_uuid,
        "timestamp": now,
    }


def build_summary_message(summary_text: str, leaf_uuid: str) -> dict[str, Any]:
    """Build a summary message (used at the start of resumed sessions)."""
    return {
        "type": "summary",
        "summary": summary_text,
        "leafUuid": leaf_uuid,
    }


# ---------------------------------------------------------------------------
# Test Operations
# ---------------------------------------------------------------------------

def find_session_file(session_id: str) -> Path | None:
    """Find a session JSONL file by UUID across all projects."""
    for jsonl in PROJECTS_DIR.rglob(f"{session_id}.jsonl"):
        if "subagents" not in str(jsonl):
            return jsonl
    return None


def find_leaf_uuid(jsonl_path: Path) -> str | None:
    """Find the UUID of the last non-progress message in a session."""
    last_uuid = None
    with open(jsonl_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("type") in ("user", "assistant") and not obj.get("isSidechain"):
                    last_uuid = obj.get("uuid")
            except json.JSONDecodeError:
                continue
    return last_uuid


def get_session_metadata(jsonl_path: Path) -> dict[str, Any]:
    """Extract metadata from the first substantive message in a session."""
    with open(jsonl_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("type") in ("user", "assistant"):
                    return {
                        "version": obj.get("version", "2.1.59"),
                        "slug": obj.get("slug", ""),
                        "git_branch": obj.get("gitBranch", ""),
                        "cwd": obj.get("cwd", ""),
                        "session_id": obj.get("sessionId", ""),
                    }
            except json.JSONDecodeError:
                continue
    return {}


def test_inject(
    source_id: str,
    project_path: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Test 1: Copy a session to a new UUID in a project directory.

    Returns dict with test results.
    """
    source_path = find_session_file(source_id)
    if not source_path:
        return {"success": False, "error": f"Source session not found: {source_id}"}

    project_dir = get_project_dir(project_path)
    new_session_id = new_uuid()
    target_path = project_dir / f"{new_session_id}.jsonl"

    result = {
        "test": "inject",
        "source_session": source_id,
        "source_path": str(source_path),
        "new_session_id": new_session_id,
        "target_path": str(target_path),
        "project_path": project_path,
        "project_dir": str(project_dir),
    }

    if dry_run:
        result["dry_run"] = True
        result["success"] = True
        return result

    # Ensure project directory exists
    project_dir.mkdir(parents=True, exist_ok=True)

    # Copy the session file, rewriting sessionId in each line
    line_count = 0
    with open(source_path, "r") as src, open(target_path, "w") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Rewrite sessionId to the new UUID
                if "sessionId" in obj:
                    obj["sessionId"] = new_session_id
                dst.write(json.dumps(obj, separators=(",", ":")) + "\n")
                line_count += 1
            except json.JSONDecodeError:
                dst.write(line + "\n")
                line_count += 1

    # Add to sessions index
    meta = get_session_metadata(target_path)
    add_index_entry(
        project_dir,
        session_id=new_session_id,
        project_path=project_path,
        first_prompt="[Injected by SessionFS Spike 2A]",
        message_count=line_count,
        git_branch=meta.get("git_branch", ""),
    )

    _record_created(str(target_path))
    result["success"] = True
    result["lines_written"] = line_count
    return result


def test_extend(
    source_id: str,
    message_text: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Test 2: Copy a session and append a synthetic user message.

    Returns dict with test results.
    """
    source_path = find_session_file(source_id)
    if not source_path:
        return {"success": False, "error": f"Source session not found: {source_id}"}

    project_dir = source_path.parent
    new_session_id = new_uuid()
    target_path = project_dir / f"{new_session_id}.jsonl"

    # Get metadata and leaf UUID from source
    meta = get_session_metadata(source_path)
    leaf_uuid = find_leaf_uuid(source_path)

    result = {
        "test": "extend",
        "source_session": source_id,
        "new_session_id": new_session_id,
        "target_path": str(target_path),
        "leaf_uuid": leaf_uuid,
        "appended_message": message_text,
    }

    if dry_run:
        result["dry_run"] = True
        result["success"] = True
        return result

    # Copy the session
    line_count = 0
    with open(source_path, "r") as src, open(target_path, "w") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if "sessionId" in obj:
                    obj["sessionId"] = new_session_id
                dst.write(json.dumps(obj, separators=(",", ":")) + "\n")
                line_count += 1
            except json.JSONDecodeError:
                dst.write(line + "\n")
                line_count += 1

        # Append synthetic user message
        user_msg = build_user_message(
            message_text,
            session_id=new_session_id,
            parent_uuid=leaf_uuid,
            cwd=meta.get("cwd", "/tmp"),
            git_branch=meta.get("git_branch", ""),
            version=meta.get("version", "2.1.59"),
            slug=meta.get("slug", ""),
        )
        dst.write(json.dumps(user_msg, separators=(",", ":")) + "\n")
        line_count += 1

    # Update index
    add_index_entry(
        project_dir,
        session_id=new_session_id,
        project_path=meta.get("cwd", ""),
        first_prompt="[Extended by SessionFS Spike 2A]",
        message_count=line_count,
        git_branch=meta.get("git_branch", ""),
    )

    _record_created(str(target_path))
    result["success"] = True
    result["total_lines"] = line_count
    return result


def test_cross_inject(
    source_id: str,
    target_project_path: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Test 3: Copy a session from one project to a different project directory.

    Returns dict with test results.
    """
    source_path = find_session_file(source_id)
    if not source_path:
        return {"success": False, "error": f"Source session not found: {source_id}"}

    source_meta = get_session_metadata(source_path)
    target_dir = get_project_dir(target_project_path)
    new_session_id = new_uuid()
    target_path = target_dir / f"{new_session_id}.jsonl"

    result = {
        "test": "cross-inject",
        "source_session": source_id,
        "source_project": source_meta.get("cwd", "unknown"),
        "target_project": target_project_path,
        "new_session_id": new_session_id,
        "target_path": str(target_path),
    }

    if dry_run:
        result["dry_run"] = True
        result["success"] = True
        return result

    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy with rewritten sessionId and cwd
    line_count = 0
    with open(source_path, "r") as src, open(target_path, "w") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if "sessionId" in obj:
                    obj["sessionId"] = new_session_id
                # Rewrite cwd to target project
                if "cwd" in obj:
                    obj["cwd"] = target_project_path
                dst.write(json.dumps(obj, separators=(",", ":")) + "\n")
                line_count += 1
            except json.JSONDecodeError:
                dst.write(line + "\n")
                line_count += 1

    add_index_entry(
        target_dir,
        session_id=new_session_id,
        project_path=target_project_path,
        first_prompt="[Cross-injected by SessionFS Spike 2A]",
        message_count=line_count,
        git_branch=source_meta.get("git_branch", ""),
    )

    _record_created(str(target_path))
    result["success"] = True
    result["lines_written"] = line_count
    return result


def test_synthetic(
    project_path: str,
    message_text: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Test 4: Create a fully synthetic session from scratch.

    Creates a minimal valid session: one user message + one assistant reply.
    """
    project_dir = get_project_dir(project_path)
    session_id = new_uuid()
    target_path = project_dir / f"{session_id}.jsonl"
    slug = f"sfs-spike-{session_id[:8]}"

    result = {
        "test": "synthetic",
        "session_id": session_id,
        "target_path": str(target_path),
        "project_path": project_path,
        "slug": slug,
    }

    if dry_run:
        result["dry_run"] = True
        result["success"] = True
        return result

    project_dir.mkdir(parents=True, exist_ok=True)

    user_msg = build_user_message(
        message_text,
        session_id=session_id,
        parent_uuid=None,
        cwd=project_path,
        git_branch="main",
        slug=slug,
    )

    assistant_msg = build_assistant_message(
        "This is a synthetic response injected by SessionFS Spike 2A. "
        "If you can see this message in Claude Code, the write-back test succeeded.",
        session_id=session_id,
        parent_uuid=user_msg["uuid"],
        cwd=project_path,
        git_branch="main",
        slug=slug,
    )

    with open(target_path, "w") as f:
        f.write(json.dumps(user_msg, separators=(",", ":")) + "\n")
        f.write(json.dumps(assistant_msg, separators=(",", ":")) + "\n")

    add_index_entry(
        project_dir,
        session_id=session_id,
        project_path=project_path,
        first_prompt=message_text[:200],
        message_count=2,
        git_branch="main",
    )

    _record_created(str(target_path))
    result["success"] = True
    result["user_uuid"] = user_msg["uuid"]
    result["assistant_uuid"] = assistant_msg["uuid"]
    return result


def cleanup() -> dict[str, Any]:
    """Remove all files created by spike 2A tests."""
    manifest = _load_manifest()
    removed = []
    failed = []

    for path_str in manifest:
        p = Path(path_str)
        if p.exists():
            try:
                p.unlink()
                removed.append(path_str)

                # Also clean up index entry if possible
                project_dir = p.parent
                session_id = p.stem
                index_path = project_dir / "sessions-index.json"
                if index_path.exists():
                    idx = json.loads(index_path.read_text())
                    idx["entries"] = [
                        e for e in idx["entries"]
                        if e.get("sessionId") != session_id
                    ]
                    index_path.write_text(json.dumps(idx, indent=2))

            except OSError as e:
                failed.append({"path": path_str, "error": str(e)})
        else:
            removed.append(path_str)  # Already gone

    # Clear manifest
    if MANIFEST_PATH.exists():
        MANIFEST_PATH.unlink()

    return {
        "removed": removed,
        "failed": failed,
        "total": len(manifest),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Claude Code Session Write-Back Test (Spike 2A)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # inject
    p_inject = sub.add_parser("inject", help="Copy session to new UUID in a project")
    p_inject.add_argument("--source", required=True, help="Source session UUID")
    p_inject.add_argument("--project", required=True, help="Target project absolute path")
    p_inject.add_argument("--dry-run", action="store_true")

    # extend
    p_extend = sub.add_parser("extend", help="Copy session and append a user message")
    p_extend.add_argument("--source", required=True, help="Source session UUID")
    p_extend.add_argument("--message", required=True, help="Message text to append")
    p_extend.add_argument("--dry-run", action="store_true")

    # cross-inject
    p_cross = sub.add_parser("cross-inject", help="Copy session to different project")
    p_cross.add_argument("--source", required=True, help="Source session UUID")
    p_cross.add_argument("--target-project", required=True, help="Target project path")
    p_cross.add_argument("--dry-run", action="store_true")

    # synthetic
    p_synth = sub.add_parser("synthetic", help="Create a fully synthetic session")
    p_synth.add_argument("--project", required=True, help="Target project absolute path")
    p_synth.add_argument("--message", required=True, help="User message text")
    p_synth.add_argument("--dry-run", action="store_true")

    # cleanup
    sub.add_parser("cleanup", help="Remove all test sessions created by this spike")

    args = parser.parse_args()

    if args.command == "inject":
        result = test_inject(args.source, args.project, dry_run=args.dry_run)
    elif args.command == "extend":
        result = test_extend(args.source, args.message, dry_run=args.dry_run)
    elif args.command == "cross-inject":
        result = test_cross_inject(
            args.source, args.target_project, dry_run=args.dry_run
        )
    elif args.command == "synthetic":
        result = test_synthetic(args.project, args.message, dry_run=args.dry_run)
    elif args.command == "cleanup":
        result = cleanup()
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2))

    if result.get("success"):
        print(f"\nTest '{args.command}' completed successfully.")
        if not result.get("dry_run"):
            print("Run 'python src/spikes/spike_2a_cc_writeback.py cleanup' to remove test files.")
    elif "removed" in result:
        print(f"\nCleanup complete: {len(result['removed'])} files removed.")
    else:
        print(f"\nTest failed: {result.get('error', 'unknown error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
