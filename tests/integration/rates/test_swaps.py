"""Integration tests for rates.swap domain.

Tests resolution and data access for interest rate swaps.
"""

import pytest


@pytest.mark.rates
@pytest.mark.integration
class TestSwapResolution:
    """Test swap rate moniker resolution."""

    @pytest.mark.asyncio
    async def test_resolve_swap_rates(self, service, caller):
        """Swap moniker should resolve to Snowflake source."""
        result = await service.resolve(
            "moniker://rates.swap/USD/10Y/ALL",
            caller
        )

        assert result.source.source_type == "snowflake"
        assert result.binding_path == "rates.swap"

    @pytest.mark.asyncio
    async def test_resolve_all_currencies(self, service, caller):
        """Should support ALL currencies query."""
        result = await service.resolve(
            "moniker://rates.swap/ALL/5Y/ALL",
            caller
        )

        assert result.source.source_type == "snowflake"
        assert "'ALL' = 'ALL'" in result.source.query or "ALL" in result.source.query


@pytest.mark.rates
@pytest.mark.integration
class TestSwapData:
    """Test swap data from mock Snowflake."""

    def test_swap_curve_data(self, snowflake_adapter):
        """Should have full swap curve across tenors."""
        query = """
            SELECT DISTINCT tenor
            FROM swap_rates
            WHERE currency = 'USD'
            ORDER BY tenor
        """
        results = snowflake_adapter.execute(query)

        tenors = [r["TENOR"] for r in results]
        assert len(tenors) >= 5
        assert "10Y" in tenors

    def test_multi_currency_data(self, snowflake_adapter):
        """Should have data for multiple currencies."""
        query = """
            SELECT DISTINCT currency
            FROM swap_rates
        """
        results = snowflake_adapter.execute(query)

        currencies = {r["CURRENCY"] for r in results}
        assert "USD" in currencies
        assert "EUR" in currencies
        assert len(currencies) >= 3

    def test_rate_values_reasonable(self, snowflake_adapter):
        """Swap rates should be in reasonable range."""
        query = """
            SELECT currency, tenor, par_rate
            FROM swap_rates
            WHERE currency = 'USD' AND tenor = '10Y'
            LIMIT 10
        """
        results = snowflake_adapter.execute(query)

        for row in results:
            rate = row["PAR_RATE"]
            # Rates should be between -5% and 20%
            assert -0.05 < rate < 0.20, f"Rate {rate} out of range"


@pytest.mark.rates
@pytest.mark.integration
class TestSofrResolution:
    """Test SOFR rate resolution."""

    @pytest.mark.asyncio
    async def test_resolve_sofr(self, service, caller):
        """SOFR moniker should resolve."""
        result = await service.resolve(
            "moniker://rates.sofr/USD/ON/ALL",
            caller
        )

        assert result.source.source_type == "snowflake"

    def test_sofr_rate_types(self, snowflake_adapter):
        """Should have multiple SOFR rate types."""
        query = """
            SELECT DISTINCT rate_type
            FROM sofr_rates
        """
        results = snowflake_adapter.execute(query)

        rate_types = {r["RATE_TYPE"] for r in results}
        assert "ON" in rate_types  # Overnight
        assert len(rate_types) >= 3
