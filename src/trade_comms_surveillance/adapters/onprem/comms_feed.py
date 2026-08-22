"""On-prem CommsFeedPort: fail-fast portability placeholder (P-12)."""

from __future__ import annotations

from speech_lexicon_kit import Transcript

from ...config import Settings


class OnPremCommsFeedAdapter:
    """Satisfies the port but refuses: the client binds its own recorded-comms store."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def transcripts(self, case_id: str) -> tuple[Transcript, ...]:
        raise NotImplementedError(
            "on-prem comms feed is a portability placeholder: bind the client's own recorded-"
            "comms transcript store (see docs/onprem-migration.md)"
        )
