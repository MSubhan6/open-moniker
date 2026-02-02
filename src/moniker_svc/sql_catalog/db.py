"""SQLite database connection and schema initialization for SQL Catalog."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator
from contextlib import contextmanager

# Default database path
DEFAULT_DB_PATH = "sql_catalog.db"

# SQL schema for the catalog
SCHEMA_SQL = """
-- Oracle schemas discovered from SQL
CREATE TABLE IF NOT EXISTS schemas (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    description TEXT,
    statement_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tables discovered from SQL (fully qualified)
CREATE TABLE IF NOT EXISTS tables (
    id INTEGER PRIMARY KEY,
    schema_id INTEGER REFERENCES schemas(id),
    name TEXT NOT NULL,
    full_name TEXT NOT NULL UNIQUE,
    statement_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Imported SQL statements
CREATE TABLE IF NOT EXISTS sql_statements (
    id INTEGER PRIMARY KEY,
    source_id INTEGER,
    space_key TEXT NOT NULL,
    space_name TEXT,
    page_id TEXT NOT NULL,
    page_title TEXT,
    last_modified TEXT,
    sql_language TEXT,
    sql_title TEXT,
    sql_description TEXT,
    sql_source TEXT,
    sql_code TEXT NOT NULL,
    line_count INTEGER,
    sql_type TEXT,
    complexity_score INTEGER,
    nesting_depth INTEGER,
    subquery_count INTEGER,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    import_batch_id TEXT
);

-- Junction: which statements reference which tables
CREATE TABLE IF NOT EXISTS statement_table_refs (
    id INTEGER PRIMARY KEY,
    statement_id INTEGER NOT NULL REFERENCES sql_statements(id),
    table_id INTEGER NOT NULL REFERENCES tables(id),
    ref_type TEXT NOT NULL,
    UNIQUE(statement_id, table_id, ref_type)
);

-- Import history
CREATE TABLE IF NOT EXISTS import_history (
    id INTEGER PRIMARY KEY,
    batch_id TEXT NOT NULL,
    source_db_path TEXT NOT NULL,
    statements_imported INTEGER,
    schemas_discovered INTEGER,
    tables_discovered INTEGER,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_tables_schema ON tables(schema_id);
CREATE INDEX IF NOT EXISTS idx_refs_statement ON statement_table_refs(statement_id);
CREATE INDEX IF NOT EXISTS idx_refs_table ON statement_table_refs(table_id);
CREATE INDEX IF NOT EXISTS idx_statements_type ON sql_statements(sql_type);
CREATE INDEX IF NOT EXISTS idx_statements_space ON sql_statements(space_key);
CREATE INDEX IF NOT EXISTS idx_statements_batch ON sql_statements(import_batch_id);
"""


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Initialize the database and create tables if they don't exist.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A connection to the database.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    return conn


@contextmanager
def get_db(db_path: str | Path = DEFAULT_DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection as a context manager.

    Args:
        db_path: Path to the SQLite database file.

    Yields:
        A connection to the database.
    """
    conn = init_db(db_path)
    try:
        yield conn
    finally:
        conn.close()


class DatabaseManager:
    """Manages database connections for the SQL Catalog."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        """Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self._conn is None:
            self._conn = init_db(self.db_path)
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> sqlite3.Connection:
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
