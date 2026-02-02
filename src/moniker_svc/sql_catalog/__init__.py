"""SQL Catalog - Import and browse SQL statements by schema/table taxonomy.

This module provides:
- Import SQL statements from external databases (e.g., confluence extraction)
- Automatic taxonomy based on Oracle schemas and tables extracted from SQL
- Browse by schema → table → statements hierarchy
- Data lineage view: which queries touch which tables
"""

from .db import get_db, init_db
from .models import (
    Schema,
    Table,
    SqlStatement,
    TableRef,
    ImportHistory,
    SchemaListResponse,
    TableListResponse,
    StatementListResponse,
    StatementDetailResponse,
    ImportResponse,
    SummaryResponse,
)
from .repository import SqlCatalogRepository
from .analyzer import SqlAnalyzer
from .importer import SqlImporter

__all__ = [
    # Database
    "get_db",
    "init_db",
    # Models
    "Schema",
    "Table",
    "SqlStatement",
    "TableRef",
    "ImportHistory",
    "SchemaListResponse",
    "TableListResponse",
    "StatementListResponse",
    "StatementDetailResponse",
    "ImportResponse",
    "SummaryResponse",
    # Services
    "SqlCatalogRepository",
    "SqlAnalyzer",
    "SqlImporter",
]
