"""Unit tests for API key generation, hashing, and auth dependency."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock

from sessionfs.server.auth.keys import generate_api_key, hash_api_key, validate_key_format
from sessionfs.server.auth.rate_limit import SlidingWindowRateLimiter


def test_generate_key_format():
    key = generate_api_key()
    assert key.startswith("sk_sfs_")
    assert len(key) == 7 + 32  # prefix + 32 hex chars


def test_generate_key_unique():
    keys = {generate_api_key() for _ in range(100)}
    assert len(keys) == 100


def test_hash_deterministic():
    key = "sk_sfs_abcdef1234567890abcdef1234567890"
    assert hash_api_key(key) == hash_api_key(key)


def test_hash_different_keys():
    k1 = generate_api_key()
    k2 = generate_api_key()
    assert hash_api_key(k1) != hash_api_key(k2)


def test_validate_key_format_valid():
    key = generate_api_key()
    assert validate_key_format(key) is True


def test_validate_key_format_invalid():
    assert validate_key_format("bad_key") is False
    assert validate_key_format("sk_sfs_tooshort") is False
    assert validate_key_format("") is False
    assert validate_key_format("sk_sfs_ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ") is False  # uppercase
