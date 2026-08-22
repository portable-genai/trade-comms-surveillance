"""ONE canonical request per port, shared by the structural and behavioural contract suites.

Parity means the same request through every implementation, so the request needs a single home.
Retyping it per suite is how two "parity" tests end up asserting different things.

Each :class:`PortCase` answers three questions about one port:

* ``invoke``   : what a single canonical call to this port looks like;
* ``answered`` : what it means for the OFFLINE family to have actually answered (a port that
  returns ``None`` and records nothing has not answered, it has merely not raised);
* ``managed_refusal`` : what the MANAGED family must do when called with no cloud reachable.
  Never a silent success: either it refuses because it is unconfigured, or its lazy SDK import
  fails. Both are honest; returning as if the work happened is not.

Adding a port means adding a case here. ``test_port_parity.py`` fails the build if this table
and the port map ever disagree, so the touch list in ``CONTRIBUTING.md`` is enforced rather than
merely written down.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_eval_kit import EvalReport
from hex_service_kit.identity import IdentityError, Principal, RequestContext
from hex_service_kit.observability import TokenUsage

from trade_comms_surveillance.domain.kernel import (
    AuditEvent,
    Citation,
    Decision,
    Disposition,
    Severity,
)
from trade_comms_surveillance.domain.models import (
    RestrictedReference,
    SurveillanceCase,
)

from tests.fixtures import sample_cases

#: The audit record every audit-port implementation is handed. Already redacted, as the port
#: requires: a raw identifier must never reach a WORM record.
CANONICAL_EVENT = AuditEvent(
    action="surveillance.assess",
    actor=sample_cases.ACTOR,
    decision=Decision.ESCALATED,
    severity=Severity.HIGH,
    redacted_summary="Acme Holdings (FICTIONAL): escalate on spoofing_layering",
    citations=(Citation(source_id="case:acme", title="Market-data window", snippet="12 orders"),),
)

#: The consequential case every review-router and case-store implementation is handed.
CANONICAL_RESULT = SurveillanceCase(
    case_id="case:SPOOF.SG",
    subject=sample_cases.SUBJECT,
    instrument="SPOOF.SG",
    as_of=sample_cases.AS_OF,
    disposition=Disposition.ESCALATE,
    severity=Severity.HIGH,
    summary="trader-a/SPOOF.SG: escalate on spoofing_layering score 4.0 vs 3.0",
    requires_human_review=True,
    citations=(Citation(source_id="case:acme", title="Market-data window", snippet="12 orders"),),
    tenant=sample_cases.TENANT,
)

#: The inbound transport context every identity implementation is handed.
CANONICAL_CONTEXT = RequestContext(headers={"x-dev-persona": "auditor"})


@dataclass(frozen=True, slots=True)
class PortCase:
    """One port's canonical call plus the two verdicts the parity suites need."""

    invoke: Callable[[Any], Any]
    answered: Callable[[Any, Any], bool]
    managed_refusal: tuple[type[BaseException], ...]
    detail: str


def _audit_invoke(adapter: Any) -> Any:
    return adapter.record(CANONICAL_EVENT)


def _audit_answered(adapter: Any, _result: Any) -> bool:
    stored = adapter.log.read_all()
    return bool(stored) and stored[-1]["actor"] == sample_cases.ACTOR and adapter.verify().ok


def _identity_invoke(adapter: Any) -> Any:
    return adapter.resolve(CANONICAL_CONTEXT)


def _identity_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, Principal) and bool(result.actor)


def _review_invoke(adapter: Any) -> Any:
    return adapter.route(CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def _review_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.outbox.pending()) == 1


def _market_invoke(adapter: Any) -> Any:
    return adapter.window("SPOOF.SG", sample_cases.AS_OF)


def _market_answered(_adapter: Any, result: Any) -> bool:
    return bool(result.orders) or bool(result.trades)


def _reference_invoke(adapter: Any) -> Any:
    return adapter.snapshot(sample_cases.AS_OF)


