"""GCP RestrictedReferencePort: conflicts-gifts-pad-register's A2A reference feed (client import
stays lazy).

Slice 8: once conflicts-gifts-pad-register publishes its restricted-list / blackout / MNPI feed, the
managed family calls it over A2A behind this unchanged port. Until that endpoint exists the offline
fixture family is the binding; this adapter is the seam it switches into.
"""

from __future__ import annotations

from datetime import datetime

from ...config import Settings
from ...domain.models import RestrictedReference


class CloudRestrictedReferenceAdapter:
    """Fetch the reference snapshot from conflicts-gifts-pad-register over
    A2A (lazy client import).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def snapshot(self, as_of: datetime) -> RestrictedReference:  # pragma: no cover - live
        from google.auth.transport.requests import AuthorizedSession  # noqa: F401

        raise NotImplementedError(
            "bind conflicts-gifts-pad-register's A2A reference feed here (slice 8); see "
            "docs/runbook.md"
        )
