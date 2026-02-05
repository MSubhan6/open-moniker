"""Core moniker types."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VersionType(Enum):
    """Semantic type of a version specifier.

    Examples:
        @20260101 -> DATE
        @latest -> LATEST
        @3M, @12Y, @1W -> TENOR
        @all -> ALL
        @anything_else -> CUSTOM
    """
    DATE = "date"       # @20260101 (YYYYMMDD format)
    LATEST = "latest"   # @latest
    TENOR = "tenor"     # @3M, @12Y, @1W, @5D (duration)
    ALL = "all"         # @all (full time series)
    CUSTOM = "custom"   # Source-specific version identifier


@dataclass(frozen=True, slots=True)
class MonikerPath:
    """
    A hierarchical path to a data asset.

    Supports dots within segments for sub-categorization:
        indices.sovereign/developed/EU.GovBondIndex
        commodities.derivatives/energy/crude

    Examples:
        indices.sovereign/developed/EUR/ALL
        reference.security/ISIN/US0378331005
        holdings/20260115/fund_alpha
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
        """First segment - the data domain (e.g., indices.sovereign, reference)."""
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


@dataclass(frozen=True, slots=True)
class Moniker:
    """
    A complete moniker reference with optional namespace, version, and revision.

    Format: [namespace@]path/segments[@version][/sub.resource][/vN][?query=params]

    Components:
        namespace: Access scope (e.g., "official", "user", "trading-desk")
        path: Hierarchical path with dot-notation support
        version: Point-in-time reference (date, "latest", tenor like "3M", or "all")
        version_type: Semantic type of version (DATE, LATEST, TENOR, ALL, CUSTOM)
        sub_resource: Path after @version (e.g., "details" or "details.corporate.actions")
        revision: Schema/format revision (integer, e.g., 2 for /v2)
        params: Additional query parameters

    Examples:
        indices.sovereign/developed/EUR/ALL
        commodities.derivatives/crypto/ETH@20260115/v2
        verified@reference.security/ISIN/US0378331005@latest
        user@analytics.risk/views/my-watchlist@20260115/v3
        securities/012345678@20260101/details
        securities/012345678@20260101/details.corporate.actions
        prices.equity/AAPL@3M (3-month lookback)
        risk.cvar/portfolio-123@all (full time series)
        holdings/20260115/fund_alpha?format=json
    """
    path: MonikerPath
    namespace: str | None = None
    version: str | None = None  # @latest, @20260115, @3M, @all, etc.
    version_type: VersionType | None = None  # Semantic type of version
    sub_resource: str | None = None  # Path after @version (e.g., "details.corporate.actions")
    revision: int | None = None  # /v2 -> 2
    params: QueryParams = field(default_factory=lambda: QueryParams({}))

    def __str__(self) -> str:
        parts = []

        # Namespace prefix
        if self.namespace:
            parts.append(f"{self.namespace}@")

        # Path
        parts.append(str(self.path))

        # Version suffix
        if self.version:
            parts.append(f"@{self.version}")

        # Sub-resource (after version, before revision)
        if self.sub_resource:
            parts.append(f"/{self.sub_resource}")

        # Revision suffix
        if self.revision is not None:
            parts.append(f"/v{self.revision}")

        base = "".join(parts)

        # Query params
        if self.params:
            param_str = "&".join(f"{k}={v}" for k, v in self.params.params.items())
            return f"moniker://{base}?{param_str}"

        return f"moniker://{base}"

    @property
    def domain(self) -> str | None:
        """The data domain (first path segment)."""
        return self.path.domain

    @property
    def canonical_path(self) -> str:
        """The path as a string (without namespace, version, or params)."""
        return str(self.path)

    @property
    def full_path(self) -> str:
        """Path including version, sub-resource, and revision but not namespace."""
        parts = [str(self.path)]
        if self.version:
            parts.append(f"@{self.version}")
        if self.sub_resource:
            parts.append(f"/{self.sub_resource}")
        if self.revision is not None:
            parts.append(f"/v{self.revision}")
        return "".join(parts)

    @property
    def is_versioned(self) -> bool:
        """Whether this moniker has a version specifier."""
        return self.version is not None

    @property
    def is_latest(self) -> bool:
        """Whether this moniker explicitly requests latest version."""
        return self.version == "latest"

    @property
    def version_date(self) -> str | None:
        """Extract date from version if it's a date format (YYYYMMDD)."""
        if self.version_type == VersionType.DATE:
            return self.version
        # Fallback for backwards compatibility
        if self.version and self.version.isdigit() and len(self.version) == 8:
            return self.version
        return None

    @property
    def version_tenor(self) -> tuple[int, str] | None:
        """Extract tenor components if version is a tenor (e.g., 3M -> (3, 'M')).

        Returns:
            Tuple of (value, unit) where unit is Y/M/W/D, or None if not a tenor.
        """
        if self.version_type == VersionType.TENOR and self.version:
            match = re.match(r"^(\d+)([YMWD])$", self.version, re.IGNORECASE)
            if match:
                return (int(match.group(1)), match.group(2).upper())
        return None

    @property
    def is_all(self) -> bool:
        """Whether this moniker requests the full time series."""
        return self.version_type == VersionType.ALL

    def with_version(self, version: str, version_type: VersionType | None = None) -> Moniker:
        """Create a copy with a different version."""
        return Moniker(
            path=self.path,
            namespace=self.namespace,
            version=version,
            version_type=version_type,
            sub_resource=self.sub_resource,
            revision=self.revision,
            params=self.params,
        )

    def with_namespace(self, namespace: str | None) -> Moniker:
        """Create a copy with a different namespace."""
        return Moniker(
            path=self.path,
            namespace=namespace,
            version=self.version,
            version_type=self.version_type,
            sub_resource=self.sub_resource,
            revision=self.revision,
            params=self.params,
        )

    def with_sub_resource(self, sub_resource: str | None) -> Moniker:
        """Create a copy with a different sub-resource."""
        return Moniker(
            path=self.path,
            namespace=self.namespace,
            version=self.version,
            version_type=self.version_type,
            sub_resource=sub_resource,
            revision=self.revision,
            params=self.params,
        )
