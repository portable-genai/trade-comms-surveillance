"""Deterministic, obviously fictional market and comms fixtures for the offline profile.

Every timestamp is fixed and every party is invented, so a window replays byte for byte across
runs (the property slice 2 asserts). Five instruments, one seeded abuse episode each plus a clean
control, so the engine's per-pattern precision and recall have an independent target and the
offline demo shows every detector firing:

* ``SPOOF.SG``  - a spoofing/layering ladder: one account posts and pulls fast quotes.
* ``WASH.SG``   - a wash cycle: a self-cross that changes no beneficial ownership.
* ``INSIDE.SG`` - insider dealing: a trade inside a results blackout, followed by a large move.
* ``FRONT.SG``  - front-running: a proprietary order placed just ahead of a client order.
* ``CLEAN.SG``  - a control with ordinary two-sided flow and nothing that should fire.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from speech_lexicon_kit import ChannelRole, SpeakerTurn, Transcript

from ...domain.models import (
    BlackoutWindow,
    ClientOrder,
    MarketWindow,
    Order,
    PricePoint,
    RestrictedReference,
    Side,
    Trade,
)

#: The single fixed clock for the offline replay. Nothing here reads the wall clock.
BASE = datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC)


def _t(seconds: int) -> datetime:
    return BASE + timedelta(seconds=seconds)


def _account_orders(
    account: str, *, total: int, cancels: int, fast: bool, base_second: int
) -> list[Order]:
    """Build ``total`` orders for one account, of which ``cancels`` are cancellations.

    ``fast`` marks the cancels as resting below the layering floor (the spoof signature); ordinary
    peers rest well above it, so their high-turnover flow is not mistaken for layering.
    """
    resting = 120 if fast else 8000
    out: list[Order] = []
    for i in range(total):
        is_cancel = i < cancels
        out.append(
            Order(
                order_id=f"{account}-{i}",
                account=account,
                instrument="SPOOF.SG",
                side=Side.BUY if i % 2 else Side.SELL,
                price=10.0 + i * 0.01,
                quantity=500,
                ts=_t(base_second + i),
                venue="SGX",
                is_cancel=is_cancel,
                resting_ms=resting if is_cancel else 0,
            )
        )
    return out


def _spoof_window() -> MarketWindow:
    """One layering account (trader-a) against peers with real, varied cancel ratios.

    trader-a cancels 9 of 10 orders, all resting below the floor (a robust-z outlier); the four
    peers cancel 2 or 3 of 10 with long resting times, so the median/MAD baseline has genuine
    dispersion and trader-a's z lands in the HIGH band rather than saturating to CRITICAL.
    """
    orders: list[Order] = []
    orders += _account_orders("trader-a", total=10, cancels=9, fast=True, base_second=0)
    orders += _account_orders("trader-p", total=10, cancels=2, fast=False, base_second=30)
    orders += _account_orders("trader-q", total=10, cancels=3, fast=False, base_second=60)
    orders += _account_orders("trader-r", total=10, cancels=2, fast=False, base_second=90)
    orders += _account_orders("trader-s", total=10, cancels=3, fast=False, base_second=120)
    return MarketWindow(instrument="SPOOF.SG", as_of=BASE, orders=tuple(orders))


def _wash_window() -> MarketWindow:
    """A self-cross between two accounts in the same beneficial-owner group, on ``WASH.SG``."""
    trades = (
        Trade(
            "w1",
            "trader-b1",
            "trader-b2",
            "WASH.SG",
            25.0,
            5000,
            _t(5),
            "SGX",
            buyer_owner_group="omega-group",
            seller_owner_group="omega-group",
        ),
        Trade(
            "w2",
            "trader-x",
            "trader-y",
            "WASH.SG",
            25.1,
            300,
            _t(6),
            "SGX",
            buyer_owner_group="x-grp",
            seller_owner_group="y-grp",
        ),
    )
    return MarketWindow(instrument="WASH.SG", as_of=BASE, trades=trades)


def _inside_window() -> MarketWindow:
    """A trade inside a blackout window, followed by a large favourable move, on ``INSIDE.SG``."""
    trades = (Trade("i1", "trader-c", "market", "INSIDE.SG", 50.0, 2000, _t(10), "SGX"),)
    prices = (
        PricePoint("INSIDE.SG", _t(10), 50.0),
        PricePoint("INSIDE.SG", _t(3600), 58.0),  # +16% after the trade
    )
    return MarketWindow(instrument="INSIDE.SG", as_of=BASE, trades=trades, prices=prices)


def _front_window() -> MarketWindow:
    """A proprietary order placed just ahead of a same-side client order, on ``FRONT.SG``."""
    orders = (
        Order(
            "f-prop", "trader-d", "FRONT.SG", Side.BUY, 12.0, 1000, _t(1), "SGX", proprietary=True
        ),
    )
    client_orders = (ClientOrder("f-client", "client-1", "FRONT.SG", Side.BUY, 5000, _t(2)),)
    return MarketWindow(
        instrument="FRONT.SG", as_of=BASE, orders=orders, client_orders=client_orders
    )


def _clean_window() -> MarketWindow:
    """Ordinary flow with nothing that should fire, on ``CLEAN.SG`` (the control)."""
    orders = (
        Order("c1", "trader-e", "CLEAN.SG", Side.BUY, 8.0, 300, _t(1), "SGX"),
        Order("c2", "trader-f", "CLEAN.SG", Side.SELL, 8.0, 300, _t(2), "SGX"),
    )
    trades = (
        Trade(
            "c-t1",
            "trader-e",
            "trader-f",
            "CLEAN.SG",
            8.0,
            300,
            _t(3),
            "SGX",
            buyer_owner_group="e-grp",
            seller_owner_group="f-grp",
        ),
    )
    return MarketWindow(instrument="CLEAN.SG", as_of=BASE, orders=orders, trades=trades)


#: Every seeded window, keyed by instrument. The market-data adapter serves from this map.
WINDOWS: dict[str, MarketWindow] = {
    "SPOOF.SG": _spoof_window(),
    "WASH.SG": _wash_window(),
    "INSIDE.SG": _inside_window(),
    "FRONT.SG": _front_window(),
    "CLEAN.SG": _clean_window(),
}

#: The reference snapshot: INSIDE.SG is in a results blackout across the trade, and trader-c is
#: recorded as an MNPI holder. Dated so an ``as_of`` replay is exact.
REFERENCE = RestrictedReference(
    as_of=BASE,
    restricted_symbols=frozenset({"INSIDE.SG"}),
    blackouts=(
        BlackoutWindow(
            instrument="INSIDE.SG",
            start=BASE - timedelta(days=1),
            end=BASE + timedelta(days=1),
            reason="results blackout (FICTIONAL)",
        ),
    ),
    mnpi_holders=(("trader-c", "INSIDE.SG"),),
)


def _transcript(case_id: str, speaker: str, text: str) -> Transcript:
    turns = (
        SpeakerTurn(index=0, speaker_id=speaker, role=ChannelRole.PARTICIPANT, text="morning all"),
        SpeakerTurn(index=1, speaker_id=speaker, role=ChannelRole.PARTICIPANT, text=text),
    )
    return Transcript(transcript_id=f"{case_id}-{speaker}", locale="en", turns=turns)


#: Recorded-comms transcripts by case id. The tipping and collusion cues corroborate the trading
#: signals, so a STOR recommendation has both legs. Obviously fictional dialogue.
TRANSCRIPTS: dict[str, tuple[Transcript, ...]] = {
    "INSIDE.SG": (
        _transcript("INSIDE.SG", "trader-c", "keep this between us before the announcement ok"),
    ),
    "SPOOF.SG": (_transcript("SPOOF.SG", "trader-a", "i will hold the bid you take the offer"),),
    "WASH.SG": (_transcript("WASH.SG", "trader-b1", "park it for me and cross it back later"),),
}
