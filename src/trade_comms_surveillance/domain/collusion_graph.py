"""Deterministic collusion-proximity scoring over trades and comms participants.

Links accounts, counterparties and comms participants, and scores relationship proximity with
pure arithmetic: shared trading counterparties plus comms co-occurrences, both counted, never
inferred. Embeddings could add advisory colour elsewhere; nothing here consults a model, so the
proximity number is replayable and defensible in a case file.
"""

from __future__ import annotations

from .models import CommsHit, MarketWindow, ProximityEdge

#: Weights for the two deterministic proximity signals. Kept explicit so the score is auditable.
_COUNTERPARTY_WEIGHT = 1.0
_COMMS_WEIGHT = 2.0


def _counterparties(window: MarketWindow) -> dict[str, set[str]]:
    """Map each account to the set of accounts it traded against in the window."""
    edges: dict[str, set[str]] = {}
    for trade in window.trades:
        if trade.buyer_account == trade.seller_account:
            continue
        edges.setdefault(trade.buyer_account, set()).add(trade.seller_account)
        edges.setdefault(trade.seller_account, set()).add(trade.buyer_account)
    return edges


def _comms_participants(comms_hits: tuple[CommsHit, ...]) -> set[str]:
    return {hit.account for hit in comms_hits}


def score_proximity(
    window: MarketWindow, comms_hits: tuple[CommsHit, ...] = ()
) -> tuple[ProximityEdge, ...]:
    """Score every unordered account pair by shared counterparties and comms co-occurrence.

    Two accounts are proximate when they trade against the same counterparties (a shared-network
    signal) and when both appear in the same flagged comms (a coordination signal). The score is
    a weighted sum of the two counts; only positive-scoring pairs are returned, sorted high first.
    """
    counterparties = _counterparties(window)
    accounts = sorted(counterparties)
    comms_accounts = _comms_participants(comms_hits)

    edges: list[ProximityEdge] = []
    for i, left in enumerate(accounts):
        for right in accounts[i + 1 :]:
            shared = len(counterparties[left] & counterparties[right])
            cooccur = 1 if (left in comms_accounts and right in comms_accounts) else 0
            score = _COUNTERPARTY_WEIGHT * shared + _COMMS_WEIGHT * cooccur
            if score <= 0.0:
                continue
            edges.append(
                ProximityEdge(
                    left=left,
                    right=right,
                    score=round(score, 4),
                    shared_counterparties=shared,
                    comms_cooccurrences=cooccur,
                )
            )
    return tuple(sorted(edges, key=lambda e: (-e.score, e.left, e.right)))


__all__ = ["score_proximity"]
