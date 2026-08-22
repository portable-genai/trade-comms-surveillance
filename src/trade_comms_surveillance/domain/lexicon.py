"""The per-vertical surveillance lexicon: market-abuse cue phrases, as pure pack data.

The speech-lexicon-kit carries the MATCHING kernel (spans, speaker, timing) and the transcript
types; the PHRASES live here, in the consuming repo, because a surveillance cue list is reviewed
vertical policy that must not need a release of a shared package to change. This is exactly the
kit's kernel-only boundary: it matches, we own the words.

Three families of cue, each a :class:`~speech_lexicon_kit.matching.LexiconEntry`: tipping
(passing inside information), collusion (coordinating orders) and off-channel (moving the
conversation to an unrecorded medium). All phrases are obviously illustrative, not a real
firm's detection list.
"""

from __future__ import annotations

from speech_lexicon_kit import Lexicon, LexiconEntry, PhraseSpec

from .kernel import Severity

#: Cue phrases by family. The entry id is stable so a case citation of a hit is reproducible.
_TIPPING: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tip-1", ("keep this between us", "not public yet", "before the announcement")),
    ("tip-2", ("you did not hear it from me", "under the table")),
)
_COLLUSION: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("col-1", ("i will hold the bid", "you take the offer", "we move it together")),
    ("col-2", ("park it for me", "cross it back later")),
)
_OFF_CHANNEL: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("off-1", ("call my personal", "take this to signal", "off the record")),
)

#: Which family maps to which severity when it hits. Tipping and collusion are the serious cues.
LEXICON_SEVERITY: dict[str, Severity] = {
    "tipping": Severity.CRITICAL,
    "collusion": Severity.HIGH,
    "off_channel": Severity.MEDIUM,
}


def _phrases(rows: tuple[str, ...]) -> tuple[PhraseSpec, ...]:
    return tuple(PhraseSpec(phrase_id=f"p{i}", text=text) for i, text in enumerate(rows))


def _entries(rows: tuple[tuple[str, tuple[str, ...]], ...]) -> tuple[LexiconEntry, ...]:
    return tuple(
        LexiconEntry(entry_id=entry_id, phrases=_phrases(phrases)) for entry_id, phrases in rows
    )


def _lexicon(family: str, rows: tuple[tuple[str, tuple[str, ...]], ...]) -> Lexicon:
    return Lexicon(lexicon_id=family, locale="en", entries=_entries(rows))


#: The three built lexicons, keyed by family name (the key is the ``LEXICON_SEVERITY`` key).
SURVEILLANCE_LEXICONS: dict[str, Lexicon] = {
    "tipping": _lexicon("tipping", _TIPPING),
    "collusion": _lexicon("collusion", _COLLUSION),
    "off_channel": _lexicon("off_channel", _OFF_CHANNEL),
}


__all__ = ["LEXICON_SEVERITY", "SURVEILLANCE_LEXICONS"]
