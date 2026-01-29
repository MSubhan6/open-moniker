"""Integration tests for risk.cvar Oracle domain.

Tests the full flow: moniker resolution → query generation → ALL operators.
"""

import pytest
from pathlib import Path

from moniker_svc.cache.memory import InMemoryCache
from moniker_svc.catalog.loader import load_catalog
from moniker_svc.config import Config
from moniker_svc.service import MonikerService
from moniker_svc.telemetry.emitter import TelemetryEmitter
from moniker_svc.telemetry.events import CallerIdentity

from tests.mocks.oracle_risk_mock import execute_query, reset_mock_oracle_db


@pytest.fixture
def catalog_registry():
    """Load the sample catalog with risk.cvar domain."""
    catalog_path = Path(__file__).parent.parent / "sample_catalog.yaml"
    return load_catalog(str(catalog_path))


@pytest.fixture
def service(catalog_registry):
    """Create MonikerService with catalog."""
    config = Config()
    cache = InMemoryCache(max_size=1000, default_ttl_seconds=300.0)
    telemetry = TelemetryEmitter()
    return MonikerService(
        catalog=catalog_registry,
        cache=cache,
        telemetry=telemetry,
        config=config,
    )


@pytest.fixture
def caller():
    """Test caller identity."""
    return CallerIdentity(
        service_id="test-service",
        user_id="test-user",
        app_id="test-app",
        team="test-team",
    )


@pytest.fixture(autouse=True)
def reset_mock_db():
    """Reset mock database before each test."""
    reset_mock_oracle_db()


class TestRiskCvarResolution:
    """Test moniker resolution for risk.cvar domain."""

    @pytest.mark.asyncio
    async def test_resolve_specific_portfolio_currency_security(self, service, caller):
        """Test resolving a fully specified moniker."""
        result = await service.resolve("moniker://risk.cvar/758-A/USD/B0YHY8V7", caller)

        assert result.source.source_type == "oracle"
        assert "proteus.firm.com:1521/RISKDB" in result.source.connection.get("dsn", "")
        assert result.binding_path == "risk.cvar"
        assert result.sub_path == "758-A/USD/B0YHY8V7"

        # Check query has correct filters
        query = result.source.query
        assert "port_no || '-' || port_type = '758-A'" in query
        assert "base_currency = 'USD'" in query
        assert "ssm_id = 'B0YHY8V7'" in query

    @pytest.mark.asyncio
    async def test_resolve_all_securities(self, service, caller):
        """Test ALL operator on security dimension."""
        result = await service.resolve("moniker://risk.cvar/758-A/USD/ALL", caller)

        query = result.source.query
        # Portfolio and currency should be filtered
        assert "port_no || '-' || port_type = '758-A'" in query
        assert "base_currency = 'USD'" in query
        # Security should have ALL clause
        assert "'ALL' = 'ALL'" in query or "ssm_id" not in query.split("'ALL'")[-1]

    @pytest.mark.asyncio
    async def test_resolve_all_currencies(self, service, caller):
        """Test ALL operator on currency dimension."""
        result = await service.resolve("moniker://risk.cvar/758-A/ALL/B0YHY8V7", caller)

        query = result.source.query
        # Portfolio should be filtered
        assert "port_no || '-' || port_type = '758-A'" in query
        # Currency should have ALL clause
        assert "'ALL' = 'ALL'" in query
        # Security should be filtered
        assert "ssm_id = 'B0YHY8V7'" in query

    @pytest.mark.asyncio
    async def test_resolve_all_portfolios(self, service, caller):
        """Test ALL operator on portfolio dimension."""
        result = await service.resolve("moniker://risk.cvar/ALL/USD/B0YHY8V7", caller)

        query = result.source.query
        # Portfolio should have ALL clause
        assert "'ALL' = 'ALL'" in query
        # Currency and security should be filtered
        assert "base_currency = 'USD'" in query
        assert "ssm_id = 'B0YHY8V7'" in query

    @pytest.mark.asyncio
    async def test_resolve_all_everything(self, service, caller):
        """Test ALL on all dimensions (dangerous but valid)."""
        result = await service.resolve("moniker://risk.cvar/ALL/ALL/ALL", caller)

        query = result.source.query
        # All dimensions should have ALL clauses
        assert query.count("'ALL' = 'ALL'") == 3

    @pytest.mark.asyncio
    async def test_ownership_inherited(self, service, caller):
        """Test that ownership is inherited from risk domain."""
        result = await service.resolve("moniker://risk.cvar/758-A/USD/ALL", caller)

        assert result.ownership.accountable_owner == "risk-governance@firm.com"
        assert result.ownership.data_specialist == "risk-quant@firm.com"
        assert result.ownership.support_channel == "#risk-analytics"


