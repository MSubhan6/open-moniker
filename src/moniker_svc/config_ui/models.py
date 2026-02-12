"""Pydantic models for Config UI API requests and responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Ownership Models
# =============================================================================

class OwnershipModel(BaseModel):
    """Mutable ownership model for API input/output."""
    accountable_owner: str | None = None
    data_specialist: str | None = None
    support_channel: str | None = None
    adop: str | None = None
    ads: str | None = None
    adal: str | None = None
    ui: str | None = None


class ResolvedOwnershipModel(BaseModel):
    """Ownership with provenance info."""
    accountable_owner: str | None = None
    accountable_owner_source: str | None = None
    data_specialist: str | None = None
    data_specialist_source: str | None = None
    support_channel: str | None = None
    support_channel_source: str | None = None
    adop: str | None = None
    adop_source: str | None = None
    ads: str | None = None
    ads_source: str | None = None
    adal: str | None = None
    adal_source: str | None = None
    ui: str | None = None
    ui_source: str | None = None


# =============================================================================
# Source Binding Models
# =============================================================================

class SourceBindingModel(BaseModel):
    """Mutable source binding model."""
    type: str  # SourceType value
    config: dict[str, Any] = Field(default_factory=dict)
    allowed_operations: list[str] | None = None
    schema_def: dict[str, Any] | None = Field(default=None, alias="schema")
    read_only: bool = True

    model_config = {"populate_by_name": True}


# =============================================================================
# Data Quality Models
# =============================================================================

class DataQualityModel(BaseModel):
    """Mutable data quality model."""
    dq_owner: str | None = None
    quality_score: float | None = None
    validation_rules: list[str] = Field(default_factory=list)
    known_issues: list[str] = Field(default_factory=list)
    last_validated: str | None = None


# =============================================================================
# SLA Models
# =============================================================================

class SLAModel(BaseModel):
    """Mutable SLA model."""
    freshness: str | None = None
    availability: str | None = None
    support_hours: str | None = None
    escalation_contact: str | None = None


# =============================================================================
# Freshness Models
# =============================================================================

class FreshnessModel(BaseModel):
    """Mutable freshness model."""
    last_loaded: str | None = None
    refresh_schedule: str | None = None
    source_system: str | None = None
    upstream_dependencies: list[str] = Field(default_factory=list)


# =============================================================================
# Schema Models
# =============================================================================

class ColumnSchemaModel(BaseModel):
    """Mutable column schema model."""
    name: str
    type: str = Field(alias="data_type", default="string")
    description: str = ""
    semantic_type: str | None = None
    example: str | None = None
    nullable: bool = True
    primary_key: bool = False
    foreign_key: str | None = None

    model_config = {"populate_by_name": True}


class DataSchemaModel(BaseModel):
    """Mutable data schema model."""
    columns: list[ColumnSchemaModel] = Field(default_factory=list)
    description: str = ""
    semantic_tags: list[str] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    related_monikers: list[str] = Field(default_factory=list)
    granularity: str | None = None
    typical_row_count: str | None = None
    update_frequency: str | None = None


# =============================================================================
# Access Policy Models
# =============================================================================

class AccessPolicyModel(BaseModel):
    """Mutable access policy model."""
    required_segments: list[int] = Field(default_factory=list)
    min_filters: int = 0
    blocked_patterns: list[str] = Field(default_factory=list)
    max_rows_warn: int | None = None
    max_rows_block: int | None = None
    cardinality_multipliers: list[int] = Field(default_factory=list)
    base_row_count: int = 100
    require_confirmation_above: int | None = None
    denial_message: str | None = None
    allowed_roles: list[str] = Field(default_factory=list)
    allowed_hours: tuple[int, int] | None = None


# =============================================================================
# Documentation Models
# =============================================================================

class DocumentationModel(BaseModel):
    """Mutable documentation model."""
    glossary: str | None = None
    runbook: str | None = None
    onboarding: str | None = None
    data_dictionary: str | None = None
    api_docs: str | None = None
    architecture: str | None = None
    changelog: str | None = None
    contact: str | None = None
    additional: dict[str, str] = Field(default_factory=dict)


# =============================================================================
# Node Models
# =============================================================================

class CatalogNodeModel(BaseModel):
    """Mutable catalog node model for API input/output."""
    path: str
    display_name: str = ""
    description: str = ""
    domain: str | None = None
    ownership: OwnershipModel | None = None
    source_binding: SourceBindingModel | None = None
    data_quality: DataQualityModel | None = None
    sla: SLAModel | None = None
    freshness: FreshnessModel | None = None
    data_schema: DataSchemaModel | None = Field(default=None, alias="schema")
    access_policy: AccessPolicyModel | None = None
    documentation: DocumentationModel | None = None
    classification: str = "internal"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_leaf: bool = False

    model_config = {"populate_by_name": True}


class NodeWithOwnershipModel(BaseModel):
    """Node with resolved ownership info."""
    node: CatalogNodeModel
    resolved_ownership: ResolvedOwnershipModel


# =============================================================================
# Request Models
# =============================================================================

class CreateNodeRequest(BaseModel):
    """Request to create a new node."""
    path: str
    display_name: str = ""
    description: str = ""
    domain: str | None = None
    ownership: OwnershipModel | None = None
    source_binding: SourceBindingModel | None = None
    data_quality: DataQualityModel | None = None
    sla: SLAModel | None = None
    freshness: FreshnessModel | None = None
    data_schema: DataSchemaModel | None = Field(default=None, alias="schema")
    access_policy: AccessPolicyModel | None = None
    documentation: DocumentationModel | None = None
    classification: str = "internal"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class UpdateNodeRequest(BaseModel):
    """Request to update a node (partial update allowed)."""
    display_name: str | None = None
    description: str | None = None
    domain: str | None = None
    ownership: OwnershipModel | None = None
    source_binding: SourceBindingModel | None = None
    data_quality: DataQualityModel | None = None
    sla: SLAModel | None = None
    freshness: FreshnessModel | None = None
    data_schema: DataSchemaModel | None = Field(default=None, alias="schema")
    access_policy: AccessPolicyModel | None = None
    documentation: DocumentationModel | None = None
    classification: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


# =============================================================================
# Response Models
# =============================================================================

class NodeListResponse(BaseModel):
    """List of nodes response."""
    nodes: list[CatalogNodeModel]
    total: int


class SaveResponse(BaseModel):
    """Save to YAML response."""
    success: bool
    path: str
    moniker_count: int
    message: str = ""


class ReloadResponse(BaseModel):
    """Reload from YAML response."""
    success: bool
    moniker_count: int
    message: str = ""


class SourceTypeInfo(BaseModel):
    """Info about a source type."""
    type: str
    display_name: str
    config_schema: dict[str, Any]
    execution_mode: str = "server"  # "client" or "server"
    execution_hint: str = ""  # Human-readable explanation


class SourceTypesResponse(BaseModel):
    """List of source types with their config schemas."""
    source_types: list[SourceTypeInfo]


class DeleteResponse(BaseModel):
    """Delete node response."""
    success: bool
    path: str
    message: str = ""
