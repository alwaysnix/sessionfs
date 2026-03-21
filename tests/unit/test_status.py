"""Tests for daemon status reporting."""

from __future__ import annotations

from pathlib import Path

from sessionfs.daemon.status import (
    DaemonStatus,
    WatcherStatus,
    clear_status,
    read_status,
    write_status,
)


def test_write_and_read_status(tmp_path: Path):
    """Status can be written and read back."""
    status_path = tmp_path / "daemon.json"
    status = DaemonStatus(
        store_dir="/tmp/test",
        sessions_total=5,
        watchers=[
            WatcherStatus(name="claude-code", enabled=True, health="healthy", sessions_tracked=5)
        ],
    )
    write_status(status, status_path)

    loaded = read_status(status_path)
    assert loaded is not None
    assert loaded.sessions_total == 5
    assert len(loaded.watchers) == 1
    assert loaded.watchers[0].name == "claude-code"


def test_read_status_missing(tmp_path: Path):
    """Reading missing status file returns None."""
    assert read_status(tmp_path / "nonexistent.json") is None


def test_read_status_corrupt(tmp_path: Path):
    """Reading corrupt status file returns None."""
    status_path = tmp_path / "daemon.json"
    status_path.write_text("not json")
    assert read_status(status_path) is None


def test_clear_status(tmp_path: Path):
    """clear_status removes the file."""
    status_path = tmp_path / "daemon.json"
    status_path.write_text("{}")
    clear_status(status_path)
    assert not status_path.exists()


def test_clear_status_missing(tmp_path: Path):
    """clear_status on missing file doesn't raise."""
    clear_status(tmp_path / "nonexistent.json")


def test_atomic_write(tmp_path: Path):
    """write_status uses atomic write (no .tmp file left behind)."""
    status_path = tmp_path / "daemon.json"
    write_status(DaemonStatus(store_dir="/tmp"), status_path)
    assert status_path.exists()
    assert not status_path.with_suffix(".tmp").exists()
