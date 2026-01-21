"""Bloomberg data adapter."""

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


class BloombergAdapter(DataAdapter):
    """
    Adapter for Bloomberg data services.

    Supports multiple Bloomberg APIs:
    - BLPAPI (Bloomberg API)
    - BQL (Bloomberg Query Language)
    - B-PIPE (market data feed)

    Config:
        api_type: blpapi | bql | bpipe
        host: Bloomberg server host (for BLPAPI/B-PIPE)
        port: Bloomberg server port

        # For BLPAPI:
        securities: List of securities or template with {path}
        fields: List of fields to request

        # For BQL:
        query: BQL query string (can include {path} placeholder)

        # For B-PIPE:
        topic: Subscription topic
    """

    @property
    def source_type(self) -> SourceType:
        return SourceType.BLOOMBERG

    async def fetch(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> AdapterResult:
        start = time.perf_counter()

        api_type = binding.config.get("api_type", "blpapi")

        if api_type == "blpapi":
            data = await self._fetch_blpapi(moniker, binding, sub_path)
        elif api_type == "bql":
            data = await self._fetch_bql(moniker, binding, sub_path)
        elif api_type == "bpipe":
            data = await self._fetch_bpipe(moniker, binding, sub_path)
        else:
            raise AdapterError(f"Unknown Bloomberg API type: {api_type}")

        elapsed = (time.perf_counter() - start) * 1000

        return AdapterResult(
            data=data,
            source_type=self.source_type,
            source_path=f"bloomberg:{api_type}",
            query_ms=elapsed,
            row_count=len(data) if isinstance(data, list) else None,
        )

    async def _fetch_blpapi(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None,
    ) -> Any:
        """Fetch data using Bloomberg BLPAPI."""
        try:
            import blpapi
        except ImportError:
            raise AdapterError(
                "blpapi required for Bloomberg: pip install blpapi "
                "(requires Bloomberg SDK)"
            )

        config = binding.config
        path_str = sub_path or str(moniker.path)

        # Get securities - can be list or template
        securities = config.get("securities", [])
        if isinstance(securities, str):
            securities = [securities.format(path=path_str)]
        elif not securities:
            # Use path as security identifier
            securities = [path_str.upper()]

        fields = config.get("fields", ["PX_LAST"])

        # Setup session
        session_options = blpapi.SessionOptions()
        session_options.setServerHost(config.get("host", "localhost"))
        session_options.setServerPort(config.get("port", 8194))

        session = blpapi.Session(session_options)
        if not session.start():
            raise AdapterConnectionError("Failed to start Bloomberg session")

        if not session.openService("//blp/refdata"):
            session.stop()
            raise AdapterConnectionError("Failed to open Bloomberg refdata service")

        service = session.getService("//blp/refdata")
        request = service.createRequest("ReferenceDataRequest")

        for sec in securities:
            request.append("securities", sec)
        for field in fields:
            request.append("fields", field)

        session.sendRequest(request)

        # Process response
        data = []
        while True:
            event = session.nextEvent(500)
            for msg in event:
                if msg.hasElement("securityData"):
                    sec_data = msg.getElement("securityData")
                    for i in range(sec_data.numValues()):
                        sec = sec_data.getValue(i)
                        security_name = sec.getElementAsString("security")
                        field_data = sec.getElement("fieldData")

                        record = {"security": security_name}
                        for field in fields:
                            if field_data.hasElement(field):
                                record[field] = field_data.getElementAsFloat(field)

                        data.append(record)

            if event.eventType() == blpapi.Event.RESPONSE:
                break

        session.stop()
        return data

    async def _fetch_bql(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None,
    ) -> Any:
        """Fetch data using Bloomberg BQL."""
        # BQL typically requires the Bloomberg Terminal or BQuant
        # This is a placeholder showing the interface
        raise AdapterError("BQL adapter requires Bloomberg Terminal/BQuant environment")

    async def _fetch_bpipe(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None,
    ) -> Any:
        """Fetch data using Bloomberg B-PIPE."""
        # B-PIPE is for real-time market data
        raise AdapterError("B-PIPE adapter requires subscription handling")

    async def list_children(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> list[str]:
        # Bloomberg doesn't have a natural hierarchy for listing
        return []

    async def describe(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> dict[str, Any]:
        info = await super().describe(moniker, binding, sub_path)
        info["api_type"] = binding.config.get("api_type", "blpapi")
        info["fields"] = binding.config.get("fields", [])
        return info

    async def health_check(self, binding: SourceBinding) -> bool:
        """Check Bloomberg connectivity."""
        try:
            import blpapi
            session_options = blpapi.SessionOptions()
            session_options.setServerHost(binding.config.get("host", "localhost"))
            session_options.setServerPort(binding.config.get("port", 8194))
            session = blpapi.Session(session_options)
            result = session.start()
            session.stop()
            return result
        except Exception:
            return False
