"""Local RestrictedReferencePort: the fixture-backed reference snapshot (the day-one binding).

Serves the seeded :class:`RestrictedReference` from ``_fixtures.py``. Inside the wave the managed
family switches to conflicts-gifts-pad-register's A2A feed behind this same port (slice 8); until
then this fixture IS the reference, and the wire schema is whatever this port defines.
"""

from __future__ import annotations

from datetime import datetime

from ...config import Settings
from ...domain.models import RestrictedReference
from ._fixtures import REFERENCE


class LocalRestrictedReferenceAdapter:
    """Return the seeded restricted-list / blackout / MNPI snapshot for the ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def snapshot(self, as_of: datetime) -> RestrictedReference:
        return REFERENCE
