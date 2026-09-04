"""Driving-layer orchestration: assemble a market-abuse assessment from the bound ports.

Not pure domain (it reaches ports and the redactor), and not a driving adapter (it has no
transport). It is the one place that wires the market-data, restricted-reference and comms feeds
into a :class:`SurveillanceRequest`, runs the deterministic engine, persists the case and routes a
consequential one to human-review-console (rule R8) in the same call. The CLI, the agent tool, the
eval and the demo all call it, so the pipeline exists in exactly one place rather than four.

Comms transcripts are redacted with ``pii-kit`` before anything downstream could reach a model
(P-04); the deterministic lexicon scan finds cue phrases either way, and no raw identifier travels
with a hit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Container
from .domain.abuse_patterns import PatternThresholds
from .domain.comms_scan import scan_transcript
from .domain.kernel import authorize_tenant, utcnow
from .domain.models import CommsHit, SurveillanceCase, SurveillanceRequest
from .domain.surveillance_service import SurveillanceService


@dataclass(frozen=True, slots=True)
class AssessmentOutcome:
    """What one instrument assessment produced: the case and where any escalation was routed."""

    case: SurveillanceCase
    review_ref: str


def _comms_hits(container: Container, comms_key: str) -> tuple[CommsHit, ...]:
    """Deterministic lexicon hits over the recorded comms for a case.

    The scan is pure matching, not a model call, so P-04's redact-before-a-model rule is not
    engaged here: a :class:`CommsHit` carries only the matched cue phrase (conduct vocabulary,
    never an identifier), and the audit and review payloads redact before anything is persisted or
    leaves the process. A future model-narration adapter must redact the transcript first.
    """
    hits: list[CommsHit] = []
    for transcript in container.comms_feed.transcripts(comms_key):
        hits.extend(scan_transcript(transcript))
    return tuple(hits)


def assess_instrument(
    container: Container,
    thresholds: PatternThresholds,
    *,
    instrument: str,
    subject: str,
    actor: str,
    tenant: str = "",
    route: bool = True,
) -> AssessmentOutcome:
    """Run the full market-abuse assessment for one instrument and persist the case.

    ``route`` is True on the serving paths (rule R8 in the same call) and can be set False by an
    offline evaluator that only scores dispositions and must not depend on a review sink.
    """
    as_of = utcnow()
    window = container.market_data.window(instrument, as_of)
    reference = container.restricted_reference.snapshot(as_of)
    comms_hits = _comms_hits(container, instrument)
    request = SurveillanceRequest(
        case_id=f"case:{instrument}",
        subject=subject,
        window=window,
        reference=reference,
        comms_hits=comms_hits,
        tenant=tenant or container.settings.tenant,
    )
    service = SurveillanceService(container.audit, thresholds, tracer=container.tracer)
    case = service.assess(request, actor=actor)
    container.case_store.put(case)

    review_ref = ""
    if route and case.requires_human_review:
        review_ref = container.review_router.route(case, maker=actor, tenant=case.tenant)
    return AssessmentOutcome(case=case, review_ref=review_ref)


def read_case(
    container: Container, case_id: str, *, principal_tenant: str
) -> SurveillanceCase | None:
    """Fetch one stored case, authorizing the tenant in the DOMAIN, not in the store.

    ``CaseStorePort.get`` is a raw fetch by id that does NOT filter (the two-method contract), so
    the tenant check happens HERE, against the VERIFIED principal's tenant: a case belonging to
    another tenant raises ``TenantAccessDeniedError`` (HTTP 403), never a 404 that would hide
    whether the id exists. Every driving surface that reads a case calls this, so no adapter can
    become the only place the boundary is enforced. Returns ``None`` only when the id is unknown.
    """
    case = container.case_store.get(case_id)
    if case is None:
        return None
    authorize_tenant(case.tenant, principal_tenant)
    return case


__all__ = ["AssessmentOutcome", "assess_instrument", "read_case"]
