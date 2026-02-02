"""Repository layer for SQL Catalog database operations."""

from __future__ import annotations

import sqlite3
from typing import Any

from .analyzer import TableReference
from .models import (
    Schema,
    Table,
    SqlStatement,
    TableRef,
    ImportHistory,
    SchemaInfo,
    TableInfo,
    StatementInfo,
    TableRefInfo,
)


class SqlCatalogRepository:
    """Repository for SQL Catalog database operations."""

    def __init__(self, conn: sqlite3.Connection):
        """Initialize the repository.

        Args:
            conn: SQLite database connection.
        """
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # =========================================================================
    # Schema Operations
    # =========================================================================

    def get_or_create_schema(self, name: str) -> int:
        """Get or create a schema by name.

        Args:
            name: The schema name (e.g., "HR", "SALES").

        Returns:
            The schema ID.
        """
        cursor = self.conn.execute(
            "SELECT id FROM schemas WHERE name = ?",
            (name.upper(),)
        )
        row = cursor.fetchone()
        if row:
            return row["id"]

        cursor = self.conn.execute(
            "INSERT INTO schemas (name, display_name) VALUES (?, ?)",
            (name.upper(), name.upper())
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_schemas(self) -> list[SchemaInfo]:
        """List all schemas with statistics.

        Returns:
            List of SchemaInfo objects.
        """
        cursor = self.conn.execute("""
            SELECT
                s.name,
                s.display_name,
                s.statement_count,
                COUNT(DISTINCT t.id) as table_count
            FROM schemas s
            LEFT JOIN tables t ON t.schema_id = s.id
            GROUP BY s.id
            ORDER BY s.name
        """)

        return [
            SchemaInfo(
                name=row["name"],
                display_name=row["display_name"],
                statement_count=row["statement_count"],
                table_count=row["table_count"],
            )
            for row in cursor.fetchall()
        ]

    def get_schema(self, name: str) -> Schema | None:
        """Get a schema by name.

        Args:
            name: The schema name.

        Returns:
            Schema object or None.
        """
        cursor = self.conn.execute(
            "SELECT * FROM schemas WHERE name = ?",
            (name.upper(),)
        )
        row = cursor.fetchone()
        if not row:
            return None

        # Get table count
        table_cursor = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM tables WHERE schema_id = ?",
            (row["id"],)
        )
        table_count = table_cursor.fetchone()["cnt"]

        return Schema(
            id=row["id"],
            name=row["name"],
            display_name=row["display_name"],
            description=row["description"],
            statement_count=row["statement_count"],
            table_count=table_count,
            created_at=row["created_at"],
        )

    def update_schema_statement_count(self, schema_id: int) -> None:
        """Update the statement count for a schema.

        Args:
            schema_id: The schema ID.
        """
        self.conn.execute("""
            UPDATE schemas SET statement_count = (
                SELECT COUNT(DISTINCT str.statement_id)
                FROM statement_table_refs str
                JOIN tables t ON str.table_id = t.id
                WHERE t.schema_id = ?
            ) WHERE id = ?
        """, (schema_id, schema_id))
        self.conn.commit()

    # =========================================================================
    # Table Operations
    # =========================================================================

    def get_or_create_table(self, schema_name: str, table_name: str) -> int:
        """Get or create a table by schema and name.

        Args:
            schema_name: The schema name (e.g., "HR").
            table_name: The table name (e.g., "EMPLOYEES").

        Returns:
            The table ID.
        """
        full_name = f"{schema_name.upper()}.{table_name.upper()}"

        cursor = self.conn.execute(
            "SELECT id FROM tables WHERE full_name = ?",
            (full_name,)
        )
        row = cursor.fetchone()
        if row:
            return row["id"]

        # Get or create schema first
        schema_id = self.get_or_create_schema(schema_name)

        cursor = self.conn.execute(
            "INSERT INTO tables (schema_id, name, full_name) VALUES (?, ?, ?)",
            (schema_id, table_name.upper(), full_name)
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_tables(self, schema_name: str | None = None) -> list[TableInfo]:
        """List tables, optionally filtered by schema.

        Args:
            schema_name: Optional schema name to filter by.

        Returns:
            List of TableInfo objects.
        """
        if schema_name:
            cursor = self.conn.execute("""
                SELECT t.name, t.full_name, t.statement_count
                FROM tables t
                JOIN schemas s ON t.schema_id = s.id
                WHERE s.name = ?
                ORDER BY t.name
            """, (schema_name.upper(),))
        else:
            cursor = self.conn.execute("""
                SELECT name, full_name, statement_count
                FROM tables
                ORDER BY full_name
            """)

        return [
            TableInfo(
                name=row["name"],
                full_name=row["full_name"],
                statement_count=row["statement_count"],
            )
            for row in cursor.fetchall()
        ]

    def get_table(self, full_name: str) -> Table | None:
        """Get a table by full name.

        Args:
            full_name: The full table name (e.g., "HR.EMPLOYEES").

        Returns:
            Table object or None.
        """
        cursor = self.conn.execute(
            "SELECT * FROM tables WHERE full_name = ?",
            (full_name.upper(),)
        )
        row = cursor.fetchone()
        if not row:
            return None

        return Table(
            id=row["id"],
            schema_id=row["schema_id"],
            name=row["name"],
            full_name=row["full_name"],
            statement_count=row["statement_count"],
            created_at=row["created_at"],
        )

    def update_table_statement_count(self, table_id: int) -> None:
        """Update the statement count for a table.

        Args:
            table_id: The table ID.
        """
        self.conn.execute("""
            UPDATE tables SET statement_count = (
                SELECT COUNT(DISTINCT statement_id)
                FROM statement_table_refs
                WHERE table_id = ?
            ) WHERE id = ?
        """, (table_id, table_id))
        self.conn.commit()

    # =========================================================================
    # Statement Operations
    # =========================================================================

    def insert_statement(
        self,
        data: dict[str, Any],
        table_refs: list[TableReference],
        batch_id: str,
    ) -> int:
        """Insert a SQL statement with its table references.

        Args:
            data: Statement data from source database.
            table_refs: List of TableReference objects.
            batch_id: Import batch ID.

        Returns:
            The statement ID.
        """
        cursor = self.conn.execute("""
            INSERT INTO sql_statements (
                source_id, space_key, space_name, page_id, page_title,
                last_modified, sql_language, sql_title, sql_description,
                sql_source, sql_code, line_count, sql_type,
                complexity_score, nesting_depth, subquery_count,
                import_batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("source_id") or data.get("id"),
            data["space_key"],
            data.get("space_name"),
            data["page_id"],
            data.get("page_title"),
            data.get("last_modified"),
            data.get("sql_language"),
            data.get("sql_title"),
            data.get("sql_description"),
            data.get("sql_source"),
            data["sql_code"],
            data.get("line_count"),
            data.get("sql_type"),
            data.get("complexity_score"),
            data.get("nesting_depth"),
            data.get("subquery_count"),
            batch_id,
        ))
        statement_id = cursor.lastrowid

        # Insert table references
        for ref in table_refs:
            table_id = self.get_or_create_table(ref.schema, ref.table)
            try:
                self.conn.execute("""
                    INSERT INTO statement_table_refs (statement_id, table_id, ref_type)
                    VALUES (?, ?, ?)
                """, (statement_id, table_id, ref.ref_type.value))
            except sqlite3.IntegrityError:
                # Duplicate reference, skip
                pass

        self.conn.commit()
        return statement_id

    def list_statements(
        self,
        table_full_name: str | None = None,
        sql_type: str | None = None,
        space_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StatementInfo]:
        """List statements with optional filters.

        Args:
            table_full_name: Filter by table (e.g., "HR.EMPLOYEES").
            sql_type: Filter by SQL type (e.g., "SELECT").
            space_key: Filter by Confluence space.
            limit: Maximum number of results.
            offset: Offset for pagination.

        Returns:
            List of StatementInfo objects.
        """
        conditions = []
        params: list[Any] = []

        if table_full_name:
            conditions.append("""
                s.id IN (
                    SELECT str.statement_id
                    FROM statement_table_refs str
                    JOIN tables t ON str.table_id = t.id
                    WHERE t.full_name = ?
                )
            """)
            params.append(table_full_name.upper())

        if sql_type:
            conditions.append("s.sql_type = ?")
            params.append(sql_type.upper())

        if space_key:
            conditions.append("s.space_key = ?")
            params.append(space_key)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT
                s.id, s.sql_type, s.page_title, s.space_key,
                s.line_count, s.complexity_score
            FROM sql_statements s
            {where_clause}
            ORDER BY s.id
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor = self.conn.execute(query, params)

        results = []
        for row in cursor.fetchall():
            # Get ref types for this statement
            ref_cursor = self.conn.execute("""
                SELECT DISTINCT ref_type
                FROM statement_table_refs
                WHERE statement_id = ?
            """, (row["id"],))
            ref_types = [r["ref_type"] for r in ref_cursor.fetchall()]

            results.append(StatementInfo(
                id=row["id"],
                sql_type=row["sql_type"],
                page_title=row["page_title"],
                space_key=row["space_key"],
                line_count=row["line_count"],
                complexity_score=row["complexity_score"],
                ref_types=ref_types,
            ))

        return results

    def get_statement(self, statement_id: int) -> SqlStatement | None:
        """Get a statement by ID.

        Args:
            statement_id: The statement ID.

        Returns:
            SqlStatement object or None.
        """
        cursor = self.conn.execute(
            "SELECT * FROM sql_statements WHERE id = ?",
            (statement_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        return SqlStatement(
            id=row["id"],
            source_id=row["source_id"],
            space_key=row["space_key"],
            space_name=row["space_name"],
            page_id=row["page_id"],
            page_title=row["page_title"],
            last_modified=row["last_modified"],
            sql_language=row["sql_language"],
            sql_title=row["sql_title"],
            sql_description=row["sql_description"],
            sql_source=row["sql_source"],
            sql_code=row["sql_code"],
            line_count=row["line_count"],
            sql_type=row["sql_type"],
            complexity_score=row["complexity_score"],
            nesting_depth=row["nesting_depth"],
            subquery_count=row["subquery_count"],
            imported_at=row["imported_at"],
            import_batch_id=row["import_batch_id"],
        )

    def get_statement_tables(self, statement_id: int) -> list[TableRefInfo]:
        """Get tables referenced by a statement.

        Args:
            statement_id: The statement ID.

        Returns:
            List of TableRefInfo objects.
        """
        cursor = self.conn.execute("""
            SELECT t.full_name, str.ref_type
            FROM statement_table_refs str
            JOIN tables t ON str.table_id = t.id
            WHERE str.statement_id = ?
            ORDER BY t.full_name
        """, (statement_id,))

        return [
            TableRefInfo(full_name=row["full_name"], ref_type=row["ref_type"])
            for row in cursor.fetchall()
        ]

    def get_statements_for_table(self, full_name: str) -> list[StatementInfo]:
        """Get all statements that reference a table.

        Args:
            full_name: The full table name (e.g., "HR.EMPLOYEES").

        Returns:
            List of StatementInfo objects.
        """
        return self.list_statements(table_full_name=full_name, limit=1000)

    def count_statements(
        self,
        table_full_name: str | None = None,
        sql_type: str | None = None,
        space_key: str | None = None,
    ) -> int:
        """Count statements matching filters.

        Args:
            table_full_name: Filter by table.
            sql_type: Filter by SQL type.
            space_key: Filter by space.

        Returns:
            Count of matching statements.
        """
        conditions = []
        params: list[Any] = []

        if table_full_name:
            conditions.append("""
                s.id IN (
                    SELECT str.statement_id
                    FROM statement_table_refs str
                    JOIN tables t ON str.table_id = t.id
                    WHERE t.full_name = ?
                )
            """)
            params.append(table_full_name.upper())

        if sql_type:
            conditions.append("s.sql_type = ?")
            params.append(sql_type.upper())

        if space_key:
            conditions.append("s.space_key = ?")
            params.append(space_key)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"SELECT COUNT(*) as cnt FROM sql_statements s {where_clause}"
        cursor = self.conn.execute(query, params)
        return cursor.fetchone()["cnt"]

    # =========================================================================
    # Import History Operations
    # =========================================================================

    def record_import(
        self,
        batch_id: str,
        source_db_path: str,
        statements_imported: int,
        schemas_discovered: int,
        tables_discovered: int,
    ) -> int:
        """Record an import operation.

        Args:
            batch_id: Unique batch identifier.
            source_db_path: Path to source database.
            statements_imported: Number of statements imported.
            schemas_discovered: Number of new schemas.
            tables_discovered: Number of new tables.

        Returns:
            The import history ID.
        """
        cursor = self.conn.execute("""
            INSERT INTO import_history (
                batch_id, source_db_path, statements_imported,
                schemas_discovered, tables_discovered
            ) VALUES (?, ?, ?, ?, ?)
        """, (batch_id, source_db_path, statements_imported,
              schemas_discovered, tables_discovered))
        self.conn.commit()
        return cursor.lastrowid

    def list_imports(self, limit: int = 100) -> list[ImportHistory]:
        """List import history.

        Args:
            limit: Maximum number of results.

        Returns:
            List of ImportHistory objects.
        """
        cursor = self.conn.execute("""
            SELECT * FROM import_history
            ORDER BY imported_at DESC
            LIMIT ?
        """, (limit,))

        return [
            ImportHistory(
                id=row["id"],
                batch_id=row["batch_id"],
                source_db_path=row["source_db_path"],
                statements_imported=row["statements_imported"],
                schemas_discovered=row["schemas_discovered"],
                tables_discovered=row["tables_discovered"],
                imported_at=row["imported_at"],
            )
            for row in cursor.fetchall()
        ]

    def get_last_import(self) -> ImportHistory | None:
        """Get the most recent import.

        Returns:
            ImportHistory object or None.
        """
        imports = self.list_imports(limit=1)
        return imports[0] if imports else None

    # =========================================================================
    # Statistics Operations
    # =========================================================================

    def get_summary_stats(self) -> dict[str, Any]:
        """Get summary statistics for the catalog.

        Returns:
            Dictionary with summary stats.
        """
        # Total counts
        stmt_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM sql_statements"
        ).fetchone()["cnt"]

        schema_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM schemas"
        ).fetchone()["cnt"]

        table_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM tables"
        ).fetchone()["cnt"]

        # Statements by type
        type_cursor = self.conn.execute("""
            SELECT sql_type, COUNT(*) as cnt
            FROM sql_statements
            GROUP BY sql_type
            ORDER BY cnt DESC
        """)
        by_type = {
            row["sql_type"] or "UNKNOWN": row["cnt"]
            for row in type_cursor.fetchall()
        }

        # Statements by space
        space_cursor = self.conn.execute("""
            SELECT space_key, COUNT(*) as cnt
            FROM sql_statements
            GROUP BY space_key
            ORDER BY cnt DESC
            LIMIT 10
        """)
        by_space = {row["space_key"]: row["cnt"] for row in space_cursor.fetchall()}

        # Top tables by statement count
        top_tables_cursor = self.conn.execute("""
            SELECT name, full_name, statement_count
            FROM tables
            ORDER BY statement_count DESC
            LIMIT 10
        """)
        top_tables = [
            TableInfo(
                name=row["name"],
                full_name=row["full_name"],
                statement_count=row["statement_count"],
            )
            for row in top_tables_cursor.fetchall()
        ]

        return {
            "total_statements": stmt_count,
            "total_schemas": schema_count,
            "total_tables": table_count,
            "statements_by_type": by_type,
            "statements_by_space": by_space,
            "top_tables": top_tables,
        }

    def update_all_counts(self) -> None:
        """Update all denormalized counts for schemas and tables."""
        # Update table counts
        self.conn.execute("""
            UPDATE tables SET statement_count = (
                SELECT COUNT(DISTINCT statement_id)
                FROM statement_table_refs
                WHERE table_id = tables.id
            )
        """)

        # Update schema counts
        self.conn.execute("""
            UPDATE schemas SET statement_count = (
                SELECT COUNT(DISTINCT str.statement_id)
                FROM statement_table_refs str
                JOIN tables t ON str.table_id = t.id
                WHERE t.schema_id = schemas.id
            )
        """)

        self.conn.commit()
