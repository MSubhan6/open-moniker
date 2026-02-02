"""SQL Analyzer - Extract table references and compute metrics from SQL code."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class RefType(str, Enum):
    """Type of table reference in SQL."""

    FROM = "FROM"
    JOIN = "JOIN"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    TRUNCATE = "TRUNCATE"
    INTO = "INTO"
    MERGE = "MERGE"


class SqlType(str, Enum):
    """Type of SQL statement."""

    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    MERGE = "MERGE"
    CREATE = "CREATE"
    ALTER = "ALTER"
    DROP = "DROP"
    TRUNCATE = "TRUNCATE"
    GRANT = "GRANT"
    REVOKE = "REVOKE"
    COMMENT = "COMMENT"
    DDL = "DDL"
    DML = "DML"
    OTHER = "OTHER"


@dataclass
class TableReference:
    """A reference to a table found in SQL."""

    schema: str
    table: str
    ref_type: RefType
    full_name: str

    @classmethod
    def from_parts(cls, schema: str | None, table: str, ref_type: RefType) -> TableReference:
        """Create a TableReference from schema and table parts."""
        schema = schema.upper() if schema else "_UNKNOWN_"
        table = table.upper()
        full_name = f"{schema}.{table}"
        return cls(schema=schema, table=table, ref_type=ref_type, full_name=full_name)


class SqlAnalyzer:
    """Analyzes SQL code to extract table references and compute metrics."""

    # Pattern to match schema.table or just table names
    # Handles quoted identifiers and common Oracle naming conventions
    TABLE_NAME_PATTERN = r'''
        (?:
            "?([A-Za-z_][A-Za-z0-9_$#]*)"?  # Schema name (optional quotes)
            \.                               # Dot separator
        )?
        "?([A-Za-z_][A-Za-z0-9_$#]*)"?      # Table name (optional quotes)
    '''

    # Patterns for different SQL clauses
    FROM_PATTERN = re.compile(
        r'\bFROM\s+' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    JOIN_PATTERN = re.compile(
        r'\bJOIN\s+' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    INSERT_PATTERN = re.compile(
        r'\bINSERT\s+(?:INTO\s+)?' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    UPDATE_PATTERN = re.compile(
        r'\bUPDATE\s+' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    DELETE_PATTERN = re.compile(
        r'\bDELETE\s+(?:FROM\s+)?' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    TRUNCATE_PATTERN = re.compile(
        r'\bTRUNCATE\s+(?:TABLE\s+)?' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    MERGE_PATTERN = re.compile(
        r'\bMERGE\s+INTO\s+' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    INTO_PATTERN = re.compile(
        r'\bINTO\s+' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    # DDL patterns for CREATE/ALTER/DROP
    CREATE_TABLE_PATTERN = re.compile(
        r'\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    ALTER_TABLE_PATTERN = re.compile(
        r'\bALTER\s+TABLE\s+' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    DROP_TABLE_PATTERN = re.compile(
        r'\bDROP\s+TABLE\s+' + TABLE_NAME_PATTERN,
        re.IGNORECASE | re.VERBOSE
    )

    # SQL keywords to filter out (these are not table names)
    SQL_KEYWORDS = frozenset([
        'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'EXISTS',
        'BETWEEN', 'LIKE', 'IS', 'NULL', 'TRUE', 'FALSE', 'AS', 'ON',
        'INNER', 'LEFT', 'RIGHT', 'OUTER', 'FULL', 'CROSS', 'NATURAL',
        'JOIN', 'USING', 'GROUP', 'BY', 'HAVING', 'ORDER', 'ASC', 'DESC',
        'LIMIT', 'OFFSET', 'FETCH', 'FIRST', 'NEXT', 'ROWS', 'ONLY',
        'UNION', 'INTERSECT', 'EXCEPT', 'MINUS', 'ALL', 'DISTINCT',
        'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE', 'MERGE',
        'CREATE', 'ALTER', 'DROP', 'TRUNCATE', 'TABLE', 'VIEW', 'INDEX',
        'GRANT', 'REVOKE', 'COMMIT', 'ROLLBACK', 'SAVEPOINT',
        'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'CAST', 'CONVERT',
        'OVER', 'PARTITION', 'WINDOW', 'WITH', 'RECURSIVE',
        'DUAL', 'ROWNUM', 'ROWID', 'SYSDATE', 'SYSTIMESTAMP',
        'USER', 'CURRENT_USER', 'SESSION_USER', 'CURRENT_DATE',
        'CURRENT_TIMESTAMP', 'CURRENT_TIME', 'LOCALTIME', 'LOCALTIMESTAMP',
    ])

    def __init__(self):
        """Initialize the SQL analyzer."""
        pass

    def extract_table_references(self, sql_code: str) -> list[TableReference]:
        """Extract all table references from SQL code.

        Args:
            sql_code: The SQL code to analyze.

        Returns:
            A list of TableReference objects.
        """
        if not sql_code:
            return []

        # Remove comments before analysis
        sql_clean = self._remove_comments(sql_code)

        refs: list[TableReference] = []
        seen: set[tuple[str, str, RefType]] = set()

        # Extract from each clause type
        for pattern, ref_type in [
            (self.FROM_PATTERN, RefType.FROM),
            (self.JOIN_PATTERN, RefType.JOIN),
            (self.INSERT_PATTERN, RefType.INSERT),
            (self.UPDATE_PATTERN, RefType.UPDATE),
            (self.DELETE_PATTERN, RefType.DELETE),
            (self.TRUNCATE_PATTERN, RefType.TRUNCATE),
            (self.MERGE_PATTERN, RefType.MERGE),
            (self.INTO_PATTERN, RefType.INTO),
            (self.CREATE_TABLE_PATTERN, RefType.FROM),  # Treat DDL as FROM
            (self.ALTER_TABLE_PATTERN, RefType.FROM),
            (self.DROP_TABLE_PATTERN, RefType.FROM),
        ]:
            for match in pattern.finditer(sql_clean):
                schema = match.group(1)
                table = match.group(2)

                # Skip SQL keywords
                if table.upper() in self.SQL_KEYWORDS:
                    continue

                # Skip common non-table patterns
                if self._is_common_non_table(table):
                    continue

                # Create reference
                key = (schema.upper() if schema else "_UNKNOWN_", table.upper(), ref_type)
                if key not in seen:
                    seen.add(key)
                    refs.append(TableReference.from_parts(schema, table, ref_type))

        return refs

    def get_sql_type(self, sql_code: str) -> SqlType:
        """Determine the type of SQL statement.

        Args:
            sql_code: The SQL code to analyze.

        Returns:
            The SqlType enum value.
        """
        if not sql_code:
            return SqlType.OTHER

        # Clean and normalize
        sql_clean = self._remove_comments(sql_code).strip().upper()

        # Check for common statement types
        if sql_clean.startswith('SELECT') or sql_clean.startswith('WITH'):
            return SqlType.SELECT
        elif sql_clean.startswith('INSERT'):
            return SqlType.INSERT
        elif sql_clean.startswith('UPDATE'):
            return SqlType.UPDATE
        elif sql_clean.startswith('DELETE'):
            return SqlType.DELETE
        elif sql_clean.startswith('MERGE'):
            return SqlType.MERGE
        elif sql_clean.startswith('CREATE'):
            return SqlType.CREATE
        elif sql_clean.startswith('ALTER'):
            return SqlType.ALTER
        elif sql_clean.startswith('DROP'):
            return SqlType.DROP
        elif sql_clean.startswith('TRUNCATE'):
            return SqlType.TRUNCATE
        elif sql_clean.startswith('GRANT'):
            return SqlType.GRANT
        elif sql_clean.startswith('REVOKE'):
            return SqlType.REVOKE
        elif sql_clean.startswith('COMMENT'):
            return SqlType.COMMENT

        return SqlType.OTHER

    def compute_complexity(self, sql_code: str) -> dict[str, int]:
        """Compute complexity metrics for SQL code.

        Args:
            sql_code: The SQL code to analyze.

        Returns:
            A dict with complexity_score, nesting_depth, and subquery_count.
        """
        if not sql_code:
            return {"complexity_score": 0, "nesting_depth": 0, "subquery_count": 0}

        sql_clean = self._remove_comments(sql_code)
        sql_upper = sql_clean.upper()

        # Count various SQL elements
        join_count = len(re.findall(r'\bJOIN\b', sql_upper))
        subquery_count = sql_upper.count('(SELECT')
        case_count = len(re.findall(r'\bCASE\b', sql_upper))
        union_count = len(re.findall(r'\bUNION\b', sql_upper))
        group_by = 1 if 'GROUP BY' in sql_upper else 0
        having = 1 if 'HAVING' in sql_upper else 0
        distinct = 1 if 'DISTINCT' in sql_upper else 0
        order_by = 1 if 'ORDER BY' in sql_upper else 0
        cte_count = len(re.findall(r'\bWITH\s+\w+\s+AS\s*\(', sql_upper))
        window_count = len(re.findall(r'\bOVER\s*\(', sql_upper))

        # Calculate nesting depth (approximate based on parentheses)
        nesting_depth = self._calculate_nesting_depth(sql_clean)

        # Compute complexity score (weighted sum)
        complexity_score = (
            join_count * 3 +
            subquery_count * 5 +
            case_count * 2 +
            union_count * 3 +
            group_by * 2 +
            having * 2 +
            distinct * 1 +
            order_by * 1 +
            cte_count * 4 +
            window_count * 3 +
            nesting_depth * 2
        )

        return {
            "complexity_score": complexity_score,
            "nesting_depth": nesting_depth,
            "subquery_count": subquery_count,
        }

    def _remove_comments(self, sql_code: str) -> str:
        """Remove SQL comments from code."""
        # Remove single-line comments
        sql_code = re.sub(r'--[^\n]*', '', sql_code)
        # Remove multi-line comments
        sql_code = re.sub(r'/\*.*?\*/', '', sql_code, flags=re.DOTALL)
        return sql_code

    def _calculate_nesting_depth(self, sql_code: str) -> int:
        """Calculate the maximum nesting depth of parentheses."""
        max_depth = 0
        current_depth = 0
        in_string = False
        string_char = None

        for char in sql_code:
            if char in ("'", '"') and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                in_string = False
                string_char = None
            elif not in_string:
                if char == '(':
                    current_depth += 1
                    max_depth = max(max_depth, current_depth)
                elif char == ')':
                    current_depth = max(0, current_depth - 1)

        return max_depth

    def _is_common_non_table(self, name: str) -> bool:
        """Check if a name is a common non-table identifier."""
        name_upper = name.upper()
        non_tables = {
            # Common Oracle pseudo-tables/functions
            'DUAL', 'SYS', 'SYSTEM',
            # Common column aliases mistaken for tables
            'T', 'T1', 'T2', 'A', 'B', 'C', 'X', 'Y', 'Z',
            # Numbers that might appear
            '1', '2', '3',
        }
        return name_upper in non_tables or len(name) == 1

    def analyze(self, sql_code: str) -> dict:
        """Perform full analysis of SQL code.

        Args:
            sql_code: The SQL code to analyze.

        Returns:
            A dict with table_refs, sql_type, and complexity metrics.
        """
        table_refs = self.extract_table_references(sql_code)
        sql_type = self.get_sql_type(sql_code)
        complexity = self.compute_complexity(sql_code)

        return {
            "table_refs": table_refs,
            "sql_type": sql_type.value,
            **complexity,
        }
