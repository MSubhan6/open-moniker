"""MS-SQL dialect implementation."""

from __future__ import annotations

from .base import VersionDialect


class MSSQLDialect(VersionDialect):
    """MS-SQL dialect for version type translation.

    Uses T-SQL date functions:
    - CAST(GETDATE() AS DATE) for current date
    - CONVERT(DATE, 'YYYYMMDD', 112) for date literals
    - DATEADD(unit, -N, CAST(GETDATE() AS DATE)) for lookback
    """

    @property
    def name(self) -> str:
        return "mssql"

    def current_date(self) -> str:
        return "CAST(GETDATE() AS DATE)"

    def date_literal(self, date_str: str) -> str:
        """Convert YYYYMMDD to MS-SQL date literal."""
        return f"CONVERT(DATE, '{date_str}', 112)"

    def lookback_start(self, value: int, unit: str) -> str:
        """Generate MS-SQL DATEADD expression for lookback.

        MS-SQL uses: DATEADD(part, amount, date)
        """
        unit_upper = unit.upper()
        unit_map = {
            "Y": "YEAR",
            "M": "MONTH",
            "W": "WEEK",
            "D": "DAY",
        }
        sql_unit = unit_map.get(unit_upper, "DAY")
        return f"DATEADD({sql_unit}, -{value}, CAST(GETDATE() AS DATE))"
