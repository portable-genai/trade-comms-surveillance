"""On-prem RestrictedReferencePort: fail-fast portability placeholder (P-12)."""

from __future__ import annotations

from datetime import datetime

from ...config import Settings
from ...domain.models import RestrictedReference


class OnPremRestrictedReferenceAdapter:
    """Satisfies the port but refuses: the client binds its own restricted-reference store."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def snapshot(self, as_of: datetime) -> RestrictedReference:
        raise NotImplementedError(
            "on-prem restricted-reference feed is a portability placeholder: bind the client's "
            "own restricted-list / blackout / MNPI store (see docs/onprem-migration.md)"
        )
