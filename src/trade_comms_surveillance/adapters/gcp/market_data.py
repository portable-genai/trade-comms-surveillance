"""GCP MarketDataPort: BigQuery order/trade history (SDK imports stay lazy)."""

from __future__ import annotations

from datetime import datetime

from ...config import Settings
from ...domain.models import MarketWindow


class CloudMarketDataAdapter:
    """Read a dated market window from BigQuery.

    The ``google.cloud.bigquery`` import lives inside the method so the ``local``/``onprem``
    profiles import this module with no GCP SDK installed (the portability proof).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def window(self, instrument: str, as_of: datetime) -> MarketWindow:  # pragma: no cover - live
        from google.cloud import bigquery

        _ = bigquery.Client()
        raise NotImplementedError(
            "wire the BigQuery order/trade query for the deployment's market-data dataset"
        )
