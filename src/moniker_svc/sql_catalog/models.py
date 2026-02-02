"""Pydantic models for SQL Catalog API."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


# =============================================================================
# Database Entity Models
# =============================================================================

class Schema(BaseModel):
    """An Oracle schema discovered from SQL statements."""

    id: int
    name: str
    display_name: str | None = None
    description: str | None = None
    statement_count: int = 0
    table_count: int = 0
    created_at: datetime | None = None


class Table(BaseModel):
    """A table discovered from SQL statements."""

    id: int
    schema_id: int
    name: str
    full_name: str
    statement_count: int = 0
    created_at: datetime | None = None


class TableRef(BaseModel):
    """A reference from a SQL statement to a table."""

    table_id: int
    full_name: str
    ref_type: str  # FROM, JOIN, INSERT, UPDATE, DELETE, TRUNCATE


class SqlStatement(BaseModel):
    """An imported SQL statement with metadata."""

    id: int
    source_id: int | None = None
    space_key: str
    space_name: str | None = None
    page_id: str
    page_title: str | None = None
    last_modified: str | None = None
    sql_language: str | None = None
    sql_title: str | None = None
    sql_description: str | None = None
    sql_source: str | None = None
    sql_code: str
    line_count: int | None = None
    sql_type: str | None = None
    complexity_score: int | None = None
    nesting_depth: int | None = None
    subquery_count: int | None = None
    imported_at: datetime | None = None
    import_batch_id: str | None = None


class ImportHistory(BaseModel):
    """Record of an import operation."""

    id: int
    batch_id: str
    source_db_path: str
    statements_imported: int
    schemas_discovered: int
    tables_discovered: int
    imported_at: datetime | None = None


# =============================================================================
# API Response Models
# =============================================================================

class SchemaInfo(BaseModel):
    """Schema info for list responses."""

    name: str
    display_name: str | None = None
    statement_count: int = 0
    table_count: int = 0


class TableInfo(BaseModel):
    """Table info for list responses."""

    name: str
    full_name: str
    statement_count: int = 0


class StatementInfo(BaseModel):
    """Statement info for list responses (abbreviated)."""

    id: int
    sql_type: str | None = None
    page_title: str | None = None
    space_key: str
    line_count: int | None = None
    complexity_score: int | None = None
    ref_types: list[str] = Field(default_factory=list)


class SchemaListResponse(BaseModel):
    """Response for GET /sql/schemas."""

    schemas: list[SchemaInfo]
    total: int


class SchemaDetailResponse(BaseModel):
    """Response for GET /sql/schemas/{name}."""

    name: str
    display_name: str | None = None
    description: str | None = None
    statement_count: int = 0
    table_count: int = 0
    tables: list[TableInfo] = Field(default_factory=list)


class TableListResponse(BaseModel):
    """Response for GET /sql/schemas/{name}/tables."""

    schema_name: str
    tables: list[TableInfo]
    total: int


class AllTablesResponse(BaseModel):
    """Response for GET /sql/tables."""

    tables: list[TableInfo]
    total: int


class TableDetailResponse(BaseModel):
    """Response for GET /sql/tables/{full_name}."""

    name: str
    full_name: str
    schema_name: str
    statement_count: int = 0


class StatementListResponse(BaseModel):
    """Response for GET /sql/tables/{full_name}/statements or /sql/statements."""

    table: str | None = None
    statements: list[StatementInfo]
    total: int


class TableRefInfo(BaseModel):
    """Table reference info for statement detail."""

    full_name: str
    ref_type: str


class StatementDetailResponse(BaseModel):
    """Response for GET /sql/statements/{id}."""

    id: int
    sql_code: str
    sql_type: str | None = None
    page_title: str | None = None
    page_id: str
    space_key: str
    space_name: str | None = None
    sql_title: str | None = None
    sql_description: str | None = None
    last_modified: str | None = None
    line_count: int | None = None
    complexity_score: int | None = None
    nesting_depth: int | None = None
    subquery_count: int | None = None
    tables: list[TableRefInfo] = Field(default_factory=list)


class ImportRequest(BaseModel):
    """Request body for POST /sql/import."""

    source_db_path: str | None = None


class ImportResponse(BaseModel):
    """Response for POST /sql/import."""

    batch_id: str
    source_db_path: str
    statements_imported: int
    schemas_discovered: int
    tables_discovered: int
    import_time_seconds: float


class ImportHistoryResponse(BaseModel):
    """Response for GET /sql/import/history."""

    imports: list[ImportHistory]
    total: int


class SummaryResponse(BaseModel):
    """Response for GET /sql/summary."""

    total_statements: int
    total_schemas: int
    total_tables: int
    statements_by_type: dict[str, int]
    statements_by_space: dict[str, int]
    top_tables: list[TableInfo]
    last_import: ImportHistory | None = None
