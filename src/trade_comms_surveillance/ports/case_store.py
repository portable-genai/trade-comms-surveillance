"""CaseStorePort: the tenant-scoped store of assessed surveillance cases (slice 7).

Authorization contract (fail-closed, server-verified), the two-method shape Mkt6's evidence store
proved: :meth:`list_for_subject` takes the tenant and MUST filter on it in the store, so a query
can never span tenants; :meth:`get` is a raw fetch by id that does NOT filter, and the caller (the
domain) compares the stored case's tenant to the VERIFIED principal's tenant and denies with 403,
not 404. Keeping the check in the domain means every driving adapter inherits it and an adapter
cannot become the only place the boundary is enforced. Never pass a client-supplied tenant into
either method: the tenant comes from the principal the IdentityPort verified.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import SurveillanceCase


@runtime_checkable
class CaseStorePort(Protocol):
    def list_for_subject(self, tenant: str, subject: str) -> tuple[SurveillanceCase, ...]:
        """Return the cases ``tenant`` holds for ``subject`` (store-side tenant filter)."""
        ...

    def get(self, case_id: str) -> SurveillanceCase | None:
        """Return one case by id, or ``None``; the DOMAIN authorizes the tenant, not the store."""
        ...

    def put(self, case: SurveillanceCase) -> str:
        """Upsert one case and return its id."""
        ...
