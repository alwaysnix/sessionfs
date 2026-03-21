"""Tests for the local session store."""

from __future__ import annotations

from pathlib import Path

from sessionfs.store.local import LocalStore


def test_initialize_creates_dirs(tmp_path: Path):
    """initialize() creates store and sessions directories."""
    store_dir = tmp_path / ".sessionfs"
    store = LocalStore(store_dir)
    store.initialize()

    assert store_dir.is_dir()
    assert (store_dir / "sessions").is_dir()
    assert (store_dir / "index.db").exists()
    store.close()


def test_allocate_session_dir(tmp_path: Path):
    """allocate_session_dir creates a .sfs directory."""
    store = LocalStore(tmp_path)
    store.initialize()

    session_dir = store.allocate_session_dir("test-session-123")
    assert session_dir.is_dir()
    assert session_dir.name == "test-session-123.sfs"
    store.close()


def test_get_session_dir_exists(tmp_path: Path):
    """get_session_dir returns the directory if it exists."""
    store = LocalStore(tmp_path)
    store.initialize()

    store.allocate_session_dir("abc")
    assert store.get_session_dir("abc") is not None
    store.close()


def test_get_session_dir_missing(tmp_path: Path):
    """get_session_dir returns None for missing sessions."""
    store = LocalStore(tmp_path)
    store.initialize()

    assert store.get_session_dir("nonexistent") is None
    store.close()


def test_session_manifest_read(tmp_path: Path):
    """get_session_manifest reads manifest.json from session dir."""
    store = LocalStore(tmp_path)
    store.initialize()

    session_dir = store.allocate_session_dir("test-manifest")
    import json
    (session_dir / "manifest.json").write_text(json.dumps({"title": "Test"}))

    manifest = store.get_session_manifest("test-manifest")
    assert manifest is not None
    assert manifest["title"] == "Test"
    store.close()
