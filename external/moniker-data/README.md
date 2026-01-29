# Moniker Test Data

Test fixtures and mock data sources for the Moniker resolution service.

## Purpose

This repository provides **realistic mock data** that simulates production data sources.
It is intentionally separated from the main service and tests to:

1. **Prevent "teaching to the test"** - Tests can't peek at mock implementation details
2. **Enable contract-based testing** - Mocks follow real source schemas/contracts
3. **Support data versioning** - Fixtures can be generated from sanitized prod snapshots
4. **Separate ownership** - Data team owns fixtures, dev team owns service code

## Structure

```
src/moniker_data/
├── adapters/           # Mock database/API adapters
│   ├── oracle.py       # Mock Oracle (CVaR risk data)
│   ├── snowflake.py    # Mock Snowflake (govies, rates)
│   ├── rest.py         # Mock REST APIs (NEFA commodities)
│   └── excel.py        # Mock Excel sources (MBS data)
├── fixtures/           # Static test data files
│   ├── risk/           # CVaR and tail risk fixtures
│   ├── govies/         # Government bond fixtures
│   ├── rates/          # Interest rate fixtures
│   └── mortgages/      # MBS pool fixtures
└── schemas/            # Data contracts/schemas
    └── *.json          # JSON Schema definitions
```

## Usage

```python
from moniker_data.adapters.oracle import MockOracleAdapter

# Create mock adapter with realistic data
adapter = MockOracleAdapter()

# Execute queries against mock data
results = adapter.execute("SELECT * FROM te_stress_tail_risk_pnl WHERE ...")
```

## Data Generation

Fixtures are generated from production data snapshots (sanitized/anonymized):

```bash
# Generate fixtures from prod (requires prod access)
python -m moniker_data.generate --source prod --output fixtures/

# Validate fixtures against schemas
python -m moniker_data.validate
```

## Important

- **Never commit real production data** - All data must be synthetic or sanitized
- **Maintain schema compatibility** - Changes to schemas require versioning
- **Document data characteristics** - Row counts, distributions, edge cases
