"""Integration tests for domain-based ownership inheritance (OM-8).

Tests the ownership inheritance feature where catalog nodes inherit
ownership from their domain if not explicitly set in the catalog hierarchy.

Key behaviors tested:
1. Ownership inherits from catalog hierarchy first
2. Missing ownership fields fall back to domain ownership
3. Domain ownership uses correct field mappings
4. Provenance tracking shows where ownership came from
"""

import pytest
from moniker_svc.catalog.registry import CatalogRegistry
from moniker_svc.catalog.types import CatalogNode, Ownership, SourceBinding, SourceType
from moniker_svc.domains.registry import DomainRegistry
from moniker_svc.domains.types import Domain


@pytest.fixture
def domain_registry() -> DomainRegistry:
    """Create a domain registry with test domains."""
    registry = DomainRegistry()

    registry.register(Domain(
        name="risk",
        display_name="Risk Analytics",
        owner="risk-owner@firm.com",
        tech_custodian="risk-tech@firm.com",
        help_channel="#risk-support",
    ))

    registry.register(Domain(
        name="indices",
        display_name="Market Indices",
        owner="indices-owner@firm.com",
        tech_custodian="indices-tech@firm.com",
        help_channel="#indices-support",
    ))

    registry.register(Domain(
        name="commodities",
        display_name="Commodities",
        # Missing owner/tech_custodian to test partial fallback
        help_channel="#commodities-support",
    ))

    return registry


@pytest.fixture
def catalog_registry() -> CatalogRegistry:
    """Create a catalog with various ownership configurations.

    Note: Domain fallback uses "/" path separator. Paths like "indices/equity"
    will look up domain "indices", but paths like "indices/equity" will look
    up domain "indices/equity" (which likely doesn't exist).
    """
    registry = CatalogRegistry()

    # Root node with full ownership
    registry.register(CatalogNode(
        path="risk",
        display_name="Risk Domain",
        domain="risk",
        ownership=Ownership(
            accountable_owner="risk-catalog-owner@firm.com",
            data_specialist="risk-catalog-specialist@firm.com",
            support_channel="#risk-catalog-support",
        ),
    ))

    # Child with partial ownership (inherits remaining from parent)
    # Using "/" separator for child path
    registry.register(CatalogNode(
        path="risk/cvar",
        display_name="CVaR Risk",
        ownership=Ownership(
            data_specialist="cvar-specialist@firm.com",
            # accountable_owner and support_channel inherited from parent
        ),
        source_binding=SourceBinding(
            source_type=SourceType.ORACLE,
            config={"query": "SELECT * FROM cvar"},
        ),
    ))

    # Child with no ownership (inherits all from hierarchy)
    registry.register(CatalogNode(
        path="risk/cvar/portfolio",
        display_name="Portfolio CVaR",
    ))

    # Node with no catalog ownership - falls back to domain
    registry.register(CatalogNode(
        path="indices",
        display_name="Indices Domain",
        domain="indices",
        # No ownership - should fall back to domain
    ))

    # Child under indices with partial ownership (using "/" separator)
    registry.register(CatalogNode(
        path="indices/equity",
        display_name="Equity Indices",
        ownership=Ownership(
            accountable_owner="equity-owner@firm.com",
            # Other fields fall back to domain
        ),
    ))

    # Node with domain that has partial ownership
    registry.register(CatalogNode(
        path="commodities",
        display_name="Commodities Domain",
        domain="commodities",
        # No ownership - domain also has partial ownership
    ))

    # Node with ownership that overrides domain (using "/" separator)
    registry.register(CatalogNode(
        path="commodities/energy",
        display_name="Energy Commodities",
        ownership=Ownership(
            accountable_owner="energy-override@firm.com",
            data_specialist="energy-specialist@firm.com",
            support_channel="#energy-override",
        ),
    ))

    return registry


