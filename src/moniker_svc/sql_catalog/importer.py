"""SQL Importer - Import SQL statements from source databases."""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .analyzer import SqlAnalyzer
from .db import init_db
from .repository import SqlCatalogRepository


class SqlImporter:
    """Imports SQL statements from source databases."""

    def __init__(
        self,
        target_db_path: str | Path,
        source_db_path: str | Path | None = None,
    ):
        """Initialize the importer.

        Args:
            target_db_path: Path to the target sql_catalog.db.
            source_db_path: Default path to source sql_queries.db.
        """
        self.target_db_path = Path(target_db_path)
        self.default_source_db_path = Path(source_db_path) if source_db_path else None
        self.analyzer = SqlAnalyzer()

    def import_from_db(
        self,
        source_db_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Import SQL statements from a source database.

        Args:
            source_db_path: Path to source database. Uses default if not provided.

        Returns:
            Import statistics.
        """
        start_time = time.time()

        # Resolve source path
        source_path = Path(source_db_path) if source_db_path else self.default_source_db_path
        if not source_path:
            raise ValueError("No source database path provided")

        if not source_path.exists():
            raise FileNotFoundError(f"Source database not found: {source_path}")

        # Generate batch ID
        batch_id = str(uuid.uuid4())[:8]

        # Connect to both databases
        target_conn = init_db(self.target_db_path)
        repo = SqlCatalogRepository(target_conn)

        source_conn = sqlite3.connect(str(source_path))
        source_conn.row_factory = sqlite3.Row

        # Count initial schemas and tables
        initial_schemas = target_conn.execute(
            "SELECT COUNT(*) as cnt FROM schemas"
        ).fetchone()["cnt"]
        initial_tables = target_conn.execute(
            "SELECT COUNT(*) as cnt FROM tables"
        ).fetchone()["cnt"]

        # Read statements from source
        statements = self._read_source_statements(source_conn)
        source_conn.close()

        # Import each statement
        statements_imported = 0
        for stmt_data in statements:
            sql_code = stmt_data.get("sql_code", "")
            if not sql_code:
                continue

            # Analyze the SQL
            analysis = self.analyzer.analyze(sql_code)

            # Add analysis results to statement data
            stmt_data["sql_type"] = analysis["sql_type"]
            stmt_data["complexity_score"] = analysis["complexity_score"]
            stmt_data["nesting_depth"] = analysis["nesting_depth"]
            stmt_data["subquery_count"] = analysis["subquery_count"]

            # Insert statement with table references
            repo.insert_statement(
                data=stmt_data,
                table_refs=analysis["table_refs"],
                batch_id=batch_id,
            )
            statements_imported += 1

        # Update denormalized counts
        repo.update_all_counts()

        # Count new schemas and tables
        final_schemas = target_conn.execute(
            "SELECT COUNT(*) as cnt FROM schemas"
        ).fetchone()["cnt"]
        final_tables = target_conn.execute(
            "SELECT COUNT(*) as cnt FROM tables"
        ).fetchone()["cnt"]

        schemas_discovered = final_schemas - initial_schemas
        tables_discovered = final_tables - initial_tables

        # Record import
        repo.record_import(
            batch_id=batch_id,
            source_db_path=str(source_path),
            statements_imported=statements_imported,
            schemas_discovered=schemas_discovered,
            tables_discovered=tables_discovered,
        )

        target_conn.close()

        elapsed = time.time() - start_time

        return {
            "batch_id": batch_id,
            "source_db_path": str(source_path),
            "statements_imported": statements_imported,
            "schemas_discovered": schemas_discovered,
            "tables_discovered": tables_discovered,
            "import_time_seconds": round(elapsed, 2),
        }

    def _read_source_statements(
        self,
        conn: sqlite3.Connection,
    ) -> list[dict[str, Any]]:
        """Read statements from source database.

        Supports multiple schema formats that might be in the source DB.

        Args:
            conn: Connection to source database.

        Returns:
            List of statement dictionaries.
        """
        # Try to detect the schema
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row["name"] for row in cursor.fetchall()}

        if "sql_queries" in tables:
            return self._read_sql_queries_table(conn, "sql_queries")
        elif "sql_scripts" in tables:
            return self._read_sql_queries_table(conn, "sql_scripts")
        elif "statements" in tables:
            return self._read_statements_table(conn)
        else:
            raise ValueError(
                f"Unknown source schema. Found tables: {tables}. "
                "Expected 'sql_queries', 'sql_scripts', or 'statements'."
            )

    def _read_sql_queries_table(
        self,
        conn: sqlite3.Connection,
        table_name: str = "sql_queries",
    ) -> list[dict[str, Any]]:
        """Read from sql_queries or sql_scripts table (confluence extraction format)."""
        # Get column names to handle schema variations
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        columns = {row["name"] for row in cursor.fetchall()}

        # Build select based on available columns
        select_cols = ["id"]

        # Map expected columns to actual columns
        column_mapping = {
            "space_key": ["space_key", "spaceKey"],
            "space_name": ["space_name", "spaceName"],
            "page_id": ["page_id", "pageId"],
            "page_title": ["page_title", "pageTitle"],
            "last_modified": ["last_modified", "lastModified"],
            "sql_language": ["sql_language", "language"],
            "sql_title": ["sql_title", "title"],
            "sql_description": ["sql_description", "description"],
            "sql_source": ["sql_source", "source"],
            "sql_code": ["sql_code", "code", "sql"],
            "line_count": ["line_count", "lineCount"],
        }

        found_columns = {}
        for target, candidates in column_mapping.items():
            for candidate in candidates:
                if candidate in columns:
                    found_columns[target] = candidate
                    break

        # Ensure we have sql_code
        if "sql_code" not in found_columns:
            raise ValueError("Source table missing sql_code/code/sql column")

        # Ensure we have required columns
        if "space_key" not in found_columns:
            found_columns["space_key"] = "'UNKNOWN'"  # Default value
        if "page_id" not in found_columns:
            found_columns["page_id"] = "id"  # Use id as page_id

        # Build query
        select_parts = ["id as source_id"]
        for target, source in found_columns.items():
            if source.startswith("'"):  # Literal value
                select_parts.append(f"{source} as {target}")
            else:
                select_parts.append(f"{source} as {target}")

        query = f"SELECT {', '.join(select_parts)} FROM {table_name}"
        cursor = conn.execute(query)

        return [dict(row) for row in cursor.fetchall()]

    def _read_statements_table(
        self,
        conn: sqlite3.Connection,
    ) -> list[dict[str, Any]]:
        """Read from statements table (alternative format)."""
        cursor = conn.execute("""
            SELECT
                id as source_id,
                COALESCE(space_key, 'UNKNOWN') as space_key,
                space_name,
                COALESCE(page_id, CAST(id AS TEXT)) as page_id,
                page_title,
                last_modified,
                language as sql_language,
                title as sql_title,
                description as sql_description,
                source as sql_source,
                code as sql_code,
                line_count
            FROM statements
        """)
        return [dict(row) for row in cursor.fetchall()]


def import_sql_catalog(
    target_db_path: str | Path,
    source_db_path: str | Path,
) -> dict[str, Any]:
    """Convenience function to import SQL statements.

    Args:
        target_db_path: Path to target sql_catalog.db.
        source_db_path: Path to source sql_queries.db.

    Returns:
        Import statistics.
    """
    importer = SqlImporter(target_db_path)
    return importer.import_from_db(source_db_path)
