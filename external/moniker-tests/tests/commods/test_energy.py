"""Integration tests for commods.energy domain.

Tests resolution and data access for energy commodities via NEFA API.
"""

import pytest


@pytest.mark.integration
class TestEnergyResolution:
    """Test energy commodity moniker resolution."""

    @pytest.mark.asyncio
    async def test_resolve_crude(self, service, caller):
        """Crude oil moniker should resolve to REST source."""
        result = await service.resolve(
            "moniker://commods.energy/CL/SPOT/ALL",
            caller
        )

        assert result.source.source_type == "rest"
        assert result.binding_path == "commods.energy"

    @pytest.mark.asyncio
    async def test_resolve_natgas(self, service, caller):
        """Natural gas moniker should resolve."""
        result = await service.resolve(
            "moniker://commods.energy/NG/F1/ALL",
            caller
        )

        assert result.source.source_type == "rest"


@pytest.mark.integration
class TestEnergyData:
    """Test energy data from mock REST adapter."""

    def test_crude_spot_data(self, rest_adapter):
        """Should return crude oil spot prices."""
        results = rest_adapter.get_energy("CL", "SPOT")

        assert len(results) > 0
        row = results[0]

        assert row["SYMBOL"] == "CL"
        assert row["CONTRACT"] == "SPOT"
        assert row["PRICE"] > 0

    def test_futures_curve(self, rest_adapter):
        """Should have futures curve data."""
        results = rest_adapter.get_energy("CL", "ALL")

        contracts = {r["CONTRACT"] for r in results}
        assert "SPOT" in contracts
        assert "F1" in contracts
        assert "F2" in contracts

    def test_energy_symbols(self, rest_adapter):
        """Should have data for multiple energy commodities."""
        results = rest_adapter.get_energy("ALL", "SPOT")

        symbols = {r["SYMBOL"] for r in results}
        assert "CL" in symbols  # Crude
        assert "NG" in symbols  # Natural gas

    def test_price_change_fields(self, rest_adapter):
        """Should include price change data."""
        results = rest_adapter.get_energy("CL", "SPOT")

        row = results[0]
        assert "CHANGE" in row
        assert "CHANGE_PCT" in row
        assert "VOLUME" in row


@pytest.mark.integration
class TestMetalsData:
    """Test metals data from mock REST adapter."""

    def test_gold_spot(self, rest_adapter):
        """Should return gold spot prices."""
        results = rest_adapter.get_metals("GC", "SPOT")

        assert len(results) > 0
        row = results[0]

        assert row["SYMBOL"] == "GC"
        assert row["PRICE"] > 1000  # Gold > $1000/oz

    def test_precious_metals(self, rest_adapter):
        """Should have precious metals data."""
        results = rest_adapter.get_metals("ALL", "SPOT")

        symbols = {r["SYMBOL"] for r in results}
        assert "GC" in symbols  # Gold
        assert "SI" in symbols  # Silver
