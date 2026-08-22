"""GCP CaseStorePort: Firestore case store in the residency region (SDK imports stay lazy)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import SurveillanceCase


class CloudCaseStoreAdapter:
    """Tenant-scoped case store on Firestore (lazy SDK import; store-side tenant filter)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_for_subject(
        self, tenant: str, subject: str
    ) -> tuple[SurveillanceCase, ...]:  # pragma: no cover - live
        from google.cloud import firestore

        _ = firestore.Client()
        raise NotImplementedError("wire the Firestore case query for the deployment")

    def get(self, case_id: str) -> SurveillanceCase | None:  # pragma: no cover - live
        from google.cloud import firestore

        _ = firestore.Client()
        raise NotImplementedError("wire the Firestore case fetch for the deployment")

    def put(self, case: SurveillanceCase) -> str:  # pragma: no cover - live
        from google.cloud import firestore

        _ = firestore.Client()
        raise NotImplementedError("wire the Firestore case upsert for the deployment")
