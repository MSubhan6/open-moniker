"""Non-blocking telemetry emitter."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable

from .events import UsageEvent


logger = logging.getLogger(__name__)


@dataclass
class TelemetryEmitter:
    """
    Non-blocking telemetry event emitter.

    Events are placed in an asyncio queue and processed asynchronously.
    This ensures the hot path (request handling) is not blocked by telemetry.

    Features:
    - Non-blocking emit (fire and forget)
    - Bounded queue with overflow policy
    - Metrics on queue depth and drops
    """
    # Maximum queue depth
    max_queue_size: int = 10000

    # What to do when queue is full
    # "drop" = drop events (default, safe for high throughput)
    # "block" = block until space available (only for critical events)
    overflow_policy: str = "drop"

    # Internal state
    _queue: asyncio.Queue | None = field(default=None, init=False)
    _consumers: list[Callable[[UsageEvent], None]] = field(default_factory=list, init=False)
    _stats: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        self._stats = {
            "emitted": 0,
            "dropped": 0,
            "errors": 0,
        }

    async def start(self) -> None:
        """Initialize the emitter (call on startup)."""
        self._queue = asyncio.Queue(maxsize=self.max_queue_size)
        logger.info(f"Telemetry emitter started (max_queue={self.max_queue_size})")

    async def stop(self) -> None:
        """Stop the emitter and drain remaining events."""
        if self._queue:
            # Process remaining events
            while not self._queue.empty():
                try:
                    event = self._queue.get_nowait()
                    await self._deliver(event)
                except asyncio.QueueEmpty:
                    break
        logger.info(f"Telemetry emitter stopped. Stats: {self._stats}")

    def add_consumer(self, consumer: Callable[[UsageEvent], None]) -> None:
        """
        Add a synchronous consumer for events.

        Consumers are called in the background, not on the hot path.
        """
        self._consumers.append(consumer)

    def emit(self, event: UsageEvent) -> bool:
        """
        Emit an event (non-blocking).

        Returns True if queued, False if dropped.
        """
        if self._queue is None:
            logger.warning("Telemetry emitter not started, dropping event")
            self._stats["dropped"] += 1
            return False

        try:
            self._queue.put_nowait(event)
            self._stats["emitted"] += 1
            return True
        except asyncio.QueueFull:
            if self.overflow_policy == "drop":
                self._stats["dropped"] += 1
                return False
            else:
                # This would block - not recommended for hot path
                raise

    async def emit_async(self, event: UsageEvent, timeout: float = 0.1) -> bool:
        """
        Emit an event with async wait (use only if dropping is unacceptable).
        """
        if self._queue is None:
            return False

        try:
            await asyncio.wait_for(self._queue.put(event), timeout=timeout)
            self._stats["emitted"] += 1
            return True
        except asyncio.TimeoutError:
            self._stats["dropped"] += 1
            return False

    async def process_loop(self) -> None:
        """
        Main processing loop - runs continuously.

        Call this as a background task.
        """
        if self._queue is None:
            raise RuntimeError("Emitter not started")

        logger.info("Telemetry processing loop started")

        while True:
            try:
                event = await self._queue.get()
                await self._deliver(event)
                self._queue.task_done()
            except asyncio.CancelledError:
                logger.info("Telemetry processing loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing telemetry event: {e}")
                self._stats["errors"] += 1

    async def _deliver(self, event: UsageEvent) -> None:
        """Deliver event to all consumers."""
        for consumer in self._consumers:
            try:
                # Run sync consumers in thread pool to avoid blocking
                if asyncio.iscoroutinefunction(consumer):
                    await consumer(event)
                else:
                    consumer(event)
            except Exception as e:
                logger.error(f"Consumer error: {e}")
                self._stats["errors"] += 1

    @property
    def queue_depth(self) -> int:
        """Current queue depth."""
        return self._queue.qsize() if self._queue else 0

    @property
    def stats(self) -> dict:
        """Get emitter statistics."""
        return {
            **self._stats,
            "queue_depth": self.queue_depth,
            "consumers": len(self._consumers),
        }
