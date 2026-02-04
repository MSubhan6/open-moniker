"""
Domain data model.

A Domain represents a top-level organizational unit in the moniker catalog,
providing governance metadata and ownership information.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass(frozen=True)
class Domain:
    """
    A domain is a top-level organizational unit for data governance.

    Domains map to the first segment of moniker paths (e.g., "indices", "commodities").
    They carry governance metadata including ownership, confidentiality, and contact info.
    """

    # Required: domain identifier (matches first segment of moniker paths)
    name: str

    # Display and identification
    display_name: str = ""      # Human-readable name, e.g., "Market Indices"
    short_code: str = ""        # Short code, e.g., "IDX", "CMD", "REF"
    color: str = "#6B7280"      # Hex color for UI display (default: gray)

    # Ownership and governance
    owner: str = ""             # Executive/business owner
    tech_custodian: str = ""    # Technical custodian (team/individual)
    business_steward: str = ""  # Business data steward

    # Classification
    data_category: str = ""     # e.g., "Market Data", "Reference Data"
    confidentiality: str = "internal"  # internal, confidential, strictly_confidential, public
    pii: bool = False           # Contains personally identifiable information?

    # Contact and documentation
    help_channel: str = ""      # Teams/Slack channel for support
    wiki_link: str = ""         # Link to documentation (Confluence, wiki, etc.)
    notes: str = ""             # Free-text notes

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "Domain":
        """
        Create a Domain from a dictionary.

        Args:
            name: The domain identifier
            data: Dictionary of domain attributes

        Returns:
            Domain instance
        """
        return cls(
            name=name,
            display_name=data.get("display_name", ""),
            short_code=data.get("short_code", ""),
            color=data.get("color", "#6B7280"),
            owner=data.get("owner", ""),
            tech_custodian=data.get("tech_custodian", ""),
            business_steward=data.get("business_steward", ""),
            data_category=data.get("data_category", ""),
            confidentiality=data.get("confidentiality", "internal"),
            pii=data.get("pii", False),
            help_channel=data.get("help_channel", ""),
            wiki_link=data.get("wiki_link", ""),
            notes=data.get("notes", ""),
        )


# Valid confidentiality levels
CONFIDENTIALITY_LEVELS = ["public", "internal", "confidential", "strictly_confidential"]
