"""Minimal stdlib CLI: assess a manual alert, run the market-abuse engine, or verify the chain."""

from __future__ import annotations

import argparse
import sys

from hex_service_kit.logging import configure_logging

from ..config import build_container
from ..domain.alert_intake_service import AlertIntakeService
from ..domain.models import AlertInput
from ..pipeline import assess_instrument
from ..surveillance_pack import thresholds_for


def _run_alert(args: argparse.Namespace) -> int:
    container = build_container()
    # Idempotent: a process that is both an API app and a CLI configures once.
    configure_logging(container.settings.profile, service="trade-comms-surveillance")
    service = AlertIntakeService(container.audit, tracer=container.tracer)
    case = service.assess(AlertInput(subject=args.subject, text=args.text), actor=args.actor)
    print(f"{case.subject}: {case.severity.value} ({case.disposition.value})")
    print(f"  requires_human_review: {case.requires_human_review}")
    if case.requires_human_review:
        # Rule R8 on the CLI path too: the same escalation, the same router.
        ref = container.review_router.route(case, maker=args.actor, tenant=args.tenant)
        print(f"  routed to human review: {ref}")
    return 0


def _run_surveil(args: argparse.Namespace) -> int:
    container = build_container()
    thresholds = thresholds_for(container.settings)
    outcome = assess_instrument(
        container,
        thresholds,
        instrument=args.instrument,
        subject=args.subject,
        actor=args.actor,
        tenant=args.tenant,
    )
    case = outcome.case
    print(f"{case.subject}/{case.instrument}: {case.severity.value} ({case.disposition.value})")
    for signal in case.fired_signals:
        print(f"  FIRED {signal.pattern.value}: score {signal.score} vs {signal.threshold}")
    for hit in case.comms_hits:
        print(f"  COMMS {hit.lexicon}@turn{hit.turn_index}: {hit.snippet!r}")
    print(f"  requires_human_review: {case.requires_human_review}")
    if outcome.review_ref:
        print(f"  routed to human review: {outcome.review_ref}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trade_comms_surveillance")
    sub = parser.add_subparsers(dest="command", required=True)

    alert = sub.add_parser("alert", help="Assess a manual conduct alert (free text).")
    alert.add_argument("subject")
    alert.add_argument("text")
    alert.add_argument("--actor", default="cli-user@bank.example")
    alert.add_argument("--tenant", default="", help="Tenant partition asserted to Hrz7.")

    surveil = sub.add_parser("surveil", help="Run the market-abuse engine over an instrument.")
    surveil.add_argument("instrument", help="A seeded instrument, e.g. SPOOF.SG / INSIDE.SG.")
    surveil.add_argument("--subject", default="trader-a", help="Account under review.")
    surveil.add_argument("--actor", default="cli-user@bank.example")
    surveil.add_argument("--tenant", default="", help="Tenant partition asserted to Hrz7.")

    args = parser.parse_args(argv)
    if args.command == "alert":
        return _run_alert(args)
    if args.command == "surveil":
        return _run_surveil(args)
    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
