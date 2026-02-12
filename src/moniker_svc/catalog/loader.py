"""Catalog loader - loads catalog definitions from YAML/JSON files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .registry import CatalogRegistry
from .types import (
    AccessPolicy, CatalogNode, ColumnSchema, DataQuality, DataSchema,
    Documentation, Freshness, NodeStatus, Ownership, SLA, SourceBinding, SourceType,
)


logger = logging.getLogger(__name__)


class CatalogLoader:
    """
    Loads catalog definitions from YAML or JSON files.

    File format:
    ```yaml
    market-data:
      display_name: Market Data
      description: Real-time and historical market data
      ownership:
        accountable_owner: jane@firm.com
        data_specialist: team@firm.com
        support_channel: "#market-data"

    market-data/prices/equity:
      display_name: Equity Prices
      source_binding:
        type: snowflake
        config:
          account: acme.us-east-1
          database: MARKET_DATA
          query: "SELECT * FROM PRICES WHERE symbol = '{path}'"
    ```
    """

    def load_file(self, path: str | Path) -> CatalogRegistry:
        """Load catalog from a YAML or JSON file."""
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Catalog file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            if path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(f)
            else:
                import json
                data = json.load(f)

        return self.load_dict(data or {})

    def load_dict(self, data: dict[str, Any]) -> CatalogRegistry:
        """Load catalog from a dictionary."""
        registry = CatalogRegistry()

        for path, node_data in data.items():
            node = self._parse_node(path, node_data)
            registry.register(node)
            logger.debug(f"Loaded catalog node: {path}")

        logger.info(f"Loaded {len(registry.all_paths())} monikers")
        return registry

    def _parse_node(self, path: str, data: dict[str, Any]) -> CatalogNode:
        """Parse a single catalog node from dictionary."""
        # Parse ownership (including formal governance roles)
        ownership = Ownership()
        if "ownership" in data:
            own_data = data["ownership"]
            ownership = Ownership(
                accountable_owner=own_data.get("accountable_owner"),
                data_specialist=own_data.get("data_specialist"),
                support_channel=own_data.get("support_channel"),
                # Formal governance roles (ADOP, ADS, ADAL)
                adop=own_data.get("adop"),
                ads=own_data.get("ads"),
                adal=own_data.get("adal"),
            )

        # Parse source binding
        source_binding = None
        if "source_binding" in data:
            sb_data = data["source_binding"]
            source_type_str = sb_data.get("type", "").lower()

            try:
                source_type = SourceType(source_type_str)
            except ValueError:
                logger.warning(f"Unknown source type '{source_type_str}' for {path}")
                source_type = SourceType.STATIC

            source_binding = SourceBinding(
                source_type=source_type,
                config=sb_data.get("config", {}),
                schema=sb_data.get("schema"),
                read_only=sb_data.get("read_only", True),
            )

        # Parse tags
        tags = frozenset(data.get("tags", []))

        # Parse data quality
        data_quality = None
        if "data_quality" in data:
            dq_data = data["data_quality"]
            data_quality = DataQuality(
                dq_owner=dq_data.get("dq_owner"),
                quality_score=dq_data.get("quality_score"),
                validation_rules=tuple(dq_data.get("validation_rules", [])),
                known_issues=tuple(dq_data.get("known_issues", [])),
                last_validated=dq_data.get("last_validated"),
            )

        # Parse SLA
        sla = None
        if "sla" in data:
            sla_data = data["sla"]
            sla = SLA(
                freshness=sla_data.get("freshness"),
                availability=sla_data.get("availability"),
                support_hours=sla_data.get("support_hours"),
                escalation_contact=sla_data.get("escalation_contact"),
            )

        # Parse freshness
        freshness = None
        if "freshness" in data:
            fresh_data = data["freshness"]
            freshness = Freshness(
                last_loaded=fresh_data.get("last_loaded"),
                refresh_schedule=fresh_data.get("refresh_schedule"),
                source_system=fresh_data.get("source_system"),
                upstream_dependencies=tuple(fresh_data.get("upstream_dependencies", [])),
            )

        # Parse data schema (AI-readable metadata)
        data_schema = None
        if "schema" in data:
            schema_data = data["schema"]
            columns = []
            for col_data in schema_data.get("columns", []):
                columns.append(ColumnSchema(
                    name=col_data.get("name", ""),
                    data_type=col_data.get("type", "string"),
                    description=col_data.get("description", ""),
                    semantic_type=col_data.get("semantic_type"),
                    example=col_data.get("example"),
                    nullable=col_data.get("nullable", True),
                    primary_key=col_data.get("primary_key", False),
                    foreign_key=col_data.get("foreign_key"),
                ))
            data_schema = DataSchema(
                columns=tuple(columns),
                description=schema_data.get("description", ""),
                semantic_tags=tuple(schema_data.get("semantic_tags", [])),
                primary_key=tuple(schema_data.get("primary_key", [])),
                use_cases=tuple(schema_data.get("use_cases", [])),
                examples=tuple(schema_data.get("examples", [])),
                related_monikers=tuple(schema_data.get("related_monikers", [])),
                granularity=schema_data.get("granularity"),
                typical_row_count=schema_data.get("typical_row_count"),
                update_frequency=schema_data.get("update_frequency"),
            )

        # Parse access policy (query guardrails)
        access_policy = None
        if "access_policy" in data:
            ap_data = data["access_policy"]
            access_policy = AccessPolicy(
                required_segments=tuple(ap_data.get("required_segments", [])),
                min_filters=ap_data.get("min_filters", 0),
                blocked_patterns=tuple(ap_data.get("blocked_patterns", [])),
                max_rows_warn=ap_data.get("max_rows_warn"),
                max_rows_block=ap_data.get("max_rows_block"),
                cardinality_multipliers=tuple(ap_data.get("cardinality_multipliers", [])),
                base_row_count=ap_data.get("base_row_count", 100),
                require_confirmation_above=ap_data.get("require_confirmation_above"),
                denial_message=ap_data.get("denial_message"),
                allowed_roles=tuple(ap_data.get("allowed_roles", [])),
            )

        # Parse documentation links (Confluence, runbooks, etc.)
        documentation = None
        if "documentation" in data:
            doc_data = data["documentation"]
            # Parse additional links as tuple of (name, url) pairs
            additional = doc_data.get("additional", {})
            additional_links = tuple((k, v) for k, v in additional.items()) if additional else ()

            documentation = Documentation(
                glossary_url=doc_data.get("glossary"),
                runbook_url=doc_data.get("runbook"),
                onboarding_url=doc_data.get("onboarding"),
                data_dictionary_url=doc_data.get("data_dictionary"),
                api_docs_url=doc_data.get("api_docs"),
                architecture_url=doc_data.get("architecture"),
                changelog_url=doc_data.get("changelog"),
                contact_url=doc_data.get("contact"),
                additional_links=additional_links,
            )

        # Parse lifecycle status from YAML
        status = NodeStatus.ACTIVE
        if "status" in data:
            try:
                status = NodeStatus(data["status"])
            except ValueError:
                logger.warning(f"Unknown status '{data['status']}' for {path}, defaulting to active")

        return CatalogNode(
            path=path,
            display_name=data.get("display_name", ""),
            description=data.get("description", ""),
            domain=data.get("domain"),
            ownership=ownership,
            source_binding=source_binding,
            data_quality=data_quality,
            sla=sla,
            freshness=freshness,
            data_schema=data_schema,
            access_policy=access_policy,
            documentation=documentation,
            classification=data.get("classification", "internal"),
            tags=tags,
            metadata=data.get("metadata", {}),
            status=status,
            deprecation_message=data.get("deprecation_message"),
            successor=data.get("successor"),
            sunset_deadline=data.get("sunset_deadline"),
            migration_guide_url=data.get("migration_guide_url"),
            is_leaf=source_binding is not None,
        )

    def load_directory(self, directory: str | Path) -> CatalogRegistry:
        """
        Load catalog from all YAML/JSON files in a directory.

        Files are loaded in alphabetical order. Later files can override
        earlier definitions.
        """
        directory = Path(directory)
        registry = CatalogRegistry()

        if not directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")) + sorted(directory.glob("*.json"))

        for file_path in files:
            logger.info(f"Loading catalog file: {file_path}")
            file_registry = self.load_file(file_path)
            for node in file_registry.all_nodes():
                registry.register(node)

        return registry


def load_catalog(source: str | Path | dict) -> CatalogRegistry:
    """
    Convenience function to load a catalog.

    Args:
        source: File path, directory path, or dictionary

    Returns:
        CatalogRegistry with loaded nodes
    """
    loader = CatalogLoader()

    if isinstance(source, dict):
        return loader.load_dict(source)

    path = Path(source)
    if path.is_dir():
        return loader.load_directory(path)
    else:
        return loader.load_file(path)
