"""Tests for telemetry system."""

import asyncio
import pytest

from moniker_svc.telemetry.events import UsageEvent, CallerIdentity, EventOutcome, Operation
from moniker_svc.telemetry.emitter import TelemetryEmitter
from moniker_svc.telemetry.batcher import TelemetryBatcher


@pytest.fixture
def caller():
    return CallerIdentity(
        service_id="test-service",
        user_id="test-user",
        team="test-team",
    )


class TestUsageEvent:
    def test_create(self, caller):
        event = UsageEvent.create(
            moniker="moniker://market-data/prices",
            moniker_path="market-data/prices",
            operation=Operation.READ,
            caller=caller,
            outcome=EventOutcome.SUCCESS,
            latency_ms=42.5,
        )

        assert event.moniker == "moniker://market-data/prices"
        assert event.operation == Operation.READ
        assert event.outcome == EventOutcome.SUCCESS
        assert event.latency_ms == 42.5
        assert event.request_id is not None
        assert event.timestamp is not None

    def test_to_dict(self, caller):
        event = UsageEvent.create(
            moniker="moniker://test",
            moniker_path="test",
            operation=Operation.READ,
            caller=caller,
            outcome=EventOutcome.SUCCESS,
        )

        d = event.to_dict()
        assert d["moniker"] == "moniker://test"
        assert d["operation"] == "read"
        assert d["outcome"] == "success"
        assert d["caller"]["principal"] == "test-service"


class TestCallerIdentity:
    def test_principal_service(self):
        caller = CallerIdentity(service_id="my-service")
        assert caller.principal == "my-service"

    def test_principal_user(self):
        caller = CallerIdentity(user_id="user@firm.com")
        assert caller.principal == "user@firm.com"

    def test_principal_precedence(self):
        # service_id takes precedence
        caller = CallerIdentity(
            service_id="service",
            user_id="user",
            app_id="app",
        )
        assert caller.principal == "service"

    def test_principal_anonymous(self):
        caller = CallerIdentity()
        assert caller.principal == "anonymous"


class TestTelemetryEmitter:
    @pytest.mark.asyncio
    async def test_emit(self, caller):
        emitter = TelemetryEmitter()
        await emitter.start()

        received = []
        emitter.add_consumer(lambda e: received.append(e))

        event = UsageEvent.create(
            moniker="test",
            moniker_path="test",
            operation=Operation.READ,
            caller=caller,
            outcome=EventOutcome.SUCCESS,
        )

        assert emitter.emit(event)
        assert emitter.stats["emitted"] == 1

        await emitter.stop()

    @pytest.mark.asyncio
    async def test_queue_overflow(self, caller):
        emitter = TelemetryEmitter(max_queue_size=2)
        await emitter.start()

        # Don't add consumer - events will queue up

        event = UsageEvent.create(
            moniker="test",
            moniker_path="test",
            operation=Operation.READ,
            caller=caller,
            outcome=EventOutcome.SUCCESS,
        )

        # Fill queue
        assert emitter.emit(event)
        assert emitter.emit(event)

        # This should be dropped
        assert not emitter.emit(event)
        assert emitter.stats["dropped"] == 1

        await emitter.stop()


class TestTelemetryBatcher:
    @pytest.mark.asyncio
    async def test_batch_on_size(self, caller):
        batches = []

        async def sink(events):
            batches.append(events)

        batcher = TelemetryBatcher(batch_size=3, sink=sink)

        event = UsageEvent.create(
            moniker="test",
            moniker_path="test",
            operation=Operation.READ,
            caller=caller,
            outcome=EventOutcome.SUCCESS,
        )

        # Add 3 events - should trigger flush
        await batcher.add(event)
        await batcher.add(event)
        await batcher.add(event)

        assert len(batches) == 1
        assert len(batches[0]) == 3

    @pytest.mark.asyncio
    async def test_flush(self, caller):
        batches = []

        async def sink(events):
            batches.append(events)

        batcher = TelemetryBatcher(batch_size=100, sink=sink)

        event = UsageEvent.create(
            moniker="test",
            moniker_path="test",
            operation=Operation.READ,
            caller=caller,
            outcome=EventOutcome.SUCCESS,
        )

        await batcher.add(event)
        assert len(batches) == 0  # Not flushed yet

        await batcher.flush()
        assert len(batches) == 1
        assert len(batches[0]) == 1
