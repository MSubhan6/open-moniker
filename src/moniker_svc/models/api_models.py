"""
Pydantic models for Business Models API.

Provides request/response models for the model configuration endpoints.
"""

from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class ModelOwnershipModel(BaseModel):
    """Ownership info for a business model."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "methodology_owner": "quant-research@firm.com",
                "business_steward": "risk-committee@firm.com",
                "support_channel": "#risk-methodology",
            }
        }
    )

    methodology_owner: str | None = Field(None, description="Owns calculation methodology")
    business_steward: str | None = Field(None, description="Business representative")
    support_channel: str | None = Field(None, description="Where to get help")


class MonikerLinkModel(BaseModel):
    """Defines where a model appears in the moniker catalog."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "moniker_pattern": "risk.cvar/*/*",
                "column_name": "DV01",
                "notes": "Primary risk measure",
            }
        }
    )

    moniker_pattern: str = Field(..., description="Glob pattern for moniker paths")
    column_name: str | None = Field(None, description="Column name if different from model name")
    notes: str | None = Field(None, description="Context about this appearance")


class BusinessModelModel(BaseModel):
    """Business model representation for API responses."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "path": "risk.analytics/dv01",
                "display_name": "Dollar Value of 01",
                "description": "Change in portfolio value for 1bp yield shift",
                "formula": "dV/dy × 0.0001",
                "unit": "USD",
                "data_type": "float",
                "ownership": {
                    "methodology_owner": "quant-research@firm.com",
                },
                "documentation_url": "https://wiki/DV01",
                "appears_in": [
                    {"moniker_pattern": "risk.cvar/*/*", "column_name": "DV01"},
                ],
                "semantic_tags": ["interest-rate-risk", "duration"],
            }
        }
    )

    path: str = Field(..., description="Hierarchical model path")
    display_name: str = Field("", description="Human-readable name")
    description: str = Field("", description="Description of the model/measure")

    # Business metadata
    formula: str | None = Field(None, description="Mathematical formula")
    unit: str | None = Field(None, description="Unit of measure (USD, bps, years)")
    data_type: str = Field("float", description="Expected data type")

    # Governance
    ownership: ModelOwnershipModel | None = Field(None, description="Ownership info")
    documentation_url: str | None = Field(None, description="Link to documentation")
    methodology_url: str | None = Field(None, description="Link to methodology docs")

    # Relationships
    appears_in: list[MonikerLinkModel] = Field(default_factory=list, description="Where this model appears")

    # Tags
    semantic_tags: list[str] = Field(default_factory=list, description="Semantic categorization")
    tags: list[str] = Field(default_factory=list, description="Generic tags")


class ModelSummaryModel(BaseModel):
    """Lightweight model summary for lists and cross-references."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "path": "risk.analytics/dv01",
                "display_name": "Dollar Value of 01",
                "description": "Change in portfolio value for 1bp yield shift",
                "unit": "USD",
                "formula": "dV/dy × 0.0001",
                "documentation_url": "https://wiki/DV01",
            }
        }
    )

    path: str = Field(..., description="Model path")
    display_name: str = Field("", description="Display name")
    description: str = Field("", description="Brief description")
    unit: str | None = Field(None, description="Unit of measure")
    formula: str | None = Field(None, description="Formula")
    documentation_url: str | None = Field(None, description="Documentation link")


class CreateModelRequest(BaseModel):
    """Request model for creating a new business model."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "path": "risk.analytics/convexity",
                "display_name": "Convexity",
                "description": "Second derivative of price with respect to yield",
                "formula": "d²V/dy²",
                "unit": "years²",
            }
        }
    )

    path: str = Field(..., description="Model path (must be unique)")
    display_name: str = Field("", description="Human-readable display name")
    description: str = Field("", description="Description")
    formula: str | None = Field(None, description="Mathematical formula")
    unit: str | None = Field(None, description="Unit of measure")
    data_type: str = Field("float", description="Data type")
    ownership: ModelOwnershipModel | None = Field(None, description="Ownership info")
    documentation_url: str | None = Field(None, description="Documentation link")
    methodology_url: str | None = Field(None, description="Methodology link")
    appears_in: list[MonikerLinkModel] = Field(default_factory=list, description="Moniker appearances")
    semantic_tags: list[str] = Field(default_factory=list, description="Semantic tags")
    tags: list[str] = Field(default_factory=list, description="Generic tags")


