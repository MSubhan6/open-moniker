"""Base sink interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..events import UsageEvent


class TelemetrySink(ABC):
    """
    Abstract base class for telemetry sinks.

    Sinks receive batches of events and deliver them to a destination
    (file, message queue, database, etc.).
    """

    @abstractmethod
    async def send(self, events: list[UsageEvent]) -> None:
        """
        Send a batch of events to the sink.

        Should be idempotent if possible (for retry scenarios).
        """
        ...

    async def start(self) -> None:
        """Initialize the sink (called on startup)."""
        pass

    async def stop(self) -> None:
        """Clean up the sink (called on shutdown)."""
        pass

    async def health_check(self) -> bool:
        """Check if the sink is healthy."""
        return True
