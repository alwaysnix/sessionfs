"""Unit tests for the sliding window rate limiter."""

from __future__ import annotations

import time
from unittest.mock import patch

from sessionfs.server.auth.rate_limit import SlidingWindowRateLimiter


def test_under_limit():
    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        assert limiter.is_allowed("key1") is True


def test_over_limit():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        limiter.is_allowed("key1")
    assert limiter.is_allowed("key1") is False


def test_window_expiry():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=1)
    limiter.is_allowed("key1")
    limiter.is_allowed("key1")
    assert limiter.is_allowed("key1") is False

    # Simulate time passing beyond window
    base_time = time.monotonic()
    with patch("sessionfs.server.auth.rate_limit.time") as mock_time:
        mock_time.monotonic.return_value = base_time + 2.0
        assert limiter.is_allowed("key1") is True


def test_remaining_count():
    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
    assert limiter.remaining("key1") == 5
    limiter.is_allowed("key1")
    limiter.is_allowed("key1")
    assert limiter.remaining("key1") == 3
