"""Refinitiv adapter - connects to Refinitiv/LSEG data services."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import ResolvedSource
    from ..config import ClientConfig

from .base import BaseAdapter


class RefinitivAdapter(BaseAdapter):
    """
    Adapter for Refinitiv (LSEG) data services.

    Supports Eikon Data API.
    Requires Refinitiv Eikon terminal or API access.
    """

    def fetch(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        conn_info = resolved.connection
        params = resolved.params

        api_type = conn_info.get("api_type", "eikon")

        if api_type == "eikon":
            return self._fetch_eikon(resolved, config, **kwargs)
        elif api_type == "rdp":
            return self._fetch_rdp(resolved, config, **kwargs)
        else:
            raise ValueError(f"Unsupported Refinitiv API type: {api_type}")

    def _fetch_eikon(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        try:
            import eikon as ek
        except ImportError:
            raise ImportError(
                "eikon required for Refinitiv: pip install eikon "
                "(requires Refinitiv Eikon)"
            )

        params = resolved.params

        # Set app key from config
        app_key = config.credentials.get("refinitiv_app_key")
        if app_key:
            ek.set_app_key(app_key)

        # Get instruments and fields
        instruments = params.get("instruments", [])
        if isinstance(instruments, str):
            instruments = [instruments]

        fields = params.get("fields", ["TR.PriceClose"])

        # Make request
        df, err = ek.get_data(instruments, fields)
        if err:
            raise RuntimeError(f"Eikon error: {err}")

        # Convert DataFrame to list of dicts
        return df.to_dict(orient="records")

    def _fetch_rdp(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        try:
            import refinitiv.data as rd
        except ImportError:
            raise ImportError(
                "refinitiv-data required: pip install refinitiv-data"
            )

        params = resolved.params

        # Open RDP session
        rd.open_session()

        try:
            instruments = params.get("instruments", [])
            if isinstance(instruments, str):
                instruments = [instruments]

            fields = params.get("fields", [])

            # Get data
            df = rd.get_data(instruments, fields)
            return df.to_dict(orient="records")

        finally:
            rd.close_session()
