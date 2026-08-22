"""Tool functions an agent runtime calls: thin, side-effect-honest wrappers on the services.

Design rules, in the order they matter:

* **No business logic here.** The domain service decides HOW; the model only decides WHICH tool
  to call. A rule that lives in a tool wrapper is a rule the CLI and the API do not have.
* **Rule R8 applies on this path too.** An escalated result is ROUTED from inside the tool, in
  the same call that produced it. An agent surface that only returned the flag would be a third
  place an escalation can quietly stop, after the API and the CLI.
* **Import-safe without a runtime.** ``google.adk`` is imported lazily inside
  :func:`build_function_tools`, so these callables are importable, testable and runnable with
  no ADK and no cloud SDK installed.
* **Typed and documented.** A runtime derives each tool's name, description and JSON parameter
  schema from the signature and the docstring, so both are part of the contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hex_service_kit.serialization import to_jsonable
from pii_kit import redact

from ..config import Container, Settings, build_container
from ..domain.alert_intake_service import AlertIntakeService
from ..domain.models import AlertInput
from ..domain.pii import PII_PATTERNS
from ..pipeline import assess_instrument
from ..surveillance_pack import thresholds_for

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

#: The identity a tool call is attributed to when the runtime propagates none. It names the
#: SERVICE, not a person, so an unattributed action is never mistaken for a human's.
DEFAULT_ACTOR = "trade-comms-surveillance-agent"


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def _redacted(node: Any) -> Any:
    """Mask personal data in every string of a tool result, however deeply it is nested.

    A tool result is not an API response. The API returns to the authenticated caller the text
    that caller just submitted; a TOOL result goes into a model's context, and P-04 says
    minimise the data that reaches a model. The evidence snippet a caller may legitimately read
    back is therefore masked here, on the way to the agent, using the same pattern pack the
    audit write masks with. Walking the whole structure rather than three named fields means a
    future field cannot arrive unredacted just because nobody remembered to add it.
    """
    if isinstance(node, str):
        return redact(node, PII_PATTERNS)
    if isinstance(node, dict):
        return {key: _redacted(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_redacted(value) for value in node]
    return node


def assess_alert(
    subject: str,
    text: str,
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Assess one manual conduct alert and route it for human review when it is consequential.

    Scores the alert text into a deterministic severity band and disposition, writes an
    already-redacted audit event, and, when the disposition escalates, submits the case to the
    human-review console (rule R8).

    Args:
      subject: The party the alert is about.
      text: The free-text alert note.
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition asserted on an outbound review.

    Returns:
      A JSON-safe case dict with every string masked for personal data (P-04: a tool result goes
      into a model's context), plus ``review_ref``: where the escalation WENT. It is empty only
      when the case did not escalate.
    """
    container = _container(settings)
    result = AlertIntakeService(container.audit, tracer=container.tracer).assess(
        AlertInput(subject=subject, text=text), actor=actor
    )
    review_ref = ""
    if result.requires_human_review:
        review_ref = container.review_router.route(result, maker=actor, tenant=tenant)
    payload = _redacted(to_jsonable(result))
    if not isinstance(payload, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("a case must serialise to a JSON object")
    payload["review_ref"] = review_ref
    return payload


def assess_window(
    instrument: str,
    subject: str = "trader-a",
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run the deterministic market-abuse engine over one instrument's order/trade window.

    Fetches the dated window, restricted-reference snapshot and recorded comms through the bound
    ports, scores every pattern with pure code (no model produces a number or a verdict), persists
    the case, and routes a consequential case to human review (rule R8).

    Args:
      instrument: A seeded instrument to assess, e.g. ``SPOOF.SG`` or ``INSIDE.SG``.
      subject: The account under review.
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition asserted on an outbound review.

    Returns:
      A JSON-safe case dict (strings masked for personal data), plus ``review_ref``.
    """
    container = _container(settings)
    thresholds = thresholds_for(container.settings)
    outcome = assess_instrument(
        container, thresholds, instrument=instrument, subject=subject, actor=actor, tenant=tenant
    )
    payload = _redacted(to_jsonable(outcome.case))
    if not isinstance(payload, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("a case must serialise to a JSON object")
    payload["review_ref"] = outcome.review_ref
    return payload


def verify_audit_trail(settings: Settings | None = None) -> dict[str, Any]:
    """Verify the audit trail's hash chain and its external head anchor.

    Returns:
      A dict with ``ok``, the record counts and a ``detail`` string. ``ok`` is false for an
      edited, deleted or reordered record, and, when an external anchor is configured, for a
      truncated tail as well. Without an anchor a truncation cannot be detected, and the detail
      says so rather than implying a stronger guarantee than the store provides.
    """
    resolved = settings or Settings.load()
    audit = _container(resolved).audit
    verify = getattr(audit, "verify", None)
    if verify is None:
        raise NotImplementedError(
            f"the {resolved.profile} audit adapter does not expose chain verification; a "
            "managed WORM sink is verified by its own retention policy, not from here"
        )
    report = verify()
    return {
        "ok": report.ok,
        "entries": report.entries,
        "chained": report.chained,
        "legacy": report.legacy,
        "first_bad_seq": report.first_bad_seq,
        "detail": report.detail,
        "anchored": bool(resolved.audit_anchor_path),
    }


#: The tool table. The agent card advertises exactly these, by function name.
TOOL_FUNCTIONS = (assess_alert, assess_window, verify_audit_trail)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each callable as a runtime FunctionTool (the only ADK-dependent code path).

    The import is deliberately here rather than at module scope: without it this module, the
    card and every tool would need an agent runtime installed to be imported at all, and the
    offline gate installs none.
    """
    # No ignore comment: the missing-import error for this module is already reported (and
    # ignored) at the TYPE_CHECKING import above, and a second one would be flagged as unused.
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=function) for function in TOOL_FUNCTIONS]
