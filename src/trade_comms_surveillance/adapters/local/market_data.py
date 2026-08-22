"""Local MarketDataPort: a deterministic fictional order-book replay (SDK-free).

Serves the seeded windows in ``_fixtures.py``, so the offline gate, the demo and the eval score a
book that is byte-identical across runs. An unknown instrument returns an empty (but valid) window
rather than raising: an instrument with no activity is a legitimate answer, not an error.
"""

from __future__ import annotations

from datetime import datetime

from ...config import Settings
from ...domain.models import MarketWindow
from ._fixtures import WINDOWS


class LocalMarketDataAdapter:
    """Replay the seeded fictional windows for the ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def window(self, instrument: str, as_of: datetime) -> MarketWindow:
        found = WINDOWS.get(instrument)
        if found is not None:
            return found
        return MarketWindow(instrument=instrument, as_of=as_of)
