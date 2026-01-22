"""ZeroMQ sink for telemetry streaming."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ..events import UsageEvent
from .base import TelemetrySink


logger = logging.getLogger(__name__)


@dataclass
class ZmqSink(TelemetrySink):
    """
    Sink that publishes events to ZeroMQ.

    ZeroMQ is a lightweight, high-performance messaging library.
    This sink uses PUB/SUB pattern for fan-out to multiple consumers.

    Config:
        endpoint: ZMQ endpoint (e.g., "tcp://*:5555")
        topic: Topic prefix for messages (default: "telemetry")
        socket_type: push | pub (default: pub)
        high_water_mark: Max queued messages before dropping
    """
    endpoint: str = "tcp://*:5555"
    topic: str = "telemetry"
    socket_type: str = "pub"  # pub | push
    high_water_mark: int = 10000

    # Internal state
    _context: Any = field(default=None, init=False)
    _socket: Any = field(default=None, init=False)

    async def start(self) -> None:
        try:
            import zmq
            import zmq.asyncio
        except ImportError:
            raise RuntimeError("pyzmq required: pip install pyzmq")

        self._context = zmq.asyncio.Context()

        if self.socket_type == "pub":
            self._socket = self._context.socket(zmq.PUB)
        else:
            self._socket = self._context.socket(zmq.PUSH)

        self._socket.set_hwm(self.high_water_mark)
        self._socket.bind(self.endpoint)

        logger.info(f"ZMQ sink started on {self.endpoint} ({self.socket_type})")

    async def stop(self) -> None:
        if self._socket:
            self._socket.close()
            self._socket = None
        if self._context:
            self._context.term()
            self._context = None

        logger.info("ZMQ sink stopped")

    async def send(self, events: list[UsageEvent]) -> None:
        if not self._socket:
            logger.warning("ZMQ sink not started")
            return

        for event in events:
            # Format: topic + space + json
            message = f"{self.topic} {json.dumps(event.to_dict(), default=str)}"
            try:
                await self._socket.send_string(message)
            except Exception as e:
                logger.error(f"ZMQ send error: {e}")

    async def health_check(self) -> bool:
        return self._socket is not None


@dataclass
class ZmqPullReceiver:
    """
    Helper class for receiving events from ZMQ (for testing/downstream).

    Usage:
        receiver = ZmqPullReceiver(endpoint="tcp://localhost:5555")
        await receiver.start()
        async for event_dict in receiver.receive():
            print(event_dict)
    """
    endpoint: str
    topic: str = "telemetry"

    _context: Any = field(default=None, init=False)
    _socket: Any = field(default=None, init=False)

    async def start(self) -> None:
        try:
            import zmq
            import zmq.asyncio
        except ImportError:
            raise RuntimeError("pyzmq required: pip install pyzmq")

        self._context = zmq.asyncio.Context()
        self._socket = self._context.socket(zmq.SUB)
        self._socket.connect(self.endpoint)
        self._socket.subscribe(self.topic)

        logger.info(f"ZMQ receiver connected to {self.endpoint}")

    async def stop(self) -> None:
        if self._socket:
            self._socket.close()
        if self._context:
            self._context.term()

    async def receive(self):
        """Async generator that yields event dictionaries."""
        while True:
            try:
                message = await self._socket.recv_string()
                # Parse: topic + space + json
                _, json_str = message.split(" ", 1)
                yield json.loads(json_str)
            except Exception as e:
                logger.error(f"ZMQ receive error: {e}")
                break
