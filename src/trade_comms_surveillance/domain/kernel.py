"""Vertical-neutral domain kernel: pure-stdlib types the service reasons over.

Taxonomies are ``StrEnum``s from the commons (a member IS its wire value), citations carry
provenance, and the WORM audit record is stored already-redacted. Nothing here imports a web
framework or a cloud SDK (the commons packages it uses are themselves stdlib).

"Already redacted" is ENFORCED here rather than asked of every call site: see
:class:`AuditEvent`. The pattern selection comes from the sibling ``domain.pii``, which is the
one vertical-specific thing this module knows, because a boundary that cannot name the rows it
masks with is not a boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from hex_service_kit.enums import LenientStrEnum
from pii_kit import redact

from .pii import PII_PATTERNS


def utcnow() -> datetime:
    """Timezone-aware UTC now (the single clock the domain uses)."""
    return datetime.now(UTC)


class TenantAccessDeniedError(PermissionError):
    """Raised when a principal reads a record belonging to another tenant (HTTP 403, not 404).

    403 rather than 404 is deliberate: the record EXISTS, the caller simply may not see it, and
    pretending it is absent would leak whether an id is in use across the tenant boundary.
    """

    http_status = 403


def authorize_tenant(record_tenant: str, principal_tenant: str) -> None:
    """Deny unless the record's tenant matches the verified principal's tenant.

    The check lives in the domain so every driving adapter inherits it and no store adapter can
    become the only place the boundary is enforced. Both tenants come from server-side state (the
    stored record and the verified principal), never from anything a client wrote.
    """
    if record_tenant != principal_tenant:
        raise TenantAccessDeniedError(
            "case belongs to another tenant; access denied at the tenant boundary"
        )


class Severity(LenientStrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Decision(LenientStrEnum):
    ALLOWED = "allowed"
    ESCALATED = "escalated"  # routed to a human (maker-checker, P-06)


class Disposition(LenientStrEnum):
    """The surveillance tier the deterministic engine assigns to a case.

    The tier is owned by pure code, never by a model: ``CLOSE`` closes the alert with no human
    action, ``ESCALATE`` routes to a conduct analyst, and ``FILE_STOR`` recommends a Suspicious
    Transaction and Order Report. Filing is always a human act, so ``FILE_STOR`` is a
    RECOMMENDATION that sets ``requires_human_review`` and routes to Hrz7; the engine never files.
    """

    CLOSE = "close"
    ESCALATE = "escalate"
    FILE_STOR = "file_stor"


#: Which dispositions are consequential (route to a human under rule R8). ``CLOSE`` is the only
#: terminal-without-review tier, and it is terminal precisely because the engine found nothing.
CONSEQUENTIAL_DISPOSITIONS: frozenset[Disposition] = frozenset(
    {Disposition.ESCALATE, Disposition.FILE_STOR}
)


def disposition_to_decision(disposition: Disposition) -> Decision:
    """Map a surveillance tier onto the audit ``Decision`` taxonomy (CLOSE is ALLOWED)."""
    return Decision.ALLOWED if disposition is Disposition.CLOSE else Decision.ESCALATED


@dataclass(frozen=True, slots=True)
class Citation:
    """Provenance attached to a generated claim (source + optional locator)."""

    source_id: str
    title: str
    snippet: str = ""


def redacted_citations(citations: tuple[Citation, ...]) -> tuple[Citation, ...]:
    """Mask EVERY field of every citation: the locator and the title as well as the snippet.

    A snippet is a slice of its source and a locator is routinely built from one
    (``alert:<the alert subject>``), so both are raw client text wearing a structural-looking
    name. In this vertical the source is recorded trader comms, so a snippet is a chat or email
    body and carries whatever the desk typed. No sink can tell an engine-built citation from an
    intake-built one by inspection, so this masks unconditionally: redacting a threshold pack's
    regulator instrument carries no identifier and is a no-op, while deciding per caller is how
    one caller ends up forgetting.
    """
    return tuple(
        Citation(
            source_id=redact(c.source_id, PII_PATTERNS),
            title=redact(c.title, PII_PATTERNS),
            snippet=redact(c.snippet, PII_PATTERNS),
        )
        for c in citations
    )


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """An immutable, already-redacted record of one interaction (P-04 / rule R2).

    "Already redacted" as a convention each call site has to remember is not enough: a call site
    that masks ``redacted_summary`` and passes its citations through untouched writes the
    identifier into the WORM record anyway, one field away, into a record that is immutable and
    long-retained by design. So construction masks every CONTENT field: the summary, and each
    citation's locator, title and snippet. Redaction is idempotent, so a caller that already
    redacted loses nothing by the second pass.

    ``actor`` is NOT masked. It is the verified principal and is an address by design: it is
    attribution, not content, and masking it would erase the only column that says who acted.
    That is also why a leak scan runs over the content fields rather than over a whole row.
    """

    action: str
    actor: str
    decision: Decision
    severity: Severity
    redacted_summary: str
    citations: tuple[Citation, ...] = ()
    timestamp: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "redacted_summary", redact(self.redacted_summary, PII_PATTERNS))
        object.__setattr__(self, "citations", redacted_citations(tuple(self.citations)))
