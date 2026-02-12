"""Circuit breaker for tracking source health and preventing cascade failures."""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation - requests flow through
    OPEN = "open"           # Failures exceeded threshold - requests blocked
    HALF_OPEN = "half_open" # Testing if source recovered - limited requests


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open for a source."""
    def __init__(self, source_key: str, retry_after_seconds: float):
        super().__init__(f"Circuit breaker open for {source_key}")
        self.source_key = source_key
        self.retry_after_seconds = retry_after_seconds


@dataclass
class _CircuitState:
    """State tracking for a single source."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    opened_at: float = 0.0


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    enabled: bool = True
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 3          # Successes in half-open to close
    timeout_seconds: float = 30.0       # How long to stay open before half-open
    half_open_max_requests: int = 3     # Max concurrent requests in half-open


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for source health tracking.

    Tracks success/failure of source connections and prevents cascade
    failures by temporarily blocking requests to unhealthy sources.
    """
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

    _circuits: dict[str, _CircuitState] = field(default_factory=dict, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def check(self, source_key: str) -> None:
        """
        Check if requests to a source are allowed.

        Args:
            source_key: Unique identifier for the source (e.g., "snowflake:prod")

        Raises:
            CircuitBreakerOpen: If the circuit is open for this source
        """
        if not self.config.enabled:
            return

        with self._lock:
            circuit = self._circuits.get(source_key)
            if circuit is None:
                return  # No circuit = never failed = allow

            if circuit.state == CircuitState.CLOSED:
                return  # Allow

            if circuit.state == CircuitState.OPEN:
                # Check if timeout has elapsed
                elapsed = time.monotonic() - circuit.opened_at
                if elapsed >= self.config.timeout_seconds:
                    # Transition to half-open
                    circuit.state = CircuitState.HALF_OPEN
                    circuit.success_count = 0
                    return  # Allow (testing)
                else:
                    retry_after = self.config.timeout_seconds - elapsed
                    raise CircuitBreakerOpen(source_key, retry_after)

            if circuit.state == CircuitState.HALF_OPEN:
                return  # Allow limited requests for testing

    def record_success(self, source_key: str) -> None:
        """Record a successful request to a source."""
        if not self.config.enabled:
            return

        with self._lock:
            circuit = self._circuits.get(source_key)
            if circuit is None:
                return

            circuit.last_success_time = time.monotonic()

            if circuit.state == CircuitState.HALF_OPEN:
                circuit.success_count += 1
                if circuit.success_count >= self.config.success_threshold:
                    # Source recovered - close circuit
                    circuit.state = CircuitState.CLOSED
                    circuit.failure_count = 0

    def record_failure(self, source_key: str) -> None:
        """Record a failed request to a source."""
        if not self.config.enabled:
            return

        now = time.monotonic()

        with self._lock:
            circuit = self._circuits.get(source_key)
            if circuit is None:
                circuit = _CircuitState()
                self._circuits[source_key] = circuit

            circuit.failure_count += 1
            circuit.last_failure_time = now

            if circuit.state == CircuitState.HALF_OPEN:
                # Failed during testing - reopen
                circuit.state = CircuitState.OPEN
                circuit.opened_at = now
            elif circuit.state == CircuitState.CLOSED:
                if circuit.failure_count >= self.config.failure_threshold:
                    circuit.state = CircuitState.OPEN
                    circuit.opened_at = now

    def get_source_health(self) -> dict[str, dict]:
        """Get health status of all tracked sources."""
        with self._lock:
            result = {}
            for key, circuit in self._circuits.items():
                result[key] = {
                    "state": circuit.state.value,
                    "failure_count": circuit.failure_count,
                    "success_count": circuit.success_count,
                    "last_failure": circuit.last_failure_time,
                    "last_success": circuit.last_success_time,
                }
            return result

    @property
    def stats(self) -> dict:
        """Circuit breaker statistics."""
        with self._lock:
            states = {"closed": 0, "open": 0, "half_open": 0}
            for circuit in self._circuits.values():
                states[circuit.state.value] += 1
            return {
                "enabled": self.config.enabled,
                "tracked_sources": len(self._circuits),
                "states": states,
            }
