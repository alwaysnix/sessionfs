"""Unit tests for Pydantic schemas."""

from __future__ import annotations

from datetime import datetime, timezone

from sessionfs.server.schemas.auth import CreateApiKeyRequest, CreateApiKeyResponse, ApiKeySummary
from sessionfs.server.schemas.errors import ErrorResponse, ErrorDetail
from sessionfs.server.schemas.sessions import (
    SessionSummary,
    SessionListResponse,
    SessionMetadataUpdate,
)


def test_error_response_serialization():
    err = ErrorResponse(error=ErrorDetail(code="404", message="Not found"))
    data = err.model_dump()
    assert data["error"]["code"] == "404"
    assert data["error"]["message"] == "Not found"
    assert data["error"]["details"] == {}


def test_session_summary_defaults():
    now = datetime.now(timezone.utc)
    s = SessionSummary(
        id="ses_123",
        source_tool="claude-code",
        etag="abc123",
        created_at=now,
        updated_at=now,
    )
    assert s.tags == []
    assert s.message_count == 0
    assert s.title is None


def test_session_metadata_update_partial():
    update = SessionMetadataUpdate(title="New Title")
    assert update.title == "New Title"
    assert update.tags is None

    update2 = SessionMetadataUpdate(tags=["a", "b"])
    assert update2.title is None
    assert update2.tags == ["a", "b"]


def test_create_api_key_response():
    now = datetime.now(timezone.utc)
    resp = CreateApiKeyResponse(
        key_id="uuid-1",
        raw_key="sk_sfs_abc123",
        name="my-key",
        created_at=now,
    )
    data = resp.model_dump()
    assert data["raw_key"] == "sk_sfs_abc123"
    assert data["name"] == "my-key"
