"""On-prem CaseStorePort: fail-fast portability placeholder (P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import SurveillanceCase


class OnPremCaseStoreAdapter:
    """Satisfies the port but refuses: the client binds its own case store."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_for_subject(self, tenant: str, subject: str) -> tuple[SurveillanceCase, ...]:
        raise NotImplementedError(
            "on-prem case store is a portability placeholder: bind the client's own store "
            "(see docs/onprem-migration.md)"
        )

    def get(self, case_id: str) -> SurveillanceCase | None:
        raise NotImplementedError(
            "on-prem case store is a portability placeholder (see docs/onprem-migration.md)"
        )

    def put(self, case: SurveillanceCase) -> str:
        raise NotImplementedError(
            "on-prem case store is a portability placeholder (see docs/onprem-migration.md)"
        )
