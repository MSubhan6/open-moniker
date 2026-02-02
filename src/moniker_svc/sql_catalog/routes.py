"""FastAPI routes for SQL Catalog API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from .db import get_db, DatabaseManager
from .importer import SqlImporter
from .models import (
    AllTablesResponse,
    ImportHistoryResponse,
    ImportRequest,
    ImportResponse,
    SchemaDetailResponse,
    SchemaListResponse,
    StatementDetailResponse,
    StatementListResponse,
    SummaryResponse,
    TableDetailResponse,
    TableInfo,
    TableListResponse,
)
from .repository import SqlCatalogRepository

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/sql", tags=["SQL Catalog"])

# Configuration - will be set during app startup
_db_path: str = "sql_catalog.db"
_source_db_path: str | None = None


def configure(db_path: str, source_db_path: str | None = None) -> None:
    """Configure the SQL catalog routes.

    Args:
        db_path: Path to the sql_catalog.db file.
        source_db_path: Default path to source sql_queries.db for imports.
    """
    global _db_path, _source_db_path
    _db_path = db_path
    _source_db_path = source_db_path


def get_repository() -> SqlCatalogRepository:
    """Dependency to get a repository instance."""
    with get_db(_db_path) as conn:
        return SqlCatalogRepository(conn)


# =============================================================================
# UI Endpoint
# =============================================================================

@router.get("/ui", response_class=HTMLResponse)
async def sql_catalog_ui():
    """Serve the SQL Catalog browser UI."""
    static_dir = Path(__file__).parent / "static"
    index_path = static_dir / "index.html"

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI not found")

    return HTMLResponse(content=index_path.read_text(), status_code=200)


# =============================================================================
# Schema Endpoints
# =============================================================================

@router.get("/schemas", response_model=SchemaListResponse)
async def list_schemas():
    """List all discovered schemas."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)
        schemas = repo.list_schemas()
        return SchemaListResponse(schemas=schemas, total=len(schemas))


@router.get("/schemas/{name}", response_model=SchemaDetailResponse)
async def get_schema(name: str):
    """Get schema details."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)
        schema = repo.get_schema(name)
        if not schema:
            raise HTTPException(status_code=404, detail=f"Schema not found: {name}")

        tables = repo.list_tables(schema_name=name)
        return SchemaDetailResponse(
            name=schema.name,
            display_name=schema.display_name,
            description=schema.description,
            statement_count=schema.statement_count,
            table_count=schema.table_count,
            tables=tables,
        )


@router.get("/schemas/{name}/tables", response_model=TableListResponse)
async def list_schema_tables(name: str):
    """List tables in a schema."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)

        # Verify schema exists
        schema = repo.get_schema(name)
        if not schema:
            raise HTTPException(status_code=404, detail=f"Schema not found: {name}")

        tables = repo.list_tables(schema_name=name)
        return TableListResponse(
            schema_name=name.upper(),
            tables=tables,
            total=len(tables),
        )


# =============================================================================
# Table Endpoints
# =============================================================================

@router.get("/tables", response_model=AllTablesResponse)
async def list_tables(
    schema: Annotated[str | None, Query(description="Filter by schema name")] = None,
):
    """List all tables, optionally filtered by schema."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)
        tables = repo.list_tables(schema_name=schema)
        return AllTablesResponse(tables=tables, total=len(tables))


@router.get("/tables/{full_name}", response_model=TableDetailResponse)
async def get_table(full_name: str):
    """Get table details."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)
        table = repo.get_table(full_name)
        if not table:
            raise HTTPException(status_code=404, detail=f"Table not found: {full_name}")

        # Get schema name
        schema = repo.get_schema(full_name.split(".")[0])
        schema_name = schema.name if schema else "_UNKNOWN_"

        return TableDetailResponse(
            name=table.name,
            full_name=table.full_name,
            schema_name=schema_name,
            statement_count=table.statement_count,
        )


