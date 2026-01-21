"""Bloomberg adapter - connects to Bloomberg API."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import ResolvedSource
    from ..config import ClientConfig

from .base import BaseAdapter


class BloombergAdapter(BaseAdapter):
    """
    Adapter for Bloomberg data services.

    Connects directly to Bloomberg BLPAPI.
    Requires Bloomberg Terminal or B-PIPE.
    """

    def fetch(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        try:
            import blpapi
        except ImportError:
            raise ImportError(
                "blpapi required for Bloomberg: pip install blpapi "
                "(requires Bloomberg SDK)"
            )

        conn_info = resolved.connection
        params = resolved.params

        api_type = conn_info.get("api_type", "blpapi")
        if api_type != "blpapi":
            raise ValueError(f"Unsupported Bloomberg API type: {api_type}")

        # Get securities and fields
        securities = params.get("securities", [])
        if isinstance(securities, str):
            securities = [securities]

        fields = params.get("fields", ["PX_LAST"])

        # Setup Bloomberg session
        session_options = blpapi.SessionOptions()
        session_options.setServerHost(conn_info.get("host", "localhost"))
        session_options.setServerPort(conn_info.get("port", 8194))

        session = blpapi.Session(session_options)
        if not session.start():
            raise ConnectionError("Failed to start Bloomberg session")

        try:
            if not session.openService("//blp/refdata"):
                raise ConnectionError("Failed to open Bloomberg refdata service")

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
                                    try:
                                        record[field] = field_data.getElementAsFloat(field)
                                    except Exception:
                                        record[field] = str(field_data.getElement(field))

                            data.append(record)

                if event.eventType() == blpapi.Event.RESPONSE:
                    break

            return data

        finally:
            session.stop()
