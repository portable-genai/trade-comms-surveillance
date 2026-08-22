"""Each surveillance path opens ONE span, and no span carries content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit
store. So the value of tracing these paths depends entirely on the spans carrying
structural attributes only: which action, whose, which tenant. An alert's free text, a
subject, an instrument, a transcript snippet or a planted identifier reaching a span has
left the boundary the services' ``redact`` calls exist to hold, and it has left it silently.

Two orchestrators are pinned because both sit on real request paths: the manual alert
intake (API, CLI, agent tool) and the market-abuse engine (CLI, agent tool, eval, demo via
the pipeline). They do not nest: neither drives the other. The content case drives the
alert whose text carries a planted NRIC, so the check runs against input that would
actually leak.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from trade_comms_surveillance.config import Settings, build_container
from trade_comms_surveillance.domain.alert_intake_service import AlertIntakeService
from trade_comms_surveillance.domain.models import AlertInput
from trade_comms_surveillance.domain.surveillance_service import SurveillanceService
from trade_comms_surveillance.surveillance_pack import thresholds_for

from tests.fixtures import sample_cases

#: Every attribute key each span is allowed to carry. A verdict that started explaining
#: itself on the span (a disposition, a subject, a snippet) would widen these sets, which is
#: the point of asserting on the set rather than on the individual keys.
_ALERT_KEYS = {"action", "actor"}
_ASSESS_KEYS = {"action", "actor", "tenant"}


class _RecordingTracer:
    """Captures every span name and attribute so the test can inspect what was emitted."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _settings() -> Settings:
    return Settings(profile="local", audit_path=":memory:")


def _alert(alert: AlertInput) -> _RecordingTracer:
    tracer = _RecordingTracer()
    container = build_container(_settings())
    service = AlertIntakeService(container.audit, tracer=tracer)  # type: ignore[arg-type]
    service.assess(alert, actor=sample_cases.ACTOR)
    return tracer


def _surveil(instrument: str = "SPOOF.SG") -> _RecordingTracer:
    tracer = _RecordingTracer()
    settings = _settings()
    container = build_container(settings)
    service = SurveillanceService(
        container.audit,
        thresholds_for(settings),
        tracer=tracer,  # type: ignore[arg-type]
    )
    service.assess(sample_cases.engine_request(instrument), actor=sample_cases.ACTOR)
    return tracer


def _emitted(tracer: _RecordingTracer) -> str:
    """Every attribute KEY and VALUE that was emitted, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


def test_a_manual_alert_opens_exactly_one_named_span() -> None:
    tracer = _alert(sample_cases.ROUTINE_ALERT)
    assert [name for name, _ in tracer.spans] == ["surveillance.alert_intake"]


def test_an_engine_assessment_opens_exactly_one_named_span() -> None:
    tracer = _surveil()
    assert [name for name, _ in tracer.spans] == ["surveillance.assess"]


def test_the_alert_span_carries_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose intake is slow", and nothing more."""
    _, attributes = _alert(sample_cases.ROUTINE_ALERT).spans[0]
    assert attributes["action"] == "alert_intake"
    assert attributes["actor"] == sample_cases.ACTOR


def test_the_assess_span_carries_the_structural_attributes_an_operator_needs() -> None:
    _, attributes = _surveil().spans[0]
    assert attributes["action"] == "assess"
    assert attributes["actor"] == sample_cases.ACTOR
    assert attributes["tenant"] == sample_cases.TENANT


@pytest.mark.parametrize(
    "alert",
    [sample_cases.ROUTINE_ALERT, sample_cases.ESCALATING_ALERT, sample_cases.PII_ALERT],
    ids=["routine", "escalating", "pii"],
)
def test_the_alert_attribute_set_is_a_fixed_allowlist_whatever_the_verdict(
    alert: AlertInput,
) -> None:
    """An escalating alert must not start attaching its band, or its text, to the span."""
    for _, attributes in _alert(alert).spans:
        assert set(attributes) == _ALERT_KEYS, (
            "a new span attribute appeared; confirm it is structural, then widen "
            "_ALERT_KEYS here deliberately"
        )


def test_the_assess_attribute_set_is_a_fixed_allowlist() -> None:
    """A fired signal must not start attaching its instrument, or its score, to the span."""
    for _, attributes in _surveil().spans:
        assert set(attributes) == _ASSESS_KEYS, (
            "a new span attribute appeared; confirm it is structural, then widen "
            "_ASSESS_KEYS here deliberately"
        )


def test_no_alert_span_attribute_carries_content_or_the_planted_identifier() -> None:
    """The alert used here has an NRIC planted in its free text, so a leak would show."""
    emitted = _emitted(_alert(sample_cases.PII_ALERT)).lower()
    forbidden = (
        sample_cases.PLANTED_NRIC,
        sample_cases.PII_ALERT.text,
        sample_cases.PII_ALERT.subject,
        "ops@gamma.example",
        "urgent breach",
    )
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal.lower() not in emitted, f"a span attribute carried {literal!r}"


def test_no_assess_span_attribute_carries_the_subject_or_the_instrument() -> None:
    """The window's identifiers are the content-shaped values in reach of this call site."""
    emitted = _emitted(_surveil()).lower()
    for literal in (sample_cases.SUBJECT, "SPOOF.SG", "case:SPOOF.SG"):
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal.lower() not in emitted, f"a span attribute carried {literal!r}"


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    values = [
        value
        for tracer in (_alert(sample_cases.ESCALATING_ALERT), _surveil())
        for _, attributes in tracer.spans
        for value in attributes.values()
    ]
    assert values
    assert all(isinstance(value, str) for value in values)
