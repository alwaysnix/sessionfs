"""M1: Path traversal protection in LocalBlobStore."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="Server tests require: pip install -e '.[dev]'")

from sessionfs.server.storage.local import LocalBlobStore


@pytest.fixture
def blob_store(tmp_path: Path) -> LocalBlobStore:
    root = tmp_path / "blobs"
    root.mkdir()
    return LocalBlobStore(root)


class TestPathTraversalRejection:

    @pytest.mark.asyncio
    async def test_put_dotdot_rejected(self, blob_store: LocalBlobStore):
        with pytest.raises(ValueError, match="Invalid blob key"):
            await blob_store.put("../../etc/passwd", b"malicious")

    @pytest.mark.asyncio
    async def test_get_dotdot_rejected(self, blob_store: LocalBlobStore):
        with pytest.raises(ValueError, match="Invalid blob key"):
            await blob_store.get("../../../etc/shadow")

    @pytest.mark.asyncio
    async def test_delete_dotdot_rejected(self, blob_store: LocalBlobStore):
        with pytest.raises(ValueError, match="Invalid blob key"):
            await blob_store.delete("../../etc/passwd")

    @pytest.mark.asyncio
    async def test_exists_dotdot_rejected(self, blob_store: LocalBlobStore):
        with pytest.raises(ValueError, match="Invalid blob key"):
            await blob_store.exists("../secret")

    @pytest.mark.asyncio
    async def test_absolute_path_rejected(self, blob_store: LocalBlobStore):
        with pytest.raises(ValueError, match="Invalid blob key"):
            await blob_store.put("/etc/passwd", b"data")

    @pytest.mark.asyncio
    async def test_null_byte_rejected(self, blob_store: LocalBlobStore):
        with pytest.raises(ValueError, match="Invalid blob key"):
            await blob_store.put("file\x00.txt", b"data")

    @pytest.mark.asyncio
    async def test_nested_traversal_rejected(self, blob_store: LocalBlobStore):
        with pytest.raises(ValueError, match="Invalid blob key"):
            await blob_store.put("sessions/../../escape", b"data")

    @pytest.mark.asyncio
    async def test_valid_key_works(self, blob_store: LocalBlobStore):
        await blob_store.put("sessions/user1/data.tar.gz", b"valid")
        result = await blob_store.get("sessions/user1/data.tar.gz")
        assert result == b"valid"

    @pytest.mark.asyncio
    async def test_valid_nested_key(self, blob_store: LocalBlobStore):
        await blob_store.put("a/b/c/d.txt", b"deep")
        assert await blob_store.exists("a/b/c/d.txt")
