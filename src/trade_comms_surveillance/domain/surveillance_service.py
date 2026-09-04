"""The surveillance orchestrator: pure engine decides, narrative restates, audit is redacted.

The consequential outputs (every abuse score, the case severity and the close/escalate/file-STOR
disposition) are pure stdlib and replayable from ``as_of``. A model narrates elsewhere and never
produces a number or a verdict. PII is redacted BEFORE the audit write (R1/P-04), every case carries
citations, and a consequential case sets ``requires_human_review`` and is routed to
human-review-console by the driving layer (rule R8) rather than auto-executed.

The disposition tiering is deterministic policy: a fired CRITICAL abuse signal, or a tipping cue
corroborated by a fired trading signal, recommends a STOR filing; any other fired signal or a
HIGH comms cue escalates to an analyst; nothing fired closes the alert. Filing is always human,
so ``FILE_STOR`` is a recommendation, never an action taken here.
"""

from __future__ import annotations

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.observability import ObservabilityTracerPort
from .abuse_patterns import PatternThresholds, score_window
from .collusion_graph import score_proximity
from .kernel import (
    AuditEvent,
    Citation,
    Disposition,
    Severity,
    disposition_to_decision,
    utcnow,
)
from .models import (
    AbuseSignal,
    CommsHit,
    SurveillanceCase,
    SurveillanceRequest,
)
from .pii import PII_PATTERNS

#: Severity rank for taking a maximum deterministically (higher is worse).
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


def _max_severity(severities: tuple[Severity, ...]) -> Severity:
    if not severities:
        return Severity.LOW
    return max(severities, key=lambda s: _SEVERITY_RANK[s])


def _disposition(
    fired: tuple[AbuseSignal, ...], comms_hits: tuple[CommsHit, ...], severity: Severity
) -> Disposition:
    """Assign the tier from the engine's own findings, deterministically."""
    tipping = any(h.lexicon == "tipping" for h in comms_hits)
    if severity is Severity.CRITICAL and (fired or tipping):
        return Disposition.FILE_STOR
    if tipping and fired:
        return Disposition.FILE_STOR
    if fired or any(h.severity in (Severity.HIGH, Severity.CRITICAL) for h in comms_hits):
        return Disposition.ESCALATE
    return Disposition.CLOSE


def _narrative(
    request: SurveillanceRequest,
    fired: tuple[AbuseSignal, ...],
    comms_hits: tuple[CommsHit, ...],
    disposition: Disposition,
) -> str:
    """A grounded one-line summary that RESTATES engine findings only (no figure it did not
    produce). Every number here traces to a signal score, so the groundedness metric can reject a
    narrative that invents one."""
    if not fired and not comms_hits:
        return f"{request.subject}/{request.window.instrument}: no pattern fired; closing."
    parts = [f"{s.pattern.value} score {s.score} vs {s.threshold}" for s in fired]
    parts.extend(f"comms:{h.lexicon}@turn{h.turn_index}" for h in comms_hits)
    return f"{request.subject}/{request.window.instrument}: {disposition.value} on " + "; ".join(
        parts
    )


def _citations(
    request: SurveillanceRequest, fired: tuple[AbuseSignal, ...]
) -> tuple[Citation, ...]:
    seen: set[str] = set()
    out: list[Citation] = [
        Citation(
            source_id=f"window:{request.window.instrument}:{request.window.as_of.isoformat()}",
            title="Market-data window",
            snippet=f"{len(request.window.orders)} orders, {len(request.window.trades)} trades",
        )
    ]
    for signal in fired:
        for citation in signal.citations:
            if citation.source_id in seen:
                continue
            seen.add(citation.source_id)
            out.append(citation)
    return tuple(out)


#: One span per assessed window. Structural attributes only: see :meth:`SurveillanceService.assess`.
_ASSESS_SPAN = "surveillance.assess"


class SurveillanceService:
    """Assess one account/instrument window into a disposition and record a redacted audit event."""

    def __init__(
        self,
        audit: AuditSinkPort,
        thresholds: PatternThresholds,
        *,
        tracer: ObservabilityTracerPort,
    ) -> None:
        self._audit = audit
        self._thresholds = thresholds
        self._tracer = tracer

    def assess(self, request: SurveillanceRequest, *, actor: str) -> SurveillanceCase:
        """Assess ``request`` deterministically and record the already-redacted audit event.

        The whole path runs inside one span. Its attributes are STRUCTURAL only, never the
        subject, the instrument, a transcript snippet or a fired signal: a trace backend is
        not the WORM audit trail; it has no redaction stage, a wider read audience and no
        retention rule written against a regulator's requirement, so anything content-shaped
        that reaches a span has left the boundary the ``redact`` call below exists to hold,
        and left it silently.
        """
        with self._tracer.span(_ASSESS_SPAN, action="assess", actor=actor, tenant=request.tenant):
            return self._assess(request, actor=actor)

    def _assess(self, request: SurveillanceRequest, *, actor: str) -> SurveillanceCase:
        signals = score_window(request.window, request.reference, self._thresholds)
        fired = tuple(s for s in signals if s.fired)
        comms_hits = request.comms_hits
        proximity = score_proximity(request.window, comms_hits)

        severity = _max_severity(
            tuple(s.severity for s in fired) + tuple(h.severity for h in comms_hits)
        )
        disposition = _disposition(fired, comms_hits, severity)
        consequential = disposition is not Disposition.CLOSE
        summary = _narrative(request, fired, comms_hits, disposition)
        citations = _citations(request, fired)

        # Redact BEFORE the audit write: no raw identifier reaches the WORM record.
        self._audit.record(
            AuditEvent(
                action="surveillance.assess",
                actor=actor,
                decision=disposition_to_decision(disposition),
                severity=severity,
                redacted_summary=redact(summary, PII_PATTERNS),
                citations=citations,
                timestamp=utcnow(),
            )
        )

        return SurveillanceCase(
            case_id=request.case_id,
            subject=request.subject,
            instrument=request.window.instrument,
            as_of=request.window.as_of,
            disposition=disposition,
            severity=severity,
            summary=summary,
            requires_human_review=consequential,
            signals=signals,
            comms_hits=comms_hits,
            proximity=proximity,
            citations=citations,
            tenant=request.tenant,
        )


__all__ = ["SurveillanceService"]