@pytest.mark.integration
class TestCatalogOwnershipInheritance:
    """Test ownership inheritance within catalog hierarchy."""

    def test_full_ownership_at_node(self, catalog_registry, domain_registry):
        """Node with full ownership should use its own values."""
        resolved = catalog_registry.resolve_ownership("risk", domain_registry)

        assert resolved.accountable_owner == "risk-catalog-owner@firm.com"
        assert resolved.accountable_owner_source == "risk"
        assert resolved.data_specialist == "risk-catalog-specialist@firm.com"
        assert resolved.data_specialist_source == "risk"
        assert resolved.support_channel == "#risk-catalog-support"
        assert resolved.support_channel_source == "risk"

    def test_partial_ownership_inherits_from_parent(self, catalog_registry, domain_registry):
        """Node with partial ownership inherits missing fields from parent."""
        resolved = catalog_registry.resolve_ownership("risk/cvar", domain_registry)

        # data_specialist set at this node
        assert resolved.data_specialist == "cvar-specialist@firm.com"
        assert resolved.data_specialist_source == "risk/cvar"

        # accountable_owner inherited from parent
        assert resolved.accountable_owner == "risk-catalog-owner@firm.com"
        assert resolved.accountable_owner_source == "risk"

        # support_channel inherited from parent
        assert resolved.support_channel == "#risk-catalog-support"
        assert resolved.support_channel_source == "risk"

    def test_no_ownership_inherits_all_from_hierarchy(self, catalog_registry, domain_registry):
        """Node with no ownership inherits all from parent hierarchy."""
        resolved = catalog_registry.resolve_ownership("risk/cvar/portfolio", domain_registry)

        # All inherited from ancestors
        assert resolved.data_specialist == "cvar-specialist@firm.com"
        assert resolved.data_specialist_source == "risk/cvar"

        assert resolved.accountable_owner == "risk-catalog-owner@firm.com"
        assert resolved.accountable_owner_source == "risk"

        assert resolved.support_channel == "#risk-catalog-support"
        assert resolved.support_channel_source == "risk"


@pytest.mark.integration
class TestDomainOwnershipFallback:
    """Test ownership fallback to domain when not in catalog hierarchy.

    Domain fallback uses the FIRST PATH SEGMENT to look up the domain,
    not the 'domain' field on the catalog node. For example:
    - Path "indices/equity" → looks up domain "indices"
    - Path "risk/cvar" → looks up domain "risk"
    """

    def test_fallback_to_domain_all_fields(self, catalog_registry, domain_registry):
        """Node with no catalog ownership falls back to domain based on path."""
        resolved = catalog_registry.resolve_ownership("indices", domain_registry)

        # All fields from domain (looked up by first path segment "indices")
        assert resolved.accountable_owner == "indices-owner@firm.com"
        assert resolved.accountable_owner_source == "domain:indices"

        assert resolved.data_specialist == "indices-tech@firm.com"
        assert resolved.data_specialist_source == "domain:indices"

        assert resolved.support_channel == "#indices-support"
        assert resolved.support_channel_source == "domain:indices"

    def test_catalog_overrides_domain(self, catalog_registry, domain_registry):
        """Catalog ownership should take precedence over domain."""
        resolved = catalog_registry.resolve_ownership("indices/equity", domain_registry)

        # accountable_owner from catalog
        assert resolved.accountable_owner == "equity-owner@firm.com"
        assert resolved.accountable_owner_source == "indices/equity"

        # Domain fallback uses path first segment "indices"
        # But since indices node has no ownership, and indices/equity only sets accountable_owner,
        # the other fields should fall back to domain
        assert resolved.data_specialist == "indices-tech@firm.com"
        assert resolved.data_specialist_source == "domain:indices"

        assert resolved.support_channel == "#indices-support"
        assert resolved.support_channel_source == "domain:indices"

    def test_partial_domain_ownership(self, catalog_registry, domain_registry):
        """Domain with partial ownership only provides set fields."""
        resolved = catalog_registry.resolve_ownership("commodities", domain_registry)

        # Domain only has help_channel set
        assert resolved.support_channel == "#commodities-support"
        assert resolved.support_channel_source == "domain:commodities"

        # Owner and tech_custodian not set in domain, so None
        assert resolved.accountable_owner is None
        assert resolved.data_specialist is None

    def test_catalog_overrides_partial_domain(self, catalog_registry, domain_registry):
        """Full catalog ownership overrides partial domain ownership."""
        resolved = catalog_registry.resolve_ownership("commodities/energy", domain_registry)

        # All from catalog, not domain
        assert resolved.accountable_owner == "energy-override@firm.com"
        assert resolved.accountable_owner_source == "commodities/energy"

        assert resolved.data_specialist == "energy-specialist@firm.com"
        assert resolved.data_specialist_source == "commodities/energy"

        assert resolved.support_channel == "#energy-override"
        assert resolved.support_channel_source == "commodities/energy"


