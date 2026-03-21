"""M8: File permissions on ~/.sessionfs/."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from sessionfs.store.local import LocalStore


class TestFilePermissions:

    def test_store_dir_created_with_0700(self, tmp_path: Path):
        store_dir = tmp_path / ".sessionfs"
        store = LocalStore(store_dir)
        store.initialize()

        mode = os.stat(store_dir).st_mode & 0o777
        assert mode == 0o700, f"Expected 0o700, got {oct(mode)}"

    def test_sessions_dir_created_with_0700(self, tmp_path: Path):
        store_dir = tmp_path / ".sessionfs"
        store = LocalStore(store_dir)
        store.initialize()

        sessions_dir = store_dir / "sessions"
        mode = os.stat(sessions_dir).st_mode & 0o777
        assert mode == 0o700, f"Expected 0o700, got {oct(mode)}"

    def test_index_db_created_with_0600(self, tmp_path: Path):
        store_dir = tmp_path / ".sessionfs"
        store = LocalStore(store_dir)
        store.initialize()

        index_path = store_dir / "index.db"
        assert index_path.exists()
        mode = os.stat(index_path).st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_session_dir_allocated_with_0700(self, tmp_path: Path):
        store_dir = tmp_path / ".sessionfs"
        store = LocalStore(store_dir)
        store.initialize()

        session_dir = store.allocate_session_dir("ses_abc123def456ab")
        mode = os.stat(session_dir).st_mode & 0o777
        assert mode == 0o700, f"Expected 0o700, got {oct(mode)}"

    def test_check_permissions_warns_on_wrong_perms(self, tmp_path: Path):
        store_dir = tmp_path / ".sessionfs"
        store_dir.mkdir(parents=True)
        os.chmod(store_dir, 0o755)  # Wrong permissions

        store = LocalStore(store_dir)
        warnings = store.check_permissions()
        assert len(warnings) > 0
        assert "0o755" in warnings[0]

    def test_check_permissions_ok_when_correct(self, tmp_path: Path):
        store_dir = tmp_path / ".sessionfs"
        store = LocalStore(store_dir)
        store.initialize()

        warnings = store.check_permissions()
        assert len(warnings) == 0

    def test_store_not_group_readable(self, tmp_path: Path):
        store_dir = tmp_path / ".sessionfs"
        store = LocalStore(store_dir)
        store.initialize()

        st = os.stat(store_dir)
        assert not (st.st_mode & stat.S_IRGRP), "Store should not be group-readable"
        assert not (st.st_mode & stat.S_IROTH), "Store should not be other-readable"
