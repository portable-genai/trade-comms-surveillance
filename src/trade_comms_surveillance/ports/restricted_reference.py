"""RestrictedReferencePort: the restricted-list / blackout / MNPI reference boundary (slice 4).

The reference data is a DATA boundary owned by Rgc11 (the conflicts/gifts/PAD register); Cmp1
reads it. Day one the offline family is fixture-backed; inside the wave the managed family calls
Rgc11 over A2A behind this unchanged port (slice 8). The on-prem family fails fast. Every snapshot
is dated so an ``as_of`` replay reproduces the same verdict: the same window plus the same
reference yields the same disposition, byte for byte.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from ..domain.models import RestrictedReference


@runtime_checkable
class RestrictedReferencePort(Protocol):
    def snapshot(self, as_of: datetime) -> RestrictedReference:
        """Return the restricted-list / blackout / MNPI snapshot effective at ``as_of``."""
        ...
