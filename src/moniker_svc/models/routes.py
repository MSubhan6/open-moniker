"""FastAPI routes for Business Models API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from .types import Model, ModelOwnership, MonikerLink
from .registry import ModelRegistry
from .loader import load_models_from_yaml
from .serializer import save_models_to_yaml
from .api_models import (
    BusinessModelModel,
    CreateModelRequest,
    ModelListResponse,
    ModelOwnershipModel,
    ModelSummaryModel,
    ModelTreeNode,
    ModelTreeResponse,
    ModelWithMonikersResponse,
    ModelsForMonikerResponse,
    MonikerLinkModel,
    ReloadResponse,
    SaveResponse,
    UpdateModelRequest,
)

if TYPE_CHECKING:
    from ..catalog.registry import CatalogRegistry

logger = logging.getLogger(__name__)

# Create router with Models tag for OpenAPI grouping
router = APIRouter(prefix="/models", tags=["Models"])

# Configuration - will be set during app startup
_model_registry: ModelRegistry | None = None
_catalog_registry: "CatalogRegistry | None" = None
_models_yaml_path: str = "models.yaml"


def configure(
    model_registry: ModelRegistry,
    catalog_registry: "CatalogRegistry | None" = None,
    models_yaml_path: str = "models.yaml",
) -> None:
    """Configure the Models routes.

    Args:
        model_registry: The model registry to manage
        catalog_registry: Optional catalog registry for cross-references
        models_yaml_path: Path to models YAML file
    """
    global _model_registry, _catalog_registry, _models_yaml_path
    _model_registry = model_registry
    _catalog_registry = catalog_registry
    _models_yaml_path = models_yaml_path


def _get_model_registry() -> ModelRegistry:
    """Get the model registry, raising if not configured."""
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="Model configuration not initialized")
    return _model_registry


def _model_to_api(model: Model) -> BusinessModelModel:
    """Convert Model dataclass to Pydantic model."""
    ownership = None
    if model.ownership and not model.ownership.is_empty():
        ownership = ModelOwnershipModel(
            methodology_owner=model.ownership.methodology_owner,
            business_steward=model.ownership.business_steward,
            support_channel=model.ownership.support_channel,
        )

    appears_in = [
        MonikerLinkModel(
            moniker_pattern=link.moniker_pattern,
            column_name=link.column_name,
            notes=link.notes,
        )
        for link in model.appears_in
    ]

    return BusinessModelModel(
        path=model.path,
        display_name=model.display_name,
        description=model.description,
        formula=model.formula,
        unit=model.unit,
        data_type=model.data_type,
        ownership=ownership,
        documentation_url=model.documentation_url,
        methodology_url=model.methodology_url,
        appears_in=appears_in,
        semantic_tags=list(model.semantic_tags),
        tags=list(model.tags),
    )


def _model_to_summary(model: Model) -> ModelSummaryModel:
    """Convert Model to summary model."""
    return ModelSummaryModel(
        path=model.path,
        display_name=model.display_name,
        description=model.description,
        unit=model.unit,
        formula=model.formula,
        documentation_url=model.documentation_url,
    )


def _api_to_model(path: str, request: CreateModelRequest | UpdateModelRequest, existing: Model | None = None) -> Model:
    """Convert API request to Model dataclass."""
    # Parse ownership
    ownership = ModelOwnership()
    if request.ownership:
        ownership = ModelOwnership(
            methodology_owner=request.ownership.methodology_owner,
            business_steward=request.ownership.business_steward,
            support_channel=request.ownership.support_channel,
        )
    elif existing:
        ownership = existing.ownership

    # Parse appears_in
    appears_in: tuple[MonikerLink, ...] = ()
    if request.appears_in is not None:
        appears_in = tuple(
            MonikerLink(
                moniker_pattern=link.moniker_pattern,
                column_name=link.column_name,
                notes=link.notes,
            )
            for link in request.appears_in
        )
    elif existing:
        appears_in = existing.appears_in

    # For updates, use existing values as defaults
    if existing and isinstance(request, UpdateModelRequest):
        return Model(
            path=path,
            display_name=request.display_name if request.display_name is not None else existing.display_name,
            description=request.description if request.description is not None else existing.description,
            formula=request.formula if request.formula is not None else existing.formula,
            unit=request.unit if request.unit is not None else existing.unit,
            data_type=request.data_type if request.data_type is not None else existing.data_type,
            ownership=ownership,
            documentation_url=request.documentation_url if request.documentation_url is not None else existing.documentation_url,
            methodology_url=request.methodology_url if request.methodology_url is not None else existing.methodology_url,
            appears_in=appears_in,
            semantic_tags=tuple(request.semantic_tags) if request.semantic_tags is not None else existing.semantic_tags,
            tags=frozenset(request.tags) if request.tags is not None else existing.tags,
        )

    # For creates
    return Model(
        path=path,
        display_name=request.display_name if hasattr(request, "display_name") else "",
        description=request.description if hasattr(request, "description") else "",
        formula=request.formula if hasattr(request, "formula") else None,
        unit=request.unit if hasattr(request, "unit") else None,
        data_type=request.data_type if hasattr(request, "data_type") else "float",
        ownership=ownership,
        documentation_url=request.documentation_url if hasattr(request, "documentation_url") else None,
        methodology_url=request.methodology_url if hasattr(request, "methodology_url") else None,
        appears_in=appears_in,
        semantic_tags=tuple(request.semantic_tags) if request.semantic_tags else (),
        tags=frozenset(request.tags) if request.tags else frozenset(),
    )


def _build_tree_nodes(registry: ModelRegistry, parent: str = "") -> list[ModelTreeNode]:
    """Recursively build tree nodes."""
    children_paths = registry.children_paths(parent)
    nodes = []

    for path in children_paths:
        model = registry.get(path)
        if not model:
            continue

        child_nodes = _build_tree_nodes(registry, path)

        nodes.append(ModelTreeNode(
            path=model.path,
            name=model.name,
            display_name=model.display_name,
            children=child_nodes,
            is_container=model.is_container(),
            has_children=len(child_nodes) > 0,
        ))

    return nodes


# =============================================================================
# UI Endpoint
# =============================================================================

@router.get("/ui", response_class=HTMLResponse)
async def models_ui():
    """Serve the Models Browser UI HTML."""
    static_dir = Path(__file__).parent / "static"
    index_path = static_dir / "index.html"

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Models UI not found")

    return HTMLResponse(content=index_path.read_text(encoding="utf-8"), status_code=200)


# =============================================================================
# Model CRUD Endpoints
# =============================================================================

@router.get("", response_model=ModelListResponse)
async def list_models():
    """
    List all business models.

    Returns all registered models with their metadata.
    """
    registry = _get_model_registry()
    models = registry.all_models()

    return ModelListResponse(
        models=[_model_to_api(m) for m in models],
        count=len(models),
    )


@router.get("/tree", response_model=ModelTreeResponse)
async def get_model_tree():
    """
    Get the model hierarchy as a tree structure.

    Returns nested tree suitable for UI navigation.
    """
    registry = _get_model_registry()
    tree = _build_tree_nodes(registry)

    return ModelTreeResponse(
        tree=tree,
        total_count=registry.count(),
    )


@router.get("/for-moniker/{path:path}", response_model=ModelsForMonikerResponse)
async def get_models_for_moniker(path: str):
    """
    Get all models that appear in a given moniker.

    Uses pattern matching on model appears_in patterns.
    """
    registry = _get_model_registry()
    models = registry.models_for_moniker(path)

    return ModelsForMonikerResponse(
        moniker_path=path,
        models=[_model_to_summary(m) for m in models],
        count=len(models),
    )


@router.get("/{path:path}/monikers")
async def get_monikers_for_model(path: str):
    """
    Get all moniker patterns where a model appears.

    Returns the appears_in patterns for a model.
    """
    registry = _get_model_registry()

    model = registry.get(path)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model not found: {path}")

    patterns = registry.monikers_for_model(path)

    return {
        "model_path": path,
        "moniker_patterns": patterns,
        "count": len(patterns),
    }


@router.get("/{path:path}", response_model=ModelWithMonikersResponse)
async def get_model(path: str):
    """
    Get a single model by path.

    Returns the model details along with linked moniker patterns.
    """
    registry = _get_model_registry()

    model = registry.get(path)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model not found: {path}")

    patterns = registry.monikers_for_model(path)

    return ModelWithMonikersResponse(
        model=_model_to_api(model),
        moniker_patterns=patterns,
        moniker_count=len(patterns),
    )


@router.post("", response_model=BusinessModelModel, status_code=201)
async def create_model(request: CreateModelRequest):
    """
    Create a new business model.

    The model path must be unique.
    """
    registry = _get_model_registry()

    # Check if model already exists
    if registry.exists(request.path):
        raise HTTPException(status_code=409, detail=f"Model already exists: {request.path}")

    # Create the model
    model = _api_to_model(request.path, request)

    registry.register(model)
    logger.info(f"Created model: {request.path}")

    return _model_to_api(model)


@router.put("/{path:path}", response_model=BusinessModelModel)
async def update_model(path: str, request: UpdateModelRequest):
    """
    Update an existing business model.

    Only provided fields are updated; others retain their current values.
    """
    registry = _get_model_registry()

    # Get existing model
    existing = registry.get(path)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Model not found: {path}")

    # Build updated model
    model = _api_to_model(path, request, existing)

    registry.register_or_update(model)
    logger.info(f"Updated model: {path}")

    return _model_to_api(model)


@router.delete("/{path:path}")
async def delete_model(path: str):
    """
    Delete a business model.
    """
    registry = _get_model_registry()

    if not registry.exists(path):
        raise HTTPException(status_code=404, detail=f"Model not found: {path}")

    # Check for children
    children = registry.children_paths(path)
    if children:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete model with children. Delete children first: {children}"
        )

    registry.delete(path)
    logger.info(f"Deleted model: {path}")

    return {"success": True, "message": f"Model '{path}' deleted"}


# =============================================================================
# Save/Reload Endpoints
# =============================================================================

@router.post("/save", response_model=SaveResponse)
async def save_models():
    """
    Save all models to YAML file.

    Persists the current model configuration to the configured YAML file.
    """
    registry = _get_model_registry()

    output_path = Path(_models_yaml_path)
    try:
        save_models_to_yaml(registry, output_path)
        count = registry.count()

        logger.info(f"Saved {count} models to {output_path}")

        return SaveResponse(
            success=True,
            message=f"Saved {count} models to {output_path}",
            file_path=str(output_path.absolute()),
        )
    except Exception as e:
        logger.error(f"Failed to save models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


@router.post("/reload", response_model=ReloadResponse)
async def reload_models():
    """
    Reload models from YAML file.

    Replaces current configuration with contents of the YAML file.
    """
    registry = _get_model_registry()
    source_path = Path(_models_yaml_path)

    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Models file not found: {source_path}")

    try:
        # Clear and reload
        registry.clear()
        models = load_models_from_yaml(source_path, registry)

        logger.info(f"Reloaded {len(models)} models from {source_path}")

        return ReloadResponse(
            success=True,
            message=f"Reloaded {len(models)} models from {source_path}",
            models_loaded=len(models),
        )
    except Exception as e:
        logger.error(f"Failed to reload models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reload: {str(e)}")
