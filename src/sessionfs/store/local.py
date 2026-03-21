"""Local session store at ~/.sessionfs/.

Directory layout:
    ~/.sessionfs/
    ├── config.toml
    ├── daemon.json
    ├── sfsd.pid
    ├── index.db
    └── sessions/
        └── {session_id}.sfs/
            ├── manifest.json
            ├── messages.jsonl
            ├── workspace.json
            └── tools.json
"""

from __future__ import annotations

import json
import logging
import os
import re
import stat
from pathlib import Path
from typing import Any

from sessionfs.store.index import SessionIndex
from sessionfs.watchers.base import NativeSessionRef

logger = logging.getLogger("sessionfs.store")

# M2: Session ID validation at store layer — imported from canonical module
from sessionfs.session_id import SESSION_ID_RE, validate_session_id


def _validate_session_id(session_id: str) -> None:
    """Validate session ID format at the store layer."""
    if not validate_session_id(session_id):
        raise ValueError(f"Invalid session ID format: {session_id!r}")


def _set_dir_permissions(path: Path) -> None:
    """Set directory to 0700 (owner rwx only)."""
    os.chmod(path, stat.S_IRWXU)


def _set_file_permissions(path: Path) -> None:
    """Set file to 0600 (owner rw only)."""
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


class LocalStore:
    """Manages the local ~/.sessionfs/ directory and SQLite index."""

    def __init__(self, store_dir: Path) -> None:
        self._store_dir = store_dir
        self._sessions_dir = store_dir / "sessions"
        self._index: SessionIndex | None = None

    def initialize(self) -> None:
        """Create directory structure and open the index database."""
        self._store_dir.mkdir(parents=True, exist_ok=True)
        _set_dir_permissions(self._store_dir)
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        _set_dir_permissions(self._sessions_dir)
        self._index = SessionIndex(self._store_dir / "index.db")
        self._index.initialize()
        # M8: Restrict index.db permissions
        index_path = self._store_dir / "index.db"
        if index_path.exists():
            _set_file_permissions(index_path)

    def check_permissions(self) -> list[str]:
        """Check store directory permissions and return warnings."""
        warnings: list[str] = []
        if self._store_dir.exists():
            mode = self._store_dir.stat().st_mode
            if mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP |
                       stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH):
                warnings.append(
                    f"Store directory {self._store_dir} has permissions "
                    f"{oct(mode & 0o777)} (expected 0o700)"
                )
        return warnings

    @property
    def sessions_dir(self) -> Path:
        return self._sessions_dir

    @property
    def index(self) -> SessionIndex:
        if self._index is None:
            raise RuntimeError("Store not initialized. Call initialize() first.")
        return self._index

    def allocate_session_dir(self, session_id: str) -> Path:
        """Get or create the .sfs directory for a session."""
        session_dir = self._sessions_dir / f"{session_id}.sfs"
        session_dir.mkdir(parents=True, exist_ok=True)
        _set_dir_permissions(session_dir)
        return session_dir

    def get_session_dir(self, session_id: str) -> Path | None:
        """Get an existing session directory, or None."""
        session_dir = self._sessions_dir / f"{session_id}.sfs"
        return session_dir if session_dir.is_dir() else None

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions from the index."""
        return self.index.list_sessions()

    def get_tracked_session(self, native_session_id: str) -> NativeSessionRef | None:
        """Look up a tracked session by native ID."""
        return self.index.get_tracked_session(native_session_id)

    def upsert_tracked_session(self, ref: NativeSessionRef) -> None:
        """Insert or update a tracked session record."""
        self.index.upsert_tracked_session(ref)

    def upsert_session_metadata(
        self, session_id: str, manifest: dict[str, Any], sfs_dir_path: str
    ) -> None:
        """Insert or update session metadata in the index."""
        self.index.upsert_session(session_id, manifest, sfs_dir_path)

    def get_session_metadata(self, session_id: str) -> dict[str, Any] | None:
        """Get a single session's index data by ID."""
        return self.index.get_session(session_id)

    def find_sessions_by_prefix(self, prefix: str) -> list[dict[str, Any]]:
        """Find sessions whose ID starts with given prefix."""
        return self.index.find_sessions_by_prefix(prefix)

    def get_session_manifest(self, session_id: str) -> dict[str, Any] | None:
        """Read a session's manifest.json."""
        session_dir = self.get_session_dir(session_id)
        if not session_dir:
            return None
        manifest_path = session_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        return json.loads(manifest_path.read_text())

    def close(self) -> None:
        """Close the index database."""
        if self._index:
            self._index.close()
