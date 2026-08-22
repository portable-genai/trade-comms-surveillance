#!/usr/bin/env python3
"""Evaluation gate for Trade Comms Surveillance (Cmp1).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the REAL
  deterministic engine and the alert-intake path against a golden set with SDK-free local
  adapters and scores four metrics.
* **gate** - the promotion verdict from the shared Hrz4 authority (requires the ``gcp`` profile),
  via ``agent_eval_kit.PromotionGateClient``.

Every metric scores against the DATASET'S OWN expected_outcome, an independent golden oracle,
never the pipeline's own verdict. ``tests/unit/test_not_falsely_green.py`` wires
``agent_eval_kit.assert_each_can_go_red`` so a metric that cannot go red fails the build.

Exit is ``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_eval_kit import EvalMetricResult, EvalReport, PromotionGateClient, eval_main
from pii_kit import pack_leak

from trade_comms_surveillance.config import Settings, build_container
from trade_comms_surveillance.domain.alert_intake_service import AlertIntakeService
from trade_comms_surveillance.domain.models import AlertInput, SurveillanceCase
from trade_comms_surveillance.domain.pii import PII_PATTERNS
from trade_comms_surveillance.pipeline import assess_instrument
from trade_comms_surveillance.surveillance_pack import thresholds_for

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

THRESHOLDS: dict[str, float] = {
    "disposition_accuracy": 0.80,
    "review_safety": 1.0,
    "groundedness": 1.0,
    "pii_safety": 0.99,
}
#: The registered Hrz4 metric bundle for this vertical (Hrz4 owns the metrics + thresholds).
_BUNDLE = "trade-comms-surveillance"

_NUMBER = re.compile(r"-?\d+\.?\d*")


def _load(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 1.0


def assess_engine(instrument: str) -> SurveillanceCase:
    """Run the deterministic engine over one instrument on the offline profile (no routing)."""
    container = build_container(Settings(profile="local", audit_path=":memory:", tenant="eval"))
    thresholds = thresholds_for(container.settings)
    return assess_instrument(
        container,
        thresholds,
        instrument=instrument,
        subject="trader-a",
        actor="eval-bot",
        tenant="eval",
        route=False,
    ).case


def score_disposition(case: SurveillanceCase, expected: str) -> float:
    """1.0 when the engine's disposition matches the independent expected disposition."""
    return 1.0 if case.disposition.value == expected else 0.0


def score_review_safety(case: SurveillanceCase, expected_consequential: bool) -> float:
    """1.0 when a consequential case is flagged for review and a benign one is not.

    The oracle is the dataset's own ``expected_consequential``, never the case's own flag, so the
    metric can catch a pipeline that quietly failed to escalate.
    """
    return 1.0 if case.requires_human_review == expected_consequential else 0.0


def score_groundedness(case: SurveillanceCase) -> float:
    """1.0 when every number in the narrative traces to an engine figure it produced.

    A narrative may only RESTATE engine findings, so any numeric token in the summary that is not
    a fired signal's score/threshold or a window count is a fabricated figure and fails the case.
    """
    allowed: set[str] = set()
    for signal in case.fired_signals:
        allowed.add(_norm(signal.score))
        allowed.add(_norm(signal.threshold))
    for hit in case.comms_hits:
        allowed.add(str(hit.turn_index))
    for token in _NUMBER.findall(case.summary):
        if _norm(float(token)) not in allowed:
            return 0.0
    return 1.0


def _norm(value: float) -> str:
    return f"{value:g}"


def audit_texts(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Every CONTENT-bearing field of every audit row, which is what a leak scan has to read.

    Collecting ``redacted_summary`` and nothing else would name the one field the
    redactor already masks: the metric would ask the redactor whether it had redacted, believe
    the answer, and report a green while the SAME record's citation snippet carries the
    identifier verbatim. Citations travel inside the record, and in this vertical the source they
    quote is recorded trader comms, so ``snippet`` is a chat or email body and ``source_id`` is a
    locator built from the alert subject an analyst typed.

    ``actor`` is excluded deliberately: it is the verified principal and an address by design, so
    a blanket scan over a whole row could never go green, and a metric nobody can make green
    gets deleted rather than fixed.
    """
    texts: list[str] = []
    for row in rows:
        texts.append(str(row.get("redacted_summary", "")))
        texts.append(json.dumps(row.get("citations", []), sort_keys=True))
    return texts


def pii_safety(records: Sequence[str], planted: Sequence[str]) -> float:
    """No identifier may survive into an audit record, by the pack rows OR by planted literal.

    Two oracles, because they fail independently: the pack scan uses the same rows the redactor
    masks with (so a redactor that skipped a field is caught), and the planted-literal check
    fires even if a pattern row is broken (so a pack that stopped matching is caught too).
    """
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in records)
    literal_leaked = any(token in text for token in planted for text in records)
    return 0.0 if (pack_leaked or literal_leaked) else 1.0


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)

    disposition: list[float] = []
    review: list[float] = []
    grounded: list[float] = []
    for case in (c for c in cases if c.get("kind") == "engine"):
        assessed = assess_engine(str(case["instrument"]))
        disposition.append(score_disposition(assessed, str(case["expected_disposition"])))
        review.append(score_review_safety(assessed, bool(case["expected_consequential"])))
        grounded.append(score_groundedness(assessed))

    # pii_safety on the alert-intake path: no planted raw identifier may survive into an audit
    # record. `audit_texts` decides WHICH fields count as the record's content; see its docstring
    # for why the summary alone is not the record.
    container = build_container(Settings(profile="local", audit_path=":memory:", tenant="eval"))
    service = AlertIntakeService(container.audit, tracer=container.tracer)
    planted: list[str] = []
    for case in (c for c in cases if c.get("kind") == "alert"):
        service.assess(AlertInput(subject=str(case["subject"]), text=str(case["text"])), actor="e")
        if case.get("planted"):
            planted.append(str(case["planted"]))
    records = audit_texts(container.audit.log.read_all())

    results = (
        EvalMetricResult.scored(
            "disposition_accuracy", _mean(disposition), THRESHOLDS["disposition_accuracy"]
        ),
        EvalMetricResult.scored("review_safety", _mean(review), THRESHOLDS["review_safety"]),
        EvalMetricResult.scored("groundedness", _mean(grounded), THRESHOLDS["groundedness"]),
        EvalMetricResult.scored(
            "pii_safety", pii_safety(records, planted), THRESHOLDS["pii_safety"]
        ),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"TRADECOMMS_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("TRADECOMMS_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-3.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / Hrz4 evaluation gate for Cmp1.",
        )
    )
