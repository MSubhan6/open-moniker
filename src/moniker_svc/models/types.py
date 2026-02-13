"""
Business Model data types.

A Model represents a business measure or field (e.g., DV01, Duration, Alpha)
that can appear across multiple monikers. This creates a three-layer architecture:

    Model (business concept)  →  Moniker (data path)  →  Binding (data source)
           ↓                           ↓                        ↓
       "What it means"         "Where it lives"         "How to get it"
"""

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelOwnership:
    """Ownership and governance info for a business model."""

    methodology_owner: str | None = None   # Owns calculation methodology
    business_steward: str | None = None    # Business representative
    support_channel: str | None = None     # Where to get help

    def is_empty(self) -> bool:
        """Check if all ownership fields are empty."""
        return not any([
            self.methodology_owner,
            self.business_steward,
            self.support_channel,
        ])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "methodology_owner": self.methodology_owner,
            "business_steward": self.business_steward,
            "support_channel": self.support_channel,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelOwnership":
        """Create from dictionary."""
        if not data:
            return cls()
        return cls(
            methodology_owner=data.get("methodology_owner"),
            business_steward=data.get("business_steward"),
            support_channel=data.get("support_channel"),
        )


@dataclass(frozen=True, slots=True)
class MonikerLink:
    """Defines where a model appears in the moniker catalog."""

    moniker_pattern: str              # e.g., "risk.cvar/**/DV01" - glob pattern
    column_name: str | None = None    # Column name if different from model name
    notes: str | None = None          # Context about this appearance

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result: dict[str, Any] = {"moniker_pattern": self.moniker_pattern}
        if self.column_name:
            result["column_name"] = self.column_name
        if self.notes:
            result["notes"] = self.notes
        return result

    @classmethod
    def from_dict(cls, data: dict | str) -> "MonikerLink":
        """Create from dictionary or string."""
        if isinstance(data, str):
            return cls(moniker_pattern=data)
        return cls(
            moniker_pattern=data.get("moniker_pattern", ""),
            column_name=data.get("column_name"),
            notes=data.get("notes"),
        )


@dataclass(frozen=True, slots=True)
class Model:
    """
    A business model representing a measure, metric, or field.

    Models have their own hierarchical structure (like domains/catalog) and
    explicitly link to monikers where they appear.
    """

    # Path in the model hierarchy, e.g., "risk.analytics/dv01"
    path: str

    # Display metadata
    display_name: str = ""
    description: str = ""

    # Business metadata
    formula: str | None = None        # Mathematical formula
    unit: str | None = None           # "USD", "bps", "years"
    data_type: str = "float"          # Expected data type

    # Governance (no inheritance - each model defines its own)
    ownership: ModelOwnership = field(default_factory=ModelOwnership)
    documentation_url: str | None = None
    methodology_url: str | None = None

    # Moniker relationships (explicit only, no auto-discovery)
    appears_in: tuple[MonikerLink, ...] = ()

    # Semantic tags for categorization
    semantic_tags: tuple[str, ...] = ()

    # Generic tags
    tags: frozenset[str] = field(default_factory=frozenset)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result: dict[str, Any] = {
            "path": self.path,
        }

        if self.display_name:
            result["display_name"] = self.display_name
        if self.description:
            result["description"] = self.description
        if self.formula:
            result["formula"] = self.formula
        if self.unit:
            result["unit"] = self.unit
        if self.data_type != "float":
            result["data_type"] = self.data_type

        if not self.ownership.is_empty():
            result["ownership"] = self.ownership.to_dict()

        if self.documentation_url:
            result["documentation_url"] = self.documentation_url
        if self.methodology_url:
            result["methodology_url"] = self.methodology_url

        if self.appears_in:
            result["appears_in"] = [link.to_dict() for link in self.appears_in]

        if self.semantic_tags:
            result["semantic_tags"] = list(self.semantic_tags)

        if self.tags:
            result["tags"] = sorted(self.tags)

        return result

    @classmethod
    def from_dict(cls, path: str, data: dict) -> "Model":
        """
        Create a Model from a dictionary.

        Args:
            path: The model path (YAML key)
            data: Dictionary of model attributes

        Returns:
            Model instance
        """
        # Parse ownership
        ownership_data = data.get("ownership", {})
        ownership = ModelOwnership.from_dict(ownership_data)

        # Parse appears_in links
        appears_in_data = data.get("appears_in", [])
        appears_in = tuple(MonikerLink.from_dict(link) for link in appears_in_data)

        # Parse semantic tags
        semantic_tags_data = data.get("semantic_tags", [])
        semantic_tags = tuple(semantic_tags_data) if semantic_tags_data else ()

        # Parse generic tags
        tags_data = data.get("tags", [])
        tags = frozenset(tags_data) if tags_data else frozenset()

        return cls(
            path=path,
            display_name=data.get("display_name") or "",
            description=data.get("description") or "",
            formula=data.get("formula"),
            unit=data.get("unit"),
            data_type=data.get("data_type", "float"),
            ownership=ownership,
            documentation_url=data.get("documentation_url"),
            methodology_url=data.get("methodology_url"),
            appears_in=appears_in,
            semantic_tags=semantic_tags,
            tags=tags,
        )

    @property
    def name(self) -> str:
        """Get the model name (last segment of path)."""
        return self.path.rsplit("/", 1)[-1] if "/" in self.path else self.path

    @property
    def parent_path(self) -> str | None:
        """Get the parent path, or None if this is a root model."""
        if "/" not in self.path:
            return None
        return self.path.rsplit("/", 1)[0]

    def is_container(self) -> bool:
        """Check if this is a container node (no appears_in links)."""
        return len(self.appears_in) == 0
