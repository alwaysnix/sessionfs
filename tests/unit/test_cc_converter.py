"""Tests for Claude Code to .sfs converter."""

from __future__ import annotations

from pathlib import Path

from sessionfs.spec.convert_cc import convert_session
from sessionfs.spec.validate import validate_session
from sessionfs.watchers.claude_code import parse_session

FIXTURES = Path(__file__).parent.parent / "fixtures" / "cc_sessions"


def test_convert_minimal_session(tmp_path: Path):
    """Convert a minimal session and validate output."""
    cc_session = parse_session(FIXTURES / "minimal.jsonl", copy_on_read=False)
    session_dir = convert_session(cc_session, tmp_path)

    assert session_dir.is_dir()
    assert (session_dir / "manifest.json").exists()
    assert (session_dir / "messages.jsonl").exists()
    assert (session_dir / "workspace.json").exists()
    assert (session_dir / "tools.json").exists()

    result = validate_session(session_dir)
    assert result.valid, f"Validation errors: {result.errors}"


def test_convert_with_explicit_session_id(tmp_path: Path):
    """session_id parameter controls the output directory name."""
    cc_session = parse_session(FIXTURES / "minimal.jsonl", copy_on_read=False)
    session_dir = convert_session(cc_session, tmp_path, session_id="my-custom-id")

    assert session_dir.name == "my-custom-id"
    assert (session_dir / "manifest.json").exists()

    import json
    manifest = json.loads((session_dir / "manifest.json").read_text())
    assert manifest["session_id"] == "my-custom-id"


def test_convert_with_tools(tmp_path: Path):
    """Convert a session with tool_use blocks and validate."""
    cc_session = parse_session(FIXTURES / "with_tools.jsonl", copy_on_read=False)
    session_dir = convert_session(cc_session, tmp_path)

    result = validate_session(session_dir)
    assert result.valid, f"Validation errors: {result.errors}"

    import json
    manifest = json.loads((session_dir / "manifest.json").read_text())
    assert manifest["stats"]["tool_use_count"] >= 1
    assert manifest["stats"]["message_count"] == 4


def test_convert_with_subagents(tmp_path: Path):
    """Convert a session with sub-agents and validate."""
    cc_session = parse_session(
        FIXTURES / "test-subagent-9999.jsonl", copy_on_read=False
    )
    session_dir = convert_session(cc_session, tmp_path)

    result = validate_session(session_dir)
    assert result.valid, f"Validation errors: {result.errors}"

    import json
    manifest = json.loads((session_dir / "manifest.json").read_text())
    assert "sub_agents" in manifest
    assert len(manifest["sub_agents"]) == 1
    assert manifest["sub_agents"][0]["agent_id"] == "agent-explore-001"

    # Check messages include sidechain entries
    messages = []
    with open(session_dir / "messages.jsonl") as f:
        for line in f:
            messages.append(json.loads(line))

    sidechain = [m for m in messages if m.get("is_sidechain")]
    assert len(sidechain) == 4


def test_convert_idempotent(tmp_path: Path):
    """Re-converting with same session_id overwrites cleanly."""
    cc_session = parse_session(FIXTURES / "minimal.jsonl", copy_on_read=False)

    dir1 = convert_session(cc_session, tmp_path, session_id="test-idem")
    dir2 = convert_session(cc_session, tmp_path, session_id="test-idem")

    assert dir1 == dir2
    result = validate_session(dir2)
    assert result.valid
