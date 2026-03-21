"""Unit tests for sync archive pack/unpack."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sessionfs.sync.archive import pack_session, unpack_session


@pytest.fixture
def sample_session(tmp_path: Path) -> Path:
    """Create a minimal .sfs session directory."""
    session_dir = tmp_path / "test-session.sfs"
    session_dir.mkdir()

    manifest = {
        "sfs_version": "0.1.0",
        "session_id": "ses_testsession01",
        "title": "Test",
        "source": {"tool": "claude-code"},
    }
    (session_dir / "manifest.json").write_text(json.dumps(manifest))
    (session_dir / "messages.jsonl").write_text(
        '{"role": "user", "content": [{"type": "text", "text": "hello"}]}\n'
        '{"role": "assistant", "content": [{"type": "text", "text": "hi"}]}\n'
    )
    return session_dir


def test_pack_produces_bytes(sample_session: Path):
    data = pack_session(sample_session)
    assert isinstance(data, bytes)
    assert len(data) > 0
    # Should be gzip-compressed (magic bytes)
    assert data[:2] == b"\x1f\x8b"


def test_roundtrip(sample_session: Path, tmp_path: Path):
    """Pack then unpack should produce identical files."""
    data = pack_session(sample_session)

    target = tmp_path / "unpacked"
    unpack_session(data, target)

    # Check files exist
    assert (target / "manifest.json").exists()
    assert (target / "messages.jsonl").exists()

    # Check content matches
    original_manifest = json.loads((sample_session / "manifest.json").read_text())
    unpacked_manifest = json.loads((target / "manifest.json").read_text())
    assert original_manifest == unpacked_manifest

    original_messages = (sample_session / "messages.jsonl").read_text()
    unpacked_messages = (target / "messages.jsonl").read_text()
    assert original_messages == unpacked_messages


def test_pack_includes_subdirectories(tmp_path: Path):
    """Pack should include nested files like checkpoints/."""
    session_dir = tmp_path / "session.sfs"
    session_dir.mkdir()
    (session_dir / "manifest.json").write_text("{}")

    checkpoint_dir = session_dir / "checkpoints" / "v1"
    checkpoint_dir.mkdir(parents=True)
    (checkpoint_dir / "manifest.json").write_text('{"checkpoint": true}')

    data = pack_session(session_dir)
    target = tmp_path / "unpacked"
    unpack_session(data, target)

    assert (target / "checkpoints" / "v1" / "manifest.json").exists()


def test_unpack_creates_target_dir(sample_session: Path, tmp_path: Path):
    """Unpack should create target directory if it doesn't exist."""
    data = pack_session(sample_session)
    target = tmp_path / "new" / "nested" / "dir"
    assert not target.exists()

    unpack_session(data, target)
    assert target.exists()
    assert (target / "manifest.json").exists()
