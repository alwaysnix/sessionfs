"""Tests for the SQLite session index."""

from __future__ import annotations

from pathlib import Path

from sessionfs.store.index import SessionIndex
from sessionfs.watchers.base import NativeSessionRef


def test_initialize_creates_tables(tmp_path: Path):
    """initialize() creates all expected tables."""
    index = SessionIndex(tmp_path / "index.db")
    index.initialize()

    tables = index.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {t["name"] for t in tables}
    assert "sessions" in table_names
    assert "tracked_sessions" in table_names
    assert "schema_version" in table_names

    index.close()


def test_upsert_and_list_session(tmp_path: Path):
    """Can insert and list a session."""
    index = SessionIndex(tmp_path / "index.db")
    index.initialize()

    manifest = {
        "title": "Test session",
        "created_at": "2026-03-20T10:00:00Z",
        "source": {"tool": "claude-code", "tool_version": "2.1.59"},
        "model": {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
        "stats": {"message_count": 5, "turn_count": 2, "tool_use_count": 1},
        "tags": ["test"],
    }
    index.upsert_session("ses-001", manifest, "/tmp/ses-001.sfs")

    sessions = index.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "ses-001"
    assert sessions[0]["title"] == "Test session"
    assert sessions[0]["source_tool"] == "claude-code"
    assert sessions[0]["message_count"] == 5

    index.close()


def test_upsert_session_updates(tmp_path: Path):
    """Upserting same session_id updates the record."""
    index = SessionIndex(tmp_path / "index.db")
    index.initialize()

    manifest1 = {
        "title": "V1",
        "created_at": "2026-03-20T10:00:00Z",
        "source": {"tool": "claude-code"},
        "stats": {"message_count": 2},
    }
    index.upsert_session("ses-001", manifest1, "/tmp/ses-001.sfs")

    manifest2 = {
        "title": "V2",
        "created_at": "2026-03-20T10:00:00Z",
        "source": {"tool": "claude-code"},
        "stats": {"message_count": 10},
    }
    index.upsert_session("ses-001", manifest2, "/tmp/ses-001.sfs")

    sessions = index.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["title"] == "V2"
    assert sessions[0]["message_count"] == 10

    index.close()


def test_tracked_session_crud(tmp_path: Path):
    """Can insert, read, and update tracked sessions."""
    index = SessionIndex(tmp_path / "index.db")
    index.initialize()

    # Insert a session first (for FK)
    index.upsert_session(
        "sfs-001",
        {"created_at": "2026-03-20T10:00:00Z", "source": {"tool": "claude-code"}},
        "/tmp/sfs-001.sfs",
    )

    ref = NativeSessionRef(
        tool="claude-code",
        native_session_id="native-001",
        native_path="/home/user/.claude/projects/foo/native-001.jsonl",
        sfs_session_id="sfs-001",
        last_mtime=1234567890.0,
        last_size=5000,
        last_captured_at="2026-03-20T10:00:00Z",
        project_path="/Users/test/myproject",
    )
    index.upsert_tracked_session(ref)

    loaded = index.get_tracked_session("native-001")
    assert loaded is not None
    assert loaded.tool == "claude-code"
    assert loaded.last_mtime == 1234567890.0
    assert loaded.last_size == 5000
    assert loaded.sfs_session_id == "sfs-001"

    # Update
    ref.last_mtime = 9999999999.0
    ref.last_size = 10000
    index.upsert_tracked_session(ref)

    loaded = index.get_tracked_session("native-001")
    assert loaded is not None
    assert loaded.last_mtime == 9999999999.0
    assert loaded.last_size == 10000

    index.close()


def test_tracked_session_not_found(tmp_path: Path):
    """get_tracked_session returns None for missing entries."""
    index = SessionIndex(tmp_path / "index.db")
    index.initialize()
    assert index.get_tracked_session("nonexistent") is None
    index.close()


def test_session_count(tmp_path: Path):
    """session_count returns the correct count."""
    index = SessionIndex(tmp_path / "index.db")
    index.initialize()

    assert index.session_count() == 0

    index.upsert_session(
        "s1",
        {"created_at": "2026-03-20T10:00:00Z", "source": {"tool": "test"}},
        "/tmp/s1",
    )
    assert index.session_count() == 1

    index.close()
