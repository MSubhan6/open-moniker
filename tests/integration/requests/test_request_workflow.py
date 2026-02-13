"""End-to-end tests for the moniker request & approval workflow."""

import pytest

from moniker_svc.catalog.registry import CatalogRegistry
from moniker_svc.catalog.types import CatalogNode, NodeStatus, Ownership
from moniker_svc.requests.registry import RequestRegistry
from moniker_svc.requests.types import (
    DomainLevel,
    MonikerRequest,
    RequestStatus,
    RequesterInfo,
    ReviewComment,
)


@pytest.fixture
def catalog():
    """Catalog with a top-level domain pre-registered."""
    registry = CatalogRegistry()
    registry.register(CatalogNode(
        path="market-data",
        display_name="Market Data",
        ownership=Ownership(
            accountable_owner="jane@firm.com",
            data_specialist="team@firm.com",
            support_channel="#market-data",
        ),
    ))
    registry.register(CatalogNode(
        path="analytics",
        display_name="Analytics",
    ))
    return registry


@pytest.fixture
def req_registry():
    """Empty request registry."""
    return RequestRegistry()


def _make_requester():
    return RequesterInfo(
        name="Alice Smith",
        email="alice@firm.com",
        team="Data Engineering",
        app_id="data-portal",
    )


class TestSubmitRequest:
    """Tests for request submission."""

    def test_submit_under_existing_domain(self, catalog, req_registry):
        """Submitting under an existing domain should create a PENDING_REVIEW request."""
        request = MonikerRequest(
            request_id="",
            path="market-data/prices",
            display_name="Market Prices",
            requester=_make_requester(),
            justification="Need price data for analytics",
            adop="jane@firm.com",
            adop_name="Jane Doe",
            domain_level=DomainLevel.SUB_PATH,
        )

        result = req_registry.submit(request)

        assert result.request_id.startswith("REQ-")
        assert result.status == RequestStatus.PENDING_REVIEW
        assert result.created_at is not None
        assert result.path == "market-data/prices"
        assert result.adop_name == "Jane Doe"

    def test_top_level_detection(self, req_registry):
        """Single-segment paths should be flagged as TOP_LEVEL."""
        request = MonikerRequest(
            request_id="",
            path="new-domain",
            requester=_make_requester(),
            domain_level=DomainLevel.TOP_LEVEL,
        )

        result = req_registry.submit(request)
        assert result.domain_level == DomainLevel.TOP_LEVEL

    def test_duplicate_path_rejection(self, req_registry):
        """Should detect pending request for same path."""
        req_registry.submit(MonikerRequest(
            request_id="",
            path="market-data/prices",
            requester=_make_requester(),
        ))

        assert req_registry.path_has_pending_request("market-data/prices") is True
        assert req_registry.path_has_pending_request("market-data/other") is False


class TestApproveReject:
    """Tests for approval and rejection flows."""

    def test_approve_updates_request_status(self, req_registry):
        """Approving should move request to APPROVED."""
        req = req_registry.submit(MonikerRequest(
            request_id="",
            path="market-data/bonds",
            requester=_make_requester(),
        ))

        result = req_registry.update_status(req.request_id, RequestStatus.APPROVED, actor="reviewer@firm.com")

        assert result is not None
        assert result.status == RequestStatus.APPROVED
        assert result.reviewed_by == "reviewer@firm.com"

    def test_approve_with_catalog_integration(self, catalog, req_registry):
        """Full approval: request APPROVED, catalog node ACTIVE."""
        # Register a pending_review node in catalog (as the submit endpoint does)
        catalog.register(CatalogNode(
            path="market-data/bonds",
            display_name="Bonds",
            status=NodeStatus.PENDING_REVIEW,
        ))

        req = req_registry.submit(MonikerRequest(
            request_id="",
            path="market-data/bonds",
            requester=_make_requester(),
        ))

        # Approve the request
        req_registry.update_status(req.request_id, RequestStatus.APPROVED, actor="reviewer@firm.com")
        # Update catalog node (as the route handler does)
        catalog.update_status("market-data/bonds", NodeStatus.ACTIVE, actor="reviewer@firm.com")

        # Verify
        updated_req = req_registry.get(req.request_id)
        assert updated_req.status == RequestStatus.APPROVED

        node = catalog.get("market-data/bonds")
        assert node.status == NodeStatus.ACTIVE

    def test_reject_updates_request_and_node(self, catalog, req_registry):
        """Rejecting should set request REJECTED and node DRAFT."""
        catalog.register(CatalogNode(
            path="market-data/rejected-path",
            status=NodeStatus.PENDING_REVIEW,
        ))

        req = req_registry.submit(MonikerRequest(
            request_id="",
            path="market-data/rejected-path",
            requester=_make_requester(),
        ))

        req_registry.update_status(
            req.request_id, RequestStatus.REJECTED,
            actor="reviewer@firm.com",
            reason="Insufficient justification",
        )
        catalog.update_status("market-data/rejected-path", NodeStatus.DRAFT, actor="reviewer@firm.com")

        updated_req = req_registry.get(req.request_id)
        assert updated_req.status == RequestStatus.REJECTED
        assert updated_req.rejection_reason == "Insufficient justification"

        node = catalog.get("market-data/rejected-path")
        assert node.status == NodeStatus.DRAFT


