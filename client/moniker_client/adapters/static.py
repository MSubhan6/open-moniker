"""Static file adapter - reads JSON/CSV/Parquet files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import ResolvedSource
    from ..config import ClientConfig

from .base import BaseAdapter


class StaticAdapter(BaseAdapter):
    """
    Adapter for static files (JSON, CSV, Parquet).

    Reads files from local filesystem or network paths.
    """

    def fetch(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        conn_info = resolved.connection
        params = resolved.params

        base_path = Path(conn_info.get("base_path", "."))
        file_path_pattern = resolved.query or "{path}.json"

        # Build full file path
        file_path = base_path / file_path_pattern

        if not file_path.exists():
            from ..client import NotFoundError
            raise NotFoundError(f"File not found: {file_path}")

        file_format = params.get("format", "json")
        encoding = params.get("encoding", "utf-8")

        return self._read_file(file_path, file_format, encoding)

    def _read_file(self, path: Path, format: str, encoding: str) -> Any:
        """Read file based on format."""
        if format == "json":
            with open(path, "r", encoding=encoding) as f:
                return json.load(f)

        elif format == "csv":
            import csv
            with open(path, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader)

        elif format == "parquet":
            try:
                import pyarrow.parquet as pq
                table = pq.read_table(path)
                return table.to_pydict()
            except ImportError:
                raise ImportError("pyarrow required for parquet: pip install pyarrow")

        else:
            raise ValueError(f"Unsupported format: {format}")

    def list_children(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
    ) -> list[str]:
        """List files in directory."""
        conn_info = resolved.connection
        base_path = Path(conn_info.get("base_path", "."))

        if not base_path.is_dir():
            return []

        children = []
        for item in base_path.iterdir():
            if item.is_dir():
                children.append(item.name)
            elif item.suffix in (".json", ".csv", ".parquet"):
                children.append(item.stem)

        return sorted(children)
