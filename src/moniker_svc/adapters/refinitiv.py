"""Refinitiv (LSEG) data adapter."""

from __future__ import annotations

import time
from typing import Any

from ..catalog.types import SourceBinding, SourceType
from ..moniker.types import Moniker
from .base import (
    AdapterConnectionError,
    AdapterError,
    AdapterNotFoundError,
    AdapterResult,
    DataAdapter,
)


class RefinitivAdapter(DataAdapter):
    """
    Adapter for Refinitiv (LSEG) data services.

    Supports multiple Refinitiv APIs:
    - Eikon Data API
    - Refinitiv Data Platform (RDP)
    - Elektron (real-time data)

    Config:
        api_type: eikon | rdp | elektron
        app_key: Application key for Eikon/RDP

        # For Eikon:
        instruments: List of RICs or template with {path}
        fields: List of fields to request

        # For RDP:
        endpoint: RDP endpoint path
        query: Query parameters

        # For Elektron:
        service: Elektron service name
        ric: RIC pattern
    """

    @property
    def source_type(self) -> SourceType:
        return SourceType.REFINITIV

    async def fetch(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> AdapterResult:
        start = time.perf_counter()

        api_type = binding.config.get("api_type", "eikon")

        if api_type == "eikon":
            data = await self._fetch_eikon(moniker, binding, sub_path)
        elif api_type == "rdp":
            data = await self._fetch_rdp(moniker, binding, sub_path)
        elif api_type == "elektron":
            data = await self._fetch_elektron(moniker, binding, sub_path)
        else:
            raise AdapterError(f"Unknown Refinitiv API type: {api_type}")

        elapsed = (time.perf_counter() - start) * 1000

        return AdapterResult(
            data=data,
            source_type=self.source_type,
            source_path=f"refinitiv:{api_type}",
            query_ms=elapsed,
            row_count=len(data) if isinstance(data, list) else None,
        )

    async def _fetch_eikon(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None,
    ) -> Any:
        """Fetch data using Refinitiv Eikon Data API."""
        try:
            import eikon as ek
        except ImportError:
            raise AdapterError(
                "eikon required for Refinitiv: pip install eikon "
                "(requires Refinitiv Eikon)"
            )

        config = binding.config
        path_str = sub_path or str(moniker.path)

        # Set app key
        app_key = config.get("app_key")
        if app_key:
            ek.set_app_key(app_key)

        # Get instruments
        instruments = config.get("instruments", [])
        if isinstance(instruments, str):
            instruments = [instruments.format(path=path_str)]
        elif not instruments:
            # Use path as RIC
            instruments = [path_str.upper()]

        fields = config.get("fields", ["TR.PriceClose"])

        try:
            df, err = ek.get_data(instruments, fields)
            if err:
                raise AdapterError(f"Eikon error: {err}")

            # Convert DataFrame to list of dicts
            data = df.to_dict(orient="records")
            return data

        except Exception as e:
            if "not found" in str(e).lower():
                raise AdapterNotFoundError(f"Instrument not found: {instruments}")
            raise AdapterError(f"Eikon request failed: {e}") from e

    async def _fetch_rdp(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None,
    ) -> Any:
        """Fetch data using Refinitiv Data Platform."""
        try:
            import refinitiv.data as rd
        except ImportError:
            raise AdapterError(
                "refinitiv-data required: pip install refinitiv-data"
            )

        config = binding.config
        path_str = sub_path or str(moniker.path)

        # Open session
        rd.open_session()

        try:
            endpoint = config.get("endpoint", "/data/pricing/snapshots/v1")
            query = config.get("query", {})

            # Format query with path
            for key, value in query.items():
                if isinstance(value, str):
                    query[key] = value.format(path=path_str)

            response = rd.delivery.endpoint_request.Definition(
                url=endpoint,
                method=rd.delivery.endpoint_request.RequestMethod.GET,
                query_parameters=query,
            ).get_data()

            return response.data.raw

        finally:
            rd.close_session()

    async def _fetch_elektron(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None,
    ) -> Any:
        """Fetch data using Elektron (real-time)."""
        # Elektron requires subscription handling
        raise AdapterError("Elektron adapter requires subscription handling")

    async def list_children(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> list[str]:
        return []

    async def describe(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> dict[str, Any]:
        info = await super().describe(moniker, binding, sub_path)
        info["api_type"] = binding.config.get("api_type", "eikon")
        info["fields"] = binding.config.get("fields", [])
        return info

    async def health_check(self, binding: SourceBinding) -> bool:
        """Check Refinitiv connectivity."""
        try:
            import eikon as ek
            app_key = binding.config.get("app_key")
            if app_key:
                ek.set_app_key(app_key)
            # Try a simple request
            ek.get_data("IBM.N", "TR.CompanyName")
            return True
        except Exception:
            return False
