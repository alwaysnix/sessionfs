"""Tests for Claude Code session parser."""

from __future__ import annotations

from pathlib import Path

from sessionfs.watchers.claude_code import (
    ParsedSession,
    discover_projects,
    discover_sessions,
    parse_session,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "cc_sessions"


def test_parse_minimal_session():
    """Parse a minimal 2-message session."""
    session = parse_session(FIXTURES / "minimal.jsonl", copy_on_read=False)
    assert session.session_id == "minimal"
    assert session.message_count == 2
    assert session.messages[0].role == "user"
    assert session.messages[1].role == "assistant"
    assert session.claude_code_version == "2.1.59"
    assert session.git_branch == "main"
    assert session.project_path == "/Users/test/myproject"
    assert len(session.parse_errors) == 0


def test_parse_session_with_tools():
    """Parse a session with tool_use and tool_result blocks."""
    session = parse_session(FIXTURES / "with_tools.jsonl", copy_on_read=False)
    assert session.message_count == 4
    assert session.session_id == "with_tools"

    # Check assistant message has thinking, text, and tool_use blocks
    assistant_msg = session.messages[1]
    assert assistant_msg.role == "assistant"
    block_types = [b.block_type for b in assistant_msg.content_blocks]
    assert "thinking" in block_types
    assert "text" in block_types
    assert "tool_use" in block_types

    # Check tool_use details
    tool_block = [b for b in assistant_msg.content_blocks if b.block_type == "tool_use"][0]
    assert tool_block.tool_name == "Read"
    assert tool_block.tool_input == {"file_path": "README.md"}

    # Check tool_result
    tool_result_msg = session.messages[2]
    assert tool_result_msg.role == "user"
    result_block = tool_result_msg.content_blocks[0]
    assert result_block.block_type == "tool_result"
    assert "My Project" in (result_block.tool_result_content or "")


def test_parse_session_with_subagents():
    """Parse a session with sub-agent files."""
    session = parse_session(FIXTURES / "test-subagent-9999.jsonl", copy_on_read=False)
    assert session.message_count == 4
    assert len(session.sub_agents) == 1

    sub = session.sub_agents[0]
    assert sub.agent_id == "agent-explore-001"
    assert sub.model == "claude-haiku-4-5-20251001"
    assert len(sub.messages) == 4


def test_parse_copy_on_read():
    """copy_on_read=True still produces correct results."""
    session = parse_session(FIXTURES / "minimal.jsonl", copy_on_read=True)
    assert session.message_count == 2
    assert session.messages[0].role == "user"


def test_first_prompt_extracted():
    """First user prompt is captured."""
    session = parse_session(FIXTURES / "minimal.jsonl", copy_on_read=False)
    assert session.first_prompt == "Hello, how are you?"


def test_discover_projects_missing_dir(tmp_path: Path):
    """discover_projects returns empty for missing directory."""
    assert discover_projects(tmp_path / "nonexistent") == []


def test_discover_sessions_missing_dir(tmp_path: Path):
    """discover_sessions returns empty for missing directory."""
    assert discover_sessions(tmp_path / "nonexistent") == []


def test_discover_sessions_with_fixtures(tmp_claude_home: Path):
    """discover_sessions finds sessions in the fixture directory."""
    sessions = discover_sessions(tmp_claude_home)
    assert len(sessions) >= 3  # minimal, with_tools, test-subagent-9999
    session_ids = {s["session_id"] for s in sessions}
    assert "minimal" in session_ids
    assert "with_tools" in session_ids
