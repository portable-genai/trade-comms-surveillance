"""MarketDataPort: the hexagon edge to order/trade/quote history (slice 2).

Returns a dated :class:`~trade_comms_surveillance.domain.models.MarketWindow` for one instrument,
so the deterministic engine scores a replayable slice rather than reaching a live feed. The
managed family is BigQuery (lazy import), the offline family is a deterministic fictional book
replay with seeded abuse episodes, and the on-prem family fails fast.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from ..domain.models import MarketWindow


@runtime_checkable
class MarketDataPort(Protocol):
    def window(self, instrument: str, as_of: datetime) -> MarketWindow:
        """Return the order/trade window for ``instrument`` as of ``as_of`` (dated, replayable)."""
        ...
