"""Unit tests for the sync client (mocked HTTP)."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile

import httpx
import pytest

from sessionfs.sync.client import (
    PullResult,
    RemoteListResult,
    RemoteSession,
    SyncAuthError,
    SyncClient,
    SyncConflictError,
    SyncError,
    SyncResult,
    _validate_url,
)


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


def test_validate_url_https_ok():
    _validate_url("https://api.sessionfs.dev")


def test_validate_url_localhost_http_ok():
    _validate_url("http://localhost:8000")
    _validate_url("http://127.0.0.1:8000")


def test_validate_url_rejects_remote_http():
    with pytest.raises(SyncError, match="HTTPS required"):
        _validate_url("http://api.sessionfs.dev")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tar_bytes() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b'{"sfs_version": "0.1.0"}'
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class MockTransport(httpx.AsyncBaseTransport):
    """Mock transport that returns canned responses."""

    def __init__(self, handler):
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Read the streaming body so request.content is available
        await request.aread()
        return self._handler(request)


# ---------------------------------------------------------------------------
# Push tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_new_session():
    """Push to new session → 201."""
    archive = _make_tar_bytes()
    etag = hashlib.sha256(archive).hexdigest()

    def handler(request: httpx.Request):
        assert "session.tar.gz" in request.content.decode("latin-1", errors="replace")
        body = {
            "session_id": "ses_abc123",
            "etag": etag,
            "blob_size_bytes": len(archive),
            "synced_at": "2024-01-01T00:00:00Z",
        }
        return httpx.Response(201, json=body)

    client = SyncClient("http://localhost:8000", "test-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    result = await client.push_session("ses_abc123", archive)
    assert result.session_id == "ses_abc123"
    assert result.etag == etag
    assert result.created is True
    await client.close()


@pytest.mark.asyncio
async def test_push_update_with_etag():
    """Push with If-Match → 200."""
    archive = _make_tar_bytes()
    new_etag = hashlib.sha256(archive).hexdigest()

    def handler(request: httpx.Request):
        assert request.headers.get("If-Match") == '"old_etag"'
        body = {
            "session_id": "ses_abc123",
            "etag": new_etag,
            "blob_size_bytes": len(archive),
            "synced_at": "2024-01-01T00:00:00Z",
        }
        return httpx.Response(200, json=body)

    client = SyncClient("http://localhost:8000", "test-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    result = await client.push_session("ses_abc123", archive, etag="old_etag")
    assert result.created is False
    await client.close()


@pytest.mark.asyncio
async def test_push_conflict_raises():
    """Push with wrong etag → SyncConflictError."""

    def handler(request: httpx.Request):
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "etag_mismatch",
                    "message": "ETag mismatch",
                    "details": {"current_etag": "remote_etag_abc"},
                }
            },
        )

    client = SyncClient("http://localhost:8000", "test-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    with pytest.raises(SyncConflictError) as exc_info:
        await client.push_session("ses_abc123", b"data", etag="wrong")
    assert exc_info.value.current_etag == "remote_etag_abc"
    await client.close()


@pytest.mark.asyncio
async def test_push_auth_error():
    """Push with bad auth → SyncAuthError."""

    def handler(request: httpx.Request):
        return httpx.Response(401, json={"detail": "Unauthorized"})

    client = SyncClient("http://localhost:8000", "bad-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    with pytest.raises(SyncAuthError):
        await client.push_session("ses_abc123", b"data")
    await client.close()


# ---------------------------------------------------------------------------
# Pull tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pull_session():
    """Pull a session → 200 with data."""
    archive = _make_tar_bytes()

    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            content=archive,
            headers={"ETag": '"abc123"', "Content-Type": "application/gzip"},
        )

    client = SyncClient("http://localhost:8000", "test-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    result = await client.pull_session("ses_abc123")
    assert result.data == archive
    assert result.etag == "abc123"
    assert result.not_modified is False
    await client.close()


@pytest.mark.asyncio
async def test_pull_not_modified():
    """Pull with matching etag → 304."""

    def handler(request: httpx.Request):
        assert request.headers.get("If-None-Match") == '"current_etag"'
        return httpx.Response(304)

    client = SyncClient("http://localhost:8000", "test-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    result = await client.pull_session("ses_abc123", etag="current_etag")
    assert result.not_modified is True
    assert result.data is None
    await client.close()


@pytest.mark.asyncio
async def test_pull_not_found():
    """Pull nonexistent session → SyncError."""

    def handler(request: httpx.Request):
        return httpx.Response(404, json={"detail": "Session not found"})

    client = SyncClient("http://localhost:8000", "test-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    with pytest.raises(SyncError, match="not found"):
        await client.pull_session("ses_nonexistent")
    await client.close()


# ---------------------------------------------------------------------------
# List tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_remote_sessions():
    """List sessions from server."""

    def handler(request: httpx.Request):
        assert "page" in str(request.url)
        return httpx.Response(
            200,
            json={
                "sessions": [
                    {
                        "id": "ses_001",
                        "title": "Test",
                        "source_tool": "claude-code",
                        "model_id": "opus-4",
                        "message_count": 10,
                        "etag": "abc",
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T01:00:00Z",
                        "blob_size_bytes": 1024,
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 50,
                "has_more": False,
            },
        )

    client = SyncClient("http://localhost:8000", "test-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    result = await client.list_remote_sessions()
    assert len(result.sessions) == 1
    assert result.sessions[0].id == "ses_001"
    assert result.total == 1
    assert result.has_more is False
    await client.close()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check():
    """Health check returns server status."""

    def handler(request: httpx.Request):
        return httpx.Response(200, json={"status": "healthy", "version": "0.1.0"})

    client = SyncClient("http://localhost:8000", "test-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    result = await client.health_check()
    assert result["status"] == "healthy"
    await client.close()


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_503():
    """Client retries on 503 then succeeds."""
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json={"status": "healthy"})

    client = SyncClient("http://localhost:8000", "test-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    result = await client.health_check()
    assert result["status"] == "healthy"
    assert call_count == 3
    await client.close()


@pytest.mark.asyncio
async def test_retry_exhausted():
    """Client raises after max retries."""

    def handler(request: httpx.Request):
        return httpx.Response(503, text="Service Unavailable")

    client = SyncClient("http://localhost:8000", "test-key")
    client._client = httpx.AsyncClient(transport=MockTransport(handler))

    with pytest.raises(SyncError, match="failed after"):
        await client.health_check()
    await client.close()
