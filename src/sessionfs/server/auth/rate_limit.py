"""In-memory sliding window rate limiter."""

from __future__ import annotations

import time


class SlidingWindowRateLimiter:
    """Simple per-key sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    def _prune(self, key: str) -> None:
        cutoff = time.monotonic() - self.window_seconds
        if key in self._requests:
            self._requests[key] = [t for t in self._requests[key] if t > cutoff]
            if not self._requests[key]:
                del self._requests[key]

    def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed and record it if so."""
        self._prune(key)
        timestamps = self._requests.get(key, [])
        if len(timestamps) >= self.max_requests:
            return False
        self._requests.setdefault(key, []).append(time.monotonic())
        return True

    def remaining(self, key: str) -> int:
        """Return how many requests remain in the current window."""
        self._prune(key)
        used = len(self._requests.get(key, []))
        return max(0, self.max_requests - used)
