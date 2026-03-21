"""API key generation and hashing."""

from __future__ import annotations

import hashlib
import secrets
import re

_KEY_PATTERN = re.compile(r"^sk_sfs_[0-9a-f]{32}$")


def generate_api_key() -> str:
    """Generate a new API key in the format sk_sfs_{32_hex_chars}."""
    return f"sk_sfs_{secrets.token_hex(16)}"


def hash_api_key(raw_key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def validate_key_format(raw_key: str) -> bool:
    """Check if a key matches the expected format."""
    return bool(_KEY_PATTERN.match(raw_key))
