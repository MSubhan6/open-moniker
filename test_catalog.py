"""Tests for catalog registry."""

import pytest

from moniker_svc.catalog.registry import CatalogRegistry
from moniker_svc.catalog.types import CatalogNode, Ownership, SourceBinding, SourceType


@pytest.fixture
def registry():
    reg = CatalogRegistry()

    # Set up hierarchy
    reg.register(CatalogNode(
        path="market-data",
        display_name="Market Data",
        ownership=Ownership(
            accountable_owner="jane@firm.com",
            data_specialist="market-team@firm.com",
            support_channel="#market-data",
        ),
    ))

    reg.register(CatalogNode(
        path="market-data/prices",
        display_name="Prices",
        # Inherits ownership from parent
    ))

    reg.register(CatalogNode(
        path="market-data/prices/equity",
        display_name="Equity Prices",
        ownership=Ownership(
            data_specialist="equity-team@firm.com",  # Override data_specialist
        ),
        source_binding=SourceBinding(
            source_type=SourceType.SNOWFLAKE,
            config={"table": "EQUITY_PRICES"},
        ),
        is_leaf=True,
    ))

    return reg


class TestCatalogRegistry:
    def test_register_and_get(self, registry):
        node = registry.get("market-data")
        assert node is not None
        assert node.display_name == "Market Data"

    def test_get_nonexistent(self, registry):
        node = registry.get("nonexistent")
        assert node is None

    def test_exists(self, registry):
        assert registry.exists("market-data")
        assert not registry.exists("nonexistent")

    def test_children(self, registry):
        children = registry.children("market-data")
        assert len(children) == 1
        assert children[0].path == "market-data/prices"

    def test_children_paths(self, registry):
        paths = registry.children_paths("market-data")
        assert "market-data/prices" in paths


class TestOwnershipResolution:
    def test_direct_ownership(self, registry):
        ownership = registry.resolve_ownership("market-data")
        assert ownership.accountable_owner == "jane@firm.com"
        assert ownership.accountable_owner_source == "market-data"

    def test_inherited_ownership(self, registry):
        ownership = registry.resolve_ownership("market-data/prices")
        # All fields inherited from parent
        assert ownership.accountable_owner == "jane@firm.com"
        assert ownership.accountable_owner_source == "market-data"
        assert ownership.data_specialist == "market-team@firm.com"
        assert ownership.support_channel == "#market-data"

    def test_partial_override(self, registry):
        ownership = registry.resolve_ownership("market-data/prices/equity")
        # accountable_owner inherited from market-data
        assert ownership.accountable_owner == "jane@firm.com"
        assert ownership.accountable_owner_source == "market-data"
        # data_specialist overridden at this level
        assert ownership.data_specialist == "equity-team@firm.com"
        assert ownership.data_specialist_source == "market-data/prices/equity"
        # support_channel inherited from market-data
        assert ownership.support_channel == "#market-data"
        assert ownership.support_channel_source == "market-data"


class TestSourceBinding:
    def test_find_source_binding_exact(self, registry):
        result = registry.find_source_binding("market-data/prices/equity")
        assert result is not None
        binding, path = result
        assert binding.source_type == SourceType.SNOWFLAKE
        assert path == "market-data/prices/equity"

    def test_find_source_binding_ancestor(self, registry):
        # Child of equity should find binding at equity level
        result = registry.find_source_binding("market-data/prices/equity/AAPL")
        assert result is not None
        binding, path = result
        assert binding.source_type == SourceType.SNOWFLAKE
        assert path == "market-data/prices/equity"

    def test_find_source_binding_none(self, registry):
        result = registry.find_source_binding("market-data")
        assert result is None


class TestAtomicReplace:
    def test_atomic_replace_all(self, registry):
        new_nodes = [
            CatalogNode(path="new-domain", display_name="New"),
            CatalogNode(path="new-domain/child", display_name="Child"),
        ]

        registry.atomic_replace(new_nodes)

        assert registry.exists("new-domain")
        assert not registry.exists("market-data")  # Old nodes gone
