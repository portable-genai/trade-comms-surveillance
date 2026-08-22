"""Deterministic comms scan: transcript in, lexicon hits out, no model in the path.

Runs the in-repo surveillance lexicons through the speech-lexicon-kit matching kernel over a
:class:`~speech_lexicon_kit.transcript.Transcript` and returns :class:`CommsHit` findings. The
kit owns the matching; the words live in ``lexicon.py``. A model may later add advisory colour to
a case narrative, but it takes no part in producing a hit: the scorecard here is identical with
any model adapter stubbed out, which is the property the eval asserts.

Redaction happens in the DRIVING layer before any model sees the transcript (P-04). This scan is
pure and deterministic, so it runs on the already-redacted or the raw transcript identically; the
hit's snippet is the matched cue phrase, not surrounding personal text.
"""

from __future__ import annotations

from speech_lexicon_kit import Transcript, find_hits

from .lexicon import LEXICON_SEVERITY, SURVEILLANCE_LEXICONS
from .models import CommsHit


def scan_transcript(transcript: Transcript) -> tuple[CommsHit, ...]:
    """Return every lexicon hit in ``transcript`` as a deterministic, sorted tuple of hits."""
    hits: list[CommsHit] = []
    for family, lexicon in SURVEILLANCE_LEXICONS.items():
        severity = LEXICON_SEVERITY[family]
        for hit in find_hits(transcript, lexicon):
            hits.append(
                CommsHit(
                    lexicon=family,
                    entry_id=hit.entry_id,
                    account=hit.speaker_id,
                    turn_index=hit.turn_index,
                    snippet=hit.matched_text,
                    severity=severity,
                )
            )
    return tuple(sorted(hits, key=lambda h: (h.turn_index, h.lexicon, h.entry_id)))


__all__ = ["scan_transcript"]
