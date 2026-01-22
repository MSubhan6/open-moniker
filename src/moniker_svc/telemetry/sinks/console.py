"""Console sink for development/debugging."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from ..events import UsageEvent
from .base import TelemetrySink


@dataclass
class ConsoleSink(TelemetrySink):
    """
    Sink that writes events to console (stdout/stderr).

    Useful for development and debugging.
    """
    # Output destination
    stream: str = "stdout"  # stdout | stderr

    # Output format
    format: str = "json"  # json | compact | pretty

    # Prefix for each line
    prefix: str = "[TELEMETRY] "

    async def send(self, events: list[UsageEvent]) -> None:
        out = sys.stdout if self.stream == "stdout" else sys.stderr

        for event in events:
            line = self._format_event(event)
            print(f"{self.prefix}{line}", file=out)

    def _format_event(self, event: UsageEvent) -> str:
        if self.format == "json":
            return json.dumps(event.to_dict(), default=str)
        elif self.format == "compact":
            return (
                f"{event.timestamp.isoformat()} "
                f"{event.caller.principal} "
                f"{event.operation.value} "
                f"{event.moniker_path} "
                f"{event.outcome.value} "
                f"{event.latency_ms:.1f}ms"
            )
        else:  # pretty
            return json.dumps(event.to_dict(), indent=2, default=str)
