"""M9: Audit logging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sessionfs.audit import AuditLogger, EVENT_TYPES


class TestAuditLogging:

    @pytest.fixture
    def audit_log(self, tmp_path: Path) -> tuple[AuditLogger, Path]:
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path)
        return logger, log_path

    def test_log_creates_file(self, audit_log):
        logger, log_path = audit_log
        logger.log("session_captured", session_id="ses_abc123def456ab")
        assert log_path.exists()

    def test_log_json_lines_format(self, audit_log):
        logger, log_path = audit_log
        logger.log(
            "session_captured",
            user_id="user-1",
            session_id="ses_abc123def456ab",
            details={"source_tool": "claude-code"},
        )
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event_type"] == "session_captured"
        assert entry["user_id"] == "user-1"
        assert entry["session_id"] == "ses_abc123def456ab"
        assert "timestamp" in entry
        assert entry["details"]["source_tool"] == "claude-code"

    def test_multiple_events_appended(self, audit_log):
        logger, log_path = audit_log
        logger.log("session_captured", session_id="ses_abc123def456ab")
        logger.log("session_resumed", session_id="ses_abc123def456ab")
        logger.log("session_exported", session_id="ses_abc123def456ab")
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 3
        types = [json.loads(l)["event_type"] for l in lines]
        assert types == ["session_captured", "session_resumed", "session_exported"]

    def test_source_ip_logged_for_server(self, audit_log):
        logger, log_path = audit_log
        logger.log(
            "auth_success",
            user_id="user-1",
            source_ip="192.168.1.1",
        )
        entry = json.loads(log_path.read_text().strip())
        assert entry["source_ip"] == "192.168.1.1"

    def test_read_events_with_filter(self, audit_log):
        logger, _ = audit_log
        logger.log("session_captured", session_id="ses_abc123def456ab")
        logger.log("auth_success", user_id="user-1")
        logger.log("session_captured", session_id="ses_xyz789012345ab")

        events = logger.read_events(event_type="session_captured")
        assert len(events) == 2
        assert all(e["event_type"] == "session_captured" for e in events)

    def test_read_events_by_session(self, audit_log):
        logger, _ = audit_log
        logger.log("session_captured", session_id="ses_abc123def456ab")
        logger.log("session_captured", session_id="ses_xyz789012345ab")

        events = logger.read_events(session_id="ses_abc123def456ab")
        assert len(events) == 1

    def test_all_event_types_defined(self):
        """All 15 required event types should be defined."""
        required = {
            "session_captured", "session_synced", "session_pulled",
            "session_resumed", "session_exported", "session_handoff",
            "session_deleted", "session_forked", "session_checkpoint_created",
            "api_key_created", "api_key_revoked", "auth_failed",
            "auth_success", "sync_conflict", "sync_error",
        }
        assert required.issubset(EVENT_TYPES)
        assert len(EVENT_TYPES) >= 15

    def test_audit_file_permissions(self, audit_log):
        """Audit log should be created with 0600 permissions."""
        import os
        logger, log_path = audit_log
        logger.log("auth_success")
        mode = os.stat(log_path).st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_capture_resume_flow(self, audit_log):
        """Simulate a capture + resume flow and verify audit trail."""
        logger, _ = audit_log

        logger.log("session_captured", session_id="ses_abc123def456ab",
                    details={"source_tool": "claude-code", "message_count": 42})
        logger.log("session_resumed", session_id="ses_abc123def456ab",
                    details={"target_project": "/Users/test/project"})

        events = logger.read_events(session_id="ses_abc123def456ab")
        assert len(events) == 2
        types = [e["event_type"] for e in events]
        assert "session_captured" in types
        assert "session_resumed" in types
