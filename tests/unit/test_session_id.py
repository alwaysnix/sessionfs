"""Tests for session ID generation and validation."""

from __future__ import annotations

from sessionfs.session_id import (
    generate_session_id,
    session_id_from_native,
    validate_session_id,
)


def test_generate_session_id_format():
    sid = generate_session_id()
    assert sid.startswith("ses_")
    assert len(sid) == 20  # ses_ + 16 hex chars
    assert validate_session_id(sid)


def test_generate_session_id_unique():
    ids = {generate_session_id() for _ in range(100)}
    assert len(ids) == 100


def test_session_id_from_native_uuid():
    native = "d20e3dbc-8f4e-4a3b-b2c1-1234567890ab"
    sid = session_id_from_native(native)
    assert sid == "ses_d20e3dbc8f4e4a3b"
    assert validate_session_id(sid)


def test_session_id_from_native_deterministic():
    native = "abc12345-6789-0def-1234-567890abcdef"
    assert session_id_from_native(native) == session_id_from_native(native)


def test_session_id_from_native_no_dashes():
    native = "abcdef1234567890"
    sid = session_id_from_native(native)
    assert sid == "ses_abcdef1234567890"
    assert validate_session_id(sid)


def test_validate_session_id_valid():
    assert validate_session_id("ses_abc123def456gh") is True
    assert validate_session_id("ses_abcdefghijkl") is True  # 12 chars
    assert validate_session_id("ses_abcdefghijklmnopqrst") is True  # 20 chars


def test_validate_session_id_invalid():
    assert validate_session_id("d20e3dbc-8f4e-4a3b") is False  # raw UUID
    assert validate_session_id("abc") is False
    assert validate_session_id("") is False
    assert validate_session_id("ses_") is False  # too short after prefix
    assert validate_session_id("ses_ab") is False  # less than 12
