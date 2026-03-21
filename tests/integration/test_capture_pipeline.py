"""Integration test: full capture pipeline.

Places CC session fixtures in a fake ~/.claude/, runs the watcher's
full_scan(), and verifies the output .sfs sessions pass schema validation.
"""

from __future__ import annotations

import json
from pathlib import Path

from sessionfs.daemon.config import ClaudeCodeWatcherConfig
from sessionfs.spec.validate import validate_session
from sessionfs.store.local import LocalStore
from sessionfs.watchers.claude_code import ClaudeCodeWatcher


def test_full_capture_pipeline(tmp_claude_home: Path, tmp_store: Path):
    """End-to-end: CC fixtures → watcher full_scan → .sfs → validation."""
    store = LocalStore(tmp_store)
    store.initialize()

    config = ClaudeCodeWatcherConfig(home_dir=tmp_claude_home)
    watcher = ClaudeCodeWatcher(config=config, store=store, scan_interval=0.0)

    # Run full scan
    watcher.full_scan()

    # Check watcher status
    status = watcher.get_status()
    assert status.health == "healthy"
    assert status.sessions_tracked >= 3  # minimal, with_tools, test-subagent-9999

    # Verify captured .sfs sessions
    sessions = store.list_sessions()
    assert len(sessions) >= 3

    for session_row in sessions:
        session_dir = Path(session_row["sfs_dir_path"])
        assert session_dir.is_dir(), f"Session dir missing: {session_dir}"

        # Validate against JSON schemas
        result = validate_session(session_dir)
        assert result.valid, (
            f"Session {session_row['session_id']} failed validation: {result.errors}"
        )

    store.close()


def test_capture_detects_changes(tmp_claude_home: Path, tmp_store: Path):
    """Watcher skips unchanged sessions on second scan."""
    store = LocalStore(tmp_store)
    store.initialize()

    config = ClaudeCodeWatcherConfig(home_dir=tmp_claude_home)
    watcher = ClaudeCodeWatcher(config=config, store=store, scan_interval=0.0)

    # First scan
    watcher.full_scan()
    status1 = watcher.get_status()

    # Second scan — nothing changed, should skip
    watcher.full_scan()
    status2 = watcher.get_status()

    assert status1.sessions_tracked == status2.sessions_tracked
    assert status2.health == "healthy"

    store.close()


def test_capture_subagent_session(tmp_claude_home: Path, tmp_store: Path):
    """Sub-agent messages are captured as sidechain in .sfs output."""
    store = LocalStore(tmp_store)
    store.initialize()

    config = ClaudeCodeWatcherConfig(home_dir=tmp_claude_home)
    watcher = ClaudeCodeWatcher(config=config, store=store, scan_interval=0.0)
    watcher.full_scan()

    # Find the subagent session (ID is now ses_ prefixed)
    from sessionfs.session_id import session_id_from_native
    session_dir = store.get_session_dir(session_id_from_native("test-subagent-9999"))
    assert session_dir is not None

    # Read messages and check for sidechain entries
    messages = []
    with open(session_dir / "messages.jsonl") as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))

    sidechain = [m for m in messages if m.get("is_sidechain")]
    assert len(sidechain) == 4

    # Check manifest has sub_agents
    manifest = json.loads((session_dir / "manifest.json").read_text())
    assert "sub_agents" in manifest
    assert manifest["sub_agents"][0]["agent_id"] == "agent-explore-001"

    store.close()


def test_missing_claude_dir(tmp_path: Path):
    """Watcher degrades gracefully when Claude Code is not installed."""
    store = LocalStore(tmp_path / "store")
    store.initialize()

    config = ClaudeCodeWatcherConfig(home_dir=tmp_path / "nonexistent")
    watcher = ClaudeCodeWatcher(config=config, store=store, scan_interval=0.0)
    watcher.full_scan()

    status = watcher.get_status()
    assert status.health == "degraded"
    assert status.sessions_tracked == 0

    store.close()
