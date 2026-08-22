"""Tenant isolation on the case store: the two-method authorization contract, proven red.

``CaseStorePort.list_for_subject`` filters on tenant IN the store, so a listing can never span
tenants. ``get`` is a raw fetch the DOMAIN authorizes: ``pipeline.read_case`` compares the stored
case's tenant to the verified principal's tenant and denies with 403. The "red without the check"
proof is explicit here: the raw ``get`` returns another tenant's case, and only the domain check
turns that into a refusal.
"""

from __future__ import annotations

import pytest

from trade_comms_surveillance.config import Settings, build_container
from trade_comms_surveillance.domain.kernel import (
    Disposition,
    Severity,
    TenantAccessDeniedError,
    utcnow,
)
from trade_comms_surveillance.domain.models import SurveillanceCase
from trade_comms_surveillance.pipeline import read_case


def _case(case_id: str, tenant: str) -> SurveillanceCase:
    return SurveillanceCase(
        case_id=case_id,
        subject="trader-a",
        instrument="SPOOF.SG",
        as_of=utcnow(),
        disposition=Disposition.ESCALATE,
        severity=Severity.HIGH,
        summary="escalate",
        requires_human_review=True,
        tenant=tenant,
    )


def _container() -> object:
    container = build_container(Settings(profile="local", audit_path=":memory:"))
    container.case_store.put(_case("case:alpha", "tenant-a"))
    container.case_store.put(_case("case:beta", "tenant-b"))
    return container


def test_a_principal_reads_its_own_tenants_case() -> None:
    container = _container()
    case = read_case(container, "case:alpha", principal_tenant="tenant-a")
    assert case is not None and case.case_id == "case:alpha"


def test_a_cross_tenant_read_is_denied_403_not_404() -> None:
    container = _container()
    with pytest.raises(TenantAccessDeniedError) as excinfo:
        read_case(container, "case:beta", principal_tenant="tenant-a")
    assert excinfo.value.http_status == 403


def test_the_raw_store_get_leaks_without_the_domain_check() -> None:
    """The mutant: bypassing ``read_case`` and calling the raw ``get`` returns the other tenant's
    case. That leak is exactly what the domain authorization prevents, so the guard can go red."""
    container = _container()
    leaked = container.case_store.get("case:beta")
    assert leaked is not None and leaked.tenant == "tenant-b"


def test_list_for_subject_filters_on_tenant_in_the_store() -> None:
    container = _container()
    assert len(container.case_store.list_for_subject("tenant-a", "trader-a")) == 1
    assert container.case_store.list_for_subject("tenant-a", "trader-a")[0].tenant == "tenant-a"
    # A different tenant sees only its own row, never tenant-a's.
    assert len(container.case_store.list_for_subject("tenant-b", "trader-a")) == 1
