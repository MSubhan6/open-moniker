"""
Domain configuration serializer.

Save domains to YAML format.
"""

from pathlib import Path
from typing import List, Union

import yaml

from .types import Domain
from .registry import DomainRegistry


def save_domains_to_yaml(
    domains: Union[List[Domain], DomainRegistry],
    file_path: str | Path
) -> None:
    """
    Save domains to a YAML file.

    Output format:
        # Data Domains Configuration
        indices:
          display_name: Market Indices
          short_code: IDX
          ...

    Args:
        domains: List of domains or a DomainRegistry
        file_path: Path to write the YAML file
    """
    if isinstance(domains, DomainRegistry):
        domain_list = domains.all_domains()
    else:
        domain_list = sorted(domains, key=lambda d: d.name)

    # Build the YAML structure
    data = {}
    for domain in domain_list:
        domain_data = {
            "display_name": domain.display_name,
            "short_code": domain.short_code,
            "color": domain.color,
            "owner": domain.owner,
            "tech_custodian": domain.tech_custodian,
            "business_steward": domain.business_steward,
            "data_category": domain.data_category,
            "confidentiality": domain.confidentiality,
            "pii": domain.pii,
            "help_channel": domain.help_channel,
            "wiki_link": domain.wiki_link,
            "notes": domain.notes,
        }
        # Remove empty string values for cleaner output
        domain_data = {k: v for k, v in domain_data.items() if v or isinstance(v, bool)}
        data[domain.name] = domain_data

    path = Path(file_path)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Data Domains Configuration\n")
        f.write("# Top-level organizational units for the moniker catalog\n\n")
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
