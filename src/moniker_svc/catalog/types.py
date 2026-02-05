"""Catalog types - ownership, source bindings, and catalog nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    """Supported data source types."""
    SNOWFLAKE = "snowflake"
    ORACLE = "oracle"
    REST = "rest"
    STATIC = "static"
    EXCEL = "excel"
    BLOOMBERG = "bloomberg"
    REFINITIV = "refinitiv"
    OPENSEARCH = "opensearch"  # OpenSearch/Elasticsearch
    # Synthetic/computed sources
    COMPOSITE = "composite"  # Combines multiple sources
    DERIVED = "derived"      # Computed from other monikers


@dataclass(frozen=True, slots=True)
class Ownership:
    """
    Ownership for a catalog node with data governance roles.

    Supports both simplified ownership (accountable_owner, data_specialist, support_channel)
    and formal data governance roles (ADOP, ADS, ADAL).

    Each field inherits independently from ancestors if not set.
    """
    # Simplified ownership fields
    accountable_owner: str | None = None  # Executive accountable for the data
    data_specialist: str | None = None    # Technical SME / data expert
    support_channel: str | None = None    # Slack/Teams channel for help

    # Formal data governance roles (BCBS 239 / DAMA style)
    adop: str | None = None   # Accountable Data Owner/Principal - business executive with ultimate accountability
    ads: str | None = None    # Accountable Data Steward - day-to-day data quality and standards
    adal: str | None = None   # Accountable Data Access Lead - controls access and permissions

    def merge_with_parent(self, parent: Ownership) -> Ownership:
        """
        Merge this ownership with a parent, using parent values for any
        fields not set on this instance.
        """
        return Ownership(
            accountable_owner=self.accountable_owner or parent.accountable_owner,
            data_specialist=self.data_specialist or parent.data_specialist,
            support_channel=self.support_channel or parent.support_channel,
            adop=self.adop or parent.adop,
            ads=self.ads or parent.ads,
            adal=self.adal or parent.adal,
        )

    def is_complete(self) -> bool:
        """Check if all ownership fields are defined."""
        return all([
            self.accountable_owner,
            self.data_specialist,
            self.support_channel,
        ])

    def has_governance_roles(self) -> bool:
        """Check if any formal governance roles are defined."""
        return any([self.adop, self.ads, self.adal])

    def is_empty(self) -> bool:
        """Check if no ownership fields are defined."""
        return not any([
            self.accountable_owner,
            self.data_specialist,
            self.support_channel,
            self.adop,
            self.ads,
            self.adal,
        ])


@dataclass(frozen=True, slots=True)
class SourceBinding:
    """
    Binding to an actual data source.

    The config dictionary contains source-specific connection details.
    """
    source_type: SourceType
    config: dict[str, Any] = field(default_factory=dict)

    # Optional: restrict what operations are allowed
    # If None, all operations are allowed
    allowed_operations: frozenset[str] | None = None

    # Optional: schema definition for the data
    schema: dict[str, Any] | None = None

    # Is this source read-only?
    read_only: bool = True


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    """
    Access policy for controlling query patterns and preventing expensive operations.

    This is the guardrail layer that prevents users from accidentally running
    queries that would return billions of rows or overload data sources.
    """
    # Segments that MUST be specified (cannot be ALL)
    # e.g., ["portfolio"] means you must filter by portfolio
    required_segments: tuple[int, ...] = ()

    # Minimum number of segments that must NOT be ALL
    # e.g., min_filters=2 means at least 2 of the path segments must be specific values
    min_filters: int = 0

    # Patterns that are explicitly blocked (regex on full path)
    # e.g., ["ALL/ALL/ALL"] blocks the full wildcard query
    blocked_patterns: tuple[str, ...] = ()

    # Maximum estimated rows (warn if exceeded, block if way over)
    # This uses cardinality hints to estimate result size
    max_rows_warn: int | None = None      # Warn but allow
    max_rows_block: int | None = None     # Block entirely

    # Cardinality multipliers for each segment position when ALL is used
    # e.g., (1000, 50, 10000) means segment 0=ALL adds 1000x, segment 1=ALL adds 50x, etc.
    cardinality_multipliers: tuple[int, ...] = ()

    # Base row count for a fully-filtered query (single specific value per segment)
    base_row_count: int = 100

    # Require explicit confirmation for large queries
    require_confirmation_above: int | None = None

    # Custom error message when access is denied
    denial_message: str | None = None

    # Allowed roles/groups (if specified, only these can access)
    allowed_roles: tuple[str, ...] = ()

    # Time-based restrictions (e.g., only during business hours)
    allowed_hours: tuple[int, int] | None = None  # (start_hour, end_hour) in UTC

    def estimate_rows(self, segments: list[str]) -> int:
        """
        Estimate the number of rows that would be returned based on segment values.

        Args:
            segments: List of segment values from the moniker path

        Returns:
            Estimated row count
        """
        multiplier = 1
        for i, seg in enumerate(segments):
            if seg.upper() == "ALL":
                if i < len(self.cardinality_multipliers):
                    multiplier *= self.cardinality_multipliers[i]
                else:
                    multiplier *= 100  # Default multiplier for unknown segments

        return self.base_row_count * multiplier

    def validate(self, segments: list[str]) -> tuple[bool, str | None, int | None]:
        """
        Validate if a query pattern is allowed.

        Args:
            segments: List of segment values from the moniker path

        Returns:
            Tuple of (is_allowed, error_message, estimated_rows)
        """
        import re

        path = "/".join(segments)
        estimated_rows = self.estimate_rows(segments)

        # Check blocked patterns
        for pattern in self.blocked_patterns:
            if re.match(pattern, path, re.IGNORECASE):
                msg = self.denial_message or f"Query pattern '{path}' is blocked by access policy"
                return (False, msg, estimated_rows)

        # Check required segments
        for idx in self.required_segments:
            if idx < len(segments) and segments[idx].upper() == "ALL":
                segment_name = f"segment {idx}"
                msg = f"Access policy requires {segment_name} to be specified (cannot use ALL)"
                return (False, msg, estimated_rows)

        # Check minimum filters
        if self.min_filters > 0:
            non_all_count = sum(1 for s in segments if s.upper() != "ALL")
            if non_all_count < self.min_filters:
                msg = f"Access policy requires at least {self.min_filters} specific filters, but only {non_all_count} provided"
                return (False, msg, estimated_rows)

        # Check row limits
        if self.max_rows_block and estimated_rows > self.max_rows_block:
            msg = (
                f"Query would return ~{estimated_rows:,} rows, exceeding limit of {self.max_rows_block:,}. "
                f"Add more specific filters to reduce result size."
            )
            if self.denial_message:
                msg = self.denial_message
            return (False, msg, estimated_rows)

        # Warning for large queries (but allowed)
        warning = None
        if self.max_rows_warn and estimated_rows > self.max_rows_warn:
            warning = f"Large query: estimated {estimated_rows:,} rows"

        return (True, warning, estimated_rows)


@dataclass(slots=True)
class CatalogNode:
    """
    A node in the catalog hierarchy.

    Each node represents a data asset or category of assets.
    Nodes can have:
    - Ownership (inheritable triple)
    - Source binding (how to fetch data)
    - Data quality info
    - SLA info
    - Freshness info
    - Children (sub-paths)
    - Metadata
    """
    path: str  # Full path string (e.g., "market-data/prices/equity")
    display_name: str = ""
    description: str = ""

    # Domain mapping (for top-level nodes - maps to domain registry)
    domain: str | None = None

    # Ownership (inherits from ancestors if not set)
    ownership: Ownership = field(default_factory=Ownership)

    # Source binding (only leaf nodes typically have this)
    source_binding: SourceBinding | None = None

    # Data governance
    data_quality: DataQuality | None = None
    sla: SLA | None = None
    freshness: Freshness | None = None

    # Machine-readable schema for AI agent discoverability
    data_schema: DataSchema | None = None

    # Access policy for query guardrails
    access_policy: AccessPolicy | None = None

    # Documentation links (Confluence, runbooks, etc.)
    documentation: Documentation | None = None

    # Data classification (for governance)
    classification: str = "internal"

    # Arbitrary tags for searchability
    tags: frozenset[str] = field(default_factory=frozenset)

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Is this a leaf node (actual data) or category (contains children)?
    is_leaf: bool = False

    def __post_init__(self):
        if not self.display_name:
            # Default display name from last path segment
            segments = self.path.split("/")
            self.display_name = segments[-1] if segments else ""


@dataclass(frozen=True, slots=True)
class ResolvedOwnership:
    """
    Ownership resolved through the hierarchy, with provenance.

    Shows the effective ownership and where each field came from.
    """
    # Simplified ownership with provenance
    accountable_owner: str | None = None
    accountable_owner_source: str | None = None  # Path where this was defined

    data_specialist: str | None = None
    data_specialist_source: str | None = None

    support_channel: str | None = None
    support_channel_source: str | None = None

    # Formal governance roles with provenance
    adop: str | None = None
    adop_source: str | None = None

    ads: str | None = None
    ads_source: str | None = None

    adal: str | None = None
    adal_source: str | None = None

    @property
    def ownership(self) -> Ownership:
        """Get as simple Ownership (without provenance)."""
        return Ownership(
            accountable_owner=self.accountable_owner,
            data_specialist=self.data_specialist,
            support_channel=self.support_channel,
            adop=self.adop,
            ads=self.ads,
            adal=self.adal,
        )

    @property
    def governance_roles(self) -> dict[str, dict[str, str | None]]:
        """Get governance roles with their provenance as a dictionary."""
        return {
            "adop": {"value": self.adop, "defined_at": self.adop_source},
            "ads": {"value": self.ads, "defined_at": self.ads_source},
            "adal": {"value": self.adal, "defined_at": self.adal_source},
        }


@dataclass(frozen=True, slots=True)
class DataQuality:
    """Data quality information for a catalog node."""
    # DQ owner/steward responsible for data quality
    dq_owner: str | None = None

    # Quality score (0-100) if measured
    quality_score: float | None = None

    # Validation rules applied
    validation_rules: tuple[str, ...] = ()

    # Known issues or caveats
    known_issues: tuple[str, ...] = ()

    # Last DQ check timestamp (ISO format)
    last_validated: str | None = None


@dataclass(frozen=True, slots=True)
class SLA:
    """Service level agreement for a data source."""
    # Expected freshness (e.g., "T+1", "15min", "real-time")
    freshness: str | None = None

    # Availability target (e.g., "99.9%")
    availability: str | None = None

    # Support hours (e.g., "24/7", "business hours ET")
    support_hours: str | None = None

    # Escalation contact for SLA breaches
    escalation_contact: str | None = None


@dataclass(frozen=True, slots=True)
class Freshness:
    """Data freshness information."""
    # When the data was last loaded/refreshed (ISO format)
    last_loaded: str | None = None

    # Scheduled refresh time (e.g., "06:00 ET daily")
    refresh_schedule: str | None = None

    # Source system the data comes from
    source_system: str | None = None

    # Upstream dependencies
    upstream_dependencies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    """Schema definition for a single column - AI-readable metadata."""
    name: str
    data_type: str  # e.g., "string", "float", "date", "integer", "boolean"
    description: str = ""  # Natural language description
    semantic_type: str | None = None  # e.g., "identifier", "measure", "dimension", "timestamp"
    example: str | None = None  # Example value
    nullable: bool = True
    primary_key: bool = False
    foreign_key: str | None = None  # Reference to another moniker path


@dataclass(frozen=True, slots=True)
class DataSchema:
    """
    Schema metadata for a data source - designed for AI agent discoverability.

    This provides machine-readable information about the data structure,
    semantics, and relationships that AI agents can use for:
    - Understanding what data is available
    - Generating appropriate queries
    - Validating data transformations
    - Discovering related datasets
    """
    # Column definitions
    columns: tuple[ColumnSchema, ...] = ()

    # Natural language description of the dataset
    description: str = ""

    # Semantic tags for discoverability (e.g., "risk", "timeseries", "financial")
    semantic_tags: tuple[str, ...] = ()

    # Primary key column(s)
    primary_key: tuple[str, ...] = ()

    # Common access patterns / use cases
    use_cases: tuple[str, ...] = ()

    # Example queries or monikers
    examples: tuple[str, ...] = ()

    # Related monikers (for join/enrichment)
    related_monikers: tuple[str, ...] = ()

    # Granularity (e.g., "daily", "per-security", "per-portfolio")
    granularity: str | None = None

    # Expected row count range (for AI to understand scale)
    typical_row_count: str | None = None  # e.g., "1K-10K", "1M-10M"

    # Update frequency description
    update_frequency: str | None = None  # e.g., "daily", "real-time", "monthly"


@dataclass(frozen=True, slots=True)
class Documentation:
    """
    Documentation links for a data source - enables discoverability via metadata reflection.

    Links to Confluence glossary pages, runbooks, onboarding guides, and other
    documentation that helps users understand and work with the data.
    """
    # Confluence glossary page for this data domain
    glossary_url: str | None = None

    # Operational runbook for troubleshooting and on-call
    runbook_url: str | None = None

    # Onboarding guide for new users
    onboarding_url: str | None = None

    # Data dictionary / schema documentation
    data_dictionary_url: str | None = None

    # API documentation (if applicable)
    api_docs_url: str | None = None

    # Architecture / design documentation
    architecture_url: str | None = None

    # Change log / release notes
    changelog_url: str | None = None

    # Contact page or escalation guide
    contact_url: str | None = None

    # Additional documentation links (name -> url)
    additional_links: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        result = {}
        if self.glossary_url:
            result["glossary"] = self.glossary_url
        if self.runbook_url:
            result["runbook"] = self.runbook_url
        if self.onboarding_url:
            result["onboarding"] = self.onboarding_url
        if self.data_dictionary_url:
            result["data_dictionary"] = self.data_dictionary_url
        if self.api_docs_url:
            result["api_docs"] = self.api_docs_url
        if self.architecture_url:
            result["architecture"] = self.architecture_url
        if self.changelog_url:
            result["changelog"] = self.changelog_url
        if self.contact_url:
            result["contact"] = self.contact_url
        if self.additional_links:
            result["additional"] = {name: url for name, url in self.additional_links}
        return result

    def is_empty(self) -> bool:
        """Check if no documentation links are defined."""
        return not any([
            self.glossary_url,
            self.runbook_url,
            self.onboarding_url,
            self.data_dictionary_url,
            self.api_docs_url,
            self.architecture_url,
            self.changelog_url,
            self.contact_url,
            self.additional_links,
        ])