@pytest.mark.integration
class TestOwnershipFieldMappings:
    """Test correct field mappings between domain and ownership.

    Domain lookup is based on the FIRST PATH SEGMENT, not the 'domain' field.
    So path "risk.something" will look up domain "risk".
    """

    def test_domain_owner_maps_to_accountable_owner(self, domain_registry):
        """Domain.owner should map to accountable_owner."""
        registry = CatalogRegistry()
        # Path starts with "risk" so domain "risk" is looked up
        registry.register(CatalogNode(
            path="risk",
        ))

        resolved = registry.resolve_ownership("risk", domain_registry)

        assert resolved.accountable_owner == "risk-owner@firm.com"
        assert resolved.accountable_owner_source == "domain:risk"

    def test_domain_tech_custodian_maps_to_data_specialist(self, domain_registry):
        """Domain.tech_custodian should map to data_specialist."""
        registry = CatalogRegistry()
        # Path starts with "risk" so domain "risk" is looked up
        registry.register(CatalogNode(
            path="risk",
        ))

        resolved = registry.resolve_ownership("risk", domain_registry)

        assert resolved.data_specialist == "risk-tech@firm.com"
        assert resolved.data_specialist_source == "domain:risk"

    def test_domain_help_channel_maps_to_support_channel(self, domain_registry):
        """Domain.help_channel should map to support_channel."""
        registry = CatalogRegistry()
        # Path starts with "risk" so domain "risk" is looked up
        registry.register(CatalogNode(
            path="risk",
        ))

        resolved = registry.resolve_ownership("risk", domain_registry)

        assert resolved.support_channel == "#risk-support"
        assert resolved.support_channel_source == "domain:risk"


@pytest.mark.integration
class TestOwnershipWithoutDomainRegistry:
    """Test ownership resolution without domain registry."""

    def test_no_domain_fallback_without_registry(self, catalog_registry):
        """Without domain registry, no fallback occurs."""
        # Node with no catalog ownership
        resolved = catalog_registry.resolve_ownership("indices", domain_registry=None)

        # No fallback - all None
        assert resolved.accountable_owner is None
        assert resolved.data_specialist is None
        assert resolved.support_channel is None

    def test_catalog_inheritance_still_works(self, catalog_registry):
        """Catalog hierarchy inheritance works without domain registry."""
        resolved = catalog_registry.resolve_ownership("risk/cvar/portfolio", domain_registry=None)

        # Still inherits from catalog hierarchy
        assert resolved.data_specialist == "cvar-specialist@firm.com"
        assert resolved.accountable_owner == "risk-catalog-owner@firm.com"
        assert resolved.support_channel == "#risk-catalog-support"


@pytest.mark.integration
class TestGovernanceRolesInheritance:
    """Test formal governance roles (ADOP, ADS, ADAL) inheritance."""

    @pytest.fixture
    def catalog_with_governance(self) -> CatalogRegistry:
        """Catalog with formal governance roles."""
        registry = CatalogRegistry()

        registry.register(CatalogNode(
            path="risk",
            display_name="Risk Domain",
            ownership=Ownership(
                adop="adop@firm.com",
                ads="ads@firm.com",
                adal="adal@firm.com",
            ),
        ))

        registry.register(CatalogNode(
            path="risk/cvar",
            display_name="CVaR",
            ownership=Ownership(
                ads="cvar-ads@firm.com",  # Override ADS only
            ),
        ))

        registry.register(CatalogNode(
            path="risk/cvar/portfolio",
            display_name="Portfolio CVaR",
            # No ownership - inherits all
        ))

        return registry

    def test_governance_roles_inherit(self, catalog_with_governance):
        """Formal governance roles should inherit through hierarchy."""
        resolved = catalog_with_governance.resolve_ownership("risk/cvar/portfolio")

        # ADS from risk/cvar
        assert resolved.ads == "cvar-ads@firm.com"
        assert resolved.ads_source == "risk/cvar"

        # ADOP and ADAL from risk
        assert resolved.adop == "adop@firm.com"
        assert resolved.adop_source == "risk"

        assert resolved.adal == "adal@firm.com"
        assert resolved.adal_source == "risk"

    def test_governance_roles_override(self, catalog_with_governance):
        """Child nodes can override specific governance roles."""
        resolved = catalog_with_governance.resolve_ownership("risk/cvar")

        # ADS overridden at this level
        assert resolved.ads == "cvar-ads@firm.com"
        assert resolved.ads_source == "risk/cvar"

        # ADOP and ADAL inherited
        assert resolved.adop == "adop@firm.com"
        assert resolved.adop_source == "risk"


