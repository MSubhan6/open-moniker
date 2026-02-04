"""
Pydantic models for Domain API.

Provides request/response models for the domain configuration endpoints.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class DomainModel(BaseModel):
    """Domain representation for API responses."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "indices",
                "display_name": "Market Indices",
                "short_code": "IDX",
                "color": "#4A90D9",
                "owner": "indices-governance@firm.com",
                "tech_custodian": "quant-tech@firm.com",
                "business_steward": "index-committee@firm.com",
                "data_category": "Market Data",
                "confidentiality": "internal",
                "pii": False,
                "help_channel": "#indices-support",
                "wiki_link": "https://confluence.firm.com/display/DATA/Indices",
                "notes": "Benchmark indices, aggregates, and composites",
            }
        }
    )

    name: str = Field(..., description="Domain identifier (matches first segment of moniker paths)")
    display_name: str = Field("", description="Human-readable name")
    short_code: str = Field("", description="Short code (e.g., IDX, CMD, REF)")
    color: str = Field("#6B7280", description="Hex color code for UI display")
    owner: str = Field("", description="Executive/business owner")
    tech_custodian: str = Field("", description="Technical custodian")
    business_steward: str = Field("", description="Business data steward")
    data_category: str = Field("", description="Data category classification")
    confidentiality: str = Field("internal", description="Confidentiality level: public, internal, confidential, strictly_confidential")
    pii: bool = Field(False, description="Contains personally identifiable information")
    help_channel: str = Field("", description="Support channel (Teams/Slack)")
    wiki_link: str = Field("", description="Link to documentation")
    notes: str = Field("", description="Free-text notes")


class CreateDomainRequest(BaseModel):
    """Request model for creating a new domain."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "derivatives",
                "display_name": "Derivatives",
                "short_code": "DRV",
                "color": "#8E44AD",
                "owner": "derivatives-desk@firm.com",
                "data_category": "Market Data",
                "confidentiality": "internal",
            }
        }
    )

    name: str = Field(..., description="Domain identifier (must be unique)")
    display_name: str = Field("", description="Human-readable name")
    short_code: str = Field("", description="Short code")
    color: str = Field("#6B7280", description="Hex color code")
    owner: str = Field("", description="Executive/business owner")
    tech_custodian: str = Field("", description="Technical custodian")
    business_steward: str = Field("", description="Business data steward")
    data_category: str = Field("", description="Data category")
    confidentiality: str = Field("internal", description="Confidentiality level")
    pii: bool = Field(False, description="Contains PII")
    help_channel: str = Field("", description="Support channel")
    wiki_link: str = Field("", description="Documentation link")
    notes: str = Field("", description="Notes")


class UpdateDomainRequest(BaseModel):
    """Request model for updating a domain (all fields optional)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "Market Indices (Updated)",
                "owner": "new-owner@firm.com",
                "color": "#2980B9",
            }
        }
    )

    display_name: Optional[str] = Field(None, description="Human-readable name")
    short_code: Optional[str] = Field(None, description="Short code")
    color: Optional[str] = Field(None, description="Hex color code")
    owner: Optional[str] = Field(None, description="Executive/business owner")
    tech_custodian: Optional[str] = Field(None, description="Technical custodian")
    business_steward: Optional[str] = Field(None, description="Business data steward")
    data_category: Optional[str] = Field(None, description="Data category")
    confidentiality: Optional[str] = Field(None, description="Confidentiality level")
    pii: Optional[bool] = Field(None, description="Contains PII")
    help_channel: Optional[str] = Field(None, description="Support channel")
    wiki_link: Optional[str] = Field(None, description="Documentation link")
    notes: Optional[str] = Field(None, description="Notes")


class DomainListResponse(BaseModel):
    """Response model for listing all domains."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "domains": [
                    {
                        "name": "indices",
                        "display_name": "Market Indices",
                        "short_code": "IDX",
                        "color": "#4A90D9",
                    }
                ],
                "count": 1,
            }
        }
    )

    domains: List[DomainModel] = Field(..., description="List of all domains")
    count: int = Field(..., description="Total number of domains")


class DomainWithMonikersResponse(BaseModel):
    """Response model for a domain with its linked moniker paths."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "domain": {
                    "name": "indices",
                    "display_name": "Market Indices",
                    "short_code": "IDX",
                    "color": "#4A90D9",
                },
                "moniker_paths": ["indices/equity", "indices/fixed_income"],
                "moniker_count": 2,
            }
        }
    )

    domain: DomainModel = Field(..., description="Domain details")
    moniker_paths: List[str] = Field(default_factory=list, description="Top-level moniker paths under this domain")
    moniker_count: int = Field(0, description="Number of moniker paths")


class SaveResponse(BaseModel):
    """Response model for save operations."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Status message")
    file_path: Optional[str] = Field(None, description="Path to saved file")


class ReloadResponse(BaseModel):
    """Response model for reload operations."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Status message")
    domains_loaded: int = Field(0, description="Number of domains loaded")
