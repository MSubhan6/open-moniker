"""Integration tests for govies.treasury domain.

Tests resolution and data access for US Treasury securities.
"""

import pytest


@pytest.mark.govies
@pytest.mark.integration
class TestTreasuryResolution:
    """Test Treasury moniker resolution."""

    @pytest.mark.asyncio
    async def test_resolve_treasury(self, service, caller):
        """Treasury moniker should resolve to Snowflake source."""
        result = await service.resolve(
            "moniker://govies.treasury/US/10Y/ALL",
            caller
        )

        assert result.source.source_type == "snowflake"
        assert result.binding_path == "govies.treasury"

    @pytest.mark.asyncio
    async def test_ownership_and_governance(self, service, caller, catalog_registry):
        """Govies should have proper governance roles at domain level."""
        result = await service.resolve(
            "moniker://govies.treasury/US/10Y/ALL",
            caller
        )

        # Resolution returns source binding info
        assert result.source.source_type == "snowflake"

        # Governance roles are defined at parent level (govies)
        govies_node = catalog_registry.get("govies")
        assert govies_node is not None
        assert govies_node.ownership.adop is not None
        assert govies_node.ownership.ads is not None
        assert govies_node.ownership.adal is not None


@pytest.mark.govies
@pytest.mark.integration
class TestTreasuryData:
    """Test Treasury data from mock Snowflake."""

    def test_treasury_data_structure(self, snowflake_adapter):
        """Treasury data should have expected columns."""
        query = """
            SELECT asof_date, cusip, country, tenor, yield, price, duration
            FROM treasury_securities
            WHERE tenor = '10Y'
            LIMIT 5
        """
        results = snowflake_adapter.execute(query)

        assert len(results) > 0
        for row in results:
            assert "ASOF_DATE" in row
            assert "CUSIP" in row
            assert "TENOR" in row
            assert row["TENOR"] == "10Y"

    def test_yield_curve_data(self, snowflake_adapter):
        """Should have full yield curve data."""
        query = """
            SELECT DISTINCT tenor
            FROM treasury_securities
            ORDER BY tenor
        """
        results = snowflake_adapter.execute(query)

        tenors = [r["TENOR"] for r in results]
        # Should have multiple tenors for curve
        assert len(tenors) >= 5