class UpdateModelRequest(BaseModel):
    """Request model for updating a business model (all fields optional)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "description": "Updated description",
                "documentation_url": "https://wiki/new-link",
            }
        }
    )

    display_name: str | None = Field(None, description="Display name")
    description: str | None = Field(None, description="Description")
    formula: str | None = Field(None, description="Formula")
    unit: str | None = Field(None, description="Unit")
    data_type: str | None = Field(None, description="Data type")
    ownership: ModelOwnershipModel | None = Field(None, description="Ownership")
    documentation_url: str | None = Field(None, description="Documentation link")
    methodology_url: str | None = Field(None, description="Methodology link")
    appears_in: list[MonikerLinkModel] | None = Field(None, description="Appearances")
    semantic_tags: list[str] | None = Field(None, description="Semantic tags")
    tags: list[str] | None = Field(None, description="Tags")


class ModelListResponse(BaseModel):
    """Response model for listing all models."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "models": [
                    {
                        "path": "risk.analytics/dv01",
                        "display_name": "Dollar Value of 01",
                    }
                ],
                "count": 1,
            }
        }
    )

    models: list[BusinessModelModel] = Field(..., description="List of all models")
    count: int = Field(..., description="Total number of models")


class ModelTreeNode(BaseModel):
    """A node in the model hierarchy tree."""

    path: str = Field(..., description="Model path")
    name: str = Field(..., description="Node name (last segment)")
    display_name: str = Field("", description="Display name")
    children: list["ModelTreeNode"] = Field(default_factory=list, description="Child nodes")
    is_container: bool = Field(True, description="True if no appears_in links")
    has_children: bool = Field(False, description="True if has child nodes")


# Enable self-reference
ModelTreeNode.model_rebuild()


class ModelTreeResponse(BaseModel):
    """Response model for model hierarchy tree."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tree": [
                    {
                        "path": "risk.analytics",
                        "name": "risk.analytics",
                        "display_name": "Risk Analytics",
                        "children": [
                            {
                                "path": "risk.analytics/dv01",
                                "name": "dv01",
                                "display_name": "Dollar Value of 01",
                            }
                        ],
                    }
                ],
                "total_count": 2,
            }
        }
    )

    tree: list[ModelTreeNode] = Field(..., description="Hierarchical tree structure")
    total_count: int = Field(..., description="Total number of models")


class ModelWithMonikersResponse(BaseModel):
    """Response model for a model with its linked monikers."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model": {
                    "path": "risk.analytics/dv01",
                    "display_name": "Dollar Value of 01",
                },
                "moniker_patterns": ["risk.cvar/*/*", "portfolios/*/risk/*"],
                "moniker_count": 2,
            }
        }
    )

    model: BusinessModelModel = Field(..., description="Model details")
    moniker_patterns: list[str] = Field(default_factory=list, description="Moniker patterns where model appears")
    moniker_count: int = Field(0, description="Number of moniker patterns")


class ModelsForMonikerResponse(BaseModel):
    """Response model for models available in a moniker."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "moniker_path": "risk/cvar/portfolio-123/USD",
                "models": [
                    {
                        "path": "risk.analytics/dv01",
                        "display_name": "Dollar Value of 01",
                    }
                ],
                "count": 1,
            }
        }
    )

    moniker_path: str = Field(..., description="The moniker path queried")
    models: list[ModelSummaryModel] = Field(..., description="Models available in this moniker")
    count: int = Field(..., description="Number of models")


class SaveResponse(BaseModel):
    """Response model for save operations."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Status message")
    file_path: str | None = Field(None, description="Path to saved file")


class ReloadResponse(BaseModel):
    """Response model for reload operations."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Status message")
    models_loaded: int = Field(0, description="Number of models loaded")
