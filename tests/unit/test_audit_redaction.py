"""Nothing redaction removed survives anywhere else in the WORM record (check C3).

The service masked ``redacted_summary`` and then handed the SAME event its citations untouched,
so the identifier the summary no longer carried was persisted verbatim one field away, in a
record that is by design immutable and long-retained. The summary is not the record.

This vertical makes that worse than most: the source a citation quotes is recorded trader comms,
so a snippet IS a chat or email body and a locator is built from the alert subject an analyst
typed. Both are raw client text wearing a structural-looking name.

Two rules this suite holds, and they pull in opposite directions, which is why both are written
down:

* every CONTENT field is scanned: the summary, and each citation's locator, title and snippet.
* the ATTRIBUTION field is not. ``actor`` is the verified principal and is an address by design,
  so a blanket scan over a whole audit row could never go green, and a scan that "fixed" that by
  masking the actor would erase the only column that says who acted.

Scored two ways, as the eval metric is: the shared pack's own rows, plus the planted literals,
which still fire if a pattern row is broken.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, fields
from typing import Any

import pytest
from pii_kit import pack_leak
from review_kit import Review

from trade_comms_surveillance.adapters._review_payload import result_to_review
from trade_comms_surveillance.adapters.local.audit import LocalAuditAdapter
from trade_comms_surveillance.config import Container
from trade_comms_surveillance.domain.alert_intake_service import AlertIntakeService
from trade_comms_surveillance.domain.models import AlertInput
from trade_comms_surveillance.domain.pii import PII_PATTERNS

from tests.fixtures import sample_cases

_PLANTED = (sample_cases.PLANTED_NRIC, sample_cases.PLANTED_EMAIL)


def _content(row: Mapping[str, Any]) -> str:
    """Every content-bearing field of one audit row, as one scannable blob.

    ``actor`` and the structural columns are excluded deliberately: see the module docstring.
    """
    return " ".join(
        (
            str(row.get("redacted_summary", "")),
            json.dumps(row.get("citations", []), sort_keys=True),
        )
    )


@pytest.mark.parametrize(
    "alert",
    [sample_cases.PII_ALERT, sample_cases.PII_SUBJECT_ALERT],
    ids=["identifier-in-the-comms-body", "identifier-in-the-subject-and-the-body"],
)
def test_no_identifier_reaches_the_audit_record(
    alert_service: AlertIntakeService, container: Container, alert: AlertInput
) -> None:
    alert_service.assess(alert, actor=sample_cases.ACTOR)

    audit = container.audit
    assert isinstance(audit, LocalAuditAdapter)
    rows = list(audit.log.read_all())
    assert rows, "the alert-intake path wrote no audit record, so this proves nothing"

    for row in rows:
        blob = _content(row)
        assert not pack_leak(blob, PII_PATTERNS), f"pack row matched in the WORM record: {blob}"
        for token in _PLANTED:
            assert token not in blob, f"planted {token!r} survived into the WORM record: {blob}"


def test_the_actor_is_kept_verbatim_because_it_is_attribution(
    alert_service: AlertIntakeService, container: Container
) -> None:
    """The caveat, pinned: the principal is an address and must NOT be masked away."""
    alert_service.assess(sample_cases.PII_ALERT, actor=sample_cases.ACTOR)

    audit = container.audit
    assert isinstance(audit, LocalAuditAdapter)
    actors = [str(row.get("actor", "")) for row in audit.log.read_all()]
    assert actors == [sample_cases.ACTOR]


#: The ONLY fields the payload scan skips, and why. ``maker`` is the verified principal and is an
#: address by design, exactly as ``AuditEvent.actor`` is: it is attribution, not content, so a
#: scan that included it could never go green. Everything else on the Review is content until
#: proved otherwise, including fields added after this was written.
_ATTRIBUTION_FIELDS = frozenset({"maker"})


def _wire_payload(review: Review) -> str:
    """The whole Review as it would be serialised, minus the attribution field.

    Built from ``dataclasses.asdict`` rather than a hand-written list of fields, so a field added
    to the Review later is scanned by DEFAULT instead of by somebody remembering to add it here.
    That is the specific way this defect stayed hidden: ``case_ref`` and ``source_key`` were
    never in anyone's list.
    """
    payload = {
        key: value for key, value in asdict(review).items() if key not in _ATTRIBUTION_FIELDS
    }
    return json.dumps(payload, sort_keys=True, default=str)


def test_the_scan_covers_every_review_field_except_the_named_attribution_one() -> None:
    """The exclusion list is pinned, so nothing is quietly dropped out of the scan later."""
    review_fields = {f.name for f in fields(Review)}
    unknown = _ATTRIBUTION_FIELDS - review_fields
    assert not unknown, f"the exclusion names fields the Review no longer has: {sorted(unknown)}"

    scanned = review_fields - _ATTRIBUTION_FIELDS
    for expected in ("subject", "summary", "case_ref", "source_key", "sod_group", "citations"):
        assert expected in scanned, f"{expected} must be scanned but is not"


def test_the_whole_review_payload_is_redacted_not_only_its_narrative_fields(
    alert_service: AlertIntakeService,
) -> None:
    """Every field that crosses to the console, including the ones with structural names.

    ``subject`` and ``summary`` were masked and ``case_ref`` and ``source_key`` were not, so the
    identifier the payload had just removed from one field crossed the wire in the two beside it.
    Here the key fields are derived from ``case_id``, which the intake path builds as
    ``alert:<the alert subject>``, so they carry whatever the analyst typed. A citation LOCATOR is
    the same trap one level down.
    """
    case = alert_service.assess(sample_cases.PII_SUBJECT_ALERT, actor=sample_cases.ACTOR)
    review = result_to_review(case, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)

    blob = _wire_payload(review)
    assert not pack_leak(blob, PII_PATTERNS), f"pack row matched in the review payload: {blob}"
    for token in _PLANTED:
        assert token not in blob, f"planted {token!r} crossed to the console: {blob}"


def test_the_idempotency_key_is_stable_across_retries(
    alert_service: AlertIntakeService,
) -> None:
    """Redacting the key must not make it a moving target, or every retry becomes a new review.

    The masking substitutes a fixed token per pattern, so the key is a pure function of the case.
    Checked rather than assumed, because the whole point of a source key is that a redelivery
    lands on the same one.
    """
    case = alert_service.assess(sample_cases.PII_SUBJECT_ALERT, actor=sample_cases.ACTOR)
    keys = {
        result_to_review(case, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT).source_key
        for _ in range(200)
    }
    assert len(keys) == 1, f"the idempotency key is not stable across retries: {sorted(keys)}"
