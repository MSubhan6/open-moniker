"""File-based sinks for telemetry."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..events import UsageEvent
from .base import TelemetrySink


@dataclass
class FileSink(TelemetrySink):
    """
    Sink that writes events to a file (JSONL format).

    Each event is written as a single JSON line for easy parsing.
    """
    path: str
    encoding: str = "utf-8"

    # Internal state
    _file: object = field(default=None, init=False)

    async def start(self) -> None:
        # Ensure directory exists
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a", encoding=self.encoding)

    async def stop(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    async def send(self, events: list[UsageEvent]) -> None:
        if not self._file:
            await self.start()

        for event in events:
            line = json.dumps(event.to_dict(), default=str)
            self._file.write(line + "\n")

        self._file.flush()


@dataclass
class RotatingFileSink(TelemetrySink):
    """
    Sink that writes events to rotating files.

    Creates new files based on time interval or size.
    Pattern can include strftime codes for time-based rotation.
    """
    # Path pattern (can include strftime codes like %Y%m%d)
    path_pattern: str = "telemetry-%Y%m%d-%H.jsonl"

    # Base directory
    directory: str = "./telemetry"

    # Max file size in bytes (0 = no size limit)
    max_bytes: int = 100 * 1024 * 1024  # 100MB

    # Encoding
    encoding: str = "utf-8"

    # Internal state
    _current_path: str = field(default="", init=False)
    _current_file: object = field(default=None, init=False)
    _current_size: int = field(default=0, init=False)

    async def start(self) -> None:
        Path(self.directory).mkdir(parents=True, exist_ok=True)

    async def stop(self) -> None:
        if self._current_file:
            self._current_file.close()
            self._current_file = None

    async def send(self, events: list[UsageEvent]) -> None:
        # Determine current file path
        now = datetime.now()
        expected_path = os.path.join(
            self.directory,
            now.strftime(self.path_pattern)
        )

        # Check if we need to rotate
        if expected_path != self._current_path or self._needs_size_rotation():
            await self._rotate(expected_path)

        # Write events
        for event in events:
            line = json.dumps(event.to_dict(), default=str) + "\n"
            line_bytes = line.encode(self.encoding)
            self._current_file.write(line_bytes.decode(self.encoding))
            self._current_size += len(line_bytes)

        self._current_file.flush()

    def _needs_size_rotation(self) -> bool:
        if self.max_bytes == 0:
            return False
        return self._current_size >= self.max_bytes

    async def _rotate(self, new_path: str) -> None:
        if self._current_file:
            self._current_file.close()

        # If size-based rotation, add suffix
        if new_path == self._current_path and self._needs_size_rotation():
            base, ext = os.path.splitext(new_path)
            suffix = 1
            while os.path.exists(f"{base}.{suffix}{ext}"):
                suffix += 1
            new_path = f"{base}.{suffix}{ext}"

        self._current_path = new_path
        self._current_file = open(new_path, "a", encoding=self.encoding)
        self._current_size = os.path.getsize(new_path) if os.path.exists(new_path) else 0