def _reference_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, RestrictedReference) and bool(result.restricted_symbols)


def _comms_invoke(adapter: Any) -> Any:
    return adapter.transcripts("INSIDE.SG")


def _comms_answered(_adapter: Any, result: Any) -> bool:
    return len(result) >= 1


def _case_store_invoke(adapter: Any) -> Any:
    adapter.put(CANONICAL_RESULT)
    return adapter.list_for_subject(sample_cases.TENANT, sample_cases.SUBJECT)


def _case_store_answered(_adapter: Any, result: Any) -> bool:
    return len(result) == 1 and result[0].case_id == CANONICAL_RESULT.case_id


def _tracer_invoke(adapter: Any) -> Any:
    with adapter.span("canonical.unit", action="canonical"):
        adapter.record_token_usage(TokenUsage(input_tokens=7, output_tokens=2), "canonical-model")
    return True


def _tracer_answered(adapter: Any, result: Any) -> bool:
    return bool(result)


def _evaluation_invoke(adapter: Any) -> Any:
    return adapter.evaluate("eval/datasets/canonical.jsonl")


def _evaluation_answered(adapter: Any, result: Any) -> bool:
    return isinstance(result, EvalReport) and result.dataset.endswith("canonical.jsonl")


CANONICAL_CALLS: dict[str, PortCase] = {
    "audit": PortCase(
        invoke=_audit_invoke,
        answered=_audit_answered,
        # The lazy `google.cloud` import is the first thing the managed sink does.
        managed_refusal=(ImportError,),
        detail="write one already-redacted WORM record",
    ),
    "identity": PortCase(
        invoke=_identity_invoke,
        answered=_identity_answered,
        # No IAP assertion header offline, so the managed adapter refuses before importing.
        managed_refusal=(IdentityError,),
        detail="resolve a verified principal from transport context",
    ),
    "review_router": PortCase(
        invoke=_review_invoke,
        answered=_review_answered,
        # Rule R8: with no console configured the managed router must refuse, not swallow.
        managed_refusal=(RuntimeError,),
        detail="route one consequential case to human review",
    ),
    "market_data": PortCase(
        invoke=_market_invoke,
        answered=_market_answered,
        # The lazy `google.cloud.bigquery` import is the first thing the managed feed does.
        managed_refusal=(ImportError,),
        detail="return a dated order/trade window",
    ),
    "restricted_reference": PortCase(
        invoke=_reference_invoke,
        answered=_reference_answered,
        # The lazy `google.auth` A2A client import is the first thing the managed feed does.
        managed_refusal=(ImportError,),
        detail="return the restricted-list / blackout / MNPI snapshot",
    ),
    "comms_feed": PortCase(
        invoke=_comms_invoke,
        answered=_comms_answered,
        # The lazy `google.cloud.storage` import is the first thing the managed feed does.
        managed_refusal=(ImportError,),
        detail="return recorded-comms transcripts for a case",
    ),
    "case_store": PortCase(
        invoke=_case_store_invoke,
        answered=_case_store_answered,
        # The lazy `google.cloud.firestore` import is the first thing the managed store does.
        managed_refusal=(ImportError,),
        detail="persist and read back a tenant-scoped case",
    ),
    "tracer": PortCase(
        invoke=_tracer_invoke,
        answered=_tracer_answered,
        # NOTHING. Tracing is not essential to correctness, so the managed adapter must not refuse
        # offline either: with no SDK it degrades to a no-op and the traced body still runs. An
        # adapter that raised here would take a request down over a diagnostic.
        managed_refusal=(),
        detail="open one span and report the cost of a model call",
    ),
    "evaluation": PortCase(
        invoke=_evaluation_invoke,
        answered=_evaluation_answered,
        # The managed gate reaches Hrz4 over HTTP, which is unreachable offline.
        managed_refusal=(Exception,),
        detail="score one golden dataset through the promotion authority",
    ),
}
