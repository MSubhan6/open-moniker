"""Catalog serializer - converts CatalogNode to YAML-ready dict."""

from __future__ import annotations

from typing import Any

from .types import (
    AccessPolicy, CatalogNode, ColumnSchema, DataQuality, DataSchema,
    Documentation, Freshness, Ownership, SLA, SourceBinding,
)


class CatalogSerializer:
    """
    Serializes CatalogNode objects to dictionaries for YAML output.

    Inverse of the CatalogLoader._parse_node() method.
    Omits empty/default values to keep YAML clean.
    """

    def serialize_node(self, node: CatalogNode) -> dict[str, Any]:
        """Serialize a CatalogNode to a dictionary."""
        result: dict[str, Any] = {}

        if node.display_name and node.display_name != node.path.split("/")[-1]:
            result["display_name"] = node.display_name

        if node.description:
            result["description"] = node.description

        if node.domain:
            result["domain"] = node.domain

        if node.ownership and not node.ownership.is_empty():
            result["ownership"] = self.serialize_ownership(node.ownership)

        if node.source_binding:
            result["source_binding"] = self.serialize_source_binding(node.source_binding)

        if node.data_quality:
            dq = self.serialize_data_quality(node.data_quality)
            if dq:
                result["data_quality"] = dq

        if node.sla:
            sla = self.serialize_sla(node.sla)
            if sla:
                result["sla"] = sla

        if node.freshness:
            fresh = self.serialize_freshness(node.freshness)
            if fresh:
                result["freshness"] = fresh

        if node.data_schema:
            schema = self.serialize_data_schema(node.data_schema)
            if schema:
                result["schema"] = schema

        if node.access_policy:
            ap = self.serialize_access_policy(node.access_policy)
            if ap:
                result["access_policy"] = ap

        if node.documentation and not node.documentation.is_empty():
            result["documentation"] = self.serialize_documentation(node.documentation)

        if node.classification and node.classification != "internal":
            result["classification"] = node.classification

        if node.tags:
            result["tags"] = list(node.tags)

        if node.metadata:
            result["metadata"] = node.metadata

        return result

    def serialize_ownership(self, ownership: Ownership) -> dict[str, Any]:
        """Serialize Ownership, omitting empty fields."""
        result: dict[str, Any] = {}

        if ownership.accountable_owner:
            result["accountable_owner"] = ownership.accountable_owner
        if ownership.data_specialist:
            result["data_specialist"] = ownership.data_specialist
        if ownership.support_channel:
            result["support_channel"] = ownership.support_channel
        if ownership.adop:
            result["adop"] = ownership.adop
        if ownership.ads:
            result["ads"] = ownership.ads
        if ownership.adal:
            result["adal"] = ownership.adal

        return result

    def serialize_source_binding(self, binding: SourceBinding) -> dict[str, Any]:
        """Serialize SourceBinding."""
        result: dict[str, Any] = {
            "type": binding.source_type.value,
        }

        if binding.config:
            result["config"] = binding.config

        if binding.allowed_operations is not None:
            result["allowed_operations"] = list(binding.allowed_operations)

        if binding.schema:
            result["schema"] = binding.schema

        if not binding.read_only:
            result["read_only"] = False

        return result

    def serialize_data_quality(self, dq: DataQuality) -> dict[str, Any]:
        """Serialize DataQuality, omitting empty fields."""
        result: dict[str, Any] = {}

        if dq.dq_owner:
            result["dq_owner"] = dq.dq_owner
        if dq.quality_score is not None:
            result["quality_score"] = dq.quality_score
        if dq.validation_rules:
            result["validation_rules"] = list(dq.validation_rules)
        if dq.known_issues:
            result["known_issues"] = list(dq.known_issues)
        if dq.last_validated:
            result["last_validated"] = dq.last_validated

        return result

    def serialize_sla(self, sla: SLA) -> dict[str, Any]:
        """Serialize SLA, omitting empty fields."""
        result: dict[str, Any] = {}

        if sla.freshness:
            result["freshness"] = sla.freshness
        if sla.availability:
            result["availability"] = sla.availability
        if sla.support_hours:
            result["support_hours"] = sla.support_hours
        if sla.escalation_contact:
            result["escalation_contact"] = sla.escalation_contact

        return result

    def serialize_freshness(self, freshness: Freshness) -> dict[str, Any]:
        """Serialize Freshness, omitting empty fields."""
        result: dict[str, Any] = {}

        if freshness.last_loaded:
            result["last_loaded"] = freshness.last_loaded
        if freshness.refresh_schedule:
            result["refresh_schedule"] = freshness.refresh_schedule
        if freshness.source_system:
            result["source_system"] = freshness.source_system
        if freshness.upstream_dependencies:
            result["upstream_dependencies"] = list(freshness.upstream_dependencies)

        return result

    def serialize_data_schema(self, schema: DataSchema) -> dict[str, Any]:
        """Serialize DataSchema, omitting empty fields."""
        result: dict[str, Any] = {}

        if schema.columns:
            result["columns"] = [
                self.serialize_column_schema(col)
                for col in schema.columns
            ]

        if schema.description:
            result["description"] = schema.description
        if schema.semantic_tags:
            result["semantic_tags"] = list(schema.semantic_tags)
        if schema.primary_key:
            result["primary_key"] = list(schema.primary_key)
        if schema.use_cases:
            result["use_cases"] = list(schema.use_cases)
        if schema.examples:
            result["examples"] = list(schema.examples)
        if schema.related_monikers:
            result["related_monikers"] = list(schema.related_monikers)
        if schema.granularity:
            result["granularity"] = schema.granularity
        if schema.typical_row_count:
            result["typical_row_count"] = schema.typical_row_count
        if schema.update_frequency:
            result["update_frequency"] = schema.update_frequency

        return result

    def serialize_column_schema(self, col: ColumnSchema) -> dict[str, Any]:
        """Serialize ColumnSchema."""
        result: dict[str, Any] = {
            "name": col.name,
            "type": col.data_type,
        }

        if col.description:
            result["description"] = col.description
        if col.semantic_type:
            result["semantic_type"] = col.semantic_type
        if col.example:
            result["example"] = col.example
        if not col.nullable:
            result["nullable"] = False
        if col.primary_key:
            result["primary_key"] = True
        if col.foreign_key:
            result["foreign_key"] = col.foreign_key

        return result

    def serialize_access_policy(self, policy: AccessPolicy) -> dict[str, Any]:
        """Serialize AccessPolicy, omitting default fields."""
        result: dict[str, Any] = {}

        if policy.required_segments:
            result["required_segments"] = list(policy.required_segments)
        if policy.min_filters > 0:
            result["min_filters"] = policy.min_filters
        if policy.blocked_patterns:
            result["blocked_patterns"] = list(policy.blocked_patterns)
        if policy.max_rows_warn is not None:
            result["max_rows_warn"] = policy.max_rows_warn
        if policy.max_rows_block is not None:
            result["max_rows_block"] = policy.max_rows_block
        if policy.cardinality_multipliers:
            result["cardinality_multipliers"] = list(policy.cardinality_multipliers)
        if policy.base_row_count != 100:
            result["base_row_count"] = policy.base_row_count
        if policy.require_confirmation_above is not None:
            result["require_confirmation_above"] = policy.require_confirmation_above
        if policy.denial_message:
            result["denial_message"] = policy.denial_message
        if policy.allowed_roles:
            result["allowed_roles"] = list(policy.allowed_roles)
        if policy.allowed_hours is not None:
            result["allowed_hours"] = list(policy.allowed_hours)

        return result

    def serialize_documentation(self, docs: Documentation) -> dict[str, Any]:
        """Serialize Documentation, omitting empty fields."""
        result: dict[str, Any] = {}

        if docs.glossary_url:
            result["glossary"] = docs.glossary_url
        if docs.runbook_url:
            result["runbook"] = docs.runbook_url
        if docs.onboarding_url:
            result["onboarding"] = docs.onboarding_url
        if docs.data_dictionary_url:
            result["data_dictionary"] = docs.data_dictionary_url
        if docs.api_docs_url:
            result["api_docs"] = docs.api_docs_url
        if docs.architecture_url:
            result["architecture"] = docs.architecture_url
        if docs.changelog_url:
            result["changelog"] = docs.changelog_url
        if docs.contact_url:
            result["contact"] = docs.contact_url
        if docs.additional_links:
            result["additional"] = {name: url for name, url in docs.additional_links}

        return result

    def serialize_catalog(self, nodes: list[CatalogNode]) -> dict[str, Any]:
        """
        Serialize an entire catalog to a dictionary ready for YAML output.

        Returns:
            Dictionary mapping path -> node data
        """
        result: dict[str, Any] = {}

        for node in sorted(nodes, key=lambda n: n.path):
            node_data = self.serialize_node(node)
            if node_data:  # Only include nodes with meaningful data
                result[node.path] = node_data

        return result
