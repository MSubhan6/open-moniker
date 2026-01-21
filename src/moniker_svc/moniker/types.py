"""Core moniker types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MonikerPath:
    """
    A hierarchical path to a data asset.

    Examples:
        market-data/prices/equity/AAPL
        static-data/instruments/equity
        reference/calendars/trading/NYSE
    """
    segments: tuple[str, ...]

    def __str__(self) -> str:
        return "/".join(self.segments)

    def __len__(self) -> int:
        return len(self.segments)

    def __bool__(self) -> bool:
        return len(self.segments) > 0

    @property
    def domain(self) -> str | None:
        """First segment - the data domain (e.g., market-data, static-data)."""
        return self.segments[0] if self.segments else None

    @property
    def parent(self) -> MonikerPath | None:
        """Parent path, or None if at root."""
        if len(self.segments) <= 1:
            return None
        return MonikerPath(self.segments[:-1])

    @property
    def leaf(self) -> str | None:
        """Final segment of the path."""
        return self.segments[-1] if self.segments else None

    def ancestors(self) -> list[MonikerPath]:
        """All ancestor paths from root to parent (not including self)."""
        result = []
        for i in range(1, len(self.segments)):
            result.append(MonikerPath(self.segments[:i]))
        return result

    def child(self, segment: str) -> MonikerPath:
        """Create a child path."""
        return MonikerPath(self.segments + (segment,))

    def is_ancestor_of(self, other: MonikerPath) -> bool:
        """Check if this path is an ancestor of another."""
        if len(self.segments) >= len(other.segments):
            return False
        return other.segments[:len(self.segments)] == self.segments

    def is_descendant_of(self, other: MonikerPath) -> bool:
        """Check if this path is a descendant of another."""
        return other.is_ancestor_of(self)

    @classmethod
    def root(cls) -> MonikerPath:
        """The root path (empty)."""
        return cls(())

    @classmethod
    def from_string(cls, path_str: str) -> MonikerPath:
        """Parse a path string."""
        if not path_str or path_str == "/":
            return cls.root()
        # Strip leading/trailing slashes and split
        segments = tuple(s for s in path_str.strip("/").split("/") if s)
        return cls(segments)


@dataclass(frozen=True, slots=True)
class QueryParams:
    """Query parameters on a moniker."""
    params: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.params.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.params

    def __bool__(self) -> bool:
        return bool(self.params)

    @property
    def version(self) -> str | None:
        """Shortcut for version parameter."""
        return self.params.get("version")

    @property
    def as_of(self) -> str | None:
        """Shortcut for as_of (point-in-time) parameter."""
        return self.params.get("as_of")


@dataclass(frozen=True, slots=True)
class Moniker:
    """
    A complete moniker reference.

    Format: moniker://{path}[?{params}]

    Examples:
        moniker://market-data/prices/equity/AAPL
        moniker://market-data/prices/equity/AAPL?version=latest
        moniker://reference/calendars/trading/NYSE?as_of=2024-01-15
    """
    path: MonikerPath
    params: QueryParams = field(default_factory=lambda: QueryParams({}))

    def __str__(self) -> str:
        base = f"moniker://{self.path}"
        if self.params:
            param_str = "&".join(f"{k}={v}" for k, v in self.params.params.items())
            return f"{base}?{param_str}"
        return base

    @property
    def domain(self) -> str | None:
        """The data domain."""
        return self.path.domain

    @property
    def canonical_path(self) -> str:
        """The path as a string (without scheme or params)."""
        return str(self.path)
