"""FastAPI routes for Domain Configuration API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from ..catalog.registry import CatalogRegistry
from .types import Domain
from .registry import DomainRegistry
from .loader import load_domains_from_yaml
from .serializer import save_domains_to_yaml
from .models import (
    DomainModel,
    DomainListResponse,
    DomainWithMonikersResponse,
    CreateDomainRequest,
    UpdateDomainRequest,
    SaveResponse,
    ReloadResponse,
)

logger = logging.getLogger(__name__)

# Create router with Domains tag for OpenAPI grouping
router = APIRouter(prefix="/domains", tags=["Domains"])

# Configuration - will be set during app startup
_domain_registry: DomainRegistry | None = None
_catalog_registry: CatalogRegistry | None = None
_domains_yaml_path: str = "domains.yaml"


def configure(
    domain_registry: DomainRegistry,
    catalog_registry: Optional[CatalogRegistry] = None,
    domains_yaml_path: str = "domains.yaml",
) -> None:
    """Configure the Domain routes.

    Args:
        domain_registry: The domain registry to manage
        catalog_registry: Optional catalog registry for linking domains to monikers
        domains_yaml_path: Path to domains YAML file
    """
    global _domain_registry, _catalog_registry, _domains_yaml_path
    _domain_registry = domain_registry
    _catalog_registry = catalog_registry
    _domains_yaml_path = domains_yaml_path


def _get_domain_registry() -> DomainRegistry:
    """Get the domain registry, raising if not configured."""
    if _domain_registry is None:
        raise HTTPException(status_code=503, detail="Domain configuration not initialized")
    return _domain_registry


def _domain_to_model(domain: Domain) -> DomainModel:
    """Convert Domain dataclass to Pydantic model."""
    return DomainModel(
        name=domain.name,
        display_name=domain.display_name,
        short_code=domain.short_code,
        color=domain.color,
        owner=domain.owner,
        tech_custodian=domain.tech_custodian,
        business_steward=domain.business_steward,
        data_category=domain.data_category,
        confidentiality=domain.confidentiality,
        pii=domain.pii,
        help_channel=domain.help_channel,
        wiki_link=domain.wiki_link,
        notes=domain.notes,
    )


def _get_moniker_paths_for_domain(domain_name: str) -> list[str]:
    """Get moniker paths under a domain."""
    if _catalog_registry is None:
        return []

    try:
        # Get children of the domain root
        children = _catalog_registry.children_paths(domain_name)
        return sorted(children) if children else []
    except Exception:
        return []


# =============================================================================
# UI Endpoint
# =============================================================================

@router.get("/ui", response_class=HTMLResponse)
async def domains_ui():
    """Serve the Domain Configuration UI HTML."""
    static_dir = Path(__file__).parent / "static"
    index_path = static_dir / "index.html"

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Domain Config UI not found")

    return HTMLResponse(content=index_path.read_text(), status_code=200)


# =============================================================================
# Domain CRUD Endpoints
# =============================================================================

@router.get("", response_model=DomainListResponse)
async def list_domains():
    """
    List all domains.

    Returns all registered domains with their governance metadata.
    """
    registry = _get_domain_registry()
    domains = registry.all_domains()

    return DomainListResponse(
        domains=[_domain_to_model(d) for d in domains],
        count=len(domains),
    )


@router.get("/{name}", response_model=DomainWithMonikersResponse)
async def get_domain(name: str):
    """
    Get a single domain by name.

    Returns the domain details along with linked moniker paths.
    """
    registry = _get_domain_registry()

    domain = registry.get(name)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain not found: {name}")

    moniker_paths = _get_moniker_paths_for_domain(name)

    return DomainWithMonikersResponse(
        domain=_domain_to_model(domain),
        moniker_paths=moniker_paths,
        moniker_count=len(moniker_paths),
    )


@router.post("", response_model=DomainModel, status_code=201)
async def create_domain(request: CreateDomainRequest):
    """
    Create a new domain.

    The domain name must be unique.
    """
    registry = _get_domain_registry()

    # Check if domain already exists
    if registry.exists(request.name):
        raise HTTPException(status_code=409, detail=f"Domain already exists: {request.name}")

    # Create the domain
    domain = Domain(
        name=request.name,
        display_name=request.display_name,
        short_code=request.short_code,
        color=request.color,
        owner=request.owner,
        tech_custodian=request.tech_custodian,
        business_steward=request.business_steward,
        data_category=request.data_category,
        confidentiality=request.confidentiality,
        pii=request.pii,
        help_channel=request.help_channel,
        wiki_link=request.wiki_link,
        notes=request.notes,
    )

    registry.register(domain)
    logger.info(f"Created domain: {request.name}")

    return _domain_to_model(domain)


@router.put("/{name}", response_model=DomainModel)
async def update_domain(name: str, request: UpdateDomainRequest):
    """
    Update an existing domain.

    Only provided fields are updated; others retain their current values.
    """
    registry = _get_domain_registry()

    # Get existing domain
    existing = registry.get(name)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Domain not found: {name}")

    # Build updated domain (only update fields that are not None)
    domain = Domain(
        name=name,
        display_name=request.display_name if request.display_name is not None else existing.display_name,
        short_code=request.short_code if request.short_code is not None else existing.short_code,
        color=request.color if request.color is not None else existing.color,
        owner=request.owner if request.owner is not None else existing.owner,
        tech_custodian=request.tech_custodian if request.tech_custodian is not None else existing.tech_custodian,
        business_steward=request.business_steward if request.business_steward is not None else existing.business_steward,
        data_category=request.data_category if request.data_category is not None else existing.data_category,
        confidentiality=request.confidentiality if request.confidentiality is not None else existing.confidentiality,
        pii=request.pii if request.pii is not None else existing.pii,
        help_channel=request.help_channel if request.help_channel is not None else existing.help_channel,
        wiki_link=request.wiki_link if request.wiki_link is not None else existing.wiki_link,
        notes=request.notes if request.notes is not None else existing.notes,
    )

    registry.register_or_update(domain)
    logger.info(f"Updated domain: {name}")

    return _domain_to_model(domain)


@router.delete("/{name}")
async def delete_domain(name: str):
    """
    Delete a domain.

    Note: This does not delete associated monikers, only the domain configuration.
    """
    registry = _get_domain_registry()

    if not registry.exists(name):
        raise HTTPException(status_code=404, detail=f"Domain not found: {name}")

    registry.delete(name)
    logger.info(f"Deleted domain: {name}")

    return {"success": True, "message": f"Domain '{name}' deleted"}


# =============================================================================
# Save/Reload Endpoints
# =============================================================================

@router.post("/save", response_model=SaveResponse)
async def save_domains():
    """
    Save all domains to YAML file.

    Persists the current domain configuration to the configured YAML file.
    """
    registry = _get_domain_registry()

    output_path = Path(_domains_yaml_path)
    try:
        save_domains_to_yaml(registry, output_path)
        count = registry.count()

        logger.info(f"Saved {count} domains to {output_path}")

        return SaveResponse(
            success=True,
            message=f"Saved {count} domains to {output_path}",
            file_path=str(output_path.absolute()),
        )
    except Exception as e:
        logger.error(f"Failed to save domains: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


@router.post("/reload", response_model=ReloadResponse)
async def reload_domains():
    """
    Reload domains from YAML file.

    Replaces current configuration with contents of the YAML file.
    """
    registry = _get_domain_registry()
    source_path = Path(_domains_yaml_path)

    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Domains file not found: {source_path}")

    try:
        # Clear and reload
        registry.clear()
        domains = load_domains_from_yaml(source_path, registry)

        logger.info(f"Reloaded {len(domains)} domains from {source_path}")

        return ReloadResponse(
            success=True,
            message=f"Reloaded {len(domains)} domains from {source_path}",
            domains_loaded=len(domains),
        )
    except Exception as e:
        logger.error(f"Failed to reload domains: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reload: {str(e)}")
