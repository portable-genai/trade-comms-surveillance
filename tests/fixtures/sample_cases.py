"""Canonical synthetic cases, shared by the unit and contract suites.

Every party is obviously fictional and every address is an ``.example`` domain or an RFC 5737 /
RFC 3849 literal. The manual-alert path uses :class:`AlertInput`; the market-abuse engine uses a
:class:`SurveillanceRequest` built from the offline fixtures, so the contract suite drives the
SAME request through every implementation rather than retyping it per test.
"""

from __future__ import annotations

from trade_comms_surveillance.adapters.local._fixtures import BASE, REFERENCE, WINDOWS
from trade_comms_surveillance.domain.models import (
    AlertInput,
    SurveillanceRequest,
)

#: The verified principal the tests attribute work to (never a client-asserted actor).
ACTOR = "analyst@bank.example"

#: A tenant partition, so the outbound-review assertions are not all on the empty string.
TENANT = "demo-bank"

#: The account under review in the canonical engine request.
SUBJECT = "trader-a"

#: An alert that MUST escalate: the deterministic band is HIGH, so rule R8 routing applies.
ESCALATING_ALERT = AlertInput(
    subject="Acme Holdings (FICTIONAL)",
    text="urgent spoofing and layering suspected on the SGX book",
)

#: An alert that must NOT escalate: a router that manufactured a review here would be lying.
ROUTINE_ALERT = AlertInput(
    subject="Beta Trading (FICTIONAL)",
    text="routine note about a stationery order",
)

#: A planted identifier, so a redaction assertion has an independent literal to look for
#: rather than trusting the pattern pack to agree with itself.
PLANTED_NRIC = "S1234567D"

#: A planted address, so the universal rows have an independent literal of their own.
PLANTED_EMAIL = "kai.tan@delta.example"

#: An escalating alert that also carries personal data, for the redact-before-anything proofs.
PII_ALERT = AlertInput(
    subject="Gamma LLP (FICTIONAL)",
    text=f"urgent breach, NRIC {PLANTED_NRIC} and mail ops@gamma.example on file",
)

#: The same, with the identifier in the SUBJECT as well. The citation LOCATOR is built from the
#: subject and the citation SNIPPET is cut from the note, which in this vertical is a recorded
#: chat or email body, so a redactor that masks only the summary writes the identifier back into
#: the WORM record from two fields nobody was looking at.
PII_SUBJECT_ALERT = AlertInput(
    subject=f"Delta Capital (FICTIONAL) NRIC {PLANTED_NRIC}",
    text=(
        f"chat 09:41 trader-a: insider tip for {PLANTED_EMAIL}, NRIC {PLANTED_NRIC}, "
        "results print early, keep it off-channel"
    ),
)


def engine_request(instrument: str = "SPOOF.SG", *, tenant: str = TENANT) -> SurveillanceRequest:
    """A canonical engine request over a seeded window (SPOOF.SG fires by default)."""
    return SurveillanceRequest(
        case_id=f"case:{instrument}",
        subject=SUBJECT,
        window=WINDOWS[instrument],
        reference=REFERENCE,
        tenant=tenant,
    )


#: The canonical as-of for reference/comms lookups in the contract suite.
AS_OF = BASE