@pytest.mark.integration
class TestOwnershipProvenanceTracking:
    """Test that ownership provenance (source) is correctly tracked."""

    def test_provenance_shows_catalog_node(self, catalog_registry, domain_registry):
        """Provenance should show catalog path for catalog ownership."""
        resolved = catalog_registry.resolve_ownership("risk/cvar", domain_registry)

        # From catalog node
        assert resolved.data_specialist_source == "risk/cvar"
        assert resolved.accountable_owner_source == "risk"

    def test_provenance_shows_domain(self, catalog_registry, domain_registry):
        """Provenance should show domain:name for domain ownership."""
        resolved = catalog_registry.resolve_ownership("indices", domain_registry)

        assert resolved.accountable_owner_source == "domain:indices"
        assert resolved.data_specialist_source == "domain:indices"
        assert resolved.support_channel_source == "domain:indices"

    def test_provenance_is_none_for_unset_fields(self, catalog_registry, domain_registry):
        """Provenance should be None for fields not set anywhere."""
        resolved = catalog_registry.resolve_ownership("commodities", domain_registry)

        # Commodities domain doesn't have owner or tech_custodian
        assert resolved.accountable_owner is None
        assert resolved.accountable_owner_source is None

        assert resolved.data_specialist is None
        assert resolved.data_specialist_source is None

    def test_mixed_provenance(self, catalog_registry, domain_registry):
        """Different fields can have different provenance."""
        resolved = catalog_registry.resolve_ownership("indices/equity", domain_registry)

        # Catalog overrides accountable_owner
        assert resolved.accountable_owner_source == "indices/equity"

        # Domain provides the rest (lookup by first path segment "indices")
        assert resolved.data_specialist_source == "domain:indices"
        assert resolved.support_channel_source == "domain:indices"


@pytest.mark.integration
class TestEdgeCases:
    """Test edge cases in ownership inheritance."""

    def test_nonexistent_domain_no_fallback(self, catalog_registry):
        """Node with nonexistent domain should not crash."""
        # Create registry with a domain that doesn't exist
        registry = CatalogRegistry()
        registry.register(CatalogNode(
            path="test",
            domain="nonexistent_domain",
        ))

        domain_registry = DomainRegistry()  # Empty registry

        # Should not raise, just return None for all fields
        resolved = registry.resolve_ownership("test", domain_registry)

        assert resolved.accountable_owner is None
        assert resolved.data_specialist is None
        assert resolved.support_channel is None

    def test_empty_ownership_fields_not_used(self, domain_registry):
        """Empty string ownership fields should not be used."""
        registry = CatalogRegistry()
        # Path starts with "risk" to enable domain lookup
        registry.register(CatalogNode(
            path="risk/test",
            ownership=Ownership(
                accountable_owner="",  # Empty - should fall back to domain
            ),
        ))

        resolved = registry.resolve_ownership("risk/test", domain_registry)

        # Should fall back to domain since empty string is falsy
        # Domain lookup uses first path segment "risk"
        assert resolved.accountable_owner == "risk-owner@firm.com"
        assert resolved.accountable_owner_source == "domain:risk"

    def test_deep_hierarchy_inheritance(self, domain_registry):
        """Ownership should inherit through deep hierarchies."""
        registry = CatalogRegistry()

        registry.register(CatalogNode(
            path="a",
            ownership=Ownership(accountable_owner="owner-a@firm.com"),
        ))
        registry.register(CatalogNode(
            path="a/b",
            ownership=Ownership(data_specialist="specialist-b@firm.com"),
        ))
        registry.register(CatalogNode(path="a/b/c"))
        registry.register(CatalogNode(path="a/b/c/d"))
        registry.register(CatalogNode(path="a/b/c/d/e"))

        resolved = registry.resolve_ownership("a/b/c/d/e", domain_registry)

        # Inherits through entire chain
        assert resolved.accountable_owner == "owner-a@firm.com"
        assert resolved.accountable_owner_source == "a"

        assert resolved.data_specialist == "specialist-b@firm.com"
        assert resolved.data_specialist_source == "a/b"
