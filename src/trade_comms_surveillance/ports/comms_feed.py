"""CommsFeedPort: the recorded-comms boundary for post-trade review (slice 5).

Returns already-transcribed :class:`~speech_lexicon_kit.transcript.Transcript` objects for a case.
Post-trade surveillance reviews RECORDED comms, so this is batch, not streaming (a deliberate
scope call for this repo). The transcript types and the STT/diarization ports are re-exported from
``speech-lexicon-kit`` in ``ports/comms.py``; this port delivers the transcripts an adapter has
already produced, and the driving layer redacts them (P-04) before any model sees them.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from speech_lexicon_kit import Transcript


@runtime_checkable
class CommsFeedPort(Protocol):
    def transcripts(self, case_id: str) -> tuple[Transcript, ...]:
        """Return the recorded-comms transcripts associated with ``case_id`` (batch)."""
        ...