class TestRiskCvarQueryExecution:
    """Test query execution against mock Oracle."""

    def test_mock_query_specific_portfolio(self):
        """Test query against mock database for specific portfolio."""
        query = """
            SELECT asof_date, port_no, port_type, ssm_id, base_currency, cvar
            FROM te_stress_tail_risk_pnl
            WHERE ('758-A' = 'ALL' OR port_no || '-' || port_type = '758-A')
              AND ('USD' = 'ALL' OR base_currency = 'USD')
              AND ('ALL' = 'ALL' OR ssm_id = 'ALL')
            ORDER BY asof_date DESC
            LIMIT 10
        """
        results = execute_query(query)

        assert len(results) > 0
        for row in results:
            assert row["PORT_NO"] == "758"
            assert row["PORT_TYPE"] == "A"
            assert row["BASE_CURRENCY"] == "USD"

    def test_mock_query_all_portfolios(self):
        """Test query with ALL on portfolio dimension."""
        query = """
            SELECT DISTINCT port_no, port_type
            FROM te_stress_tail_risk_pnl
            WHERE ('ALL' = 'ALL' OR port_no || '-' || port_type = 'ALL')
              AND ('USD' = 'ALL' OR base_currency = 'USD')
              AND ('ALL' = 'ALL' OR ssm_id = 'ALL')
        """
        results = execute_query(query)

        # Should have multiple portfolios
        portfolios = {(r["PORT_NO"], r["PORT_TYPE"]) for r in results}
        assert len(portfolios) > 1

    def test_mock_query_specific_security(self):
        """Test query for specific security across all portfolios."""
        query = """
            SELECT asof_date, port_no, port_type, ssm_id, base_currency, cvar
            FROM te_stress_tail_risk_pnl
            WHERE ('ALL' = 'ALL' OR port_no || '-' || port_type = 'ALL')
              AND ('ALL' = 'ALL' OR base_currency = 'ALL')
              AND ('B0YHY8V7' = 'ALL' OR ssm_id = 'B0YHY8V7')
            ORDER BY asof_date DESC
            LIMIT 10
        """
        results = execute_query(query)

        for row in results:
            assert row["SSM_ID"] == "B0YHY8V7"

    def test_mock_query_timeseries_returned(self):
        """Test that full timeseries history is returned."""
        query = """
            SELECT DISTINCT asof_date
            FROM te_stress_tail_risk_pnl
            WHERE ('758-A' = 'ALL' OR port_no || '-' || port_type = '758-A')
              AND ('USD' = 'ALL' OR base_currency = 'USD')
              AND ('ALL' = 'ALL' OR ssm_id = 'ALL')
            ORDER BY asof_date
        """
        results = execute_query(query)

        # Should have multiple dates (timeseries)
        dates = [r["ASOF_DATE"] for r in results]
        assert len(dates) > 1
        # Dates should be in order
        assert dates == sorted(dates)


class TestRiskCvarCatalogStructure:
    """Test catalog structure and metadata."""

    def test_risk_domain_exists(self, catalog_registry):
        """Test that risk domain is registered."""
        assert catalog_registry.exists("risk")

    def test_risk_cvar_exists(self, catalog_registry):
        """Test that risk.cvar domain is registered."""
        assert catalog_registry.exists("risk.cvar")

    def test_risk_cvar_has_source_binding(self, catalog_registry):
        """Test that risk.cvar has Oracle source binding."""
        result = catalog_registry.find_source_binding("risk.cvar/758-A/USD/ALL")
        assert result is not None

        binding, path = result
        assert binding.source_type.value == "oracle"
        assert path == "risk.cvar"

    def test_risk_cvar_ownership(self, catalog_registry):
        """Test ownership resolution for risk.cvar."""
        ownership = catalog_registry.resolve_ownership("risk.cvar")

        assert ownership.accountable_owner == "risk-governance@firm.com"
        assert ownership.data_specialist == "risk-quant@firm.com"

    def test_risk_cvar_subpath_children(self, catalog_registry):
        """Test that risk.cvar path segments resolve correctly."""
        # Note: risk.cvar uses dot notation (separate domain), not slash hierarchy
        # Children are path segments under the source binding
        result = catalog_registry.find_source_binding("risk.cvar/758-A/USD/ALL")
        assert result is not None
        binding, path = result
        assert path == "risk.cvar"
