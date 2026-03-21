"""M3: Upload size limit (100 MB)."""

from __future__ import annotations

import io

import pytest

pytest.importorskip("fastapi", reason="Server tests require: pip install -e '.[dev]'")

from fastapi import HTTPException, UploadFile

from sessionfs.server.routes.sessions import _read_upload


class TestUploadSizeLimit:

    @pytest.mark.asyncio
    async def test_small_upload_accepted(self):
        data = b"x" * 1024  # 1 KB
        file = UploadFile(file=io.BytesIO(data), filename="test.tar.gz")
        result = await _read_upload(file, max_bytes=100 * 1024 * 1024)
        assert result == data

    @pytest.mark.asyncio
    async def test_exact_limit_accepted(self):
        data = b"x" * 1024
        file = UploadFile(file=io.BytesIO(data), filename="test.tar.gz")
        result = await _read_upload(file, max_bytes=1024)
        assert len(result) == 1024

    @pytest.mark.asyncio
    async def test_over_limit_rejected(self):
        data = b"x" * (1024 + 1)
        file = UploadFile(file=io.BytesIO(data), filename="test.tar.gz")
        with pytest.raises(HTTPException) as exc_info:
            await _read_upload(file, max_bytes=1024)
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_101mb_rejected(self):
        # Simulate a 101 MB upload (we don't actually allocate 101 MB,
        # we test the logic with a smaller threshold)
        data = b"x" * (2 * 1024 * 1024 + 1)  # Just over 2 MB
        file = UploadFile(file=io.BytesIO(data), filename="big.tar.gz")
        with pytest.raises(HTTPException) as exc_info:
            await _read_upload(file, max_bytes=2 * 1024 * 1024)
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_empty_upload_accepted(self):
        file = UploadFile(file=io.BytesIO(b""), filename="empty.tar.gz")
        result = await _read_upload(file)
        assert result == b""
