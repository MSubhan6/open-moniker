"""Request workflow types - domain types for moniker request and approval."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RequestStatus(str, Enum):
    """Status of a moniker request through the approval workflow."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"


class DomainLevel(str, Enum):
    """Whether the requested path is a top-level domain or sub-path."""
    TOP_LEVEL = "top_level"
    SUB_PATH = "sub_path"


@dataclass(frozen=True, slots=True)
class RequesterInfo:
    """Information about who submitted the request."""
    name: str
    email: str
    team: str = ""
    app_id: str = ""


@dataclass(frozen=True, slots=True)
class ReviewComment:
    """A comment on a moniker request during the review process."""
    timestamp: str          # ISO format
    author: str             # System identifier (email)
    author_name: str = ""   # Human-readable name
    content: str = ""
    action: str = "comment"  # comment | approve | reject | request_changes


@dataclass(slots=True)
class MonikerRequest:
    """
    A request to create a new moniker, tracking the full approval workflow.

    This is the workflow audit trail. The actual catalog node is the source
    of truth for what paths exist.
    """
    request_id: str
    path: str
    display_name: str = ""
    description: str = ""

    # Requester
    requester: RequesterInfo | None = None
    justification: str = ""

    # Proposed ownership
    adop: str | None = None
    ads: str | None = None
    adal: str | None = None
    adop_name: str | None = None
    ads_name: str | None = None
    adal_name: str | None = None

    # Source binding proposal
    source_binding_type: str | None = None
    source_binding_config: dict = field(default_factory=dict)

    # Tags
    tags: list[str] = field(default_factory=list)

    # Workflow state
    status: RequestStatus = RequestStatus.PENDING_REVIEW
    domain_level: DomainLevel = DomainLevel.SUB_PATH

    # Review
    comments: list[ReviewComment] = field(default_factory=list)
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    rejection_reason: str | None = None

    # Timestamps
    created_at: str | None = None
    updated_at: str | None = None
