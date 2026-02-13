"""FastAPI routes for Moniker Request & Approval workflow."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from .loader import save_requests_to_yaml, load_requests_from_yaml
from .models import (
    CommentBody,
    MonikerRequestModel,
    RequestListResponse,
    RequesterResponseModel,
    ReviewActionBody,
    ReviewCommentModel,
    SubmitRequestBody,
    SubmitRequestResponse,
)
from .registry import RequestRegistry
from .types import (
    DomainLevel,
    MonikerRequest,
    RequestStatus,
    RequesterInfo,
    ReviewComment,
)

if TYPE_CHECKING:
    from ..catalog.registry import CatalogRegistry
    from ..domains.registry import DomainRegistry

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/requests", tags=["Requests"])

# Configuration - set during app startup
_request_registry: RequestRegistry | None = None
_catalog_registry: "CatalogRegistry | None" = None
_domain_registry: "DomainRegistry | None" = None
_yaml_path: str | None = None


def configure(
    request_registry: RequestRegistry,
    catalog_registry: "CatalogRegistry",
    domain_registry: "DomainRegistry | None" = None,
    yaml_path: str | None = None,
) -> None:
    """Configure the request routes with registries."""
    global _request_registry, _catalog_registry, _domain_registry, _yaml_path
    _request_registry = request_registry
    _catalog_registry = catalog_registry
    _domain_registry = domain_registry
    _yaml_path = yaml_path


def _get_registries():
    """Get registries, raising if not configured."""
    if _request_registry is None or _catalog_registry is None:
        raise HTTPException(status_code=503, detail="Request module not initialized")
    return _request_registry, _catalog_registry


def _auto_save():
    """Auto-save requests to YAML after mutations."""
    if _yaml_path and _request_registry:
        try:
            save_requests_to_yaml(_yaml_path, _request_registry)
        except Exception as e:
            logger.error(f"Auto-save failed: {e}")


def _request_to_model(req: MonikerRequest) -> MonikerRequestModel:
    """Convert a MonikerRequest to Pydantic response model."""
    requester = None
    if req.requester:
        requester = RequesterResponseModel(
            name=req.requester.name,
            email=req.requester.email,
            team=req.requester.team,
            app_id=req.requester.app_id,
        )

    comments = [
        ReviewCommentModel(
            timestamp=c.timestamp,
            author=c.author,
            author_name=c.author_name,
            content=c.content,
            action=c.action,
        )
        for c in req.comments
    ]

    return MonikerRequestModel(
        request_id=req.request_id,
        path=req.path,
        display_name=req.display_name,
        description=req.description,
        requester=requester,
        justification=req.justification,
        adop=req.adop,
        ads=req.ads,
        adal=req.adal,
        adop_name=req.adop_name,
        ads_name=req.ads_name,
        adal_name=req.adal_name,
        source_binding_type=req.source_binding_type,
        source_binding_config=req.source_binding_config,
        tags=req.tags,
        status=req.status.value,
        domain_level=req.domain_level.value,
        comments=comments,
        reviewed_by=req.reviewed_by,
        reviewed_at=req.reviewed_at,
        rejection_reason=req.rejection_reason,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


# =============================================================================
# UI Endpoint
# =============================================================================

@router.get("/ui", response_class=HTMLResponse)
async def review_queue_ui():
    """Serve the Review Queue UI HTML."""
    static_dir = Path(__file__).parent / "static"
    index_path = static_dir / "index.html"

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Review Queue UI not found")

    return HTMLResponse(content=index_path.read_text(encoding="utf-8"), status_code=200)


@router.get("/api-guide", response_class=HTMLResponse)
async def api_guide():
    """Serve the developer API guide."""
    static_dir = Path(__file__).parent / "static"
    guide_path = static_dir / "api_guide.html"

    if not guide_path.exists():
        raise HTTPException(status_code=404, detail="API guide not found")

    return HTMLResponse(content=guide_path.read_text(encoding="utf-8"), status_code=200)


# =============================================================================
# Submit Request
# =============================================================================

@router.post("", response_model=SubmitRequestResponse)
async def submit_request(body: SubmitRequestBody):
    """
    Submit a new moniker request.

    Domain guard:
    - Single-segment paths are flagged as TOP_LEVEL for elevated review.
    - Multi-segment paths require the top-level domain to already exist.
    - Duplicate paths (already in catalog or pending) are rejected.
    """
    req_registry, cat_registry = _get_registries()

    path = body.path.strip().strip("/")
    if not path:
        raise HTTPException(status_code=400, detail="Path cannot be empty")

    # Check if path already exists in catalog
    if cat_registry.exists(path):
        raise HTTPException(status_code=409, detail=f"Path already exists in catalog: {path}")

    # Check for duplicate pending request
    if req_registry.path_has_pending_request(path):
        raise HTTPException(status_code=409, detail=f"A pending request already exists for path: {path}")

    # Domain guard: determine level and validate parent
    segments = path.split("/")
    # Also consider dot-separated top-level domains
    top_level = segments[0].split(".")[0] if "." in segments[0] else segments[0]

    if len(segments) == 1 and "." not in path:
        # Single segment, no dots = top-level domain request
        domain_level = DomainLevel.TOP_LEVEL
    else:
        domain_level = DomainLevel.SUB_PATH
        # Verify parent path exists
        parent_path = segments[0] if len(segments) > 1 else path.rsplit(".", 1)[0]
        if not cat_registry.exists(parent_path):
            # Try the full first segment (could be dot-notated)
            if not cat_registry.exists(segments[0]):
                raise HTTPException(
                    status_code=400,
                    detail=f"Top-level domain '{segments[0]}' does not exist. Create it first.",
                )

    # Create the catalog node with PENDING_REVIEW status
    from ..catalog.types import CatalogNode, NodeStatus, Ownership

    ownership = Ownership(
        adop=body.adop,
        ads=body.ads,
        adal=body.adal,
        adop_name=body.adop_name,
        ads_name=body.ads_name,
        adal_name=body.adal_name,
    )

    node = CatalogNode(
        path=path,
        display_name=body.display_name,
        description=body.description,
        ownership=ownership,
        tags=frozenset(body.tags),
        status=NodeStatus.PENDING_REVIEW,
    )
    cat_registry.register(node)

    # Create the request
    requester = RequesterInfo(
        name=body.requester.name,
        email=body.requester.email,
        team=body.requester.team,
        app_id=body.requester.app_id,
    )

    request = MonikerRequest(
        request_id="",  # will be assigned by registry
        path=path,
        display_name=body.display_name,
        description=body.description,
        requester=requester,
        justification=body.justification,
        adop=body.adop,
        ads=body.ads,
        adal=body.adal,
        adop_name=body.adop_name,
        ads_name=body.ads_name,
        adal_name=body.adal_name,
        source_binding_type=body.source_binding_type,
        source_binding_config=body.source_binding_config,
        tags=body.tags,
        status=RequestStatus.PENDING_REVIEW,
        domain_level=domain_level,
    )

    request = req_registry.submit(request)
    _auto_save()

    level_msg = " (TOP-LEVEL domain - requires elevated review)" if domain_level == DomainLevel.TOP_LEVEL else ""
    return SubmitRequestResponse(
        request_id=request.request_id,
        path=request.path,
        status=request.status.value,
        message=f"Request submitted for review{level_msg}",
    )


# =============================================================================
# List / Get Requests
# =============================================================================

@router.get("", response_model=RequestListResponse)
async def list_requests(status: str | None = None):
    """List requests, optionally filtered by status."""
    req_registry, _ = _get_registries()

    if status:
        try:
            filter_status = RequestStatus(status)
            requests = req_registry.find_by_status(filter_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    else:
        requests = req_registry.all_requests()

    # Sort by created_at descending
    requests.sort(key=lambda r: r.created_at or "", reverse=True)

    return RequestListResponse(
        requests=[_request_to_model(r) for r in requests],
        total=len(requests),
        by_status=req_registry.count_by_status(),
    )


@router.get("/{request_id}", response_model=MonikerRequestModel)
async def get_request(request_id: str):
    """Get a single request by ID."""
    req_registry, _ = _get_registries()

    request = req_registry.get(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")

    return _request_to_model(request)


# =============================================================================
# Approve / Reject / Comment
# =============================================================================

@router.post("/{request_id}/approve", response_model=MonikerRequestModel)
async def approve_request(request_id: str, body: ReviewActionBody):
    """
    Approve a request.

    Updates the request status to APPROVED and the catalog node to ACTIVE.
    """
    req_registry, cat_registry = _get_registries()

    request = req_registry.get(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")

    if request.status != RequestStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Request is not pending review (current status: {request.status.value})",
        )

    now = datetime.now(timezone.utc).isoformat()

    # Update request status
    req_registry.update_status(request_id, RequestStatus.APPROVED, actor=body.actor)

    # Add approval comment
    comment = ReviewComment(
        timestamp=now,
        author=body.actor,
        author_name=body.actor_name,
        content=body.reason or "Approved",
        action="approve",
    )
    req_registry.add_comment(request_id, comment)

    # Update catalog node: PENDING_REVIEW -> ACTIVE
    from ..catalog.types import NodeStatus
    cat_registry.update_status(request.path, NodeStatus.ACTIVE, actor=body.actor)

    # Add audit entry
    from ..catalog.types import AuditEntry
    cat_registry.add_audit_entry(AuditEntry(
        timestamp=now,
        path=request.path,
        action="request_approved",
        actor=body.actor,
        details=f"Request {request_id} approved",
    ))

    _auto_save()

    # Re-fetch for updated state
    updated = req_registry.get(request_id)
    return _request_to_model(updated)


@router.post("/{request_id}/reject", response_model=MonikerRequestModel)
async def reject_request(request_id: str, body: ReviewActionBody):
    """
    Reject a request.

    Updates the request status to REJECTED and the catalog node back to DRAFT.
    """
    req_registry, cat_registry = _get_registries()

    request = req_registry.get(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")

    if request.status != RequestStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Request is not pending review (current status: {request.status.value})",
        )

    now = datetime.now(timezone.utc).isoformat()

    # Update request status
    req_registry.update_status(
        request_id, RequestStatus.REJECTED,
        actor=body.actor,
        reason=body.reason,
    )

    # Add rejection comment
    comment = ReviewComment(
        timestamp=now,
        author=body.actor,
        author_name=body.actor_name,
        content=body.reason or "Rejected",
        action="reject",
    )
    req_registry.add_comment(request_id, comment)

    # Update catalog node: PENDING_REVIEW -> DRAFT
    from ..catalog.types import NodeStatus
    cat_registry.update_status(request.path, NodeStatus.DRAFT, actor=body.actor)

    # Add audit entry
    from ..catalog.types import AuditEntry
    cat_registry.add_audit_entry(AuditEntry(
        timestamp=now,
        path=request.path,
        action="request_rejected",
        actor=body.actor,
        details=f"Request {request_id} rejected: {body.reason}",
    ))

    _auto_save()

    updated = req_registry.get(request_id)
    return _request_to_model(updated)


@router.post("/{request_id}/comment", response_model=MonikerRequestModel)
async def add_comment(request_id: str, body: CommentBody):
    """Add a review comment to a request."""
    req_registry, _ = _get_registries()

    request = req_registry.get(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")

    now = datetime.now(timezone.utc).isoformat()
    comment = ReviewComment(
        timestamp=now,
        author=body.author,
        author_name=body.author_name,
        content=body.content,
        action="comment",
    )

    req_registry.add_comment(request_id, comment)
    _auto_save()

    updated = req_registry.get(request_id)
    return _request_to_model(updated)


# =============================================================================
# Save / Reload
# =============================================================================

@router.post("/save")
async def save_requests():
    """Manually save requests to YAML."""
    req_registry, _ = _get_registries()

    if not _yaml_path:
        raise HTTPException(status_code=400, detail="No YAML path configured for requests")

    count = save_requests_to_yaml(_yaml_path, req_registry)
    return {"success": True, "count": count, "message": f"Saved {count} requests"}


@router.post("/reload")
async def reload_requests():
    """Reload requests from YAML."""
    req_registry, _ = _get_registries()

    if not _yaml_path:
        raise HTTPException(status_code=400, detail="No YAML path configured for requests")

    if not Path(_yaml_path).exists():
        raise HTTPException(status_code=404, detail=f"Requests file not found: {_yaml_path}")

    req_registry.clear()
    loaded = load_requests_from_yaml(_yaml_path, req_registry)
    return {"success": True, "count": len(loaded), "message": f"Reloaded {len(loaded)} requests"}
