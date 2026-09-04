"""Vertical artifact models: the market-abuse and trade-comms surveillance domain.

Pure stdlib, frozen dataclasses, explicit ``as_of`` on everything time-sensitive. These are the
types the deterministic engine reasons over and the types a case narrative may only RESTATE. The
service's own name is deliberately kept out of any docstring line whose length would then depend
on ``friendly_name`` and fail the repo's own format check for no reason but the name's length.

The split from ``kernel.py`` is the vertical-neutral / vertical boundary: a fork building a
different surveillance vertical rewrites this module and keeps ``kernel.py`` untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Disposition, Severity


class Side(LenientStrEnum):
    BUY = "buy"
    SELL = "sell"


class PatternType(LenientStrEnum):
    """The market-abuse patterns the deterministic engine detects (one detector each)."""

    INSIDER_DEALING = "insider_dealing"
    SPOOFING_LAYERING = "spoofing_layering"
    WASH_TRADING = "wash_trading"
    FRONT_RUNNING = "front_running"


@dataclass(frozen=True, slots=True)
class Order:
    """One order-book event. ``is_cancel`` marks a cancellation of a prior resting order."""

    order_id: str
    account: str
    instrument: str
    side: Side
    price: float
    quantity: int
    ts: datetime
    venue: str
    is_cancel: bool = False
    #: True when this order is the firm's own proprietary flow (front-running looks at prop
    #: orders placed AHEAD of a client order in the same instrument and side).
    proprietary: bool = False
    #: How long the order rested before it was cancelled or filled, in milliseconds. A spoof
    #: rests briefly then cancels; a resting-time FLOOR keeps genuine fast quoting from scoring.
    resting_ms: int = 0


@dataclass(frozen=True, slots=True)
class Trade:
    """One execution. Self-crossing (buyer group == seller group) is the wash-trade signal."""

    trade_id: str
    buyer_account: str
    seller_account: str
    instrument: str
    price: float
    quantity: int
    ts: datetime
    venue: str
    #: The beneficial-owner group of each side. A wash trade changes no beneficial ownership, so
    #: equal groups on both sides is the deterministic marker, not merely equal account ids.
    buyer_owner_group: str = ""
    seller_owner_group: str = ""


@dataclass(frozen=True, slots=True)
class ClientOrder:
    """A client order the firm holds, used by the front-running detector as the 'ahead of' mark."""

    order_id: str
    account: str
    instrument: str
    side: Side
    quantity: int
    received_ts: datetime


@dataclass(frozen=True, slots=True)
class PricePoint:
    """A reference mark for an instrument (used to score the move after a suspicious trade)."""

    instrument: str
    ts: datetime
    price: float


@dataclass(frozen=True, slots=True)
class MarketWindow:
    """A dated slice of one instrument's activity: the unit the feed port returns and the engine
    scores. Everything carries ``as_of`` so an identical window replays byte for byte."""

    instrument: str
    as_of: datetime
    orders: tuple[Order, ...] = ()
    trades: tuple[Trade, ...] = ()
    client_orders: tuple[ClientOrder, ...] = ()
    prices: tuple[PricePoint, ...] = ()


@dataclass(frozen=True, slots=True)
class BlackoutWindow:
    """A period during which trading a symbol is restricted (results blackout, MNPI window)."""

    instrument: str
    start: datetime
    end: datetime
    reason: str = ""

    def covers(self, ts: datetime) -> bool:
        return self.start <= ts <= self.end


@dataclass(frozen=True, slots=True)
class RestrictedReference:
    """The as-of snapshot of restricted-list, blackout and MNPI-holdings data the engine reads.

    This is a data boundary owned by conflicts-gifts-pad-register; trade-comms-surveillance reads
    it. Every field is dated so an ``as_of``
    replay reproduces the same verdict. ``mnpi_holders`` maps an account to the instruments it is
    recorded as holding material non-public information about.
    """

    as_of: datetime
    restricted_symbols: frozenset[str] = frozenset()
    blackouts: tuple[BlackoutWindow, ...] = ()
    mnpi_holders: tuple[tuple[str, str], ...] = ()  # (account, instrument)

    def in_blackout(self, instrument: str, ts: datetime) -> bool:
        return any(b.instrument == instrument and b.covers(ts) for b in self.blackouts)

    def holds_mnpi(self, account: str, instrument: str) -> bool:
        return (account, instrument) in self.mnpi_holders


@dataclass(frozen=True, slots=True)
class AbuseSignal:
    """One detector's finding: a deterministic score against an explicit threshold, plus cited
    reasoning. ``fired`` is score >= threshold; the engine, never a model, sets every number."""

    pattern: PatternType
    account: str
    instrument: str
    score: float
    threshold: float
    severity: Severity
    as_of: datetime
    explanation: str
    citations: tuple[Citation, ...] = ()

    @property
    def fired(self) -> bool:
        return self.score >= self.threshold


@dataclass(frozen=True, slots=True)
class CommsHit:
    """A deterministic lexicon hit in recorded comms (tipping, collusion or off-channel cue)."""

    lexicon: str
    entry_id: str
    account: str
    turn_index: int
    snippet: str
    severity: Severity


@dataclass(frozen=True, slots=True)
class ProximityEdge:
    """A scored relationship between two parties in the collusion graph (deterministic)."""

    left: str
    right: str
    score: float
    shared_counterparties: int
    comms_cooccurrences: int


@dataclass(frozen=True, slots=True)
class SurveillanceCase:
    """The assessed case: a disposition tier, cited reasoning, and the R8 review flag.

    The narrative ``summary`` may only restate the engine's own findings. ``requires_human_review``
    is True for every consequential disposition, so an escalate or a STOR recommendation is always
    routed to a human and never auto-executed.
    """

    case_id: str
    subject: str
    instrument: str
    as_of: datetime
    disposition: Disposition
    severity: Severity
    summary: str
    requires_human_review: bool
    signals: tuple[AbuseSignal, ...] = ()
    comms_hits: tuple[CommsHit, ...] = ()
    proximity: tuple[ProximityEdge, ...] = ()
    citations: tuple[Citation, ...] = ()
    tenant: str = ""

    @property
    def fired_signals(self) -> tuple[AbuseSignal, ...]:
        return tuple(s for s in self.signals if s.fired)


@dataclass(frozen=True, slots=True)
class AlertInput:
    """A compact conduct-alert intake: an analyst's free-text note about a party under review.

    The manual-alert surface (the API demo path) as opposed to the structured market-abuse engine.
    Both are deterministic and both produce a :class:`SurveillanceCase`; this one scores the note
    text into a disposition with pure keyword bands, the engine scores an order book.
    """

    subject: str
    text: str


@dataclass(frozen=True, slots=True)
class SurveillanceRequest:
    """One assessment request: the window to score, the reference snapshot and any comms hits.

    Comms hits are precomputed by the deterministic lexicon kernel in the driving layer (the
    transcript is redacted before any model sees it), so the pure engine takes findings, not raw
    text. ``subject`` is the account under review; ``case_id`` is the caller-owned idempotency key.
    """

    case_id: str
    subject: str
    window: MarketWindow
    reference: RestrictedReference
    comms_hits: tuple[CommsHit, ...] = ()
    peer_accounts: tuple[str, ...] = ()
    tenant: str = ""
    extras: dict[str, str] = field(default_factory=dict)
