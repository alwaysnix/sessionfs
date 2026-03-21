"""M9: Audit logging module.

Provides structured audit logging to both local file (~/.sessionfs/audit.log)
and the server audit_events table. All significant events are logged in JSON
lines format.

IMPORTANT: Never log session content, blob data, or API key values.
Log metadata only.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("sessionfs.audit")

# Event types that can be logged
EVENT_TYPES = frozenset({
    "session_captured",
    "session_synced",
    "session_pulled",
    "session_resumed",
    "session_exported",
    "session_handoff",
    "session_deleted",
    "session_forked",
    "session_checkpoint_created",
    "api_key_created",
    "api_key_revoked",
    "auth_failed",
    "auth_success",
    "sync_conflict",
    "sync_error",
})


class AuditLogger:
    """Writes audit events to a JSON lines file."""

    def __init__(self, audit_log_path: Path | None = None) -> None:
        if audit_log_path is None:
            audit_log_path = Path.home() / ".sessionfs" / "audit.log"
        self._path = audit_log_path

    def _ensure_file(self) -> None:
        """Ensure the audit log file exists with correct permissions."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    def log(
        self,
        event_type: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        details: dict[str, Any] | None = None,
        source_ip: str | None = None,
    ) -> None:
        """Write an audit event to the log file.

        Args:
            event_type: One of the EVENT_TYPES constants.
            user_id: User who performed the action (None for daemon events).
            session_id: Session involved (if applicable).
            details: Additional context (never include secret values).
            source_ip: Client IP (server-side events only).
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
        }
        if user_id is not None:
            entry["user_id"] = user_id
        if session_id is not None:
            entry["session_id"] = session_id
        if details:
            entry["details"] = details
        if source_ip:
            entry["source_ip"] = source_ip

        try:
            self._ensure_file()
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")
        except OSError as e:
            logger.error("Failed to write audit log: %s", e)

    def read_events(
        self,
        event_type: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read audit events from the log file with optional filters."""
        if not self._path.exists():
            return []

        events: list[dict[str, Any]] = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event_type and event.get("event_type") != event_type:
                    continue
                if session_id and event.get("session_id") != session_id:
                    continue
                events.append(event)

        # Return most recent first, limited
        return events[-limit:][::-1]


# Module-level default instance
_default_logger: AuditLogger | None = None


def get_audit_logger(audit_log_path: Path | None = None) -> AuditLogger:
    """Get or create the default AuditLogger instance."""
    global _default_logger
    if _default_logger is None or audit_log_path is not None:
        _default_logger = AuditLogger(audit_log_path)
    return _default_logger


def audit_event(
    event_type: str,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    details: dict[str, Any] | None = None,
    source_ip: str | None = None,
) -> None:
    """Convenience function to log an audit event using the default logger."""
    get_audit_logger().log(
        event_type,
        user_id=user_id,
        session_id=session_id,
        details=details,
        source_ip=source_ip,
    )
