"""M2: Session ID validation."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="Server tests require: pip install -e '.[dev]'")

from fastapi import HTTPException

from sessionfs.server.routes.sessions import _validate_session_id


class TestSessionIdValidation:

    def test_valid_session_id(self):
        assert _validate_session_id("ses_abc123def456ab") == "ses_abc123def456ab"

    def test_valid_session_id_20_chars(self):
        assert _validate_session_id("ses_12345678901234567890") == "ses_12345678901234567890"

    def test_valid_session_id_12_chars(self):
        assert _validate_session_id("ses_abcdef123456") == "ses_abcdef123456"

    def test_missing_prefix(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_id("abc123def456ab")
        assert exc_info.value.status_code == 400

    def test_path_traversal(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_id("../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_sql_injection(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_id("ses_'; DROP TABLE sessions;--")
        assert exc_info.value.status_code == 400

    def test_empty_string(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_id("")
        assert exc_info.value.status_code == 400

    def test_too_short(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_id("ses_abc")
        assert exc_info.value.status_code == 400

    def test_too_long(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_id("ses_" + "a" * 30)
        assert exc_info.value.status_code == 400

    def test_null_bytes(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_id("ses_abc\x00def456ab")
        assert exc_info.value.status_code == 400

    def test_slash_in_id(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_id("ses_abc/def456ab")
        assert exc_info.value.status_code == 400

    def test_special_chars(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_id("ses_abc!@#$%^&*()")
        assert exc_info.value.status_code == 400
