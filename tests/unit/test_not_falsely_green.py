"""Prove every eval metric can go RED, per pattern (the not-falsely-green harness).

A metric that cannot fail proves nothing. The eval scores four metrics against the golden set;
here each is fed a clean case that must PASS and a degraded case that must FAIL, so a metric that
silently became a constant 1.0 breaks the build. ``assert_each_can_go_red`` runs the proof PER
market-abuse pattern, which is the safe form: a pattern missing from the config would score a
vacuous 1.0 that an aggregate check hides.

``pii_safety`` is the metric that had both halves of the problem. The previous version of this
file scored a local one-line helper defined three lines above the assertion. It passed, and it
proved nothing about the gate: the shipped metric read ``redacted_summary`` and nothing else,
which is the ONE field the redactor was already masking, so it asked the redactor whether it had
redacted and believed the answer. It reported ``pii_safety 1.000 0.99 PASS`` with the identifier
sitting in the same record's citation.

So that falsification runs against ``run_eval`` itself, imported as the gate imports it, and the
mutant is the leak the metric exists to catch: the SAME row, summary clean either way, differing
only in the citation. A metric that reads the wrong field cannot tell the two apart and stays
green on the red input, which is exactly the failure ``assert_can_go_red`` refuses.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

import run_eval as ev
from agent_eval_kit import assert_can_go_red, assert_each_can_go_red

from trade_comms_surveillance.adapters.local._fixtures import REFERENCE, WINDOWS
from trade_comms_surveillance.adapters.local.audit import LocalAuditAdapter
from trade_comms_surveillance.adapters.local.tracer import LocalNoopTracerAdapter
from trade_comms_surveillance.config import Settings
from trade_comms_surveillance.domain.alert_intake_service import AlertIntakeService
from trade_comms_surveillance.domain.models import SurveillanceCase, SurveillanceRequest
from trade_comms_surveillance.domain.surveillance_service import SurveillanceService
from trade_comms_surveillance.surveillance_pack import thresholds_for

from tests.fixtures import sample_cases

_THRESHOLDS = thresholds_for(Settings(profile="local"))
_NUMBER = re.compile(r"-?\d+\.?\d*")


def assess_engine(instrument: str) -> SurveillanceCase:
    """Run the deterministic engine over one seeded instrument (the eval's own scoring input)."""
    audit = LocalAuditAdapter(Settings(profile="local", audit_path=":memory:"))
    request = SurveillanceRequest(
        case_id=f"case:{instrument}",
        subject="trader-a",
        window=WINDOWS[instrument],
        reference=REFERENCE,
    )
    tracer = LocalNoopTracerAdapter(Settings(profile="local", audit_path=":memory:"))
    return SurveillanceService(audit, _THRESHOLDS, tracer=tracer).assess(request, actor="a")


def score_disposition(case: SurveillanceCase, expected: str) -> float:
    return 1.0 if case.disposition.value == expected else 0.0


def score_groundedness(case: SurveillanceCase) -> float:
    """1.0 when every number in the narrative traces to a figure the engine produced."""
    allowed = {f"{s.score:g}" for s in case.fired_signals}
    allowed |= {f"{s.threshold:g}" for s in case.fired_signals}
    allowed |= {str(h.turn_index) for h in case.comms_hits}
    tokens = _NUMBER.findall(case.summary)
    return 0.0 if any(f"{float(t):g}" not in allowed for t in tokens) else 1.0


#: One (instrument, expected_disposition) per pattern, plus the clean control.
_PATTERN_TRUTH: dict[str, tuple[str, str]] = {
    "insider_dealing": ("INSIDE.SG", "file_stor"),
    "spoofing_layering": ("SPOOF.SG", "escalate"),
    "wash_trading": ("WASH.SG", "file_stor"),
    "front_running": ("FRONT.SG", "file_stor"),
    "clean": ("CLEAN.SG", "close"),
}


def test_disposition_accuracy_can_go_red_per_pattern() -> None:
    """Green: the engine's disposition scored against the CORRECT expected value. Red: against a
    deliberately wrong one, so a scorer that ignored the oracle would be caught."""

    def _score(pair: tuple[str, str]) -> float:
        instrument, expected = pair
        return score_disposition(assess_engine(instrument), expected)

    _WRONG = {
        "close": "file_stor",
        "escalate": "close",
        "file_stor": "close",
    }
    cases = {
        pattern: ((instrument, expected), (instrument, _WRONG[expected]))
        for pattern, (instrument, expected) in _PATTERN_TRUTH.items()
    }
    assert_each_can_go_red(_score, cases, threshold=0.80, metric="disposition_accuracy")


def test_groundedness_can_go_red() -> None:
    """Green: a real engine case, whose every figure it produced. Red: the same case with a
    fabricated number spliced into the narrative, which a grounded metric must reject."""
    case = _real_case("INSIDE.SG")
    fabricated = replace(case, summary=case.summary + " fabricated 999999.0")
    assert_can_go_red(
        score_groundedness,
        green=case,
        red=fabricated,
        threshold=1.0,
        metric="groundedness",
    )


def _real_case(instrument: str) -> SurveillanceCase:
    return assess_engine(instrument)


_PLANTED = (sample_cases.PLANTED_NRIC,)

#: The summary is CLEAN in both rows. That is the whole point: the summary was never the field
#: that leaked, so a metric that only reads it scores these two identically.
_CLEAN_ROW: dict[str, Any] = {
    "action": "surveillance.alert_intake",
    "actor": sample_cases.ACTOR,
    "redacted_summary": (
        "Gamma LLP (FICTIONAL): manual alert scored critical (file_stor) :: "
        "chat 09:41 trader-a: insider tip, NRIC [REDACTED:SG_NRIC_FIN]"
    ),
    "citations": [
        {
            "source_id": "alert:Gamma LLP (FICTIONAL)",
            "title": "Analyst alert note",
            "snippet": "chat 09:41 trader-a: insider tip, NRIC [REDACTED:SG_NRIC_FIN]",
        }
    ],
}

#: Redaction off, in the citation only (the mutant the shipped metric used to score 1.000).
_LEAKY_ROW: dict[str, Any] = {
    **_CLEAN_ROW,
    "citations": [
        {
            "source_id": f"alert:Gamma LLP (FICTIONAL) {sample_cases.PLANTED_NRIC}",
            "title": "Analyst alert note",
            "snippet": f"chat 09:41 trader-a: insider tip, NRIC {sample_cases.PLANTED_NRIC}",
        }
    ],
}


def _score(rows: list[dict[str, Any]]) -> float:
    """The gate's own scorer over the gate's own field selection. No re-implementation here."""
    return ev.pii_safety(ev.audit_texts(rows), _PLANTED)


def test_pii_safety_can_go_red() -> None:
    assert_can_go_red(
        _score,
        green=[_CLEAN_ROW],
        red=[_LEAKY_ROW],
        threshold=ev.THRESHOLDS["pii_safety"],
        metric="pii_safety",
    )


def test_pii_safety_is_green_on_the_record_the_real_service_writes() -> None:
    """Green, and green over a real run rather than over an empty list of nothing."""
    settings = Settings(profile="local", audit_path=":memory:")
    audit = LocalAuditAdapter(settings)
    AlertIntakeService(audit, tracer=LocalNoopTracerAdapter(settings)).assess(
        sample_cases.PII_SUBJECT_ALERT, actor=sample_cases.ACTOR
    )

    texts = ev.audit_texts(audit.log.read_all())
    assert any("[REDACTED:" in text for text in texts), (
        "the scan found no redaction marker, so it is reading fields that carry no content "
        "and its green means nothing"
    )
    assert ev.pii_safety(texts, (*_PLANTED, sample_cases.PLANTED_EMAIL)) == 1.0


def test_the_scan_excludes_the_actor_so_it_can_ever_be_green() -> None:
    """The caveat, pinned: widening this to whole rows makes the metric permanently red.

    ``actor`` is the verified principal and is an address by design. A well-meaning "scan the
    whole record" change would make every run fail on the attribution column, and the next
    person would relax the threshold rather than narrow the scan.
    """
    row: dict[str, Any] = {**_CLEAN_ROW, "actor": "analyst@bank.example"}
    assert ev.pii_safety(ev.audit_texts([row]), _PLANTED) == 1.0
