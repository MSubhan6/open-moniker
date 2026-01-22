"""Batching telemetry worker for efficient downstream delivery."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from .events import UsageEvent


logger = logging.getLogger(__name__)


@dataclass
class TelemetryBatcher:
    """
    Batches telemetry events for efficient delivery to sinks.

    Instead of sending events one-by-one, collects events and flushes
    either when batch is full or timeout expires.

    This is critical for high-throughput scenarios:
    - Reduces network overhead
    - Allows efficient bulk inserts
    - Smooths out traffic spikes
    """
    # Batch configuration
    batch_size: int = 1000
    flush_interval_seconds: float = 1.0

    # Sink function: receives list of events
    sink: Callable[[list[UsageEvent]], Awaitable[None]] | None = None

    # Internal state
    _buffer: list[UsageEvent] = field(default_factory=list, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _last_flush: float = field(default_factory=time.time, init=False)
    _stats: dict = field(default_factory=dict, init=False)
    _running: bool = field(default=False, init=False)

    def __post_init__(self):
        self._stats = {
            "batches_sent": 0,
            "events_sent": 0,
            "flush_errors": 0,
        }

    async def add(self, event: UsageEvent) -> None:
        """Add an event to the batch."""
        async with self._lock:
            self._buffer.append(event)

            # Flush if batch is full
            if len(self._buffer) >= self.batch_size:
                await self._flush_unsafe()

    async def flush(self) -> None:
        """Force flush the current batch."""
        async with self._lock:
            await self._flush_unsafe()

    async def _flush_unsafe(self) -> None:
        """Flush without lock (caller must hold lock)."""
        if not self._buffer:
            return

        if self.sink is None:
            logger.warning("No sink configured, discarding batch")
            self._buffer.clear()
            return

        batch = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = time.time()

        try:
            await self.sink(batch)
            self._stats["batches_sent"] += 1
            self._stats["events_sent"] += len(batch)
        except Exception as e:
            logger.error(f"Failed to flush telemetry batch: {e}")
            self._stats["flush_errors"] += 1
            # Put events back for retry? Or drop?
            # For high-throughput, usually drop is safer
            # Could make this configurable

    async def timer_loop(self) -> None:
        """
        Background loop that flushes on interval.

        Ensures events don't sit in buffer too long during low traffic.
        """
        self._running = True
        logger.info(f"Telemetry batcher timer started (interval={self.flush_interval_seconds}s)")

        while self._running:
            try:
                await asyncio.sleep(self.flush_interval_seconds)

                async with self._lock:
                    elapsed = time.time() - self._last_flush
                    if self._buffer and elapsed >= self.flush_interval_seconds:
                        await self._flush_unsafe()

            except asyncio.CancelledError:
                logger.info("Telemetry batcher timer cancelled")
                break
            except Exception as e:
                logger.error(f"Batcher timer error: {e}")

        # Final flush on shutdown
        await self.flush()

    async def stop(self) -> None:
        """Stop the batcher and flush remaining events."""
        self._running = False
        await self.flush()
        logger.info(f"Telemetry batcher stopped. Stats: {self._stats}")

    @property
    def buffer_size(self) -> int:
        """Current buffer size."""
        return len(self._buffer)

    @property
    def stats(self) -> dict:
        """Get batcher statistics."""
        return {
            **self._stats,
            "buffer_size": self.buffer_size,
            "seconds_since_flush": time.time() - self._last_flush,
        }


def create_batched_consumer(batcher: TelemetryBatcher) -> Callable[[UsageEvent], None]:
    """
    Create a consumer function that feeds into a batcher.

    Usage:
        batcher = TelemetryBatcher(sink=my_sink)
        emitter.add_consumer(create_batched_consumer(batcher))
    """
    def consumer(event: UsageEvent) -> None:
        # Schedule the add as a task (non-blocking)
        asyncio.create_task(batcher.add(event))

    return consumer
