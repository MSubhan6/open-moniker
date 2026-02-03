"""Shared test fixtures for Moniker integration tests.

These fixtures use moniker-data for mock adapters, ensuring tests
don't have direct access to implementation details.

When running from within open-moniker-svc (development), imports are adjusted
to use local paths. When installed as packages, uses package imports.
"""

import pytest
import sys
from pathlib import Path

# Detect if running from within open-moniker-svc or as installed packages
_TESTS_DIR = Path(__file__).parent
_EXTERNAL_DIR = _TESTS_DIR.parent.parent  # external/moniker-tests -> external
_REPO_ROOT = _EXTERNAL_DIR.parent  # external -> open-moniker-svc
_RUNNING_IN_MONOREPO = (_REPO_ROOT / "src" / "moniker_svc").exists()

if _RUNNING_IN_MONOREPO:
    # Add paths for local development
    sys.path.insert(0, str(_REPO_ROOT / "src"))
    sys.path.insert(0, str(_EXTERNAL_DIR / "moniker-data" / "src"))

# Import from moniker-data package
from moniker_data.adapters import (
    MockOracleAdapter,
    MockSnowflakeAdapter,
    MockRestAdapter,
    MockExcelAdapter,
)
from moniker_data.adapters.oracle import reset_db as reset_oracle_db

# Import from moniker-svc package
from moniker_svc.cache.memory import InMemoryCache
from moniker_svc.catalog.loader import load_catalog
from moniker_svc.config import Config
from moniker_svc.service import MonikerService
from moniker_svc.telemetry.emitter import TelemetryEmitter
from moniker_svc.telemetry.events import CallerIdentity


# =============================================================================
# Catalog Fixtures
# =============================================================================

@pytest.fixture
def catalog_path() -> Path:
    """Path to sample catalog - loaded from moniker-svc package."""
    if _RUNNING_IN_MONOREPO:
        return _REPO_ROOT / "sample_catalog.yaml"
    # Fallback for installed package
    return Path(__file__).parent.parent.parent / "sample_catalog.yaml"


@pytest.fixture
def catalog_registry(catalog_path):
    """Load the catalog for testing."""
    if catalog_path.exists():
        return load_catalog(str(catalog_path))
    else:
        # Fallback: load from installed package
        import moniker_svc
        pkg_path = Path(moniker_svc.__file__).parent.parent.parent / "sample_catalog.yaml"
        return load_catalog(str(pkg_path))


# =============================================================================
# Service Fixtures
# =============================================================================

@pytest.fixture
def config() -> Config:
    """Default test configuration."""
    return Config()


@pytest.fixture
def cache() -> InMemoryCache:
    """In-memory cache for testing."""
    return InMemoryCache(max_size=1000, default_ttl_seconds=300.0)


@pytest.fixture
def telemetry() -> TelemetryEmitter:
    """Telemetry emitter for testing."""
    return TelemetryEmitter()


@pytest.fixture
def service(catalog_registry, cache, telemetry, config) -> MonikerService:
    """Create MonikerService instance for testing."""
    return MonikerService(
        catalog=catalog_registry,
        cache=cache,
        telemetry=telemetry,
        config=config,
    )


# =============================================================================
# Caller Identity Fixtures
# =============================================================================

@pytest.fixture
def caller() -> CallerIdentity:
    """Test caller identity."""
    return CallerIdentity(
        service_id="integration-test",
        user_id="test-user",
        app_id="moniker-tests",
        team="test-team",
    )


@pytest.fixture
def admin_caller() -> CallerIdentity:
    """Admin caller identity for privileged operations."""
    return CallerIdentity(
        service_id="integration-test",
        user_id="admin-user",
        app_id="moniker-tests",
        team="admin-team",
        roles=["admin", "data-steward"],
    )


# =============================================================================
# Mock Adapter Fixtures
# =============================================================================

@pytest.fixture
def oracle_adapter() -> MockOracleAdapter:
    """Mock Oracle adapter with CVaR data."""
    return MockOracleAdapter()


@pytest.fixture
def snowflake_adapter() -> MockSnowflakeAdapter:
    """Mock Snowflake adapter with govies/rates data."""
    return MockSnowflakeAdapter()


@pytest.fixture
def rest_adapter() -> MockRestAdapter:
    """Mock REST adapter with commodities data."""
    return MockRestAdapter()


@pytest.fixture
def excel_adapter() -> MockExcelAdapter:
    """Mock Excel adapter with MBS data."""
    return MockExcelAdapter()


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset mock databases before each test."""
    reset_oracle_db()
    yield
    # Cleanup after test if needed


# =============================================================================
# Test Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks test as slow")
    config.addinivalue_line("markers", "integration: marks as integration test")
    config.addinivalue_line("markers", "risk: tests for risk domain")
    config.addinivalue_line("markers", "govies: tests for govies domain")
    config.addinivalue_line("markers", "rates: tests for rates domain")
    config.addinivalue_line("markers", "mortgages: tests for mortgages domain")
