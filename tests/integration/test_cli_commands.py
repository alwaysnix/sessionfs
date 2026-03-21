"""Integration tests for CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sessionfs.cli.main import app
from sessionfs.cli.sfs_to_cc import read_sessions_index
from sessionfs.spec.convert_cc import convert_session
from sessionfs.store.local import LocalStore
from sessionfs.watchers.claude_code import parse_session

runner = CliRunner()

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "cc_sessions"


@pytest.fixture
def populated_store(tmp_path: Path) -> tuple[Path, LocalStore]:
    """Create a store populated with converted CC fixtures."""
    store_dir = tmp_path / ".sessionfs"
    store = LocalStore(store_dir)
    store.initialize()

    # Import a fixture session
    from sessionfs.session_id import session_id_from_native

    jsonl_path = FIXTURES_DIR / "with_tools.jsonl"
    cc_session = parse_session(jsonl_path, copy_on_read=False)
    native_id = cc_session.session_id or "test-with-tools"
    session_id = session_id_from_native(native_id)

    session_dir = store.allocate_session_dir(session_id)
    convert_session(cc_session, session_dir.parent, session_id=session_id, session_dir=session_dir)

    manifest = json.loads((session_dir / "manifest.json").read_text())
    store.upsert_session_metadata(session_id, manifest, str(session_dir))

    return store_dir, store


def _patch_store_dir(store_dir: Path):
    """Patch get_store_dir to return our test store directory.

    We patch in all modules that import it by name.
    """
    from contextlib import ExitStack

    class _MultiPatch:
        def __init__(self, store_dir: Path):
            self._store_dir = store_dir
            self._stack: ExitStack | None = None

        def __enter__(self):
            self._stack = ExitStack()
            targets = [
                "sessionfs.cli.common.get_store_dir",
                "sessionfs.cli.cmd_config.get_store_dir",
                "sessionfs.cli.cmd_daemon.get_store_dir",
            ]
            for target in targets:
                self._stack.enter_context(patch(target, return_value=self._store_dir))
            return self

        def __exit__(self, *args):
            if self._stack:
                self._stack.__exit__(*args)

    return _MultiPatch(store_dir)


def test_list_empty(tmp_path: Path):
    store_dir = tmp_path / ".sessionfs"
    store = LocalStore(store_dir)
    store.initialize()
    store.close()

    with _patch_store_dir(store_dir):
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No sessions found" in result.output


def test_list_with_sessions(populated_store: tuple[Path, LocalStore]):
    store_dir, store = populated_store

    with _patch_store_dir(store_dir):
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Sessions" in result.output

    store.close()


def test_list_quiet(populated_store: tuple[Path, LocalStore]):
    store_dir, store = populated_store

    with _patch_store_dir(store_dir):
        result = runner.invoke(app, ["list", "--quiet"])
        assert result.exit_code == 0
        # Output should be just the session ID(s)
        lines = result.output.strip().split("\n")
        assert len(lines) >= 1

    store.close()


def test_show_session(populated_store: tuple[Path, LocalStore]):
    store_dir, store = populated_store
    sessions = store.list_sessions()
    sid = sessions[0]["session_id"]

    with _patch_store_dir(store_dir):
        result = runner.invoke(app, ["show", sid[:8]])
        assert result.exit_code == 0
        assert "Session Details" in result.output

    store.close()


def test_checkpoint(populated_store: tuple[Path, LocalStore]):
    store_dir, store = populated_store
    sessions = store.list_sessions()
    sid = sessions[0]["session_id"]

    with _patch_store_dir(store_dir):
        result = runner.invoke(app, ["checkpoint", sid[:8], "--name", "v1"])
        assert result.exit_code == 0
        assert "Checkpoint" in result.output

    # Verify checkpoint exists
    session_dir = store.get_session_dir(sid)
    assert (session_dir / "checkpoints" / "v1" / "manifest.json").exists()
    assert (session_dir / "checkpoints" / "v1" / "messages.jsonl").exists()

    store.close()


def test_fork(populated_store: tuple[Path, LocalStore]):
    store_dir, store = populated_store
    sessions = store.list_sessions()
    sid = sessions[0]["session_id"]

    with _patch_store_dir(store_dir):
        result = runner.invoke(app, ["fork", sid[:8], "--name", "My Fork"])
        assert result.exit_code == 0
        assert "Forked" in result.output

    # Verify forked session exists
    all_sessions = store.list_sessions()
    assert len(all_sessions) == 2

    forked = [s for s in all_sessions if s["session_id"] != sid]
    assert len(forked) == 1

    forked_dir = store.get_session_dir(forked[0]["session_id"])
    manifest = json.loads((forked_dir / "manifest.json").read_text())
    assert manifest["title"] == "My Fork"
    assert manifest["parent_session_id"] == sid

    store.close()


def test_export_markdown(populated_store: tuple[Path, LocalStore], tmp_path: Path):
    store_dir, store = populated_store
    sessions = store.list_sessions()
    sid = sessions[0]["session_id"]
    output_dir = tmp_path / "export"

    with _patch_store_dir(store_dir):
        result = runner.invoke(
            app, ["export", sid[:8], "--output", str(output_dir), "--format", "markdown"]
        )
        assert result.exit_code == 0

    md_file = output_dir / f"{sid}.md"
    assert md_file.exists()
    content = md_file.read_text()
    assert "###" in content  # Has message headers

    store.close()


def test_export_claude_code(populated_store: tuple[Path, LocalStore], tmp_path: Path):
    store_dir, store = populated_store
    sessions = store.list_sessions()
    sid = sessions[0]["session_id"]
    output_dir = tmp_path / "export"

    with _patch_store_dir(store_dir):
        result = runner.invoke(
            app, ["export", sid[:8], "--output", str(output_dir), "--format", "claude-code"]
        )
        assert result.exit_code == 0

    jsonl_file = output_dir / f"{sid}.jsonl"
    assert jsonl_file.exists()

    lines = jsonl_file.read_text().strip().split("\n")
    assert len(lines) >= 1
    first = json.loads(lines[0])
    assert first["type"] in ("user", "assistant", "summary")

    store.close()


def test_config_show(tmp_path: Path):
    store_dir = tmp_path / ".sessionfs"
    store_dir.mkdir(parents=True)

    with _patch_store_dir(store_dir):
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "config.toml" in result.output.lower() or "Config" in result.output


def test_config_set(tmp_path: Path):
    store_dir = tmp_path / ".sessionfs"
    store_dir.mkdir(parents=True)

    with _patch_store_dir(store_dir):
        result = runner.invoke(app, ["config", "set", "log_level", "DEBUG"])
        assert result.exit_code == 0
        assert "Set" in result.output

        # Verify it was written
        config_path = store_dir / "config.toml"
        assert config_path.exists()
        content = config_path.read_text()
        assert "DEBUG" in content