@router.get("/tables/{full_name}/statements", response_model=StatementListResponse)
async def list_table_statements(
    full_name: str,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """List SQL statements that reference a table."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)

        # Verify table exists
        table = repo.get_table(full_name)
        if not table:
            raise HTTPException(status_code=404, detail=f"Table not found: {full_name}")

        statements = repo.list_statements(
            table_full_name=full_name,
            limit=limit,
            offset=offset,
        )
        total = repo.count_statements(table_full_name=full_name)

        return StatementListResponse(
            table=full_name.upper(),
            statements=statements,
            total=total,
        )


# =============================================================================
# Statement Endpoints
# =============================================================================

@router.get("/statements", response_model=StatementListResponse)
async def list_statements(
    table: Annotated[str | None, Query(description="Filter by table full name")] = None,
    sql_type: Annotated[str | None, Query(description="Filter by SQL type")] = None,
    space_key: Annotated[str | None, Query(description="Filter by Confluence space")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """List SQL statements with optional filters."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)
        statements = repo.list_statements(
            table_full_name=table,
            sql_type=sql_type,
            space_key=space_key,
            limit=limit,
            offset=offset,
        )
        total = repo.count_statements(
            table_full_name=table,
            sql_type=sql_type,
            space_key=space_key,
        )

        return StatementListResponse(
            table=table,
            statements=statements,
            total=total,
        )


@router.get("/statements/{statement_id}", response_model=StatementDetailResponse)
async def get_statement(statement_id: int):
    """Get statement details with referenced tables."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)
        statement = repo.get_statement(statement_id)
        if not statement:
            raise HTTPException(
                status_code=404,
                detail=f"Statement not found: {statement_id}"
            )

        tables = repo.get_statement_tables(statement_id)

        return StatementDetailResponse(
            id=statement.id,
            sql_code=statement.sql_code,
            sql_type=statement.sql_type,
            page_title=statement.page_title,
            page_id=statement.page_id,
            space_key=statement.space_key,
            space_name=statement.space_name,
            sql_title=statement.sql_title,
            sql_description=statement.sql_description,
            last_modified=statement.last_modified,
            line_count=statement.line_count,
            complexity_score=statement.complexity_score,
            nesting_depth=statement.nesting_depth,
            subquery_count=statement.subquery_count,
            tables=tables,
        )


@router.get("/statements/{statement_id}/tables")
async def get_statement_tables(statement_id: int):
    """Get tables referenced by a statement."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)

        # Verify statement exists
        statement = repo.get_statement(statement_id)
        if not statement:
            raise HTTPException(
                status_code=404,
                detail=f"Statement not found: {statement_id}"
            )

        tables = repo.get_statement_tables(statement_id)
        return {"statement_id": statement_id, "tables": tables}


# =============================================================================
# Import Endpoints
# =============================================================================

@router.post("/import", response_model=ImportResponse)
async def import_sql(request: ImportRequest | None = None):
    """Import SQL statements from source database."""
    source_path = None
    if request and request.source_db_path:
        source_path = request.source_db_path
    elif _source_db_path:
        source_path = _source_db_path

    if not source_path:
        raise HTTPException(
            status_code=400,
            detail="No source database path provided. "
                   "Set source_db_path in request or configure default."
        )

    # Check source exists
    if not Path(source_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"Source database not found: {source_path}"
        )

    try:
        importer = SqlImporter(
            target_db_path=_db_path,
            source_db_path=source_path,
        )
        result = importer.import_from_db()

        logger.info(
            f"Imported {result['statements_imported']} statements, "
            f"{result['schemas_discovered']} schemas, "
            f"{result['tables_discovered']} tables"
        )

        return ImportResponse(**result)

    except Exception as e:
        logger.exception("Import failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/import/history", response_model=ImportHistoryResponse)
async def get_import_history(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Get import history."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)
        imports = repo.list_imports(limit=limit)
        return ImportHistoryResponse(imports=imports, total=len(imports))


# =============================================================================
# Summary Endpoint
# =============================================================================

@router.get("/summary", response_model=SummaryResponse)
async def get_summary():
    """Get summary statistics for the SQL catalog."""
    with get_db(_db_path) as conn:
        repo = SqlCatalogRepository(conn)
        stats = repo.get_summary_stats()
        last_import = repo.get_last_import()

        return SummaryResponse(
            total_statements=stats["total_statements"],
            total_schemas=stats["total_schemas"],
            total_tables=stats["total_tables"],
            statements_by_type=stats["statements_by_type"],
            statements_by_space=stats["statements_by_space"],
            top_tables=stats["top_tables"],
            last_import=last_import,
        )
