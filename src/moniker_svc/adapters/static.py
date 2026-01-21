"""Static file adapter - JSON, CSV, Parquet files."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..catalog.types import SourceBinding, SourceType
from ..moniker.types import Moniker
from .base import (
    AdapterError,
    AdapterNotFoundError,
    AdapterResult,
    DataAdapter,
)


class StaticFileAdapter(DataAdapter):
    """
    Adapter for static files (JSON, CSV, Parquet).

    Config:
        base_path: Base directory for files
        file_pattern: Pattern for file path (can include {path} placeholder)
        format: json | csv | parquet (default: json)
        encoding: File encoding (default: utf-8)
    """

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATIC

    async def fetch(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> AdapterResult:
        start = time.perf_counter()

        base_path = Path(binding.config.get("base_path", "."))
        file_pattern = binding.config.get("file_pattern", "{path}.json")
        file_format = binding.config.get("format", "json")
        encoding = binding.config.get("encoding", "utf-8")

        # Build file path
        path_str = sub_path or str(moniker.path)
        file_path = base_path / file_pattern.format(path=path_str)

        if not file_path.exists():
            raise AdapterNotFoundError(f"File not found: {file_path}")

        try:
            data = self._read_file(file_path, file_format, encoding)
        except Exception as e:
            raise AdapterError(f"Failed to read {file_path}: {e}") from e

        elapsed = (time.perf_counter() - start) * 1000

        return AdapterResult(
            data=data,
            source_type=self.source_type,
            source_path=str(file_path),
            query_ms=elapsed,
            row_count=len(data) if isinstance(data, (list, dict)) else None,
        )

    def _read_file(self, path: Path, format: str, encoding: str) -> Any:
        if format == "json":
            with open(path, "r", encoding=encoding) as f:
                return json.load(f)
        elif format == "csv":
            # Simple CSV reading - for production use pandas or csv module
            import csv
            with open(path, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader)
        elif format == "parquet":
            # Requires pyarrow
            try:
                import pyarrow.parquet as pq
                table = pq.read_table(path)
                return table.to_pydict()
            except ImportError:
                raise AdapterError("pyarrow required for parquet support")
        else:
            raise AdapterError(f"Unsupported format: {format}")

    async def list_children(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> list[str]:
        base_path = Path(binding.config.get("base_path", "."))
        path_str = sub_path or str(moniker.path)

        dir_path = base_path / path_str
        if not dir_path.is_dir():
            return []

        children = []
        for item in dir_path.iterdir():
            if item.is_dir():
                children.append(item.name)
            elif item.suffix in (".json", ".csv", ".parquet"):
                children.append(item.stem)

        return sorted(children)

    async def describe(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> dict[str, Any]:
        base_path = Path(binding.config.get("base_path", "."))
        file_pattern = binding.config.get("file_pattern", "{path}.json")
        path_str = sub_path or str(moniker.path)
        file_path = base_path / file_pattern.format(path=path_str)

        info = await super().describe(moniker, binding, sub_path)
        info["file_path"] = str(file_path)
        info["exists"] = file_path.exists()
        if file_path.exists():
            info["size_bytes"] = file_path.stat().st_size
            info["modified"] = file_path.stat().st_mtime

        return info
