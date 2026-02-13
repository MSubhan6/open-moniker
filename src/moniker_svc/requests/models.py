"""Pydantic models for Request API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Request Body Models
# =============================================================================

class RequesterModel(BaseModel):
    """Requester information."""
    name: str
    email: str
    team: str = ""
    app_id: str = ""


class SubmitRequestBody(BaseModel):
    """Body for submitting a new moniker request."""
    path: str
    display_name: str = ""
    description: str = ""
    justification: str = ""

    # Requester
    requester: RequesterModel

    # Proposed ownership
    adop: str | None = None
    ads: str | None = None
    adal: str | None = None
    adop_name: str | None = None
    ads_name: str | None = None
    adal_name: str | None = None

    # Source binding proposal
    source_binding_type: str | None = None
    source_binding_config: dict[str, Any] = Field(default_factory=dict)

    # Tags
    tags: list[str] = Field(default_factory=list)


class ReviewActionBody(BaseModel):
    """Body for approve/reject actions."""
    actor: str
    actor_name: str = ""
    reason: str = ""


class CommentBody(BaseModel):
    """Body for adding a comment."""
    author: str
    author_name: str = ""
    content: str


# =============================================================================
# Response Models
# =============================================================================

class ReviewCommentModel(BaseModel):
    """A review comment."""
    timestamp: str
    author: str
    author_name: str = ""
    content: str = ""
    action: str = "comment"


class RequesterResponseModel(BaseModel):
    """Requester info in response."""
    name: str = ""
    email: str = ""
    team: str = ""
    app_id: str = ""


class MonikerRequestModel(BaseModel):
    """Full representation of a moniker request."""
    request_id: str
    path: str
    display_name: str = ""
    description: str = ""
    requester: RequesterResponseModel | None = None
    justification: str = ""

    # Proposed ownership
    adop: str | None = None
    ads: str | None = None
    adal: str | None = None
    adop_name: str | None = None
    ads_name: str | None = None
    adal_name: str | None = None

    # Source binding
    source_binding_type: str | None = None
    source_binding_config: dict[str, Any] = Field(default_factory=dict)

    tags: list[str] = Field(default_factory=list)

    # Workflow
    status: str = "pending_review"
    domain_level: str = "sub_path"
    comments: list[ReviewCommentModel] = Field(default_factory=list)
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    rejection_reason: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class RequestListResponse(BaseModel):
    """Response for listing requests."""
    requests: list[MonikerRequestModel]
    total: int
    by_status: dict[str, int] = Field(default_factory=dict)


class SubmitRequestResponse(BaseModel):
    """Response after submitting a request."""
    request_id: str
    path: str
    status: str
    message: str = ""
