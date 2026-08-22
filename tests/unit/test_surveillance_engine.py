"""The deterministic engines: market-abuse detectors, alert bands, redact-before-audit.

The market-abuse engine is the crown jewel: every score and every disposition comes from pure
code, replayable from ``as_of``. These tests pin each detector's behaviour, the disposition
tiering, the byte-identical replay, and the redact-before-write rule on both surfaces.
"""

from __future__ import annotations

from trade_comms_surveillance.adapters.local._fixtures import REFERENCE, WINDOWS
from trade_comms_surveillance.adapters.local.audit import (
    LocalAuditAdapter,
)
from trade_comms_surveillance.adapters.local.tracer import (
    LocalNoopTracerAdapter,
)
from trade_comms_surveillance.config import (
    Settings,
)
from trade_comms_surveillance.domain.abuse_patterns import (
    robust_z,
    score_window,
)
from trade_comms_surveillance.domain.alert_intake_service import (
    AlertIntakeService,
)
from trade_comms_surveillance.domain.kernel import (
    Decision,
    Disposition,
    Severity,
)
from trade_comms_surveillance.domain.models import (
    AlertInput,
    PatternType,
    SurveillanceRequest,
)
from trade_comms_surveillance.domain.surveillance_service import (
    SurveillanceService,
)
from trade_comms_surveillance.surveillance_pack import thresholds_for

_THRESHOLDS = thresholds_for(Settings(profile="local"))


def _tracer() -> LocalNoopTracerAdapter:
    return LocalNoopTracerAdapter(Settings(profile="local", audit_path=":memory:"))


def _service() -> tuple[SurveillanceService, LocalAuditAdapter]:
    audit = LocalAuditAdapter(Settings(profile="local", audit_path=":memory:"))
    return SurveillanceService(audit, _THRESHOLDS, tracer=_tracer()), audit


def _assess(instrument: str) -> SurveillanceRequest:
    return SurveillanceRequest(
        case_id=f"case:{instrument}",
        subject="trader-a",
        window=WINDOWS[instrument],
        reference=REFERENCE,
        tenant="demo-bank",
    )


def _fired_patterns(instrument: str) -> set[PatternType]:
    signals = score_window(WINDOWS[instrument], REFERENCE, _THRESHOLDS)
    return {s.pattern for s in signals if s.fired}


# --------------------------------------------------------------------------- #
# Each detector fires on its own seeded episode and not on the clean control
# --------------------------------------------------------------------------- #
def test_spoofing_layering_detector_fires_on_the_ladder() -> None:
    assert PatternType.SPOOFING_LAYERING in _fired_patterns("SPOOF.SG")


def test_wash_trading_detector_fires_on_the_self_cross() -> None:
    assert PatternType.WASH_TRADING in _fired_patterns("WASH.SG")


def test_insider_dealing_detector_fires_inside_a_blackout() -> None:
    assert PatternType.INSIDER_DEALING in _fired_patterns("INSIDE.SG")


def test_front_running_detector_fires_ahead_of_a_client_order() -> None:
    assert PatternType.FRONT_RUNNING in _fired_patterns("FRONT.SG")


def test_the_clean_control_fires_nothing() -> None:
    assert _fired_patterns("CLEAN.SG") == set()


def test_insider_verdict_changes_when_the_symbol_leaves_the_blackout() -> None:
    """Red-before/green-after: the same trade closes once the reference clears the window."""
    from dataclasses import replace

    fired_in = {
        s.pattern for s in score_window(WINDOWS["INSIDE.SG"], REFERENCE, _THRESHOLDS) if s.fired
    }
    assert PatternType.INSIDER_DEALING in fired_in
    cleared = replace(REFERENCE, blackouts=(), mnpi_holders=())
    fired_out = {
        s.pattern for s in score_window(WINDOWS["INSIDE.SG"], cleared, _THRESHOLDS) if s.fired
    }
    assert PatternType.INSIDER_DEALING not in fired_out


# --------------------------------------------------------------------------- #
# Dispositions and replay
# --------------------------------------------------------------------------- #
def test_dispositions_match_the_seeded_episodes() -> None:
    service, _ = _service()
    assert service.assess(_assess("INSIDE.SG"), actor="a").disposition is Disposition.FILE_STOR
    assert service.assess(_assess("SPOOF.SG"), actor="a").disposition is Disposition.ESCALATE
    assert service.assess(_assess("CLEAN.SG"), actor="a").disposition is Disposition.CLOSE


def test_a_consequential_case_requires_review_and_a_clean_one_does_not() -> None:
    service, _ = _service()
    assert service.assess(_assess("WASH.SG"), actor="a").requires_human_review is True
    assert service.assess(_assess("CLEAN.SG"), actor="a").requires_human_review is False


def test_the_engine_replays_byte_for_byte() -> None:
    a = score_window(WINDOWS["SPOOF.SG"], REFERENCE, _THRESHOLDS)
    b = score_window(WINDOWS["SPOOF.SG"], REFERENCE, _THRESHOLDS)
    assert a == b


def test_robust_z_is_zero_on_a_degenerate_sample() -> None:
    assert robust_z(5.0, [3.0, 3.0, 3.0]) == 0.0
    assert robust_z(5.0, [3.0]) == 0.0


# --------------------------------------------------------------------------- #
# The manual alert-intake surface
# --------------------------------------------------------------------------- #
def _band(text: str) -> Severity:
    audit = LocalAuditAdapter(Settings(profile="local", audit_path=":memory:"))
    service = AlertIntakeService(audit, tracer=_tracer())
    return service.assess(AlertInput("X", text), actor="a").severity


def test_alert_bands_are_deterministic() -> None:
    assert _band("possible insider dealing") is Severity.CRITICAL
    assert _band("urgent breach") is Severity.HIGH
    assert _band("billing dispute") is Severity.MEDIUM
    assert _band("all fine") is Severity.LOW


def test_high_and_critical_alerts_escalate_softly() -> None:
    audit = LocalAuditAdapter(Settings(profile="local", audit_path=":memory:"))
    service = AlertIntakeService(audit, tracer=_tracer())
    high = service.assess(AlertInput("X", "urgent spoofing"), actor="a")
    assert high.disposition is Disposition.ESCALATE
    assert high.requires_human_review is True

    low = service.assess(AlertInput("X", "routine note"), actor="a")
    assert low.disposition is Disposition.CLOSE
    assert low.requires_human_review is False


def test_pii_is_redacted_before_the_audit_write() -> None:
    audit = LocalAuditAdapter(Settings(profile="local", audit_path=":memory:"))
    AlertIntakeService(audit, tracer=_tracer()).assess(
        AlertInput("Gamma LLP", "urgent breach, NRIC S1234567D on file"),
        actor="analyst@bank.example",
    )
    records = audit.log.read_all()
    assert records, "an audit event should have been recorded"
    summary = records[-1]["redacted_summary"]
    assert "S1234567D" not in summary
    assert "REDACTED" in summary
    assert records[-1]["actor"] == "analyst@bank.example"
    assert records[-1]["decision"] == Decision.ESCALATED.value
    assert audit.log.verify_chain().ok
