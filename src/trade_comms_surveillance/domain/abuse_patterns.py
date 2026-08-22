"""The deterministic market-abuse pattern engine: pure stdlib, one detector per pattern.

Every number and every disposition tier in this module is computed by pure code and is
replayable from an explicit ``as_of``. A model narrates the output elsewhere; it never produces
a score or a verdict here. Thresholds are NOT engine constants: they arrive as a
:class:`PatternThresholds` value loaded from an adopter-owned pack (see
``surveillance_pack.py``), because which order-to-trade ratio is suspicious and how large an
abnormal return matters are policy the client owns, not algorithm.

Baseline deviation uses the robust median / MAD z-score (the same shape Mkt4's anomaly service
uses): the median and the median absolute deviation resist the outliers that a mean would chase,
so a single spoofer cannot raise the bar that hides them.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from .kernel import Citation, Severity
from .models import (
    AbuseSignal,
    ClientOrder,
    MarketWindow,
    Order,
    PatternType,
    RestrictedReference,
    Side,
    Trade,
)

#: Scale factor that makes the MAD a consistent estimator of the standard deviation for normal
#: data (1 / 0.6745). Named, not inlined, so the intent is legible.
_MAD_TO_SIGMA = 1.4826


def robust_z(value: float, sample: Sequence[float]) -> float:
    """Robust z-score of ``value`` against ``sample`` via median and MAD.

    Returns 0.0 for a degenerate sample (fewer than two points, or zero dispersion) rather than
    dividing by zero: with no spread there is no anomaly to speak of, and a detector must fail
    closed to "nothing unusual" rather than raise on thin data.
    """
    if len(sample) < 2:
        return 0.0
    med = statistics.median(sample)
    mad = statistics.median([abs(x - med) for x in sample])
    if mad == 0.0:
        return 0.0
    return (value - med) / (mad * _MAD_TO_SIGMA)


def _severity_for(score: float, threshold: float) -> Severity:
    """Band a fired score: at the bar is HIGH, well past it is CRITICAL, below it is LOW."""
    if score < threshold:
        return Severity.LOW
    if score >= threshold * 2.0:
        return Severity.CRITICAL
    return Severity.HIGH


@dataclass(frozen=True, slots=True)
class PatternThresholds:
    """Adopter-owned policy numbers for the detectors, plus the instruments each rule cites.

    A citation per pattern is mandatory: a fired signal states the named regulator instrument it
    derives from, with the ADOPTER's threshold, never a number baked into the engine.
    """

    insider_abnormal_return: float
    spoof_cancel_ratio_z: float
    spoof_resting_ms_floor: int
    wash_min_quantity: int
    frontrun_window_ms: int
    citations: dict[PatternType, Citation]

    def citation(self, pattern: PatternType) -> tuple[Citation, ...]:
        found = self.citations.get(pattern)
        return (found,) if found is not None else ()


def _abnormal_return(instrument: str, trade_ts_price: float, window: MarketWindow) -> float:
    """Signed fractional move of the reference price AFTER a trade, relative to its price.

    The later reference mark minus the trade price over the trade price. A large favourable move
    after a trade placed on inside information is the thing the insider detector scores.
    """
    later = [p.price for p in window.prices if p.instrument == instrument]
    if not later or trade_ts_price == 0.0:
        return 0.0
    return (later[-1] - trade_ts_price) / trade_ts_price


def detect_insider_dealing(
    window: MarketWindow, reference: RestrictedReference, thresholds: PatternThresholds
) -> tuple[AbuseSignal, ...]:
    """Trades placed inside a blackout/MNPI window, scored by the subsequent abnormal return."""
    signals: list[AbuseSignal] = []
    for trade in window.trades:
        for account in (trade.buyer_account, trade.seller_account):
            tainted = reference.in_blackout(trade.instrument, trade.ts) or reference.holds_mnpi(
                account, trade.instrument
            )
            if not tainted:
                continue
            move = abs(_abnormal_return(trade.instrument, trade.price, window))
            threshold = thresholds.insider_abnormal_return
            signals.append(
                AbuseSignal(
                    pattern=PatternType.INSIDER_DEALING,
                    account=account,
                    instrument=trade.instrument,
                    score=round(move, 4),
                    threshold=threshold,
                    severity=_severity_for(move, threshold),
                    as_of=window.as_of,
                    explanation=(
                        f"account {account} traded {trade.instrument} inside a restricted window;"
                        f" subsequent abnormal return {move:.2%} vs threshold {threshold:.2%}"
                    ),
                    citations=thresholds.citation(PatternType.INSIDER_DEALING),
                )
            )
    return tuple(signals)


def detect_spoofing_layering(
    window: MarketWindow, thresholds: PatternThresholds
) -> tuple[AbuseSignal, ...]:
    """Per-account cancellation-ratio anomaly at depth, gated by a resting-time floor.

    An account whose cancellation ratio is a robust-z outlier against its peers AND whose
    cancelled orders rested below the floor is layering: quotes posted to move the book with no
    intent to trade, pulled before they can fill.
    """
    by_account: dict[str, list[Order]] = {}
    for order in window.orders:
        by_account.setdefault(order.account, []).append(order)

    ratios: dict[str, float] = {}
    for account, orders in by_account.items():
        cancels = [o for o in orders if o.is_cancel]
        ratios[account] = len(cancels) / len(orders) if orders else 0.0
    sample = list(ratios.values())

    signals: list[AbuseSignal] = []
    for account, ratio in ratios.items():
        fast_cancels = [
            o
            for o in by_account[account]
            if o.is_cancel and 0 < o.resting_ms < thresholds.spoof_resting_ms_floor
        ]
        z = robust_z(ratio, sample) if fast_cancels else 0.0
        threshold = thresholds.spoof_cancel_ratio_z
        signals.append(
            AbuseSignal(
                pattern=PatternType.SPOOFING_LAYERING,
                account=account,
                instrument=window.instrument,
                score=round(z, 4),
                threshold=threshold,
                severity=_severity_for(z, threshold),
                as_of=window.as_of,
                explanation=(
                    f"account {account} cancel-ratio {ratio:.2f} is z={z:.2f} vs peers with "
                    f"{len(fast_cancels)} sub-{thresholds.spoof_resting_ms_floor}ms cancels; "
                    f"threshold z={threshold:.2f}"
                ),
                citations=thresholds.citation(PatternType.SPOOFING_LAYERING),
            )
        )
    return tuple(signals)


def _same_beneficial_owner(trade: Trade) -> bool:
    """True when both sides share a beneficial-owner group (no ownership change): a wash."""
    if trade.buyer_owner_group and trade.seller_owner_group:
        return trade.buyer_owner_group == trade.seller_owner_group
    return trade.buyer_account == trade.seller_account


def detect_wash_trading(
    window: MarketWindow, thresholds: PatternThresholds
) -> tuple[AbuseSignal, ...]:
    """Self-crossing trades that change no beneficial ownership, above a minimum size."""
    signals: list[AbuseSignal] = []
    for trade in window.trades:
        if not _same_beneficial_owner(trade):
            continue
        if trade.quantity < thresholds.wash_min_quantity:
            continue
        # A wash is a binary structural finding, so the score is the size ratio over the floor:
        # >= 1.0 fires, and larger notionals band up. The threshold is a constant 1.0 boundary.
        score = trade.quantity / thresholds.wash_min_quantity
        signals.append(
            AbuseSignal(
                pattern=PatternType.WASH_TRADING,
                account=trade.buyer_account,
                instrument=trade.instrument,
                score=round(score, 4),
                threshold=1.0,
                severity=_severity_for(score, 1.0),
                as_of=window.as_of,
                explanation=(
                    f"self-cross on {trade.instrument}: buyer {trade.buyer_account} and seller "
                    f"{trade.seller_account} share beneficial ownership; qty {trade.quantity} "
                    f">= floor {thresholds.wash_min_quantity}"
                ),
                citations=thresholds.citation(PatternType.WASH_TRADING),
            )
        )
    return tuple(signals)


def _milliseconds(a: object, b: object) -> float:
    from datetime import datetime

    assert isinstance(a, datetime) and isinstance(b, datetime)
    return abs((a - b).total_seconds()) * 1000.0


def detect_front_running(
    window: MarketWindow, thresholds: PatternThresholds
) -> tuple[AbuseSignal, ...]:
    """Proprietary orders placed just ahead of a same-side client order in the same instrument."""
    client_marks: list[ClientOrder] = list(window.client_orders)
    signals: list[AbuseSignal] = []
    for order in window.orders:
        if not order.proprietary or order.is_cancel:
            continue
        for client in client_marks:
            if client.instrument != order.instrument or client.side != order.side:
                continue
            # Ahead of: the prop order precedes the client order within the configured window.
            if not (order.ts < client.received_ts):
                continue
            gap_ms = _milliseconds(order.ts, client.received_ts)
            if gap_ms > thresholds.frontrun_window_ms:
                continue
            score = thresholds.frontrun_window_ms / gap_ms if gap_ms else float("inf")
            signals.append(
                AbuseSignal(
                    pattern=PatternType.FRONT_RUNNING,
                    account=order.account,
                    instrument=order.instrument,
                    score=round(score, 4) if gap_ms else 999.0,
                    threshold=1.0,
                    severity=_severity_for(score, 1.0),
                    as_of=window.as_of,
                    explanation=(
                        f"proprietary {order.side.value} on {order.instrument} placed "
                        f"{gap_ms:.0f}ms ahead of client order {client.order_id} "
                        f"(window {thresholds.frontrun_window_ms}ms)"
                    ),
                    citations=thresholds.citation(PatternType.FRONT_RUNNING),
                )
            )
    return tuple(signals)


def score_window(
    window: MarketWindow, reference: RestrictedReference, thresholds: PatternThresholds
) -> tuple[AbuseSignal, ...]:
    """Run every detector over one window and return every signal (fired or not), sorted.

    Returns all signals, not only fired ones, so a caller can show why a pattern did NOT fire.
    Sorting is deterministic (pattern, account, instrument) so the output is replayable.
    """
    signals: list[AbuseSignal] = []
    signals.extend(detect_insider_dealing(window, reference, thresholds))
    signals.extend(detect_spoofing_layering(window, thresholds))
    signals.extend(detect_wash_trading(window, thresholds))
    signals.extend(detect_front_running(window, thresholds))
    return tuple(
        sorted(signals, key=lambda s: (s.pattern.value, s.account, s.instrument, -s.score))
    )


__all__ = [
    "PatternThresholds",
    "detect_front_running",
    "detect_insider_dealing",
    "detect_spoofing_layering",
    "detect_wash_trading",
    "robust_z",
    "score_window",
    "Side",
]
