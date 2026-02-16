"""Mock MS-SQL database with credit exposure data for testing.

Uses SQLite in-memory to simulate a SQL Server credit risk database.
Domain: Credit Exposures and Limits.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from typing import Any
import random


# =============================================================================
# Sample Data Configuration - Credit Risk Domain
# =============================================================================

COUNTERPARTIES = [
    ("CP001", "Goldman Sachs Group", "Investment Banking", "AA-", "US"),
    ("CP002", "Deutsche Bank AG", "Commercial Banking", "A-", "DE"),
    ("CP003", "JPMorgan Chase & Co", "Investment Banking", "A+", "US"),
    ("CP004", "Morgan Stanley", "Broker-Dealer", "A", "US"),
    ("CP005", "Barclays Bank PLC", "Commercial Banking", "A+", "GB"),
    ("CP006", "UBS Group AG", "Wealth Management", "BB-", "CH"),
    ("CP007", "Citigroup Inc", "Commercial Banking", "AA-", "US"),
    ("CP008", "BNP Paribas SA", "Commercial Banking", "AA", "FR"),
]

EXPOSURE_TYPES = ["Loan", "Derivative", "Guarantee", "TradeFinance"]

LIMIT_TYPES = ["SingleName", "Sector", "Country", "Aggregate"]

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF"]


# =============================================================================
# Mock Database Creation
# =============================================================================

def create_mock_mssql_db() -> sqlite3.Connection:
    """Create an in-memory SQLite database mimicking SQL Server credit risk tables."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Create credit_exposures table (15 columns)
    conn.execute("""
        CREATE TABLE credit_exposures (
            ASOF_DATE TEXT,
            COUNTERPARTY_ID TEXT,
            COUNTERPARTY_NAME TEXT,
            SECTOR TEXT,
            RATING TEXT,
            COUNTRY TEXT,
            EXPOSURE_TYPE TEXT,
            NOTIONAL REAL,
            MARK_TO_MARKET REAL,
            PFE REAL,
            CVA REAL,
            LGD REAL,
            PD REAL,
            EXPECTED_LOSS REAL,
            CURRENCY TEXT
        )
    """)

    # Create credit_limits table (7 columns)
    conn.execute("""
        CREATE TABLE credit_limits (
            COUNTERPARTY_ID TEXT,
            LIMIT_TYPE TEXT,
            LIMIT_AMOUNT REAL,
            UTILIZED REAL,
            AVAILABLE REAL,
            APPROVED_BY TEXT,
            EXPIRY_DATE TEXT
        )
    """)

    # Generate credit exposure data: ~8 counterparties × 4 exposure types × 30 days
    # Skip weekends to create realistic gaps the notebook can detect
    random.seed(42)
    base_date = date(2026, 1, 1)
    exposure_rows = []

    for day_offset in range(42):  # 42 calendar days → ~30 business days
        asof = base_date + timedelta(days=day_offset)
        # Skip weekends (Saturday=5, Sunday=6) to create timeseries gaps
        if asof.weekday() >= 5:
            continue
        asof_str = asof.strftime("%Y-%m-%d")

        for cp_id, cp_name, sector, rating, country in COUNTERPARTIES:
            for exp_type in EXPOSURE_TYPES:
                currency = random.choice(CURRENCIES)

                # Generate realistic credit exposure values
                notional = round(random.uniform(5_000_000, 500_000_000), 2)
                mtm = round(notional * random.uniform(-0.05, 0.15), 2)
                pfe = round(abs(notional) * random.uniform(0.01, 0.10), 2)

                # Risk metrics
                lgd = round(random.uniform(0.30, 0.65), 4)
                pd = round(random.uniform(0.0001, 0.05), 6)
                cva = round(pfe * lgd * pd * random.uniform(0.8, 1.2), 2)
                expected_loss = round(notional * lgd * pd, 2)

                exposure_rows.append((
                    asof_str, cp_id, cp_name, sector, rating, country,
                    exp_type, notional, mtm, pfe, cva, lgd, pd,
                    expected_loss, currency,
                ))

    conn.executemany("""
        INSERT INTO credit_exposures
        (ASOF_DATE, COUNTERPARTY_ID, COUNTERPARTY_NAME, SECTOR, RATING, COUNTRY,
         EXPOSURE_TYPE, NOTIONAL, MARK_TO_MARKET, PFE, CVA, LGD, PD, EXPECTED_LOSS, CURRENCY)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, exposure_rows)

    # Generate credit limits data
    approvers = [
        "J. Smith (CRO)", "M. Chen (Head of Credit)",
        "A. Patel (Risk Committee)", "R. Müller (Board)",
    ]
    limit_rows = []

    for cp_id, cp_name, sector, rating, country in COUNTERPARTIES:
        for limit_type in LIMIT_TYPES:
            limit_amount = round(random.uniform(100_000_000, 2_000_000_000), 2)
            utilized = round(limit_amount * random.uniform(0.20, 0.85), 2)
            available = round(limit_amount - utilized, 2)
            approved_by = random.choice(approvers)
            expiry_date = (date(2026, 1, 1) + timedelta(days=random.randint(90, 730))).strftime("%Y-%m-%d")

            limit_rows.append((
                cp_id, limit_type, limit_amount, utilized,
                available, approved_by, expiry_date,
            ))

    conn.executemany("""
        INSERT INTO credit_limits
        (COUNTERPARTY_ID, LIMIT_TYPE, LIMIT_AMOUNT, UTILIZED, AVAILABLE, APPROVED_BY, EXPIRY_DATE)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, limit_rows)

    conn.commit()
    return conn


