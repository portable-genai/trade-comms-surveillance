"""Re-export of the shared speech ports and transcript types (slice 5).

trade-comms-surveillance does NOT redeclare the speech boundary: the transcription and diarization
ports, the transcript and speaker-turn types, and the redaction spans all come from the pinned
``speech-lexicon-kit`` so a citation of "turn 7, characters 12 to 34" means the same thing here as
in every other repo that reads recorded comms. They are re-exported through this one module so a
consumer has a single import site for the comms boundary, exactly as ``ports/__init__.py`` gives the
rest of the hexagon one.

Post-trade surveillance reviews RECORDED comms, so this repo uses these ports in BATCH: an adapter
resolves an ``AudioRef`` to a ``Transcript`` offline, and ``ports/comms_feed.py`` delivers the
already-transcribed result. Streaming STT is deliberately out of scope here (it belongs to the
real-time verticals E1/E3), which is why these are re-exported rather than bound as container
ports: nothing in trade-comms-surveillance's request path calls a live recogniser.
"""

from __future__ import annotations

from speech_lexicon_kit import (
    AudioRef,
    ChannelRole,
    DiarizationPort,
    DiarizationRequest,
    DiarizationResult,
    RedactionSpan,
    SpeakerTurn,
    SpeechToTextPort,
    Transcript,
    TranscriptionRequest,
    TranscriptionResult,
)

__all__ = [
    "AudioRef",
    "ChannelRole",
    "DiarizationPort",
    "DiarizationRequest",
    "DiarizationResult",
    "RedactionSpan",
    "SpeakerTurn",
    "SpeechToTextPort",
    "Transcript",
    "TranscriptionRequest",
    "TranscriptionResult",
]
