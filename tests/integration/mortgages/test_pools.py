"""Integration tests for mortgages.pools domain.

Tests resolution and data access for MBS pool data.
"""

import pytest


@pytest.mark.mortgages
@pytest.mark.integration
class TestMbsResolution:
    """Test MBS moniker resolution."""

    @pytest.mark.asyncio
    async def test_resolve_pools(self, service, caller):
        """MBS pool moniker should resolve to Excel source."""
        result = await service.resolve(
            "moniker://mortgages.pools/FNMA/30Y/ALL",
            caller
        )

        assert result.source.source_type == "excel"
        assert result.binding_path == "mortgages.pools"

    @pytest.mark.asyncio
    async def test_resolve_prepay(self, service, caller):
        """Prepayment moniker should resolve."""
        result = await service.resolve(
            "moniker://mortgages.prepay/FNMA/30Y/ALL",
            caller
        )

        assert result.source.source_type == "excel"

    @pytest.mark.asyncio
    async def test_confidential_classification(self, service, caller):
        """MBS data should be classified as confidential."""
        result = await service.describe(
            "moniker://mortgages",
            caller
        )

        assert result.node.classification == "confidential"


@pytest.mark.mortgages
@pytest.mark.integration
class TestMbsData:
    """Test MBS data from mock Excel adapter."""

    def test_pool_data_structure(self, excel_adapter):
        """Pool data should have expected columns."""
        results = excel_adapter.get_pool_data("FNMA", "30Y")

        assert len(results) > 0
        row = results[0]

        # Required fields
        assert "POOL_ID" in row
        assert "AGENCY" in row
        assert "WAC" in row
        assert "WAM" in row
        assert "POOL_FACTOR" in row
        assert "CPR_1M" in row

    def test_agencies_available(self, excel_adapter):
        """Should have data for all agencies."""
        results = excel_adapter.get_pool_data("ALL", "ALL")

        agencies = {r["AGENCY"] for r in results}
        assert "FNMA" in agencies
        assert "FHLMC" in agencies
        assert "GNMA" in agencies

    def test_pool_factor_valid(self, excel_adapter):
        """Pool factors should be between 0 and 1."""
        results = excel_adapter.get_pool_data("FNMA", "30Y")

        for row in results:
            factor = row["POOL_FACTOR"]
            assert 0 < factor <= 1, f"Invalid pool factor: {factor}"

    def test_prepay_scenarios(self, excel_adapter):
        """Prepay data should have multiple scenarios."""
        results = excel_adapter.get_prepay_data("FNMA", "30Y")

        scenarios = {r["SCENARIO"] for r in results}
        assert "BASE" in scenarios
        assert "UP100" in scenarios
        assert "DN100" in scenarios


@pytest.mark.mortgages
@pytest.mark.integration
class TestMbsGovernance:
    """Test MBS governance roles."""

    @pytest.mark.asyncio
    async def test_governance_roles_set(self, service, caller, catalog_registry):
        """MBS should have formal governance roles at domain level."""
        result = await service.resolve(
            "moniker://mortgages.pools/FNMA/30Y/ALL",
            caller
        )

        # Resolution returns source binding info
        assert result.source.source_type == "excel"

        # Governance roles are defined at parent level (mortgages)
        mortgages_node = catalog_registry.get("mortgages")
        assert mortgages_node is not None
        assert mortgages_node.ownership.adop is not None
        assert mortgages_node.ownership.ads is not None
        assert mortgages_node.ownership.adal is not None

    def test_documentation_available(self, catalog_registry):
        """MBS domain should have documentation links."""
        node = catalog_registry.get("mortgages")
        assert node is not None
        assert node.documentation is not None
        assert node.documentation.glossary_url is not None
        assert node.documentation.runbook_url is not None
