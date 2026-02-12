"""Token bucket rate limiter for protecting the resolution service."""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field


class RateLimitExceeded(Exception):
    """Raised when a caller exceeds their rate limit."""
    def __init__(self, message: str, retry_after_seconds: float = 1.0):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass
class _TokenBucket:
    """Token bucket for a single caller."""
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume tokens. Returns True if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def retry_after(self) -> float:
        """Seconds until a token will be available."""
        if self.tokens >= 1.0:
            return 0.0
        needed = 1.0 - self.tokens
        return needed / self.refill_rate


@dataclass
class RateLimiterConfig:
    """Rate limiter configuration."""
    enabled: bool = True
    # Default limits per caller
    requests_per_second: float = 50.0
    burst_capacity: float = 200.0
    # Global limits (across all callers)
    global_requests_per_second: float = 500.0
    global_burst_capacity: float = 2000.0
    # Cleanup interval for idle callers
    idle_timeout_seconds: float = 300.0


@dataclass
class RateLimiter:
    """
    Token-bucket rate limiter with per-caller and global limits.

    Thread-safe. Designed for enterprise use with thousands of callers.
    """
    config: RateLimiterConfig = field(default_factory=RateLimiterConfig)

    _buckets: dict[str, _TokenBucket] = field(default_factory=dict, init=False)
    _global_bucket: _TokenBucket = field(init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _last_cleanup: float = field(default_factory=time.monotonic, init=False)

    # Stats
    _total_requests: int = field(default=0, init=False)
    _total_limited: int = field(default=0, init=False)

    def __post_init__(self):
        self._global_bucket = _TokenBucket(
            capacity=self.config.global_burst_capacity,
            refill_rate=self.config.global_requests_per_second,
            tokens=self.config.global_burst_capacity,
        )

    def check(self, caller_id: str) -> None:
        """
        Check rate limit for a caller. Raises RateLimitExceeded if over limit.

        Args:
            caller_id: Unique identifier for the caller (app_id, IP, etc.)
        """
        if not self.config.enabled:
            return

        with self._lock:
            self._total_requests += 1

            # Check global limit first
            if not self._global_bucket.consume():
                self._total_limited += 1
                raise RateLimitExceeded(
                    f"Global rate limit exceeded ({self.config.global_requests_per_second} req/s)",
                    retry_after_seconds=self._global_bucket.retry_after,
                )

            # Get or create per-caller bucket
            bucket = self._buckets.get(caller_id)
            if bucket is None:
                bucket = _TokenBucket(
                    capacity=self.config.burst_capacity,
                    refill_rate=self.config.requests_per_second,
                    tokens=self.config.burst_capacity,
                )
                self._buckets[caller_id] = bucket

            if not bucket.consume():
                self._total_limited += 1
                raise RateLimitExceeded(
                    f"Rate limit exceeded for {caller_id} ({self.config.requests_per_second} req/s)",
                    retry_after_seconds=bucket.retry_after,
                )

            # Periodic cleanup
            self._maybe_cleanup()

    def _maybe_cleanup(self) -> None:
        """Remove idle caller buckets (caller holds lock)."""
        now = time.monotonic()
        if now - self._last_cleanup < 60.0:  # Cleanup at most every 60s
            return

        self._last_cleanup = now
        cutoff = now - self.config.idle_timeout_seconds
        stale = [k for k, v in self._buckets.items() if v.last_refill < cutoff]
        for k in stale:
            del self._buckets[k]

    @property
    def stats(self) -> dict:
        """Rate limiter statistics."""
        with self._lock:
            return {
                "enabled": self.config.enabled,
                "active_callers": len(self._buckets),
                "total_requests": self._total_requests,
                "total_limited": self._total_limited,
                "limit_rate_percent": round(
                    self._total_limited / max(self._total_requests, 1) * 100, 2
                ),
            }
