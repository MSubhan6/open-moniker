"""
Domain configuration loaders.

Load domains from YAML or CSV files.
"""

import csv
from pathlib import Path
from typing import List, Optional, Set

import yaml

from .types import Domain
from .registry import DomainRegistry


def load_domains_from_yaml(
    file_path: str | Path,
    registry: Optional[DomainRegistry] = None
) -> List[Domain]:
    """
    Load domains from a YAML file.

    Expected format:
        indices:
          display_name: Market Indices
          short_code: IDX
          color: "#4A90D9"
          owner: indices-team@firm.com
          ...

    Args:
        file_path: Path to the YAML file
        registry: Optional registry to populate

    Returns:
        List of loaded domains
    """
    path = Path(file_path)
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    domains = []
    for name, config in data.items():
        if isinstance(config, dict):
            domain = Domain.from_dict(name, config)
            domains.append(domain)
            if registry is not None:
                registry.register_or_update(domain)

    return domains


def load_domains_from_csv(
    file_path: str | Path,
    registry: Optional[DomainRegistry] = None
) -> List[Domain]:
    """
    Load domains from a CSV file.

    Expected columns: name, id, display_name, short_code, category, color, owner,
    tech_custodian, business_steward, confidentiality,
    pii, help_channel, wiki_link, notes

    Args:
        file_path: Path to the CSV file
        registry: Optional registry to populate

    Returns:
        List of loaded domains
    """
    path = Path(file_path)
    if not path.exists():
        return []

    domains = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                continue

            # Convert id to int if present
            id_val = row.get("id", "").strip()
            id_int = int(id_val) if id_val else None

            # Convert pii to boolean
            pii_value = row.get("pii", "").lower()
            pii = pii_value in ("true", "yes", "1")

            domain = Domain(
                name=name,
                id=id_int,
                display_name=row.get("display_name", ""),
                short_code=row.get("short_code", ""),
                category=row.get("category", ""),
                color=row.get("color", "#6B7280"),
                owner=row.get("owner", ""),
                tech_custodian=row.get("tech_custodian", ""),
                business_steward=row.get("business_steward", ""),
                confidentiality=row.get("confidentiality", "internal"),
                pii=pii,
                help_channel=row.get("help_channel", ""),
                wiki_link=row.get("wiki_link", ""),
                notes=row.get("notes", ""),
            )
            domains.append(domain)
            if registry is not None:
                registry.register_or_update(domain)

    return domains


def discover_domains_from_catalog(
    catalog_registry,
    domain_registry: DomainRegistry,
    existing_names: Optional[Set[str]] = None
) -> List[Domain]:
    """
    Auto-discover domains from the moniker catalog's top-level paths.

    Creates placeholder domains for any top-level paths that don't
    already have a domain configuration.

    Args:
        catalog_registry: The moniker catalog registry
        domain_registry: The domain registry to populate
        existing_names: Set of domain names that already exist

    Returns:
        List of newly discovered domains
    """
    existing = existing_names or set(domain_registry.domain_names())
    discovered = []

    # Get root-level paths from the catalog
    try:
        root_paths = catalog_registry.list_children("")
    except Exception:
        return discovered

    for path in root_paths:
        name = path.strip("/").split("/")[0]
        if name and name not in existing:
            # Create a placeholder domain
            domain = Domain(
                name=name,
                display_name=name.replace("_", " ").title(),
                notes="Auto-discovered from catalog"
            )
            domain_registry.register_or_update(domain)
            discovered.append(domain)
            existing.add(name)

    return discovered
