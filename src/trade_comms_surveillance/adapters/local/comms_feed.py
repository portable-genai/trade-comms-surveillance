"""Local CommsFeedPort: seeded recorded-comms transcripts (SDK-free, deterministic).

Serves the fictional transcripts in ``_fixtures.py``. A case with no recorded comms returns an
empty tuple, which is a legitimate answer (not every case has voice), so the scan simply finds no
lexicon hits.
"""

from __future__ import annotations

from speech_lexicon_kit import Transcript

from ...config import Settings
from ._fixtures import TRANSCRIPTS


class LocalCommsFeedAdapter:
    """Replay the seeded fictional comms transcripts for the ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def transcripts(self, case_id: str) -> tuple[Transcript, ...]:
        return TRANSCRIPTS.get(case_id, ())
