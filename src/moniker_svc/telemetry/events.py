"""Telemetry event types."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventOutcome(str, Enum):
    """Outcome of a moniker access."""
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ERROR = "error"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"


class Operation(str, Enum):
    """Type of operation performed."""
    READ = "read"
    LIST = "list"
    DESCRIBE = "describe"
    LINEAGE = "lineage"
    REQUEST_SUBMIT = "request_submit"
    REQUEST_APPROVE = "request_approve"
    REQUEST_REJECT = "request_reject"
    REQUEST_COMMENT = "request_comment"


@dataclass(frozen=True, slots=True)
class CallerIdentity:
    """
    Identity of the caller making the request.

    At minimum, one of these should be present.
    """
    # Service identity (from mTLS or service account)
    service_id: str | None = None

    # User identity (from OAuth/JWT)
    user_id: str | None = None

    # Application/client identifier
    app_id: str | None = None

    # Team/department (for chargeback)
    team: str | None = None

    # Additional claims from auth token
    claims: dict[str, Any] = field(default_factory=dict)

    @property
    def principal(self) -> str:
        """Primary identifier for this caller."""
        return self.service_id or self.user_id or self.app_id or "anonymous"

    def __str__(self) -> str:
        return self.principal


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """
    A single usage event for telemetry.

    Captures everything needed for:
    - Data lineage ("what data was accessed")
    - Governance ("who accessed what")
    - Chargeback ("which team/app used how much")
    - Debugging ("what went wrong")
    """
    # Request identification
    request_id: str

    # Timing
    timestamp: datetime

    # Who
    caller: CallerIdentity

    # What
    moniker: str  # Full moniker string
    moniker_domain: str | None  # Domain segment
    moniker_path: str  # Path without params
    operation: Operation

    # Outcome
    outcome: EventOutcome
    error_message: str | None = None

    # Performance
    latency_ms: float = 0.0

    # Resolution details
    resolved_source_type: str | None = None
    resolved_source_path: str | None = None

    # Ownership at access time (for audit)
    owner_at_access: str | None = None

    # Row/record count if applicable
    result_count: int | None = None

    # Was this served from cache?
    cached: bool = False

    # Additional context
    metadata: dict[str, Any] = field(default_factory=dict)

    # Deprecation telemetry
    deprecated: bool = False
    successor: str | None = None
    redirected_from: str | None = None

    @classmethod
    def create(
        cls,
        moniker: str,
        moniker_path: str,
        operation: Operation,
        caller: CallerIdentity,
        outcome: EventOutcome,
        latency_ms: float = 0.0,
        **kwargs,
    ) -> UsageEvent:
        """Factory method with sensible defaults."""
        # Extract domain from path
        domain = moniker_path.split("/")[0] if "/" in moniker_path else moniker_path

        return cls(
            request_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            caller=caller,
            moniker=moniker,
            moniker_domain=domain,
            moniker_path=moniker_path,
            operation=operation,
            outcome=outcome,
            latency_ms=latency_ms,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "caller": {
                "principal": self.caller.principal,
                "service_id": self.caller.service_id,
                "user_id": self.caller.user_id,
                "app_id": self.caller.app_id,
                "team": self.caller.team,
            },
            "moniker": self.moniker,
            "moniker_domain": self.moniker_domain,
            "moniker_path": self.moniker_path,
            "operation": self.operation.value,
            "outcome": self.outcome.value,
            "error_message": self.error_message,
            "latency_ms": self.latency_ms,
            "resolved_source_type": self.resolved_source_type,
            "resolved_source_path": self.resolved_source_path,
            "owner_at_access": self.owner_at_access,
            "result_count": self.result_count,
            "cached": self.cached,
            "metadata": self.metadata,
            "deprecated": self.deprecated,
            "successor": self.successor,
            "redirected_from": self.redirected_from,
        }
