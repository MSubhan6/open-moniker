# Moniker Integration Tests

Integration tests for the Moniker resolution service.

## Purpose

This repository contains **integration tests** that are intentionally separated from:
- `open-moniker-svc` - The service code
- `open-moniker-data` - The test fixtures/mocks

This separation ensures:
1. **Tests can't cheat** - No access to mock implementation details
2. **Contract-based testing** - Tests validate behavior, not implementation
3. **Independent CI** - Test failures don't block service deployment
4. **Clear ownership** - QA/test team owns tests, dev team owns service

## Structure

```
tests/
├── conftest.py           # Shared fixtures (loads from moniker-data)
├── risk/                 # Risk domain tests
│   ├── test_cvar.py      # CVaR integration tests
│   └── test_access_policy.py
├── govies/               # Government bonds tests
│   └── test_treasury.py
├── rates/                # Interest rates tests
│   └── test_swaps.py
└── mortgages/            # MBS tests
    └── test_pools.py
```

## Running Tests

```bash
# Install dependencies (pulls moniker-svc and moniker-data)
pip install -e ".[dev]"

# Run all tests
pytest

# Run specific domain tests
pytest tests/risk/

# Run with coverage
pytest --cov=moniker_svc --cov-report=html

# Run in parallel
pytest -n auto
```

## Dependencies

Tests depend on:
- `moniker-svc` - The service being tested
- `moniker-data` - Mock adapters and fixtures

These are pulled as packages, ensuring tests only see the public interface.

## Contract Testing

Tests validate:
1. **Resolution contracts** - Monikers resolve to expected source types
2. **Query generation** - Generated queries match expected patterns
3. **Access policies** - Blocked patterns are enforced
4. **Ownership inheritance** - Governance roles propagate correctly
5. **Documentation** - All domains have required docs
