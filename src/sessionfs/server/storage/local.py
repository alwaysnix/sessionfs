"""Local filesystem blob store for dev/test."""

from __future__ import annotations

from pathlib import Path


class LocalBlobStore:
    """Stores blobs on the local filesystem."""

    def __init__(self, root_path: Path) -> None:
        self.root = root_path.resolve()

    def _safe_path(self, key: str) -> Path:
        """Resolve key to a path and verify it's within root."""
        if ".." in key or key.startswith("/") or "\x00" in key:
            raise ValueError(f"Invalid blob key: {key!r}")
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root)):
            raise ValueError(f"Path traversal detected: {key!r}")
        return path

    async def put(self, key: str, data: bytes) -> None:
        path = self._safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes | None:
        path = self._safe_path(key)
        if not path.is_file():
            return None
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._safe_path(key)
        if path.is_file():
            path.unlink()

    async def exists(self, key: str) -> bool:
        path = self._safe_path(key)
        return path.is_file()
