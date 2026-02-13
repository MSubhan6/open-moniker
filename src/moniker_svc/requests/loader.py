"""Request persistence - YAML round-trip for moniker requests."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .registry import RequestRegistry
from .types import (
    DomainLevel,
    MonikerRequest,
    RequestStatus,
    RequesterInfo,
    ReviewComment,
)

logger = logging.getLogger(__name__)


def load_requests_from_yaml(
    path: str | Path,
    registry: RequestRegistry,
) -> list[MonikerRequest]:
    """Load requests from a YAML file into the registry."""
    path = Path(path)
    if not path.exists():
        logger.info(f"Requests file not found: {path}")
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "requests" not in data:
        return []

    loaded = []
    for req_data in data["requests"]:
        request = _parse_request(req_data)
        registry.submit(request)
        loaded.append(request)

    logger.info(f"Loaded {len(loaded)} requests from {path}")
    return loaded


def save_requests_to_yaml(
    path: str | Path,
    registry: RequestRegistry,
) -> int:
    """Save all requests from the registry to a YAML file."""
    path = Path(path)
    requests = registry.all_requests()

    data: dict[str, Any] = {
        "requests": [_serialize_request(r) for r in requests],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"Saved {len(requests)} requests to {path}")
    return len(requests)


def _parse_request(data: dict[str, Any]) -> MonikerRequest:
    """Parse a single request from a dictionary."""
    requester = None
    if "requester" in data:
        r = data["requester"]
        requester = RequesterInfo(
            name=r.get("name", ""),
            email=r.get("email", ""),
            team=r.get("team", ""),
            app_id=r.get("app_id", ""),
        )

    comments = []
    for c in data.get("comments", []):
        comments.append(ReviewComment(
            timestamp=c.get("timestamp", ""),
            author=c.get("author", ""),
            author_name=c.get("author_name", ""),
            content=c.get("content", ""),
            action=c.get("action", "comment"),
        ))

    status = RequestStatus.PENDING_REVIEW
    if "status" in data:
        try:
            status = RequestStatus(data["status"])
        except ValueError:
            pass

    domain_level = DomainLevel.SUB_PATH
    if "domain_level" in data:
        try:
            domain_level = DomainLevel(data["domain_level"])
        except ValueError:
            pass

    return MonikerRequest(
        request_id=data.get("request_id", ""),
        path=data.get("path", ""),
        display_name=data.get("display_name", ""),
        description=data.get("description", ""),
        requester=requester,
        justification=data.get("justification", ""),
        adop=data.get("adop"),
        ads=data.get("ads"),
        adal=data.get("adal"),
        adop_name=data.get("adop_name"),
        ads_name=data.get("ads_name"),
        adal_name=data.get("adal_name"),
        source_binding_type=data.get("source_binding_type"),
        source_binding_config=data.get("source_binding_config", {}),
        tags=data.get("tags", []),
        status=status,
        domain_level=domain_level,
        comments=comments,
        reviewed_by=data.get("reviewed_by"),
        reviewed_at=data.get("reviewed_at"),
        rejection_reason=data.get("rejection_reason"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def _serialize_request(req: MonikerRequest) -> dict[str, Any]:
    """Serialize a request to a dictionary."""
    data: dict[str, Any] = {
        "request_id": req.request_id,
        "path": req.path,
        "display_name": req.display_name,
        "description": req.description,
        "justification": req.justification,
        "status": req.status.value,
        "domain_level": req.domain_level.value,
        "created_at": req.created_at,
        "updated_at": req.updated_at,
    }

    if req.requester:
        data["requester"] = {
            "name": req.requester.name,
            "email": req.requester.email,
            "team": req.requester.team,
            "app_id": req.requester.app_id,
        }

    if req.adop:
        data["adop"] = req.adop
    if req.ads:
        data["ads"] = req.ads
    if req.adal:
        data["adal"] = req.adal
    if req.adop_name:
        data["adop_name"] = req.adop_name
    if req.ads_name:
        data["ads_name"] = req.ads_name
    if req.adal_name:
        data["adal_name"] = req.adal_name

    if req.source_binding_type:
        data["source_binding_type"] = req.source_binding_type
    if req.source_binding_config:
        data["source_binding_config"] = req.source_binding_config

    if req.tags:
        data["tags"] = req.tags

    if req.comments:
        data["comments"] = [
            {
                "timestamp": c.timestamp,
                "author": c.author,
                "author_name": c.author_name,
                "content": c.content,
                "action": c.action,
            }
            for c in req.comments
        ]

    if req.reviewed_by:
        data["reviewed_by"] = req.reviewed_by
    if req.reviewed_at:
        data["reviewed_at"] = req.reviewed_at
    if req.rejection_reason:
        data["rejection_reason"] = req.rejection_reason

    return data