# =============================================================================
# Mock MS-SQL Adapter
# =============================================================================

class MockMssqlAdapter:
    """Mock MS-SQL adapter that uses SQLite under the hood."""

    _db: sqlite3.Connection | None = None

    def __init__(self):
        self._ensure_db()

    def _ensure_db(self) -> sqlite3.Connection:
        """Ensure database is initialized with sample data."""
        if MockMssqlAdapter._db is None:
            MockMssqlAdapter._db = create_mock_mssql_db()
        return MockMssqlAdapter._db

    def execute(self, query: str, params: tuple = None) -> list[dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        db = self._ensure_db()
        cursor = db.cursor()
        translated = self._translate_tsql_to_sqlite(query)

        if params:
            cursor.execute(translated, params)
        else:
            cursor.execute(translated)

        columns = [desc[0].upper() for desc in cursor.description]
        rows = cursor.fetchall()
        cursor.close()

        return [dict(zip(columns, tuple(row))) for row in rows]

    def reset(self):
        """Reset the database with fresh data."""
        if MockMssqlAdapter._db is not None:
            MockMssqlAdapter._db.close()
        MockMssqlAdapter._db = create_mock_mssql_db()

    @staticmethod
    def _translate_tsql_to_sqlite(query: str) -> str:
        """Translate T-SQL syntax to SQLite."""
        translated = query

        # Strip [dbo]. schema prefix
        translated = re.sub(r"\[dbo\]\.", "", translated, flags=re.IGNORECASE)

        # Strip square brackets around identifiers
        translated = re.sub(r"\[(\w+)\]", r"\1", translated)

        # GETDATE() -> date('now')
        translated = re.sub(r"\bGETDATE\s*\(\s*\)", "date('now')", translated, flags=re.IGNORECASE)

        # CAST(x AS DATE) -> date(x)
        translated = re.sub(
            r"\bCAST\s*\(\s*(.+?)\s+AS\s+DATE\s*\)",
            r"date(\1)",
            translated,
            flags=re.IGNORECASE,
        )

        # CONVERT(DATE, 'YYYYMMDD', 112) -> date string
        translated = re.sub(
            r"\bCONVERT\s*\(\s*DATE\s*,\s*'(\d{8})'\s*,\s*112\s*\)",
            lambda m: f"'{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}'",
            translated,
            flags=re.IGNORECASE,
        )

        # DATEADD(DAY, -N, GETDATE()) -> date('now', '-N days')
        translated = re.sub(
            r"\bDATEADD\s*\(\s*DAY\s*,\s*(-?\d+)\s*,\s*GETDATE\s*\(\s*\)\s*\)",
            lambda m: f"date('now', '{m.group(1)} days')",
            translated,
            flags=re.IGNORECASE,
        )

        # General DATEADD(DAY, expr, base) -> date(base, expr || ' days')
        translated = re.sub(
            r"\bDATEADD\s*\(\s*DAY\s*,\s*(.+?)\s*,\s*(.+?)\s*\)",
            r"date(\2, \1 || ' days')",
            translated,
            flags=re.IGNORECASE,
        )

        # ISNULL -> COALESCE
        translated = re.sub(r"\bISNULL\s*\(", "COALESCE(", translated, flags=re.IGNORECASE)

        # TOP N -> LIMIT N (simple case only - before FROM)
        top_match = re.search(r"\bSELECT\s+TOP\s+(\d+)\b", translated, flags=re.IGNORECASE)
        if top_match:
            limit_val = top_match.group(1)
            translated = re.sub(r"\bTOP\s+\d+\b", "", translated, flags=re.IGNORECASE)
            translated = translated.rstrip().rstrip(";") + f" LIMIT {limit_val}"

        # NOLOCK hint
        translated = re.sub(r"\bWITH\s*\(\s*NOLOCK\s*\)", "", translated, flags=re.IGNORECASE)

        return translated


# =============================================================================
# Global Instance & Convenience Functions
# =============================================================================

_mock_db: sqlite3.Connection | None = None


def get_connection() -> MockMssqlAdapter:
    """Get a connection to the mock MS-SQL database."""
    return MockMssqlAdapter()


def reset_db():
    """Reset the mock database (for test isolation)."""
    MockMssqlAdapter._db = None
    MockMssqlAdapter()


def execute_query(query: str) -> list[dict[str, Any]]:
    """Execute a query against the mock MS-SQL database."""
    adapter = MockMssqlAdapter()
    return adapter.execute(query)
