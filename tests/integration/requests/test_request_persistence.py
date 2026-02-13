"""Tests for YAML round-trip persistence of moniker requests."""

import tempfile
from pathlib import Path

import pytest

from moniker_svc.requests.loader import load_requests_from_yaml, save_requests_to_yaml
from moniker_svc.requests.registry import RequestRegistry
from moniker_svc.requests.types import (
    DomainLevel,
    MonikerRequest,
    RequestStatus,
    RequesterInfo,
    ReviewComment,
)


def _make_requester():
    return RequesterInfo(
        name="Alice Smith",
        email="alice@firm.com",
        team="Data Engineering",
        app_id="data-portal",
    )


class TestYAMLRoundTrip:
    """Test saving to and loading from YAML."""

    def test_save_and_reload(self, tmp_path):
        """Requests should survive a save -> reload cycle."""
        yaml_path = tmp_path / "requests.yaml"

        # Create and populate registry
        registry = RequestRegistry()

        req1 = registry.submit(MonikerRequest(
            request_id="",
            path="market-data/bonds",
            display_name="Bond Prices",
            description="Government bond prices",
            requester=_make_requester(),
            justification="Need for risk analytics",
            adop="jane@firm.com",
            adop_name="Jane Doe",
            ads="bob@firm.com",
            ads_name="Bob Smith",
            adal="carol@firm.com",
            adal_name="Carol Williams",
            source_binding_type="snowflake",
            source_binding_config={"account": "firm.us-east-1", "warehouse": "WH"},
            tags=["bonds", "govies"],
            domain_level=DomainLevel.SUB_PATH,
        ))

        # Add a comment
        registry.add_comment(req1.request_id, ReviewComment(
            timestamp="2025-06-01T10:00:00Z",
            author="reviewer@firm.com",
            author_name="Reviewer",
            content="Looks good",
            action="comment",
        ))

        # Approve
        registry.update_status(req1.request_id, RequestStatus.APPROVED, actor="reviewer@firm.com")

        # Add a second request (pending)
        registry.submit(MonikerRequest(
            request_id="",
            path="analytics/new-metric",
            requester=_make_requester(),
            domain_level=DomainLevel.TOP_LEVEL,
        ))

        # Save
        count = save_requests_to_yaml(str(yaml_path), registry)
        assert count == 2
        assert yaml_path.exists()

        # Reload into fresh registry
        new_registry = RequestRegistry()
        loaded = load_requests_from_yaml(str(yaml_path), new_registry)
        assert len(loaded) == 2

        # Verify first request
        reloaded_req1 = new_registry.get_by_path("market-data/bonds")
        assert reloaded_req1 is not None
        assert reloaded_req1.display_name == "Bond Prices"
        assert reloaded_req1.status == RequestStatus.APPROVED
        assert reloaded_req1.adop == "jane@firm.com"
        assert reloaded_req1.adop_name == "Jane Doe"
        assert reloaded_req1.ads_name == "Bob Smith"
        assert reloaded_req1.adal_name == "Carol Williams"
        assert reloaded_req1.source_binding_type == "snowflake"
        assert reloaded_req1.source_binding_config["account"] == "firm.us-east-1"
        assert "bonds" in reloaded_req1.tags
        assert reloaded_req1.reviewed_by == "reviewer@firm.com"

        # Verify comments survived
        assert len(reloaded_req1.comments) == 1
        assert reloaded_req1.comments[0].author == "reviewer@firm.com"
        assert reloaded_req1.comments[0].content == "Looks good"

        # Verify second request
        reloaded_req2 = new_registry.get_by_path("analytics/new-metric")
        assert reloaded_req2 is not None
        assert reloaded_req2.domain_level == DomainLevel.TOP_LEVEL

    def test_load_missing_file(self, tmp_path):
        """Loading from a non-existent file should return empty list."""
        registry = RequestRegistry()
        loaded = load_requests_from_yaml(tmp_path / "nonexistent.yaml", registry)
        assert loaded == []
        assert registry.all_requests() == []

    def test_load_empty_file(self, tmp_path):
        """Loading from an empty YAML should return empty list."""
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("")
        registry = RequestRegistry()
        loaded = load_requests_from_yaml(str(yaml_path), registry)
        assert loaded == []

    def test_save_creates_parent_dirs(self, tmp_path):
        """save should create parent directories if needed."""
        yaml_path = tmp_path / "nested" / "dir" / "requests.yaml"
        registry = RequestRegistry()
        registry.submit(MonikerRequest(
            request_id="",
            path="test",
            requester=_make_requester(),
        ))

        count = save_requests_to_yaml(str(yaml_path), registry)
        assert count == 1
        assert yaml_path.exists()


class TestRegistryClear:
    """Test registry clear and counter reset."""

    def test_clear_resets_everything(self):
        """clear() should remove all requests and reset counter."""
        registry = RequestRegistry()
        registry.submit(MonikerRequest(request_id="", path="a", requester=_make_requester()))
        registry.submit(MonikerRequest(request_id="", path="b", requester=_make_requester()))

        assert len(registry.all_requests()) == 2

        registry.clear()
        assert len(registry.all_requests()) == 0

        # Counter should be reset
        r = registry.submit(MonikerRequest(request_id="", path="c", requester=_make_requester()))
        assert r.request_id == "REQ-0001"
