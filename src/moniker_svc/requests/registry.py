"""Request registry - thread-safe in-memory store for moniker requests."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from .types import DomainLevel, MonikerRequest, RequestStatus, ReviewComment

logger = logging.getLogger(__name__)


class RequestRegistry:
    """
    Thread-safe in-memory registry of moniker requests.

    Tracks the approval workflow for new moniker submissions.
    """

    def __init__(self) -> None:
        self._requests: dict[str, MonikerRequest] = {}
        self._path_index: dict[str, str] = {}  # path -> request_id
        self._lock = threading.RLock()
        self._counter = 0

    def _next_id(self) -> str:
        """Generate the next request ID."""
        self._counter += 1
        return f"REQ-{self._counter:04d}"

    def submit(self, request: MonikerRequest) -> MonikerRequest:
        """Submit a new request to the registry."""
        with self._lock:
            if not request.request_id:
                request.request_id = self._next_id()
            now = datetime.now(timezone.utc).isoformat()
            request.created_at = now
            request.updated_at = now
            self._requests[request.request_id] = request
            self._path_index[request.path] = request.request_id
            logger.info(f"Request submitted: {request.request_id} for path {request.path}")
            return request

    def get(self, request_id: str) -> MonikerRequest | None:
        """Get a request by ID."""
        with self._lock:
            return self._requests.get(request_id)

    def get_by_path(self, path: str) -> MonikerRequest | None:
        """Get the most recent request for a given path."""
        with self._lock:
            request_id = self._path_index.get(path)
            if request_id:
                return self._requests.get(request_id)
            return None

    def path_has_pending_request(self, path: str) -> bool:
        """Check if there's already a pending request for this path."""
        with self._lock:
            for req in self._requests.values():
                if req.path == path and req.status == RequestStatus.PENDING_REVIEW:
                    return True
            return False

    def find_by_status(self, status: RequestStatus) -> list[MonikerRequest]:
        """Get all requests with a given status."""
        with self._lock:
            return [r for r in self._requests.values() if r.status == status]

    def update_status(
        self,
        request_id: str,
        new_status: RequestStatus,
        actor: str | None = None,
        reason: str | None = None,
    ) -> MonikerRequest | None:
        """Update the status of a request."""
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                return None

            now = datetime.now(timezone.utc).isoformat()
            request.status = new_status
            request.updated_at = now

            if actor:
                request.reviewed_by = actor
                request.reviewed_at = now

            if reason and new_status == RequestStatus.REJECTED:
                request.rejection_reason = reason

            logger.info(f"Request {request_id} status -> {new_status.value}")
            return request

    def add_comment(
        self,
        request_id: str,
        comment: ReviewComment,
    ) -> MonikerRequest | None:
        """Add a review comment to a request."""
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                return None

            request.comments.append(comment)
            request.updated_at = datetime.now(timezone.utc).isoformat()
            return request

    def count_by_status(self) -> dict[str, int]:
        """Get counts of requests grouped by status."""
        with self._lock:
            counts: dict[str, int] = {}
            for req in self._requests.values():
                key = req.status.value
                counts[key] = counts.get(key, 0) + 1
            counts["total"] = len(self._requests)
            return counts

    def all_requests(self) -> list[MonikerRequest]:
        """Get all requests."""
        with self._lock:
            return list(self._requests.values())

    def clear(self) -> None:
        """Clear all requests."""
        with self._lock:
            self._requests.clear()
            self._path_index.clear()
            self._counter = 0
