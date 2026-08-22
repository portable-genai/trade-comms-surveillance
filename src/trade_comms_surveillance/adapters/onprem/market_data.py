"""On-prem MarketDataPort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from datetime import datetime

from ...config import Settings
from ...domain.models import MarketWindow


class OnPremMarketDataAdapter:
    """Satisfies MarketDataPort but refuses at call time: the client wires its own market feed."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def window(self, instrument: str, as_of: datetime) -> MarketWindow:
        raise NotImplementedError(
            "on-prem market-data feed is a portability placeholder: bind the client's own "
            "order/trade warehouse (see docs/onprem-migration.md)"
        )
