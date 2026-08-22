"""Conduct-alert intake: the deterministic manual-alert surface (pure bands, redact-before-audit).

The compact companion to the market-abuse engine. An analyst logs a free-text alert about a
party; this service scores the note into a severity band with pure stdlib keyword rules (no model
produces the band), maps the band to a surveillance disposition, redacts before the audit write
(R1/P-04), cites the note, and sets ``requires_human_review`` on every consequential disposition
so the driving layer routes it to Hrz7 (rule R8). The structured order-book detection lives in
``surveillance_service.py`` and ``abuse_patterns.py``; this path is for the manual alert an
analyst raises before there is a window to replay.
"""

from __future__ import annotations

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.observability import ObservabilityTracerPort
from .kernel import (
    AuditEvent,
    Citation,
    Disposition,
    Severity,
    disposition_to_decision,
    utcnow,
)
from .models import AlertInput, SurveillanceCase
from .pii import PII_PATTERNS

# Deterministic keyword bands (the manual-alert IP; swap for adopter policy). Most severe first.
_SEVERITY_KEYWORDS: tuple[tuple[Severity, frozenset[str]], ...] = (
    (Severity.CRITICAL, frozenset({"insider", "mnpi", "fraud", "collusion"})),
    (Severity.HIGH, frozenset({"breach", "spoof", "layering", "wash", "urgent", "front-run"})),
    (Severity.MEDIUM, frozenset({"complaint", "dispute", "delay", "off-channel"})),
)

#: Band to disposition: a critical manual alert recommends a STOR, a high one escalates, and
#: anything lower closes. The engine owns this mapping; a model never sees it.
_BAND_DISPOSITION: dict[Severity, Disposition] = {
    Severity.CRITICAL: Disposition.FILE_STOR,
    Severity.HIGH: Disposition.ESCALATE,
    Severity.MEDIUM: Disposition.CLOSE,
    Severity.LOW: Disposition.CLOSE,
}

#: One span per manual alert. Structural attributes only: see :meth:`AlertIntakeService.assess`.
_ALERT_SPAN = "surveillance.alert_intake"


class AlertIntakeService:
    """Score a manual alert into a disposition and record an already-redacted audit event."""

    def __init__(self, audit: AuditSinkPort, *, tracer: ObservabilityTracerPort) -> None:
        self._audit = audit
        self._tracer = tracer

    def assess(self, alert: AlertInput, *, actor: str) -> SurveillanceCase:
        """Score ``alert`` deterministically and record the already-redacted audit event.

        The whole path runs inside one span. Its attributes are STRUCTURAL only, never the
        alert's free text, its subject or any finding: a trace backend is not the WORM audit
        trail; it has no redaction stage, a wider read audience and no retention rule written
        against a regulator's requirement, so anything content-shaped that reaches a span has
        left the boundary the ``redact`` call below exists to hold, and left it silently.
        """
        with self._tracer.span(_ALERT_SPAN, action="alert_intake", actor=actor):
            return self._assess(alert, actor=actor)

    def _assess(self, alert: AlertInput, *, actor: str) -> SurveillanceCase:
        severity = self._severity(alert.text)
        disposition = _BAND_DISPOSITION[severity]
        consequential = disposition is not Disposition.CLOSE
        summary = f"{alert.subject}: manual alert scored {severity.value} ({disposition.value})"
        citation = Citation(
            source_id=f"alert:{alert.subject}",
            title="Analyst alert note",
            snippet=alert.text[:80],
        )
        now = utcnow()

        # Redact BEFORE the audit write: raw identifiers never reach the WORM record.
        self._audit.record(
            AuditEvent(
                action="surveillance.alert_intake",
                actor=actor,
                decision=disposition_to_decision(disposition),
                severity=severity,
                redacted_summary=redact(f"{summary} :: {alert.text}", PII_PATTERNS),
                citations=(citation,),
                timestamp=now,
            )
        )

        return SurveillanceCase(
            case_id=f"alert:{alert.subject}",
            subject=alert.subject,
            instrument="",
            as_of=now,
            disposition=disposition,
            severity=severity,
            summary=summary,
            requires_human_review=consequential,
            citations=(citation,),
        )

    @staticmethod
    def _severity(text: str) -> Severity:
        lowered = text.lower()
        for severity, keywords in _SEVERITY_KEYWORDS:
            if any(word in lowered for word in keywords):
                return severity
        return Severity.LOW


__all__ = ["AlertIntakeService"]