class TestComments:
    """Tests for the review comment thread."""

    def test_comment_thread_ordering(self, req_registry):
        """Comments should maintain insertion order."""
        req = req_registry.submit(MonikerRequest(
            request_id="",
            path="test-path",
            requester=_make_requester(),
        ))

        c1 = ReviewComment(timestamp="2025-01-01T00:00:00Z", author="a@firm.com", content="First")
        c2 = ReviewComment(timestamp="2025-01-01T01:00:00Z", author="b@firm.com", content="Second")
        c3 = ReviewComment(timestamp="2025-01-01T02:00:00Z", author="a@firm.com", content="Third", action="approve")

        req_registry.add_comment(req.request_id, c1)
        req_registry.add_comment(req.request_id, c2)
        req_registry.add_comment(req.request_id, c3)

        updated = req_registry.get(req.request_id)
        assert len(updated.comments) == 3
        assert updated.comments[0].content == "First"
        assert updated.comments[1].content == "Second"
        assert updated.comments[2].content == "Third"
        assert updated.comments[2].action == "approve"


class TestCountsAndFiltering:
    """Tests for status counts and filtering."""

    def test_count_by_status(self, req_registry):
        """count_by_status should return accurate counts."""
        req_registry.submit(MonikerRequest(request_id="", path="a", requester=_make_requester()))
        req_registry.submit(MonikerRequest(request_id="", path="b", requester=_make_requester()))
        r3 = req_registry.submit(MonikerRequest(request_id="", path="c", requester=_make_requester()))
        req_registry.update_status(r3.request_id, RequestStatus.APPROVED)

        counts = req_registry.count_by_status()
        assert counts["pending_review"] == 2
        assert counts["approved"] == 1
        assert counts["total"] == 3

    def test_find_by_status(self, req_registry):
        """find_by_status should filter correctly."""
        req_registry.submit(MonikerRequest(request_id="", path="x", requester=_make_requester()))
        r2 = req_registry.submit(MonikerRequest(request_id="", path="y", requester=_make_requester()))
        req_registry.update_status(r2.request_id, RequestStatus.REJECTED, reason="No")

        pending = req_registry.find_by_status(RequestStatus.PENDING_REVIEW)
        rejected = req_registry.find_by_status(RequestStatus.REJECTED)

        assert len(pending) == 1
        assert pending[0].path == "x"
        assert len(rejected) == 1
        assert rejected[0].path == "y"


class TestOwnershipNameFields:
    """Tests that human name fields work through the ownership chain."""

    def test_ownership_name_fields_default_none(self):
        """New name fields should default to None for backwards compatibility."""
        o = Ownership(adop="jane@firm.com", ads="bob@firm.com")
        assert o.adop_name is None
        assert o.ads_name is None
        assert o.adal_name is None

    def test_ownership_merge_inherits_names(self):
        """merge_with_parent should inherit name fields independently."""
        parent = Ownership(
            adop="jane@firm.com",
            adop_name="Jane Doe",
            ads="bob@firm.com",
            ads_name="Bob Smith",
        )
        child = Ownership(
            adop="alice@firm.com",
            adop_name="Alice Jones",
            # ads and ads_name not set - should inherit
        )

        merged = child.merge_with_parent(parent)
        assert merged.adop == "alice@firm.com"
        assert merged.adop_name == "Alice Jones"
        assert merged.ads == "bob@firm.com"
        assert merged.ads_name == "Bob Smith"

    def test_resolved_ownership_includes_names(self):
        """ResolvedOwnership governance_roles should include name key."""
        from moniker_svc.catalog.types import ResolvedOwnership

        resolved = ResolvedOwnership(
            adop="jane@firm.com",
            adop_source="market-data",
            adop_name="Jane Doe",
            adop_name_source="market-data",
        )

        roles = resolved.governance_roles
        assert roles["adop"]["name"] == "Jane Doe"
        assert roles["adop"]["value"] == "jane@firm.com"
