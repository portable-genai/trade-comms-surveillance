"""GCP CommsFeedPort: recorded-comms transcripts from managed storage (SDK imports stay lazy)."""

from __future__ import annotations

from speech_lexicon_kit import Transcript

from ...config import Settings


class CloudCommsFeedAdapter:
    """Read already-transcribed recorded comms from managed storage (lazy SDK import)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def transcripts(self, case_id: str) -> tuple[Transcript, ...]:  # pragma: no cover - live
        from google.cloud import storage

        _ = storage.Client()
        raise NotImplementedError(
            "wire the managed comms-transcript store for the deployment (see docs/runbook.md)"
        )
