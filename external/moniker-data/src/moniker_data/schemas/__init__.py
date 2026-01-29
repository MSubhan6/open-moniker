"""JSON Schema definitions for data contracts.

These schemas define the expected structure of data from each source.
Mocks must produce data that validates against these schemas.
"""

import json
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).parent


def load_schema(name: str) -> dict[str, Any]:
    """Load a schema by name (without .json extension)."""
    schema_path = SCHEMA_DIR / f"{name}.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {name}")

    with open(schema_path) as f:
        return json.load(f)


def validate(data: dict[str, Any], schema_name: str) -> tuple[bool, list[str]]:
    """
    Validate data against a schema.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    try:
        import jsonschema
    except ImportError:
        # If jsonschema not installed, skip validation
        return (True, [])

    schema = load_schema(schema_name)
    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(data))

    if errors:
        return (False, [e.message for e in errors])
    return (True, [])


def validate_rows(rows: list[dict[str, Any]], schema_name: str) -> tuple[bool, list[str]]:
    """Validate a list of data rows against a schema."""
    all_errors = []
    for i, row in enumerate(rows):
        is_valid, errors = validate(row, schema_name)
        if not is_valid:
            all_errors.extend([f"Row {i}: {e}" for e in errors])

    return (len(all_errors) == 0, all_errors)


# Available schemas
SCHEMAS = [
    "risk_cvar",
    "govies_treasury",
    "govies_sovereign",
    "rates_swap",
    "rates_sofr",
    "commods_energy",
    "commods_metals",
    "mortgages_pools",
    "mortgages_prepay",
]
