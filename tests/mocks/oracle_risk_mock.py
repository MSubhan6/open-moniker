"""Mock Oracle database with CVaR risk data for testing.

Uses SQLite in-memory to simulate the Oracle risk tables.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any
import random


# Sample data configuration
PORTFOLIOS = [
    ("758", "A"),
    ("758", "B"),
    ("622", "A"),
    ("622", "B"),
]

CURRENCIES = ["USD", "EUR", "GBP", "JPY"]

SECURITIES = [
    "B0YHY8V7",
    "3140K1AP1",
    "3140L7Y55",
    "3164XW9F3",
    "353469109",
    "31428XCE4",
    "31417EQ38",
    "35086T109",
]

ACCT_KEYS = [
    "758-IDX-16220-[TPH200010]",
    "758-3938",
    "758-IDX-16480-[MESH20007]",
    "758-IDX-16620-[RTYH20002]",
    "758-IDX-13930-[SW00AA483]",
    "758-IDX-16620-[RTYZ10037]",
]


def create_mock_oracle_db() -> sqlite3.Connection:
    """Create an in-memory SQLite database mimicking Oracle risk tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create the CVaR table matching the structure from the screenshots
    conn.execute("""
        CREATE TABLE te_stress_tail_risk_pnl (
            report_id INTEGER,
            asof_date TEXT,
            port_no TEXT,
            port_type TEXT,
            ssm_id TEXT,
            base_currency TEXT,
            acct_key TEXT,
            lt_id INTEGER,
            lt_id_2 INTEGER,
            cvar_coeff REAL,
            cvar REAL
        )
    """)

    # Generate sample timeseries data
    base_date = date(2021, 12, 1)
    rows = []

    for report_id in [1, 2, 3]:
        for day_offset in range(30):  # 30 days of history
            asof = base_date + timedelta(days=day_offset)
            asof_str = asof.strftime("%Y-%m-%d")

            for port_no, port_type in PORTFOLIOS:
                for currency in CURRENCIES:
                    # Each portfolio/currency combo has a subset of securities
                    securities_sample = random.sample(SECURITIES, k=random.randint(3, 6))

                    for ssm_id in securities_sample:
                        acct_key = random.choice(ACCT_KEYS)
                        lt_id = random.choice([0, 24])
                        lt_id_2 = random.choice([0, None])

                        # Generate realistic-looking CVaR values
                        cvar_coeff = random.uniform(-0.0001, 0.0001)
                        cvar = random.uniform(-0.02, 0.02)

                        rows.append((
                            report_id,
                            asof_str,
                            port_no,
                            port_type,
                            ssm_id,
                            currency,
                            acct_key,
                            lt_id,
                            lt_id_2,
                            cvar_coeff,
                            cvar,
                        ))

    conn.executemany("""
        INSERT INTO te_stress_tail_risk_pnl
        (report_id, asof_date, port_no, port_type, ssm_id, base_currency,
         acct_key, lt_id, lt_id_2, cvar_coeff, cvar)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    conn.commit()
    return conn


class MockOracleConnection:
    """Mock Oracle connection that uses SQLite under the hood."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def cursor(self):
        return MockOracleCursor(self._conn.cursor())

    def close(self):
        self._conn.close()


class MockOracleCursor:
    """Mock Oracle cursor wrapping SQLite cursor."""

    def __init__(self, cursor: sqlite3.Cursor):
        self._cursor = cursor
        self._description = None

    @property
    def description(self):
        return self._description

    def execute(self, query: str, params: tuple = None):
        # Translate Oracle-specific SQL to SQLite
        translated = self._translate_oracle_to_sqlite(query)

        if params:
            self._cursor.execute(translated, params)
        else:
            self._cursor.execute(translated)

        # Build description like Oracle does
        if self._cursor.description:
            self._description = [
                (col[0].upper(), None, None, None, None, None, None)
                for col in self._cursor.description
            ]
        return self

    def fetchall(self) -> list[tuple]:
        rows = self._cursor.fetchall()
        # Convert sqlite3.Row to tuple
        return [tuple(row) for row in rows]

    def fetchone(self) -> tuple | None:
        row = self._cursor.fetchone()
        return tuple(row) if row else None

    def close(self):
        self._cursor.close()

    def _translate_oracle_to_sqlite(self, query: str) -> str:
        """Translate Oracle SQL syntax to SQLite."""
        translated = query

        # Handle Oracle's || concat (same in SQLite, so OK)
        # Handle TO_DATE - SQLite uses strings directly
        import re
        translated = re.sub(
            r"TO_DATE\('(\d{8})',\s*'YYYYMMDD'\)",
            lambda m: f"'{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}'",
            translated
        )

        # Handle SYSDATE -> date('now')
        translated = translated.replace("SYSDATE", "date('now')")

        # Handle NVL -> COALESCE
        translated = re.sub(r"\bNVL\s*\(", "COALESCE(", translated, flags=re.IGNORECASE)

        return translated


# Global mock database instance for testing
_mock_db: sqlite3.Connection | None = None


def get_mock_oracle_connection() -> MockOracleConnection:
    """Get a connection to the mock Oracle database."""
    global _mock_db
    if _mock_db is None:
        _mock_db = create_mock_oracle_db()
    return MockOracleConnection(_mock_db)


def reset_mock_oracle_db():
    """Reset the mock database (for test isolation)."""
    global _mock_db
    if _mock_db:
        _mock_db.close()
    _mock_db = create_mock_oracle_db()


def execute_query(query: str) -> list[dict[str, Any]]:
    """Execute a query against the mock Oracle database."""
    conn = get_mock_oracle_connection()
    cursor = conn.cursor()
    cursor.execute(query)

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    cursor.close()

    return [dict(zip(columns, row)) for row in rows]
