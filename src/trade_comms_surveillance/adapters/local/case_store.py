"""Local CaseStorePort: an in-memory, tenant-scoped case store (SDK-free).

Honours the two-method authorization contract: :meth:`list_for_subject` filters on tenant in the
store, and :meth:`get` is a raw fetch the DOMAIN authorizes. The store is per-process, which is
right for the offline gate and the demo; a durable managed store arrives with the gcp adapter.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import SurveillanceCase


class LocalCaseStoreAdapter:
    """A dict-backed tenant-scoped case store for the ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._by_id: dict[str, SurveillanceCase] = {}

    def list_for_subject(self, tenant: str, subject: str) -> tuple[SurveillanceCase, ...]:
        # Store-side tenant filter: a query can never span tenants.
        return tuple(
            case
            for case in self._by_id.values()
            if case.tenant == tenant and case.subject == subject
        )

    def get(self, case_id: str) -> SurveillanceCase | None:
        # Raw fetch by id; the DOMAIN compares tenants and denies with 403 (see kernel).
        return self._by_id.get(case_id)

    def put(self, case: SurveillanceCase) -> str:
        self._by_id[case.case_id] = case
        return case.case_id
